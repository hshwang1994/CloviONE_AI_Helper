"""MEGA CYCLE H regression tests — AI Assistant quick-fix sweep, follow-up to MEGA CYCLE A.

Covers AI-37 (CREATE-mode 탈출어 안내) and AI-65 (질문판정 정규식의 조합 불가능 자모).
Same module-loading convention as test_mega_cycle_ai_assistant.py — no HTTP layer.
"""
import importlib.util
import os
from pathlib import Path

os.environ.setdefault("RUNNER_TOKEN", "test")

_spec = importlib.util.spec_from_file_location(
    "assistant_h", str(Path(__file__).with_name("assistant.py"))
)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


# ── AI-37: NEED_INPUT while mode=CREATE must mention the escape word ──────────

def test_create_mode_need_input_mentions_cancel_word():
    ctx = {"mode": "CREATE"}
    d = m.response("NEED_INPUT", "티켓을 생성할 프로젝트를 알려주세요.", ctx)
    assert "취소" in d["response_text"], d["response_text"]


def test_non_create_need_input_is_left_alone():
    d = m.response("NEED_INPUT", "우선순위를 알려주세요.", {"mode": None})
    assert "취소" not in d["response_text"]


def test_create_mode_non_need_input_is_left_alone():
    d = m.response("OK", "완료했습니다.", {"mode": "CREATE"})
    assert "취소" not in d["response_text"]


def test_hint_is_not_duplicated_if_already_present():
    ctx = {"mode": "CREATE"}
    d = m.response("NEED_INPUT", "다시 알려주세요.\n\n('취소'라고 답하면 이 작업을 그만둘 수 있어요.)", ctx)
    assert d["response_text"].count("취소") == 1


def test_hint_does_not_break_scannable_multiline_format():
    # test_assistant.py::test_create_not_ready_text_is_scannable pins the exact
    # indented "   선택지: …" line — the hint must land as its own trailing block,
    # never concatenated onto an existing line.
    ctx = {"mode": "CREATE"}
    body = "작업 지시를 확인했습니다.\n\n1. 질문\n2. 질문2\n   선택지: 나 / 미할당"
    d = m.response("NEED_INPUT", body, ctx)
    lines = d["response_text"].split("\n")
    assert lines[4] == "   선택지: 나 / 미할당"
    assert lines[-1] == "('취소'라고 답하면 이 작업을 그만둘 수 있어요.)"


# ── AI-65: -ㄹ까/-ㄴ지 endings on precomposed Hangul syllables must be recognized ──

def test_rieul_kka_ending_recognized_as_question():
    for word in ("될까", "할까", "바꿀까", "갈까", "바뀔까요"):
        assert m._READ_OR_QUESTION_RE.search(word), word


def test_nieun_ji_ending_recognized_as_question():
    for word in ("된 건지", "한 건지", "간 건지"):
        assert m._READ_OR_QUESTION_RE.search(word), word


def test_existing_literal_alternatives_still_match():
    # Regression guard: the rewrite must not drop any previously-working alternative.
    for word in ("보여줘", "일까", "을까", "완료했는지", "됐는지", "했는지"):
        assert m._READ_OR_QUESTION_RE.search(word), word
