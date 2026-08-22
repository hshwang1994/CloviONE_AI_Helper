"""다섯 역할의 뜻이 **바뀌지 않았다** — 권한 모델 도입 전후 동등성 (S5 Exit).

## 무엇을 증명해야 하는가

S5 는 「누가 무엇을 할 수 있는가」를 파이썬 상수에서 DB 표로 옮겼다. 그 이관이 옳다는 것은
**옛 게이트와 새 게이트가 다섯 역할 전부에 대해 같은 답을 낸다**는 뜻이고, 그 말은 전수로만
증명된다 — 한두 개를 표본으로 확인하면 나머지가 조용히 달라져도 아무도 모른다.

두 층에서 본다:

  1. **표 층** — `require_permission(P)` 가 통과시키는 역할 집합이
     `require_roles(*GROUP)` 의 집합과 같은가 (권한마다).
  2. **실제 요청 층** — 옮긴 라우트를 다섯 역할이 실제로 호출했을 때 허용/거부가
     옛 규칙과 같은가. 표만 맞고 배선이 틀린 경우를 여기서 잡는다.

## 왜 「음성」이 반이어야 하는가

허용만 확인하면 **전부 허용하는 게이트**도 통과한다. 그래서 각 케이스마다 「이 역할은
막힌다」를 함께 단언한다.
"""

from __future__ import annotations

import pytest

from app.authz.permissions import (
    AUDIT_READ,
    BACKUP_EXECUTE,
    BACKUP_READ,
    IMPERSONATE,
    ORG_MANAGE,
    SYSTEM_CONFIGURE,
    USER_MANAGE,
    BUILTIN_ROLE_PERMISSIONS,
)
from app.authz.service import effective_permissions
from app.core.authz import (
    CONSOLE_READ_ROLES,
    CONSOLE_WRITE_ROLES,
    ROLE_ORDER,
    SENSITIVE_READ_ROLES,
    SYSTEM_ADMIN_ONLY,
)

pytestmark = pytest.mark.security

# 「옛 게이트 → 새 게이트」로 실제로 옮긴 자리들. 각 줄이 **한 곳도 빠짐없이** 같은 집합인지
# 본다. 여기 없는 라우트는 아직 `require_roles` 를 쓰고 있고 그건 그대로 옳다 —
# 이 시험은 «옮긴 것이 같은가» 를 묻지 «전부 옮겼는가» 를 묻지 않는다.
MIGRATED = (
    (USER_MANAGE, CONSOLE_WRITE_ROLES, "사용자 관리 · 오프보딩"),
    (ORG_MANAGE, CONSOLE_WRITE_ROLES, "부서·직책 편집"),
    (AUDIT_READ, SENSITIVE_READ_ROLES, "감사 로그 · 대리 보기 기록"),
    (IMPERSONATE, CONSOLE_WRITE_ROLES, "대리 보기 시작"),
    (BACKUP_READ, CONSOLE_READ_ROLES, "백업 목록"),
    (BACKUP_EXECUTE, SYSTEM_ADMIN_ONLY, "백업 생성·검증"),
    (SYSTEM_CONFIGURE, SYSTEM_ADMIN_ONLY, "시스템 설정"),
)


@pytest.mark.parametrize("permission,group,what", MIGRATED, ids=[m[0] for m in MIGRATED])
def test_the_permission_holds_exactly_the_old_role_group(permission, group, what):
    holders = {role for role in ROLE_ORDER if permission in BUILTIN_ROLE_PERMISSIONS[role]}
    assert holders == set(group), (
        f"{what}: 권한 {permission} 을 가진 역할이 옛 그룹과 다르다.\n"
        f"  새 규칙에만: {sorted(holders - set(group))}\n"
        f"  옛 규칙에만: {sorted(set(group) - holders)}\n"
        "다섯 역할의 뜻은 이 이관으로 바뀌면 안 된다."
    )


@pytest.mark.parametrize("permission,group,what", MIGRATED, ids=[m[0] for m in MIGRATED])
def test_someone_is_denied(permission, group, what):
    """전부 허용하는 게이트가 위 시험을 통과하지 못하게 한다."""
    denied = set(ROLE_ORDER) - set(group)
    assert denied, f"{what}: 아무도 거부되지 않는다 — 이 권한은 게이트가 아니다"


@pytest.mark.parametrize("role", ROLE_ORDER)
def test_the_database_gives_each_role_exactly_the_code_permissions(db, make_user, role):
    """DB 를 거친 계산이 코드의 표와 같은가. 시드·질의·캐시를 통째로 지난다."""
    user = make_user(f"perm-{role}@goodmit.co.kr", role=role)
    got = effective_permissions(db, user)
    assert got == BUILTIN_ROLE_PERMISSIONS[role], (
        f"역할 {role!r} 의 유효 권한이 코드와 다르다.\n"
        f"  DB 에만: {sorted(got - BUILTIN_ROLE_PERMISSIONS[role])}\n"
        f"  코드에만: {sorted(BUILTIN_ROLE_PERMISSIONS[role] - got)}"
    )


# ── 실제 요청 층 ─────────────────────────────────────────────────────────────
#
# 표가 맞아도 배선이 틀리면 소용없다. 옮긴 라우트를 다섯 역할이 실제로 부른다.

ROUTES = (
    ("GET", "/api/admin/audit", SENSITIVE_READ_ROLES, "감사 로그"),
    ("GET", "/api/admin/backups", CONSOLE_READ_ROLES, "백업 목록"),
    ("GET", "/api/admin/impersonation/sessions", SENSITIVE_READ_ROLES, "대리 보기 기록"),
    ("GET", "/api/admin/departments", CONSOLE_WRITE_ROLES, "부서 목록"),
)


@pytest.mark.parametrize("method,path,group,what", ROUTES, ids=[r[1] for r in ROUTES])
@pytest.mark.parametrize("role", ROLE_ORDER)
def test_routes_allow_and_deny_the_same_roles_as_before(
    client, login_as, method, path, group, what, role
):
    csrf = login_as(role, email=f"route-{role}@goodmit.co.kr")
    response = client.request(method, path, headers={"X-CSRF-Token": csrf})
    allowed = role in group
    if allowed:
        assert response.status_code != 403, (
            f"{what}: {role} 이 막혔다 — 옛 규칙에서는 통과했다 ({response.status_code})"
        )
    else:
        assert response.status_code == 403, (
            f"{what}: {role} 이 통과했다 — 옛 규칙에서는 403 이다 ({response.status_code})"
        )
