# qa-contract-change: 화면 문구를 문구 대장(D-597) 판정대로 바꿨다(동사표 · 마침표 · 조각 문장 · 실제 기능과 맞는 말). 단언하는 동작과 조건은 그대로이고 기대하는 글자만 새 문구다.
"""역할 설명은 **권한 표에서 계산된다** (지시 19).

## 왜 시험이 필요한가

「관리자는 …를 할 수 있습니다」를 화면이나 문서에 손으로 적는 순간 규칙이 두 벌이 된다.
권한을 `CAPABILITIES` 에서 고쳐도 그 문장은 안 따라오고, **틀린 설명은 아무 오류도 안
낸다** — 관리자가 그 문장을 믿고 역할을 고르면 의도한 것보다 넓거나 좁은 권한이 나간다.

그래서 `role_help()` 는 문장을 안 들고 있다. 능력 목록에서 계산하고, 여기서는 그 계산이
실제 권한 그룹과 어긋나지 않는지를 본다.

한 줄만 예외다 — `ROLE_CHARACTER` 의 「성격」 문장. 「감사자는 읽기 전용 가지다」는 능력
목록의 합이 아니라 설계 의도라 계산으로 만들 수 없다. 대신 그 문장이 능력 목록과 **모순**
되지 않는지는 아래에서 본다.
"""

from __future__ import annotations

import pytest

from app.core import authz

pytestmark = pytest.mark.security


def _by_role() -> dict[str, dict]:
    return {row["value"]: row for row in authz.role_help()}


def test_every_role_is_described():
    rows = _by_role()
    assert set(rows) == set(authz.ROLE_ORDER)
    for role, row in rows.items():
        assert row["label"], f"{role} 에 이름이 없다"
        assert row["character"], f"{role} 에 성격 문장이 없다"


def test_what_a_role_can_do_comes_from_the_capability_table():
    """🔴 설명의 능력 목록이 실제 권한 그룹과 **같은 집합**인가.

    여기서 갈라지면 화면이 「할 수 있다」고 적은 것을 서버가 403 으로 막는다. 그 어긋남은
    누군가 실제로 눌러 볼 때까지 안 보인다.
    """
    for role, row in _by_role().items():
        expected = [cap.label for cap in authz.CAPABILITIES if role in cap.roles]
        assert row["can"] == expected, f"{role}: 설명과 권한 표가 다르다"


def test_a_plain_user_can_do_nothing_in_the_console():
    """일반 사용자는 관리 콘솔 능력이 하나도 없다 — 그것이 이 역할의 정의다."""
    assert _by_role()["user"]["can"] == []


def test_gains_are_the_difference_from_the_role_below():
    """「무엇이 더 되는가」는 **차이**로 계산된다. 손으로 적은 목록이 아니다."""
    rows = _by_role()
    lower = {"operator": "user", "auditor": "user", "admin": "operator", "system_admin": "admin"}
    for role, base in lower.items():
        gained = set(rows[role]["can"]) - set(rows[base]["can"])
        assert set(rows[role]["gains"]) == gained, f"{role}: 새로 되는 것이 차이와 다르다"
        assert rows[role]["compared_to"] == rows[base]["label"]


def test_the_first_role_has_nothing_to_compare_against():
    row = _by_role()["user"]
    assert row["gains"] == []
    assert row["compared_to"] == ""


def test_backup_and_system_settings_belong_to_the_system_admin_alone():
    """🔴 설명이 실제 게이트와 맞는가 — 이 둘은 `SYSTEM_ADMIN_ONLY` 다.

    관리자에게 이 능력이 있다고 적히면, 서버가 막는 일을 화면이 권한다.
    """
    rows = _by_role()
    for label in ("백업 실행, 검증, 복구 안내",):
        assert label in rows["system_admin"]["can"]
        assert label not in rows["admin"]["can"]
        assert label not in rows["operator"]["can"]


def test_the_auditor_never_gains_a_writing_capability():
    """감사자의 성격 문장(「무엇도 바꾸지 않는다」)이 능력 목록과 모순되지 않는가.

    성격 문장은 계산이 아니라 사람이 쓴 것이라 **어긋날 수 있는 유일한 줄**이다. 감사자에게
    쓰기 능력이 하나라도 붙으면 그 문장은 거짓이 된다.
    """
    auditor = _by_role()["auditor"]
    writes = {
        cap.label
        for cap in authz.CAPABILITIES
        if cap.roles in (authz.CONSOLE_WRITE_ROLES, authz.CONSOLE_OPS_ROLES, authz.SYSTEM_ADMIN_ONLY)
    }
    assert not (set(auditor["can"]) & writes), f"감사자에게 쓰기 능력이 있다: {auditor['can']}"


def test_the_matrix_response_carries_the_role_help():
    """화면이 읽는 곳은 매트릭스 응답 하나다 — 별도 엔드포인트를 만들지 않았다."""
    body = authz.rbac_matrix()
    assert body["role_help"] == authz.role_help()
