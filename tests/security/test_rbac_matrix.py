"""RBAC 매트릭스는 **`app/core/authz.py` 하나에서 나온다** (Phase 6).

이 파일이 지키는 것은 화면의 모양이 아니라 **출처의 유일성**이다. 매트릭스가 자기 역할 표를
따로 들면, 권한 규칙을 authz.py 에서 고쳐도 화면은 옛 표를 계속 보여 준다 — 그리고 그 어긋남은
아무 테스트도 빨갛게 만들지 않는다(authz.py 가 애초에 생긴 이유와 정확히 같은 결함).

그래서 여기서는 세 가지를 본다:
  1. 매트릭스의 모든 행이 authz.py 의 **알려진 그룹과 같은 집합**인가(손으로 나열한 행이 없나).
  2. 응답의 역할 목록이 `ALL_ROLES` 와 정확히 같은가(빠진 역할이 있으면 열 하나가 통째로 없다).
  3. 프런트가 역할 목록을 다시 적지 않았나 — 매트릭스 화면 설정에 역할 문자열이 없어야 한다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.core.authz import (
    CAPABILITIES,
    CONSOLE_OPS_ROLES,
    CONSOLE_READ_ROLES,
    CONSOLE_WRITE_ROLES,
    MODERATOR_ROLES,
    ROLE_LABELS,
    ROLE_ORDER,
    SENSITIVE_READ_ROLES,
    SYSTEM_ADMIN_ONLY,
    rbac_matrix,
)
from app.users.models import ALL_ADMIN_SCOPES, ALL_ROLES
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# authz.py 가 정의한 그룹 전부. 매트릭스의 어떤 행도 이 중 하나와 **같은 집합**이어야 한다.
KNOWN_GROUPS = (
    CONSOLE_READ_ROLES, CONSOLE_WRITE_ROLES, CONSOLE_OPS_ROLES,
    SENSITIVE_READ_ROLES, SYSTEM_ADMIN_ONLY, MODERATOR_ROLES,
)


def test_every_capability_reuses_a_known_group():
    """행 하나가 손으로 나열되면 그 행만 조용히 옛 규칙으로 남는다."""
    for cap in CAPABILITIES:
        assert any(set(cap.roles) == set(group) for group in KNOWN_GROUPS), (
            f"{cap.key} 의 역할 집합이 authz.py 의 어떤 그룹과도 같지 않다: {cap.roles}"
        )


def test_the_role_axis_is_complete():
    assert set(ROLE_ORDER) == ALL_ROLES
    assert set(ROLE_LABELS) == ALL_ROLES, "라벨 없는 역할은 화면에 raw 값으로 노출된다"


def test_scope_axis_is_complete():
    """역할만 보여 주면 '부서 관리자가 왜 남의 부서를 못 보는지'가 화면 어디에도 없다."""
    matrix = rbac_matrix()
    assert {s["value"] for s in matrix["scopes"]} == ALL_ADMIN_SCOPES


def test_matrix_rows_only_reference_known_roles():
    for row in rbac_matrix()["items"]:
        assert set(row["allowed"]) <= ALL_ROLES, row


def test_auditor_never_appears_in_a_write_capability():
    """auditor 는 읽기 전용 가지다(§10) — 매트릭스가 그 전제를 어기면 화면이 거짓말을 한다."""
    write_keys = {"console.write", "users.manage", "users.bulk",
                  "offboarding.run", "org.manage", "system.admin", "content.moderate"}
    for row in rbac_matrix()["items"]:
        if row["id"] in write_keys:
            assert "auditor" not in row["allowed"], row


_ROLE_STRING = re.compile(r'["\'](?:user|operator|auditor|admin|system_admin)["\']')
# `//` 줄 주석은 코드가 아니다 — 규칙을 설명하는 문장이 규칙 위반으로 잡히면 사람은 설명을
# 지우는 쪽을 택하게 되고, 그게 이 저장소가 가장 아끼는 자산(왜 그렇게 했는지)을 깎는다.
_LINE_COMMENT = re.compile(r"//[^\n]*")


def _rbac_source_files() -> list[Path]:
    """rbac 화면 설정이 있을 수 있는 파일들.

    E-10/PF7 로 `registry.js` 가 조립 파일이 되고 화면 설정은 `registry/*.js` 로 쪼개졌다
    (rbac 는 지금 `registry/governance.js`). 파일 이름을 못박으면 다음 재편에서 또 깨지므로,
    조립 파일 자신과 그 아래 도메인 파일 전부를 훑어 `rbac:` 키를 실제로 든 파일을 찾는다.
    """
    screens_dir = PROJECT_ROOT / "frontend" / "src" / "screens"
    registry_dir = screens_dir / "registry"
    return [screens_dir / "registry.js", *sorted(registry_dir.glob("*.js"))]


def _rbac_block() -> str:
    for path in _rbac_source_files():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "  rbac: {" not in text:
            continue
        start = text.index("  rbac: {")
        end = text.index("\n  },", start)
        return _LINE_COMMENT.sub("", text[start:end])
    raise AssertionError(
        "rbac 화면 설정을 찾지 못했다 — registry.js 나 registry/*.js 어디에도 'rbac: {' 가 없다"
    )


def test_the_matrix_screen_does_not_redeclare_the_role_list():
    """화면이 역할 배열을 한 벌 더 들면 두 표가 어긋난다 — 그때 사람은 화면을 믿는다."""
    offenders = _ROLE_STRING.findall(_rbac_block())
    # roles: WRITE_ROLES 같은 **상수 참조**는 문자열이 아니므로 걸리지 않는다.
    assert not offenders, (
        "rbac 화면 설정에 역할 이름이 직접 적혀 있다: " + ", ".join(sorted(set(offenders)))
    )


def test_that_scan_is_not_vacuous():
    """정규식이 실제로 무엇인가를 잡는다는 증명 — 옛 문장을 넣어 보고 걸리는지 본다."""
    assert _ROLE_STRING.search('columns: [{ key: "system_admin", label: "시스템 관리자" }]')
    assert not _ROLE_STRING.search('// system_admin 은 이 화면에서 쓰지 않는다')


def test_read_only_roles_can_see_the_matrix(client, make_user):
    """'내가 무엇을 할 수 있는가'는 운영자·감사자도 볼 수 있어야 한다(사용자 데이터가 없다)."""
    make_user(email="auditor@goodmit.co.kr", role="auditor", display_name="감사자")
    assert client.post(
        "/login", json={"email": "auditor@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    ).status_code == 200
    response = client.get("/api/admin/rbac-matrix")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [r["value"] for r in body["roles"]] == list(ROLE_ORDER)
    assert body["source"] == "app/core/authz.py"


def test_a_plain_user_cannot_read_the_matrix(client, make_user):
    make_user(email="plain@goodmit.co.kr", role="user", display_name="사용자")
    assert client.post(
        "/login", json={"email": "plain@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
    ).status_code == 200
    assert client.get("/api/admin/rbac-matrix").status_code == 403
