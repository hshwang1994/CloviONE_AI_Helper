"""Audit log read API (spec §10.4, §23.7). auditor has read access here."""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import anomalies
from app.audit.models import AuditLog
from app.audit.repository import apply_scope
from app.core.authz import SENSITIVE_READ_ROLES
from app.core.deps import get_db, get_principal, require_roles
from app.core.scope import Principal, visible_user_ids
from app.core.errors import NotFoundError, ValidationAppError
from app.core.pagination import PageParams
from app.users.models import User

router = APIRouter(
    prefix="/api/admin/audit",
    tags=["admin-audit"],
    dependencies=[Depends(require_roles(*SENSITIVE_READ_ROLES))],
)

# 표시·경계 판정은 Asia/Seoul 기준(§불변 9). created_at은 UTC naive로 저장돼 있다.
_KST = ZoneInfo("Asia/Seoul")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_boundary(value: str, field: str, *, upper: bool) -> datetime:
    """필터 경계값을 UTC naive datetime으로 정규화한다.

    - 'YYYY-MM-DD'(날짜만): 화면이 KST로 시각을 보여주므로 그 날짜도 KST 달력일로
      해석한다. since는 KST 그날 00:00, until은 KST 다음날 00:00(선택한 날 포함)로 잡아
      UTC로 변환한다. 이렇게 안 하면 UTC 자정 경계가 KST 09:00에 걸려 그날 앞 9시간이
      조용히 빠지고, '종료일=오늘'이 그날 전체를 제외해 버린다.
    - 오프셋이 붙은 전체 ISO datetime: UTC로 변환. naive datetime: 기존처럼 UTC로 간주.
    """
    if _DATE_ONLY.match(value):
        try:
            day = datetime.fromisoformat(value)
        except ValueError:
            raise ValidationAppError(
                f"{field} 형식이 올바르지 않습니다 (ISO 8601)."
            ) from None
        local = day.replace(tzinfo=_KST)
        if upper:
            local = local + timedelta(days=1)  # 선택한 날을 포함(상한은 exclusive '<')
        return local.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationAppError(f"{field} 형식이 올바르지 않습니다 (ISO 8601).") from None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _filtered_stmt(
    *,
    action: str | None = None,
    exclude_actions: str | None = None,
    object_type: str | None = None,
    object_id: str | None = None,
    user_id: str | None = None,
    result: str | None = None,
    request_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    actor_ids=None,
):
    """목록과 내보내기가 **같은 질의**를 쓰게 하는 한 곳(0033).

    화면에서 좁혀 놓고 내보내기를 눌렀는데 조건이 하나라도 다르면, 받은 CSV 는 화면에서
    본 것과 다른 데이터다 — 그리고 그 차이는 파일을 열어 보기 전까지 아무도 모른다.
    """
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    # VIS-59: 로그인/로그아웃처럼 일상적으로 반복되는 사건이 화면을 지배해 실제로 봐야
    # 할 사건(실패·설정 변경 등)이 그 사이에 묻힌다. action(정확 일치, 하나만 골라 좁히는
    # 용도)과는 반대 방향 — 이건 "이것만 빼고 전부"다. 쉼표로 여러 개 받는다(지금은 화면이
    # 로그인·로그아웃 두 개만 묶어 보내지만, 나중에 다른 잡음 action이 추가돼도 화면
    # 쪽만 바꾸면 된다).
    if exclude_actions:
        excluded = [a.strip() for a in exclude_actions.split(",") if a.strip()]
        if excluded:
            stmt = stmt.where(AuditLog.action.not_in(excluded))
    if object_type:
        stmt = stmt.where(AuditLog.object_type == object_type)
    if object_id:
        stmt = stmt.where(AuditLog.object_id == object_id)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    # 실패만 격리하는 것(로그인 실패·비밀번호 변경 실패 등)은 보안 감사에서 가장 중요한
    # 질의다 — result로 서버측 필터한다(round30 감사 E). 화면은 success/failure 열을
    # 이미 보여주면서도 그 값으로 좁힐 방법이 없었다.
    if result:
        stmt = stmt.where(AuditLog.result == result)
    # 상관 id 로 찾기 (Z8). 이 값은 상세 패널에 **보이기만 했고 그것으로 찾을 수가 없었다** —
    # 사용자가 오류 화면의 문의 번호를 불러 줘도 운영자는 그 요청을 짚어낼 방법이 없었다.
    # 배관(발급·전파·응답 헤더·저장)은 다 깔려 있었는데 조회 입구만 없었다.
    if request_id:
        stmt = stmt.where(AuditLog.request_id == request_id)
    # 범위 밖 사람의 행적은 보이지 않는다 (2순위 #3). 감사 로그는 **누가 무엇을 했나** 라서
    # 행위자가 곧 축이다 — 부서/조직 관리자가 남의 부서 사람의 활동을 훑을 수 있으면
    # 목록 화면에서 가려 둔 것이 여기서 통째로 샌다(CSV 내보내기까지 딸려 온다).
    #
    # 조건 자체는 `repository.scope_clause` 한 곳에만 적혀 있다 — 이상 징후 화면이 같은
    # 판정을 **세 번째로 손으로 적다가** 아예 빼먹은 자리라서(그 화면엔 principal 조차
    # 없었다) 적을 자리를 하나로 줄였다. 시스템 행위(user_id=None)를 남기는 이유도 거기 있다.
    stmt = apply_scope(stmt, actor_ids)
    if since:
        stmt = stmt.where(AuditLog.created_at >= _parse_boundary(since, "since", upper=False))
    if until:
        stmt = stmt.where(AuditLog.created_at < _parse_boundary(until, "until", upper=True))
    return stmt


