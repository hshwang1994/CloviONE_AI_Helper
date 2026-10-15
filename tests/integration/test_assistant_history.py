"""AI 도우미가 싣는 지난 문답 — 완결 쌍만, 최근 여섯 쌍, 글자 상한 (D-535).

제공자는 사람과 도우미의 차례가 번갈아야 받는다. 그래서 실패한 사람 메시지(답이 없다), 안내 메시지(`error_notice`), 지운
메시지는 빼고 **사람 메시지와 그 답이 함께 있는 쌍**만 싣는다. 합계 글자를 넘으면 오래된 쌍부터 버린다.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.ai.assistant import history
from app.conversations.models import (
    PROC_DONE,
    PROC_FAILED,
    ROLE_ASSISTANT_MSG,
    ROLE_USER_MSG,
    Conversation,
    Message,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def conversation(db, make_user):
    user = make_user("history@goodmit.co.kr", role="user", display_name="이력")
    row = Conversation(user_id=user.id, title="이력")
    db.add(row)
    db.flush()
    return row


def _pair(db, conversation, question, answer, *, mid=None, status=PROC_DONE, notice=False, failed_reply=False):
    mid = mid or f"m{uuid.uuid4().hex[:12]}"
    db.add(Message(conversation_id=conversation.id, message_id=mid, role=ROLE_USER_MSG, content=question,
                   processing_status=status))
    db.flush()
    if answer is not None:
        job = str(uuid.uuid4())
        db.add(Message(conversation_id=conversation.id,
                       message_id=f"a-{mid}-fail-{job}" if failed_reply else f"a-{mid}-{job}",
                       role=ROLE_ASSISTANT_MSG, content=answer, processing_status=PROC_DONE,
                       structured_payload_json=json.dumps({"error_notice": True}) if notice else None))
        db.flush()
    return mid


def _current(db, conversation):
    row = Message(conversation_id=conversation.id, message_id=f"m{uuid.uuid4().hex[:12]}", role=ROLE_USER_MSG,
                  content="지금 질문", processing_status="processing")
    db.add(row)
    db.flush()
    return row


def test_only_complete_pairs_before_this_turn_are_carried(db, conversation):
    _pair(db, conversation, "첫 질문", "첫 답")
    _pair(db, conversation, "실패한 질문", "답을 만들지 못했습니다.", status=PROC_FAILED, failed_reply=True)
    _pair(db, conversation, "안내만 받은 질문", "안내", notice=True)
    _pair(db, conversation, "답이 없는 질문", None)
    deleted = _pair(db, conversation, "지운 질문", "지운 답")
    for row in db.query(Message).filter(Message.message_id.like(f"%{deleted}%")):
        row.deleted_at = row.created_at
    _pair(db, conversation, "둘째 질문", "둘째 답")
    current = _current(db, conversation)

    pairs = history.recent_pairs(db, conversation_id=conversation.id, before_seq=current.seq)
    assert pairs == (("첫 질문", "첫 답"), ("둘째 질문", "둘째 답"))


def test_six_pairs_at_most_and_oldest_dropped_past_the_character_budget(db, conversation):
    for n in range(8):
        _pair(db, conversation, f"질문 {n}", f"답 {n}")
    current = _current(db, conversation)
    pairs = history.recent_pairs(db, conversation_id=conversation.id, before_seq=current.seq)
    assert [q for q, _ in pairs] == [f"질문 {n}" for n in range(2, 8)]

    long_pairs = history.recent_pairs(db, conversation_id=conversation.id, before_seq=current.seq, total_chars=20)
    assert [q for q, _ in long_pairs] == ["질문 6", "질문 7"]


def test_a_hyphenated_message_id_does_not_steal_another_messages_answer(db, conversation):
    _pair(db, conversation, "앞 질문", "앞 답", mid="abc-12345")
    _pair(db, conversation, "뒤 질문", "뒤 답", mid="abc-12345-x")
    current = _current(db, conversation)
    pairs = history.recent_pairs(db, conversation_id=conversation.id, before_seq=current.seq)
    assert pairs == (("앞 질문", "앞 답"), ("뒤 질문", "뒤 답"))


@pytest.mark.parametrize("raw, expected", [
    ({"kind": "ticket", "ref": "ABCDEF-12", "label": "티켓"}, {"kind": "ticket", "ref": "ABCDEF-12", "label": "티켓"}),
    ({"kind": "document", "ref": "x" * 64}, {"kind": "document", "ref": "x" * 64, "label": ""}),
    ("티켓 상세", None),
    ({"kind": "user", "ref": "u-1"}, None),
    ({"kind": "ticket", "ref": "../etc/passwd"}, None),
    ({"kind": "ticket", "ref": "x" * 65}, None),
])
def test_the_screen_target_shape_is_checked(raw, expected):
    assert history.screen_target(raw) == expected


# ── 이어지는 질문의 기억 (AI 채팅 개선 회차) ──────────────────────────────────────


def _answer_with_blocks(db, conversation, question, results, *, failed_reply=False, notice=False, deleted=False):
    mid = f"m{uuid.uuid4().hex[:12]}"
    db.add(Message(conversation_id=conversation.id, message_id=mid, role=ROLE_USER_MSG, content=question,
                   processing_status=PROC_DONE))
    db.flush()
    job = str(uuid.uuid4())
    payload = {"kind": "assistant", "results": results, **({"error_notice": True} if notice else {})}
    row = Message(conversation_id=conversation.id, message_id=f"a-{mid}-fail-{job}" if failed_reply else f"a-{mid}-{job}",
                  role=ROLE_ASSISTANT_MSG, content="답", processing_status=PROC_DONE,
                  structured_payload_json=json.dumps(payload, ensure_ascii=False))
    db.add(row)
    db.flush()
    if deleted:
        from datetime import datetime

        row.deleted_at = datetime(2026, 10, 15, 0, 0, 0)
        db.flush()


def _block(tool, n, *, offset=0, total=None, shown=True, args=None):
    return {"id": "r1", "tool": tool, "kind": "document", "shown": shown, "args": args or {}, "total": total or n,
            "offset": offset, "returned": n,
            "items": [{"ref": f"d{i}", "title": f"문서 {i}", "updated_at": "2026-09-04T00:00:00", "route": f"/knowledge/d{i}"}
                      for i in range(n)]}


def test_recent_results_carry_args_refs_and_numbers(db, conversation):
    _answer_with_blocks(db, conversation, "내가 만든 문서", [_block("my_documents", 10, total=361, args={"sort": "recent"})])
    current = _current(db, conversation)
    memory = json.loads(history.recent_results(db, conversation_id=conversation.id, before_seq=current.seq))
    [entry] = memory
    assert (entry["turn"], entry["tool"], entry["shown"], entry["total"], entry["offset"]) == (-1, "my_documents", True, 361, 0)
    assert entry["args"] == {"sort": "recent"}
    assert entry["items"][0] == {"n": 1, "ref": "d0", "title": "문서 0", "updated_at": "2026-09-04T00:00:00"}


def test_recent_results_skip_failed_deleted_and_notice_answers(db, conversation):
    _answer_with_blocks(db, conversation, "쓴 질문", [_block("my_documents", 2)])
    _answer_with_blocks(db, conversation, "실패한 답", [_block("search_documents", 2)], failed_reply=True)
    _answer_with_blocks(db, conversation, "안내 답", [_block("search_documents", 2)], notice=True)
    _answer_with_blocks(db, conversation, "지운 답", [_block("search_documents", 2)], deleted=True)
    current = _current(db, conversation)
    memory = json.loads(history.recent_results(db, conversation_id=conversation.id, before_seq=current.seq))
    assert [e["tool"] for e in memory] == ["my_documents"]


def test_recent_results_keep_two_turns_oldest_first_within_the_budget(db, conversation):
    from app.ai.assistant import blocks

    for tool in ("my_documents", "search_documents", "my_work"):
        _answer_with_blocks(db, conversation, tool, [_block(tool, 10, args={"query": "가" * 90})])
    current = _current(db, conversation)
    text = history.recent_results(db, conversation_id=conversation.id, before_seq=current.seq)
    memory = json.loads(text)
    assert [e["tool"] for e in memory] == ["search_documents", "my_work"], "앞 두 차례만, 오래된 것부터"
    assert [e["turn"] for e in memory] == [-2, -1]
    assert len(text) <= blocks.MEMORY_CHARS


def test_no_blocks_means_no_memory(db, conversation):
    _pair(db, conversation, "안녕", "안녕하세요")
    current = _current(db, conversation)
    assert history.recent_results(db, conversation_id=conversation.id, before_seq=current.seq) is None
