"""내 프로필의 알림 유형 목록은 실제로 받는 역할로 거른다 (계획 M4, D-550).

못박는 것:
  * 백업 실패는 관리자 · 시스템 관리자만, AI 연결 상태는 시스템 관리자만 받는다 - 운영자 · 감사자 · 일반 사용자의 배지 목록과 메일
    목록에 그 유형이 서지 않는다(예전에는 「일반 사용자인가」만 봐서 운영자 · 감사자에게 받지도 않는 유형이 보였다).
  * 한 번뿐인 은퇴 유형은 어느 목록에도 없다.
"""

from __future__ import annotations

import pytest

from app.profiles import prefs

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("role, backup, ai_state", [
    ("user", False, False),
    ("operator", False, False),
    ("auditor", False, False),
    ("admin", True, False),
    ("system_admin", True, True),
])
def test_the_badge_catalog_follows_who_actually_receives(role, backup, ai_state):
    keys = {row["key"] for row in prefs.notification_type_catalog(role=role)}
    assert ("backup_failed" in keys) is backup
    assert ("ai_provider_state" in keys) is ai_state
    assert "ticket_assigned" in keys, "모두가 받는 유형은 언제나 선다"
    assert not (keys & prefs.PREFS_RETIRED_TYPES)


@pytest.mark.parametrize("role, expected", [
    ("operator", False), ("auditor", False), ("admin", False), ("system_admin", True),
])
def test_receivers_of_the_ai_connection_state(role, expected):
    assert prefs.receives("ai_provider_state", role) is expected