def _actor_names(db: Session, rows: list[AuditLog]) -> dict[str, dict[str, str]]:
    """행위자 id들을 표시 이름/이메일로 일괄 해석한다 — 목록과 단건 상세가 같은 로직을 쓴다."""
    actor_ids = {row.user_id for row in rows if row.user_id}
    names: dict[str, dict[str, str]] = {}
    if actor_ids:
        for u in db.execute(
            select(User.id, User.display_name, User.email).where(User.id.in_(actor_ids))
        ).all():
            names[u.id] = {"display_name": u.display_name, "email": u.email}
    return names


def _serialize_row(row: AuditLog, actor_names: dict[str, dict[str, str]]) -> dict:
    """목록·단건 상세가 같은 모양을 돌려준다 — 상세 딥링크로 연 항목과 목록에서 행을
    눌러 연 항목이 같은 필드를 가져야 화면 쪽이 두 경로를 구분해서 다룰 필요가 없다."""
    return {
        "id": row.id,
        "user_id": row.user_id,
        "actor_name": (
            actor_names.get(row.user_id, {}).get("display_name")
            if row.user_id
            else None
        ),
        "actor_email": (
            actor_names.get(row.user_id, {}).get("email")
            if row.user_id
            else None
        ),
        "action": row.action,
        "object_type": row.object_type,
        "object_id": row.object_id,
        "before": json.loads(row.before_json) if row.before_json else None,
        "after": json.loads(row.after_json) if row.after_json else None,
        "result": row.result,
        "client_ip": row.client_ip,
        "request_id": row.request_id,
        "created_at": row.created_at.isoformat(),
    }


