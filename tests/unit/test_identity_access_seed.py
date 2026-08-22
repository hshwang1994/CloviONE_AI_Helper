"""마이그레이션이 심은 권한 표가 **코드의 표와 같은가** (S5 · D-219 와 같은 관용).

마이그레이션은 앱 코드를 import 하지 않는다 — 그 시점 스키마의 얼어붙은 스냅숏이어야
하기 때문이다(`alembic/versions/0002_identity_access.py` 머리말). 그래서 값이 두 곳에
적히고, **두 곳에 적힌 값이 어긋나면 조용히 깨진다**:

  * 코드에서 권한을 하나 늘리고 마이그레이션을 안 고치면 → 새 설치에서만 그 권한이 없다.
    증상은 「어떤 서버에서만 버튼이 안 눌린다」이고 원인을 찾는 데 하루가 걸린다.
  * 역할의 권한 조합을 코드에서 바꾸고 마이그레이션을 안 고치면 → **이미 설치된 곳은
    옛 조합 그대로다.** 권한 규칙에서 그것은 곧 구멍이다.

그래서 여기서 둘을 맞물려 둔다. 시험이 유일한 방어선이다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.authz.models import Permission, Role, RolePermission
from app.authz.permissions import (
    ALL_PERMISSION_KEYS,
    BUILTIN_ROLE_PERMISSIONS,
    PERMISSION_BY_KEY,
)
from app.core.authz import ROLE_LABELS, ROLE_ORDER

pytestmark = pytest.mark.unit


def test_every_code_permission_exists_in_the_database(db):
    rows = {r.key for r in db.execute(select(Permission)).scalars()}
    missing = ALL_PERMISSION_KEYS - rows
    extra = rows - ALL_PERMISSION_KEYS
    assert not missing, (
        f"코드에는 있는데 마이그레이션이 안 심은 권한: {sorted(missing)} — "
        "새 설치에서만 그 권한이 없는 상태가 된다"
    )
    assert not extra, (
        f"DB 에는 있는데 코드에 없는 권한: {sorted(extra)} — "
        "아무도 부르지 않는 권한은 있으나 마나가 아니라 잘못된 기대를 만든다"
    )


def test_permission_labels_match_the_code(db):
    for row in db.execute(select(Permission)).scalars():
        spec = PERMISSION_BY_KEY[row.key]
        assert row.label == spec.label, f"{row.key} 의 라벨이 코드와 다르다"
        assert row.area == spec.area, f"{row.key} 의 구역이 코드와 다르다"


def test_the_five_builtin_roles_are_seeded_and_locked(db):
    rows = {r.key: r for r in db.execute(select(Role).where(Role.builtin.is_(True))).scalars()}
    assert set(rows) == set(ROLE_ORDER), (
        f"기본 제공 역할이 다섯이 아니다: {sorted(rows)}"
    )
    for key, row in rows.items():
        assert row.name == ROLE_LABELS[key], f"{key} 의 이름이 화면 라벨과 다르다"
        assert row.builtin is True


def test_role_permission_links_match_the_code_table(db):
    by_role: dict[str, set[str]] = {}
    stmt = select(Role.key, RolePermission.permission_key).join(
        RolePermission, RolePermission.role_id == Role.id
    ).where(Role.builtin.is_(True))
    for role_key, perm_key in db.execute(stmt).all():
        by_role.setdefault(role_key, set()).add(perm_key)

    for role in ROLE_ORDER:
        expected = set(BUILTIN_ROLE_PERMISSIONS[role])
        got = by_role.get(role, set())
        assert got == expected, (
            f"역할 {role!r} 의 권한 조합이 코드와 다르다.\n"
            f"  DB 에만: {sorted(got - expected)}\n"
            f"  코드에만: {sorted(expected - got)}"
        )


def test_the_comparison_above_is_not_vacuous():
    """비교가 **비어 있지 않다**는 증명 — 다섯 역할이 서로 다른 조합을 갖는다.

    전부 같은 집합이면 위 시험은 통과하면서 아무것도 증명하지 않는다.
    """
    sets = [frozenset(BUILTIN_ROLE_PERMISSIONS[r]) for r in ROLE_ORDER]
    assert len(set(sets)) == len(ROLE_ORDER), "다섯 역할의 권한 조합이 서로 구별되지 않는다"
    assert all(s for s in sets), "권한이 하나도 없는 역할이 있다 — 시드가 비었을 수 있다"
