"""Audit recording with sensitive-value masking (spec §25.7).

Passwords, tokens, secrets are masked recursively before persistence.
Password hashes are excluded entirely by the snapshot helpers that call this.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.audit.models import AuditLog

_SENSITIVE_KEY = re.compile(r"password|secret|token|credential|api[_-]?key", re.IGNORECASE)
MASK = "***"

# CORE-12: `secret_ref`/`secret_reference` 필드는 실제 secret 값이 아니라
# SECRETS_DIR 안 파일을 가리키는 이름일 뿐이다(§2-3 불변 규칙; app/core/versioning.py
# 의 config_versions 스냅샷도 같은 이유로 이 필드를 마스킹 없이 그대로 저장한다 —
# 복구하려면 어느 이름을 참조했는지 알아야 한다). 그런데 이 정규식은 "secret"이
# 들어간 키를 이름 fields까지 뭉뚱그려 "***"로 지워버려서, 같은 변경이
# config_versions 이력에는 실제 이름으로 보이는데 감사 로그에는 "*** → ***"로
# 변경이 있었는지조차 알 수 없게 나온다. 정확히 이 필드명만 예외로 둔다 — 다른
# "…secret…" 키(예: client_secret, secret_value)는 여전히 마스킹된다.
_SECRET_REFERENCE_FIELDS = frozenset({"secret_ref", "secret_reference"})


def mask_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                item
                if str(key).lower() in _SECRET_REFERENCE_FIELDS
                else MASK
                if _SENSITIVE_KEY.search(str(key))
                else mask_sensitive(item)
            )
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


@contextmanager
def audit_failure_on_exception(
    request: Request,
    db: Session,
    *,
    action: str,
    object_type: str,
    object_id: str | None = None,
    after: dict | None = None,
):
    """OPS-04: 성공했을 때만 감사를 남기는 라우터가 실패를 완전히 놓치던 문제의 공통 수정.

    `record_audit_from_request`를 시도 코드 **뒤**에만 부르면(이 저장소의 세 업로드
    라우터 — tickets/board/profiles — 가 전부 이 모양이었다) 그 사이에서 던진 예외가
    감사 기록 자체를 건너뛰고 그대로 빠져나간다. 이 컨텍스트 매니저로 감싼 코드가
    예외를 던지면 `result="failure"` 감사 행을 남기고 **원래 예외를 그대로 다시 던진다**
    (응답 코드·메시지는 안 바뀐다).

    `db.commit()`을 명시적으로 부르는 이유: `get_db`(app/core/deps.py)의 자동 commit은
    핸들러가 예외 없이 끝났을 때만 실행된다 — 예외가 나면 `db.rollback()` 경로를 타므로,
    여기서 방금 쓴 실패 감사 행까지 함께 롤백된다. `app/auth/router.py`의 로그인 실패
    경로가 이미 같은 이유로 명시적 `db.commit()`을 쓰고 있다(그 자리의 주석 참고).
    """
    try:
        yield
    except Exception:
        record_audit_from_request(
            request, db, action=action, object_type=object_type,
            object_id=object_id, after=after, result="failure",
        )
        db.commit()
        raise
