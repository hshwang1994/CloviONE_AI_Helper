"""권한 어휘가 **한 곳에서만** 정해지는가 (S5).

`app/authz/permissions.py` 의 표는 「권한 → 역할」 사상이고, 「역할 → 사람」은
`app/core/authz.py` 의 그룹 상수 한 곳에서만 정해진다. 그 표에 역할 이름을 손으로 나열하는
순간 규칙이 두 벌이 되고, 그러면 그룹을 고쳐도 그 권한만 조용히 옛 규칙으로 남는다 —
`app/core/authz.py` 가 애초에 생긴 이유와 정확히 같은 결함이다.
"""

from __future__ import annotations

import pytest

from app.authz.permissions import (
    ALL_PERMISSION_KEYS,
    BUILTIN_ROLE_PERMISSIONS,
    EVERYONE,
    PERMISSIONS,
)
from app.core.authz import (
    CONSOLE_OPS_ROLES,
    CONSOLE_READ_ROLES,
    CONSOLE_WRITE_ROLES,
    MODERATOR_ROLES,
    SENSITIVE_READ_ROLES,
    SYSTEM_ADMIN_ONLY,
    rbac_matrix,
)
from app.users.models import ALL_ROLES

pytestmark = pytest.mark.security

KNOWN_GROUPS = {
    "EVERYONE": set(EVERYONE),
    "CONSOLE_READ_ROLES": set(CONSOLE_READ_ROLES),
    "CONSOLE_WRITE_ROLES": set(CONSOLE_WRITE_ROLES),
    "CONSOLE_OPS_ROLES": set(CONSOLE_OPS_ROLES),
    "SENSITIVE_READ_ROLES": set(SENSITIVE_READ_ROLES),
    "SYSTEM_ADMIN_ONLY": set(SYSTEM_ADMIN_ONLY),
    "MODERATOR_ROLES": set(MODERATOR_ROLES),
}


@pytest.mark.parametrize("spec", PERMISSIONS, ids=[p.key for p in PERMISSIONS])
def test_every_permission_uses_a_known_role_group(spec):
    roles = set(spec.roles)
    assert any(roles == group for group in KNOWN_GROUPS.values()), (
        f"{spec.key} 의 역할 집합 {sorted(roles)} 가 알려진 그룹 중 어느 것과도 같지 않다.\n"
        f"쓸 수 있는 그룹: {', '.join(sorted(KNOWN_GROUPS))}\n"
        "역할 이름을 손으로 나열하면 그 자리만 규칙이 갈라진다."
    )


def test_permission_keys_are_unique():
    keys = [spec.key for spec in PERMISSIONS]
    assert len(keys) == len(set(keys)), "권한 키가 중복된다 — 뒤에 온 것이 앞을 조용히 덮는다"


def test_every_permission_key_is_upper_snake_case():
    """어휘가 눈으로 구별돼야 코드에서 권한과 역할을 혼동하지 않는다."""
    bad = [k for k in ALL_PERMISSION_KEYS if not k.isupper() or " " in k]
    assert not bad, f"권한 키 규칙(대문자 스네이크)에 어긋난다: {sorted(bad)}"


def test_every_role_has_at_least_one_permission():
    """권한이 하나도 없는 역할은 로그인해도 아무것도 못 한다 — 시드가 빈 것과 구별되지 않는다."""
    empty = [role for role in ALL_ROLES if not BUILTIN_ROLE_PERMISSIONS.get(role)]
    assert not empty, f"권한이 하나도 없는 역할: {sorted(empty)}"


def test_the_auditor_never_gets_a_write_permission():
    """auditor 는 읽기 전용 가지다(§10). 권한 층에서도 그 성질이 유지돼야 한다."""
    writes = {
        spec.key for spec in PERMISSIONS
        if "auditor" in spec.roles
        and any(spec.key.endswith(verb) for verb in ("_DELETE", "_ADMIN", "_CONFIGURE", "_MANAGE"))
    }
    assert not writes, f"감사자에게 쓰기 성격의 권한이 붙었다: {sorted(writes)}"


def test_the_console_matrix_carries_the_permission_catalog():
    """화면이 권한 목록을 스스로 만들지 않게 한다 — 프런트에 한 벌 더 두면 갈라진다."""
    matrix = rbac_matrix()
    assert "permissions" in matrix, "RBAC 매트릭스가 권한 목록을 싣지 않는다"
    keys = {row["key"] for row in matrix["permissions"]}
    assert keys == ALL_PERMISSION_KEYS
    for row in matrix["permissions"]:
        assert row["allowed"], f"{row['key']} 의 보유 역할이 비었다"
