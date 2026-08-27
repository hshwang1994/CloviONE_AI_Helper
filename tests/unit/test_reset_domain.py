"""지우는 목록을 **시험이 지킨다** (지시 23).

`scripts/reset_domain_data.py` 의 위험은 SQL 이 아니라 **목록**이다. 표 하나를 빠뜨리면
고아 행이 남고, 하나를 더 넣으면 남의 Domain 이 사라진다. 둘 다 실행하는 순간에는
성공으로 보이므로 사람이 눈으로 못 잡는다.

여기서 보는 것 넷:

  1. 목록이 **모델과 맞는가.** 채팅 도메인의 표가 늘거나 줄면 이 시험이 먼저 깨진다 —
     스크립트가 조용히 옛 목록으로 도는 것이 가장 나쁜 결과다.
  2. 삭제 **순서**가 외래키를 거스르지 않는가. 자식이 부모보다 먼저 와야 한다.
  3. 보호 목록의 표가 삭제 목록에 **없는가.**
  4. AI 도우미의 대화 기록(`conversations`·`messages`)이 채팅 도메인에 **안 들어갔는가.**
     지시 17 이 말한 「Chat DB 데이터」는 사내 메신저이고, 그쪽은 다른 도메인이다.
     사용자가 지우라고 한 적 없는 것을 지우는 것은 되돌릴 수 없는 사고다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load():
    """스크립트를 모듈로 읽는다. `scripts/` 는 패키지가 아니라 경로로 연다."""
    path = PROJECT_ROOT / "scripts" / "reset_domain_data.py"
    spec = importlib.util.spec_from_file_location("reset_domain_data", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_chat_domain_list_matches_the_models():
    """🔴 목록이 모델과 어긋나면 스크립트가 옛 목록으로 돈다.

    새 채팅 표가 생겼는데 여기 안 적히면, 초기화 뒤에도 그 표만 옛 데이터를 들고 남는다 —
    그리고 화면은 「지웠다」고 말한다.
    """
    from app.team_chat import models as chat_models

    declared = set(_load().DOMAINS["chat"])
    actual = {
        getattr(v, "__tablename__")
        for v in vars(chat_models).values()
        if hasattr(v, "__tablename__") and hasattr(v, "__table__")
    }
    assert declared == actual, (
        f"삭제 목록과 모델이 다르다.\n  목록에만: {sorted(declared - actual)}"
        f"\n  모델에만: {sorted(actual - declared)}"
    )


def test_children_come_before_their_parents():
    """자식이 먼저다. 부모를 먼저 지우면 외래키가 거절한다."""
    order = list(_load().DOMAINS["chat"])
    at = order.index
    assert at("chat_message_images") < at("chat_messages")
    assert at("chat_messages") < at("chat_rooms")
    assert at("chat_room_members") < at("chat_rooms")
    assert at("chat_read_cursors") < at("chat_rooms")


def test_no_protected_table_is_ever_in_a_delete_list():
    mod = _load()
    for domain, tables in mod.DOMAINS.items():
        overlap = set(tables) & set(mod.PROTECTED)
        assert not overlap, f"{domain} 목록에 보호 대상이 있다: {sorted(overlap)}"


def test_the_things_the_directive_named_are_all_protected():
    """지시 23 이 이름으로 적은 것들이 보호 목록에 있는가."""
    protected = set(_load().PROTECTED)
    for name in ("users", "organizations", "projects", "tickets", "roles", "user_roles"):
        assert name in protected, f"보호 목록에 {name} 이 없다"


def test_the_assistant_conversation_log_is_not_chat_domain():
    """🔴 AI 도우미의 대화 기록은 사내 메신저가 아니다.

    지시 17 은 「Room List · Room Header · 참여자」가 있는 화면을 말한다. 그 화면의
    데이터는 `chat_*` 다. `conversations`/`messages` 를 여기 끼워 넣으면 사용자가 지우라고
    한 적 없는 것을 지우게 되고, 그것은 되돌릴 수 없다.
    """
    chat = set(_load().DOMAINS["chat"])
    assert "conversations" not in chat
    assert "messages" not in chat


def test_the_witness_tables_are_protected_ones():
    """대조군은 **지우지 않는 표**여야 한다. 대상 표를 대조군으로 두면 늘 통과한다."""
    mod = _load()
    for name in mod.WITNESS:
        assert name in mod.PROTECTED, f"대조군 {name} 이 보호 목록에 없다"
        for tables in mod.DOMAINS.values():
            assert name not in tables
