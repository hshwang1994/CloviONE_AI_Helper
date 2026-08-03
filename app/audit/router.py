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
from app.core.authz import SENSITIVE_READ_ROLES
from app.core.deps import get_db, require_roles
from app.core.errors import ValidationAppError
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
    object_type: str | None = None,
    object_id: str | None = None,
    user_id: str | None = None,
    result: str | None = None,
    since: str | None = None,
    until: str | None = None,
):
    """목록과 내보내기가 **같은 질의**를 쓰게 하는 한 곳(0033).

    화면에서 좁혀 놓고 내보내기를 눌렀는데 조건이 하나라도 다르면, 받은 CSV 는 화면에서
    본 것과 다른 데이터다 — 그리고 그 차이는 파일을 열어 보기 전까지 아무도 모른다.
    """
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
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
    if since:
        stmt = stmt.where(AuditLog.created_at >= _parse_boundary(since, "since", upper=False))
    if until:
        stmt = stmt.where(AuditLog.created_at < _parse_boundary(until, "until", upper=True))
    return stmt


@router.get("")
def list_audit_logs(
    db: Session = Depends(get_db),
    page: PageParams = Depends(),
    action: str | None = Query(default=None, max_length=64),
    object_type: str | None = Query(default=None, max_length=64),
    object_id: str | None = Query(default=None, max_length=64),
    user_id: str | None = Query(default=None, max_length=36),
    result: str | None = Query(default=None, max_length=16),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
):
    stmt = _filtered_stmt(
        action=action, object_type=object_type, object_id=object_id,
        user_id=user_id, result=result, since=since, until=until,
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
    actor_ids = {row.user_id for row in rows if row.user_id}
    actor_names: dict[str, dict[str, str]] = {}
    if actor_ids:
        for u in db.execute(
            select(User.id, User.display_name, User.email).where(User.id.in_(actor_ids))
        ).all():
            actor_names[u.id] = {"display_name": u.display_name, "email": u.email}
    return {
        "items": [
            {
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
            for row in rows
        ],
        "total": total,
        "page": page.page,
        "page_size": page.page_size,
    }


# ── 이상 탐지 · 내보내기 · 저장 필터 (0033, PLAN Phase 6) ─────────────────────


@router.get("/anomalies")
def audit_anomalies(
    request: Request,
    db: Session = Depends(get_db),
    window_hours: int = Query(default=anomalies.DEFAULT_WINDOW_HOURS, ge=1, le=anomalies.MAX_WINDOW_HOURS),
):
    """규칙 기반 소견. 각 소견에 근거와 임계값이 함께 나간다(anomalies.py 모듈 docstring)."""
    result = anomalies.detect(db, now=request.app.state.clock.now(), window_hours=window_hours)
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
# 사람이 실제로 검토할 수 있는 양은 그보다 훨씬 적다. 잘렸다는 사실은 헤더로 알린다 —
# 조용히 자르면 "그 시간대엔 아무 일도 없었다"로 잘못 읽힌다.
EXPORT_MAX_ROWS = 50_000


@router.get("/export.csv")
def export_audit_logs(
    db: Session = Depends(get_db),
    action: str | None = Query(default=None, max_length=64),
    object_type: str | None = Query(default=None, max_length=64),
    object_id: str | None = Query(default=None, max_length=64),
    user_id: str | None = Query(default=None, max_length=36),
    result: str | None = Query(default=None, max_length=16),
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
        action=action, object_type=object_type, object_id=object_id,
        user_id=user_id, result=result, since=since, until=until,
    )
    rows = (
        db.execute(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(EXPORT_MAX_ROWS)
        )
        .scalars()
        .all()
    )
    actor_ids = {row.user_id for row in rows if row.user_id}
    actor_names: dict[str, dict[str, str]] = {}
    if actor_ids:
        for u in db.execute(
            select(User.id, User.display_name, User.email).where(User.id.in_(actor_ids))
        ).all():
            actor_names[u.id] = {"display_name": u.display_name, "email": u.email}

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
    body = "﻿" + buffer.getvalue()
    headers = {
        "Content-Disposition": 'attachment; filename="audit-log.csv"',
        "X-Export-Rows": str(len(rows)),
        "X-Export-Truncated": "1" if len(rows) >= EXPORT_MAX_ROWS else "0",
        "Cache-Control": "no-store",
    }
    return Response(content=body, media_type="text/csv; charset=utf-8", headers=headers)


# ── 저장 필터는 여기 있지 않다 (0033 설계 결정) ───────────────────────────────
#
# 감사 화면의 '저장된 뷰'는 0032 의 `saved_views`(app/profiles) 가 담당한다 — 화면별·
# 사용자별로 **쿼리 문자열 하나**를 저장하고, `DataScreen` 이 모든 화면에 같은 컨트롤을
# 그리므로 감사 로그도 이미 포함된다. 여기에 감사 전용 저장 필터를 또 만들면 같은 일을
# 하는 저장소가 둘이 되고, 어느 쪽이 정본인지 화면마다 달라진다.
# (`app/core/feature_flags.py` 가 고친 split-brain 과 같은 종류의 실수다.)
