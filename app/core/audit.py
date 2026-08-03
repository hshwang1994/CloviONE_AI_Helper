"""Audit recording with sensitive-value masking (spec §25.7).

Passwords, tokens, secrets are masked recursively before persistence.
Password hashes are excluded entirely by the snapshot helpers that call this.
"""

from __future__ import annotations

import json
import re
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.audit.models import AuditLog

_SENSITIVE_KEY = re.compile(r"password|secret|token|credential|api[_-]?key", re.IGNORECASE)
MASK = "***"


def mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: MASK if _SENSITIVE_KEY.search(str(key)) else mask_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [mask_sensitive(item) for item in value]
    return value


def record_audit(
    db: Session,
    *,
    actor_id: str | None,
    action: str,
    object_type: str,
    object_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    result: str = "success",
    client_ip: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=actor_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before_json=(
            json.dumps(mask_sensitive(before), ensure_ascii=False, default=str)
            if before is not None
            else None
        ),
        after_json=(
            json.dumps(mask_sensitive(after), ensure_ascii=False, default=str)
            if after is not None
            else None
        ),
        result=result,
        client_ip=client_ip,
        request_id=request_id,
    )
    db.add(entry)
    db.flush()
    return entry


def record_audit_from_request(
    request: Request,
    db: Session,
    *,
    action: str,
    object_type: str,
    object_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    result: str = "success",
) -> AuditLog:
    from app.core.deps import client_ip_from_request

    # 임퍼소네이션 중이면 `request.state.user` 는 **대상**이다(화면이 그 사람 눈으로 보이므로).
    # 감사의 행위자는 언제나 실제로 요청을 낸 사람이어야 하므로 `request.state.actor` 를 먼저
    # 본다 — 이게 없으면 관리자가 남의 이름으로 로그를 남길 수 있고, 그것이 임퍼소네이션이
    # 위험한 이유의 전부다(0033, PLAN Phase 6). 평소에는 둘이 같은 값이다.
    actor = getattr(request.state, "actor", None) or getattr(request.state, "user", None)
    return record_audit(
        db,
        actor_id=actor.id if actor is not None else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before=before,
        after=after,
        result=result,
        client_ip=client_ip_from_request(request),
        request_id=getattr(request.state, "request_id", None),
    )
