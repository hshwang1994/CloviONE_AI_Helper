"""Audit log read API (spec §10.4, §23.7). auditor has read access here."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