@router.get("")
def list_audit_logs(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    action: str | None = Query(default=None, max_length=64),
    exclude_actions: str | None = Query(default=None, max_length=256),
    object_type: str | None = Query(default=None, max_length=64),
    object_id: str | None = Query(default=None, max_length=64),
    user_id: str | None = Query(default=None, max_length=36),
    result: str | None = Query(default=None, max_length=16),
    request_id: str | None = Query(default=None, max_length=64),
    principal: Principal = Depends(get_principal),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
):
    stmt = _filtered_stmt(
        action=action, exclude_actions=exclude_actions, object_type=object_type, object_id=object_id,
        user_id=user_id, result=result, request_id=request_id, since=since, until=until,
        actor_ids=visible_user_ids(db, principal.scope),
    )

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(page.offset)
            .limit(page.page_size)
        )
        .scalars()
        .all()
    )
    # 행위자 id를 표시 이름/이메일로 일괄 해석한다 — '누가 바꿨나'가 이 화면의 목적인데
    # UUID만 보이면 아무 의미가 없다(대시보드 '최근 주요 변경'과 같은 방식). 시스템/CLI
    # 행위(user_id=None)는 actor_name=None으로 두고 프런트가 '시스템'으로 표시한다.
    actor_names = _actor_names(db, rows)
    return {
        "items": [_serialize_row(row, actor_names) for row in rows],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


# ── 이상 탐지 · 내보내기 · 저장 필터 (0033, PLAN Phase 6) ─────────────────────


@router.get("/anomalies")
def audit_anomalies(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
    window_hours: int = Query(default=anomalies.DEFAULT_WINDOW_HOURS, ge=1, le=anomalies.MAX_WINDOW_HOURS),
):
    """규칙 기반 소견. 각 소견에 근거와 임계값이 함께 나간다(anomalies.py 모듈 docstring).

    목록·CSV 와 **같은 판정**(`repository.scope_clause`)을 건다. 소견은 행위자별 요약이라
    가장 새기 쉬운 모양이다 — 한 줄에 그 사람이 무엇을 몇 건 했는지가 근거(action 목록)까지
    붙어 나오고, 아래에서 표시 이름과 **이메일**까지 얹는다. 범위를 안 걸면 목록 화면에서
    가려 둔 사람의 활동 요약과 연락처가 이 화면 하나로 통째로 새어 나간다.
    """
    result = anomalies.detect(
        db,
        now=request.app.state.clock.now(),
        window_hours=window_hours,
        actor_ids=visible_user_ids(db, principal.scope),
    )
    actor_ids = {f["actor_id"] for f in result["findings"] if f["actor_id"]}
    names: dict[str, dict[str, str]] = {}
    if actor_ids:
        for u in db.execute(
            select(User.id, User.display_name, User.email).where(User.id.in_(actor_ids))
        ).all():
            names[u.id] = {"display_name": u.display_name, "email": u.email}
    for finding in result["findings"]:
        info = names.get(finding["actor_id"] or "", {})
        finding["actor_name"] = info.get("display_name")
        finding["actor_email"] = info.get("email")
    # 화면이 목록 컴포넌트를 그대로 쓸 수 있게 items 이름도 함께 준다.
    result["items"] = result["findings"]
    return result


# 내보내기 상한. 감사 로그는 수십만 행이 될 수 있고, 브라우저가 한 번에 받을 수 있는 양과
# 사람이 실제로 검토할 수 있는 양은 그보다 훨씬 적다.
EXPORT_MAX_ROWS = 50_000


def _truncation_notice(limit: int) -> list[str]:
    """잘린 파일의 **마지막 줄**. 파일 자체가 자기가 일부라고 말해야 한다.

    ## 왜 헤더로는 부족한가

    예전에는 `X-Export-Truncated` 헤더로만 알렸다. 브라우저는 그 헤더를 사용자에게 보여
    주지 않는다 — 다운로드 폴더에 떨어진 파일에는 아무 표시도 없다. 감사 담당자는 그
    파일을 엑셀로 열어 **그게 전부인 줄 알고** 감사 보고서에 붙인다. 그러면 "그 기간엔
    그것뿐이었다" 라는 결론이 조용히 틀린다. 감사에서 그건 가장 나쁜 종류의 오류다.

    ## 왜 맨 아래인가

    맨 위에 끼우면 머리글이 2행으로 밀려 엑셀의 열이 통째로 어긋나고, CSV 를 읽는 도구는
    전부 깨진다. 아래에 붙이면 파싱은 그대로이고 사람은 끝까지 스크롤했을 때 본다.
    파일 이름에도 함께 적어 두는 이유가 그것이다 — 열기 전에도 보이게.
    """
    return [
        f"※ 이 파일은 내보내기 상한 {limit:,}행에서 잘렸습니다. "
        "조회 결과의 일부만 들어 있으니 감사 보고에 전체로 쓰지 마세요. "
        "기간을 좁혀 여러 번 내보내면 전부 받을 수 있습니다."
    ]


@router.get("/export.csv")
def export_audit_logs(
    db: Session = Depends(get_db),
    action: str | None = Query(default=None, max_length=64),
    # 목록과 **같은 필터 집합**이어야 한다 — 하나라도 빠지면 아래 docstring 이 못박은
    # 계약("화면에서 좁혀 놓고 내보내면 그건 다른 데이터다")이 그 필터에서만 깨진다.
    exclude_actions: str | None = Query(default=None, max_length=256),
    object_type: str | None = Query(default=None, max_length=64),
    object_id: str | None = Query(default=None, max_length=64),
    user_id: str | None = Query(default=None, max_length=36),
    result: str | None = Query(default=None, max_length=16),
    request_id: str | None = Query(default=None, max_length=64),
    principal: Principal = Depends(get_principal),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
):
    """목록과 **같은 필터**로 CSV 를 내보낸다.

    화면에서 좁혀 놓고 내보내기를 눌렀는데 전체가 나오면 그건 다른 데이터다 —
    그래서 필터 파라미터를 그대로 받아 같은 질의를 쓴다.

    엑셀이 UTF-8 CSV 를 그냥 열면 한글이 깨진다(cp949 로 읽는다). BOM 을 붙이면
    엑셀이 UTF-8 로 인식한다 — 감사 담당자가 실제로 여는 도구가 엑셀이다.
    """
    stmt = _filtered_stmt(
        action=action, exclude_actions=exclude_actions, object_type=object_type, object_id=object_id,
        user_id=user_id, result=result, request_id=request_id, since=since, until=until,
        actor_ids=visible_user_ids(db, principal.scope),
    )
    limit = EXPORT_MAX_ROWS
    # 상한보다 **한 줄 더** 읽는다. `len(rows) >= limit` 로 판정하면 정확히 상한인 파일이
    # 거짓으로 "잘렸다"가 된다 — 한 번 거짓말하는 경고는 그다음 진짜 경고도 같이 죽인다.
    rows = (
        db.execute(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit + 1)
        )
        .scalars()
        .all()
    )
    truncated = len(rows) > limit
    rows = rows[:limit]
    actor_names = _actor_names(db, rows)

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([
        "시각(KST)", "행위자", "이메일", "동작", "대상 유형", "대상 ID",
        "결과", "클라이언트 IP", "요청 ID", "변경 전", "변경 후",
    ])
    for row in rows:
        info = actor_names.get(row.user_id or "", {})
        local = row.created_at.replace(tzinfo=timezone.utc).astimezone(_KST)
        writer.writerow([
            local.strftime("%Y-%m-%d %H:%M:%S"),
            info.get("display_name") or ("시스템" if not row.user_id else row.user_id),
            info.get("email") or "",
            row.action, row.object_type, row.object_id or "",
            row.result, row.client_ip or "", row.request_id or "",
            row.before_json or "", row.after_json or "",
        ])
    if truncated:
        writer.writerow(_truncation_notice(limit))
    body = "﻿" + buffer.getvalue()
    # 파일 이름도 함께 말한다 — 다운로드 폴더에서 이름만 보이는 상황이 흔하고, 그때
    # `audit-log.csv` 는 "감사 로그 전부"로 읽힌다.
    filename = f"audit-log-partial-{limit}rows.csv" if truncated else "audit-log.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Export-Rows": str(len(rows)),
        "X-Export-Truncated": "1" if truncated else "0",
        "Cache-Control": "no-store",
    }
    return Response(content=body, media_type="text/csv; charset=utf-8", headers=headers)


