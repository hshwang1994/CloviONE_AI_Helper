"""Shared action-name matching helpers for the audit widgets (SEC-22).

## Why this exists

`app/health/service.py`'s "최근 주요 변경" 위젯과 `app/audit/anomalies.py`'s 이상
탐지 규칙은 둘 다 **같은 동작**을 웹 콘솔로 했든 CLI(`app/cli/user_cli.py`,
CLAUDE.md 가 공식으로 문서화한 계정 관리 경로)로 했든 같은 것으로 알아봐야 한다.
CLI 는 대부분 `"cli." + 웹 동사`(예: `cli.user.disable` ↔ `user.disable`)로 적지만,
전부는 아니다 — 역할 변경은 웹에서 `user.role_change`, CLI 에서
`cli.user.set_role` 로 서로 다른 동사를 쓴다.

이 매핑을 `health/service.py` 만 알고 있었다(자기 위젯을 위해 직접 풀어 뒀다).
`anomalies.py` 의 심야·중대동작·신규행위 세 규칙은 이 예외를 몰라서 **CLI 로 한
역할 변경·계정 조작이 전부 조용히 안 걸렸다** — 감사 이상 탐지의 목적과 정확히
반대되는 사각지대였다. 이 파일 하나를 두 모듈이 같이 보게 해서, 새 CLI 명령이
웹과 다른 철자를 쓰면 한 곳만 고치면 되게 한다.
"""

from __future__ import annotations

# CLI 쪽에서 웹과 다른 동사를 쓰는 자리(app/cli/user_cli.py). 대부분의 CLI 명령은
# 아래 with_cli_variants() 의 기본 규칙("cli." + 웹 동사)을 따른다 - 여기는 그 규칙이
# 안 맞는 예외만 적는다.
CLI_ACTION_ALIASES: dict[str, str] = {
    "user.role_change": "cli.user.set_role",
}


def with_cli_variants(actions: tuple[str, ...]) -> tuple[str, ...]:
    """웹 스펠링 튜플에 그 CLI 스펠링을 더해서 돌려준다.

    기본은 `"cli." + action`. `CLI_ACTION_ALIASES` 에 있는 동작은 그 자리 대신
    명시된 철자를 쓴다(예: `user.role_change` → `cli.user.set_role`).
    """
    variants = tuple(CLI_ACTION_ALIASES.get(action, "cli." + action) for action in actions)
    return actions + variants


# 심야·신규행위 규칙(app/audit/anomalies.py)이 보는 접두어. 웹 콘솔과 CLI 둘 다
# `user.`/`cli.user.` 로 시작하는 동작을 쓰므로 두 접두어 다 있어야 한다 - "user." 만
# 있으면 cli.user.* 전부(생성·활성화·비활성화·비밀번호 재설정·잠금해제·세션폐기·
# 역할변경)가 이 접두어 검사를 통째로 지나간다.
SENSITIVE_ACTION_PREFIXES: tuple[str, ...] = (
    "user.",
    "cli.user.",
    "impersonation.",
    "approval.",
    "approval_delegation.",
    "feature_flag.",
    "app_setting.",
    "backup.",
    "integration.change_config",
)
