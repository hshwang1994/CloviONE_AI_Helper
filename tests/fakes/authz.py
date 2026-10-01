"""권한 시험의 대역 — 기본 역할에서 권한 하나를 뺀다.

기본 역할 다섯은 마이그레이션이 심은 행(`roles` · `role_permissions`)이다. 시험이 「이 권한이 없는 사람」을 만들려면 그 행을
지운다 - 코드의 표(`app/authz/permissions.py`)를 고치면 판정이 실제로 읽는 DB 와 어긋난다.
"""

from __future__ import annotations

from sqlalchemy import delete, select


def revoke(db, role_key: str, permission_key: str) -> None:
    """기본 역할 ``role_key`` 에서 ``permission_key`` 를 뺀다. 같은 트랜잭션 안의 앱이 바로 본다."""
    from app.authz.models import Role, RolePermission

    role_id = db.execute(select(Role.id).where(Role.key == role_key, Role.builtin.is_(True))).scalar_one()
    db.execute(delete(RolePermission).where(
        RolePermission.role_id == role_id, RolePermission.permission_key == permission_key,
    ))
    db.commit()
