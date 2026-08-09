"""SEC-22: `app/audit/actions.py` 의 공유 매칭 헬퍼가 실제로 옳은 것을 만드는가.

`app/health/service.py`(최근 주요 변경 위젯)와 `app/audit/anomalies.py`(이상 탐지)가
같은 이 헬퍼를 쓴다 - 여기서 틀리면 둘 다 같이 틀린다.
"""

from __future__ import annotations

import pytest

from app.audit.actions import SENSITIVE_ACTION_PREFIXES, with_cli_variants

pytestmark = pytest.mark.unit


def test_default_rule_prefixes_cli_dot():
    assert with_cli_variants(("user.disable",)) == ("user.disable", "cli.user.disable")


def test_known_exception_uses_its_explicit_cli_spelling():
    """역할 변경은 웹·CLI 가 다른 동사를 쓴다 - 일반 규칙("cli."+action)으로는 못 만든다."""
    result = with_cli_variants(("user.role_change",))
    assert result == ("user.role_change", "cli.user.set_role")
    assert "cli.user.role_change" not in result


def test_original_web_spellings_survive_unchanged():
    result = with_cli_variants(("user.role_change", "impersonation.start"))
    assert "user.role_change" in result
    assert "impersonation.start" in result


def test_sensitive_prefixes_cover_both_web_and_cli_user_actions():
    """SEC-22 의 핵심: "user." 만 있으면 cli.user.* 전체가 접두어 검사를 통째로
    지나간다 - 생성·활성화·비활성화·비밀번호 재설정·잠금해제·세션폐기·역할변경 전부."""
    assert any("cli.user." in p for p in SENSITIVE_ACTION_PREFIXES), (
        "cli.user. 접두어가 없다 - CLI 로 한 계정 조작이 심야·신규행위 규칙에서 안 걸린다"
    )
    for action in (
        "cli.user.create", "cli.user.enable", "cli.user.disable",
        "cli.user.reset_password", "cli.user.unlock", "cli.user.revoke_sessions",
        "cli.user.set_role",
    ):
        assert any(action.startswith(p) for p in SENSITIVE_ACTION_PREFIXES), (
            f"{action} 이 어떤 접두어에도 안 걸린다"
        )