# PA-RC-0024: 관리자 콘솔은 상세를 URL 없는 모달로만 열어 딥링크·새로고침·뒤로가기가 안
# 됐다. 사용자 콘솔의 :id 라우트들은 서버 단건 조회가 있어서 가능했는데, 감사 로그는
# 목록뿐이라(행 클릭이 이미 받은 목록 행 객체를 그대로 쓴다) 그 라우트 자체를 못 만들었다
# — 이 엔드포인트가 그 전제를 채운다. `/{log_id}` 는 반드시 위의 `/anomalies`·`/export.csv`
# **뒤에** 와야 한다 — FastAPI 는 등록 순서로 매칭하므로, 앞에 두면 그 두 경로를
# log_id="anomalies"/"export.csv" 로 삼켜버린다.
@router.get("/{log_id}")
def get_audit_log_detail(
    log_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
):
    """목록과 같은 범위 판정(apply_scope)을 그대로 건다 — 범위 밖 id도 존재하지 않는 id와
    똑같이 404로 접어, 있는지 없는지 자체를 노출하지 않는다(users.get_scoped_user_or_404·
    org.get_or_404와 같은 원칙)."""
    stmt = apply_scope(
        select(AuditLog).where(AuditLog.id == log_id),
        visible_user_ids(db, principal.scope),
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise NotFoundError("감사 로그를 찾을 수 없습니다.")
    return _serialize_row(row, _actor_names(db, [row]))


# ── 저장 필터는 여기 있지 않다 (0033 설계 결정) ───────────────────────────────
#
# 감사 화면의 '저장된 뷰'는 0032 의 `saved_views`(app/profiles) 가 담당한다 — 화면별·
# 사용자별로 **쿼리 문자열 하나**를 저장하고, `DataScreen` 이 모든 화면에 같은 컨트롤을
# 그리므로 감사 로그도 이미 포함된다. 여기에 감사 전용 저장 필터를 또 만들면 같은 일을
# 하는 저장소가 둘이 되고, 어느 쪽이 정본인지 화면마다 달라진다.
# (`app/core/feature_flags.py` 가 고친 split-brain 과 같은 종류의 실수다.)
