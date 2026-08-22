"""유효 권한 계산과 부여 — **합집합이고, 모르면 닫는다** (D-193).

    유효 권한 = 주 역할(users.role) ∪ 추가 역할(user_roles)

빼는 항이 없다. 「이 사람에게서만 이것을 뺀다」를 만들지 않는 이유는 D-193 에 적혀 있다 —
다계층 Deny 는 「이 사람이 이걸 왜 못 보는가」를 사람이 추적할 수 없게 만들고, 추적할 수
없는 권한 모델은 AI Retrieval 에서 검증할 수 없다.

## 기본 제공 역할을 어떻게 찾는가

`users.role` 은 역할의 **키**다. 그 키로 `roles` 에서 `builtin = true` 인 행을 찾는다.
조직으로 좁히지 않는 이유: 기본 제공 다섯은 **설치 전체의 어휘**이고 조직마다 다른 뜻을
가지면 안 된다. 조직별로 다른 것은 사용자가 만든 역할이고, 그쪽은 `user_roles` 가 행으로
직접 가리키므로 애초에 찾을 필요가 없다.

## 심어져 있지 않으면 아무 권한도 없다

`role_permissions` 가 비어 있으면 이 함수는 빈 집합을 돌려주고 모든 게이트가 닫힌다.
그 상태를 «관대하게» 처리하지 않는다 — 권한 표가 없을 때 통과시키는 코드는 그 표를
지우는 것만으로 전 권한을 여는 문이 된다. 표는 마이그레이션 `0002_identity_access` 가
심고, `tests/unit/test_identity_access_seed.py` 가 코드와 같은지 확인한다.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.authz.models import (
    ALL_GRANTEE_KINDS,
    GRANTEE_ORG_UNIT,
    GRANTEE_ROLE,
    GRANTEE_USER,
    ResourceGrant,
    Role,
    RolePermission,
    UserRole,
)
from app.authz.permissions import ALL_PERMISSION_KEYS

__all__ = [
    "effective_permissions",
    "invalidate_permission_cache",
    "has_permission",
    "builtin_role",
    "assign_role",
    "unassign_role",
    "grant_resource_access",
    "revoke_resource_access",
    "resource_grantee_ids",
    "principal_grantee_pairs",
]


# ── 유효 권한 ────────────────────────────────────────────────────────────────

def effective_permissions(db: Session, user) -> frozenset[str]:
    """이 사람이 가진 권한 전부. 계산 결과는 **요청 안에서 한 번만** 만든다.

    캐시를 사용자 객체에 붙이는 이유: 한 요청이 게이트를 두 번 이상 지나는 경로가 흔하다
    (라우터 데코레이터 + 핸들러 안의 세부 판정). 사용자 객체는 요청 하나의 수명과 같은
    Session 에 붙어 있으므로 요청이 끝나면 함께 사라진다.
    """
    cached = getattr(user, "_authz_permissions", None)
    if cached is not None:
        return cached
    keys = _query_permissions(db, user)
    try:
        object.__setattr__(user, "_authz_permissions", keys)
    except AttributeError:  # pragma: no cover - 슬롯이 있는 대역 객체
        pass
    return keys


def invalidate_permission_cache(user) -> None:
    """부여가 바뀌었으니 다음 물음은 다시 계산하라."""
    for attr in ("_authz_permissions", "_authz_grantees"):
        try:
            object.__delattr__(user, attr)
        except (AttributeError, TypeError):
            pass


def _query_permissions(db: Session, user) -> frozenset[str]:
    user_id = getattr(user, "id", None)
    primary = getattr(user, "role", None)

    role_ids: set[str] = set()
    if primary:
        row = db.execute(
            select(Role.id).where(Role.key == primary, Role.builtin.is_(True))
        ).scalars().first()
        if row:
            role_ids.add(row)
    if user_id:
        extra = db.execute(
            select(UserRole.role_id).where(UserRole.user_id == user_id)
        ).scalars().all()
        role_ids.update(extra)

    if not role_ids:
        return frozenset()

    keys = db.execute(
        select(RolePermission.permission_key).where(
            RolePermission.role_id.in_(tuple(sorted(role_ids)))
        )
    ).scalars().all()
    return frozenset(keys)


def has_permission(db: Session, user, permission: str) -> bool:
    """이 사람이 이 권한을 가졌는가.

    **모르는 권한 키는 거짓이다.** 오타 난 키가 참을 내면 그 게이트는 열린 채로 통과하고,
    아무 시험도 빨개지지 않는다 — 그래서 어휘에 없는 키는 여기서 먼저 닫는다.
    """
    if permission not in ALL_PERMISSION_KEYS:
        return False
    return permission in effective_permissions(db, user)


def builtin_role(db: Session, key: str) -> Role | None:
    return db.execute(
        select(Role).where(Role.key == key, Role.builtin.is_(True))
    ).scalars().first()


# ── 역할 부여 ────────────────────────────────────────────────────────────────

def assign_role(db: Session, *, user, role_id: str, granted_by: str | None = None) -> UserRole:
    """추가 역할 하나를 준다. 이미 있으면 그 행을 그대로 돌려준다(멱등).

    사용자 **객체**를 받는 이유는 캐시 때문이다 — 같은 요청 안에서 역할을 주고 곧바로
    권한을 묻는 경로(관리 화면의 저장 후 재조회)가 실제로 있고, id 만 받으면 그 요청은
    바뀌기 전 값을 본다.
    """
    existing = db.execute(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role_id)
    ).scalars().first()
    if existing is not None:
        return existing
    row = UserRole(user_id=user.id, role_id=role_id, granted_by=granted_by)
    db.add(row)
    db.flush()
    invalidate_permission_cache(user)
    return row


def unassign_role(db: Session, *, user, role_id: str) -> int:
    """추가 역할을 거둔다. 지운 행 수를 돌려준다.

    **주 역할(`users.role`)은 이것으로 거둘 수 없다.** 그건 계정 편집이고
    `app/users/service.py` 가 담당한다 — 두 곳이 같은 값을 고치면 어느 쪽이 이겼는지
    감사 로그로 재구성할 수 없다.
    """
    result = db.execute(
        delete(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role_id)
    )
    db.flush()
    invalidate_permission_cache(user)
    return int(result.rowcount or 0)


# ── 자원 직접 부여 ───────────────────────────────────────────────────────────

def grant_resource_access(
    db: Session,
    *,
    resource_type: str,
    resource_id: str,
    grantee_kind: str,
    grantee_id: str,
    granted_by: str | None = None,
) -> ResourceGrant:
    """자원 하나를 특정 대상에게 **명시로** 연다. 멱등이다."""
    if grantee_kind not in ALL_GRANTEE_KINDS:
        raise ValueError(f"알 수 없는 부여 대상 종류: {grantee_kind!r}")
    existing = db.execute(
        select(ResourceGrant).where(
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource_id,
            ResourceGrant.grantee_kind == grantee_kind,
            ResourceGrant.grantee_id == grantee_id,
        )
    ).scalars().first()
    if existing is not None:
        return existing
    row = ResourceGrant(
        resource_type=resource_type,
        resource_id=resource_id,
        grantee_kind=grantee_kind,
        grantee_id=grantee_id,
        granted_by=granted_by,
    )
    db.add(row)
    db.flush()
    return row


def revoke_resource_access(
    db: Session,
    *,
    resource_type: str,
    resource_id: str,
    grantee_kind: str,
    grantee_id: str,
) -> int:
    result = db.execute(
        delete(ResourceGrant).where(
            ResourceGrant.resource_type == resource_type,
            ResourceGrant.resource_id == resource_id,
            ResourceGrant.grantee_kind == grantee_kind,
            ResourceGrant.grantee_id == grantee_id,
        )
    )
    db.flush()
    return int(result.rowcount or 0)


def resource_grantee_ids(
    db: Session, *, resource_type: str, resource_id: str, grantee_kind: str = GRANTEE_USER
) -> list[str]:
    """이 자원을 명시로 받은 대상 id 들. 화면이 「누구에게 열려 있는가」를 보여 준다."""
    return list(
        db.execute(
            select(ResourceGrant.grantee_id)
            .where(
                ResourceGrant.resource_type == resource_type,
                ResourceGrant.resource_id == resource_id,
                ResourceGrant.grantee_kind == grantee_kind,
            )
            .order_by(ResourceGrant.granted_at, ResourceGrant.id)
        ).scalars().all()
    )


def principal_grantee_pairs(db: Session, principal) -> tuple[tuple[str, str], ...]:
    """이 주체가 **명시 부여를 받을 수 있는 자격들** — `(kind, id)` 쌍.

    사람 자신 · 그 사람이 가진 역할 · 그 사람이 속한 조직 단위 셋이다. 질의는 자원마다가
    아니라 요청당 한 번이고, 그 결과가 `visibility.py` 의 부여 갈래에 그대로 들어간다.
    """
    cached = getattr(principal, "_authz_grantees", None)
    if cached is not None:
        return cached

    pairs: list[tuple[str, str]] = [(GRANTEE_USER, principal.user_id)]

    role_ids = db.execute(
        select(UserRole.role_id).where(UserRole.user_id == principal.user_id)
    ).scalars().all()
    primary = db.execute(
        select(Role.id).where(Role.key == principal.role, Role.builtin.is_(True))
    ).scalars().first()
    for role_id in ({*role_ids, primary} - {None}):
        pairs.append((GRANTEE_ROLE, role_id))

    if principal.department_id:
        pairs.append((GRANTEE_ORG_UNIT, principal.department_id))

    out = tuple(sorted(set(pairs)))
    try:
        object.__setattr__(principal, "_authz_grantees", out)
    except AttributeError:  # pragma: no cover
        pass
    return out
