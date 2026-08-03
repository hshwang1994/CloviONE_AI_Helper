"""_extract_text는 러너/n8n의 정본 필드 response_text를 우선한다.

2026-08-03부터 (표시 텍스트, 실제로 답이 있었는지) 튜플을 돌려준다. 답이 하나도 없는
빈 2xx를 '요청이 처리되었습니다.'로 답하면 워크플로가 중간에 끊겨도 사용자는 성공한 줄
알기 때문이다 — 그 사실을 호출측이 알 수 있어야 한다.
"""
import pytest

from app.jobs.handlers.chat_message import _extract_text

pytestmark = pytest.mark.unit


def test_prefers_response_text():
    text, answered = _extract_text({"response_text": "진행 티켓 3건 요약", "reply": "generic"})
    assert text == "진행 티켓 3건 요약"
    assert answered is True


def test_falls_back_to_reply():
    text, answered = _extract_text({"reply": "안녕하세요"})
    assert text == "안녕하세요"
    assert answered is True


def test_no_usable_answer_is_reported_as_such():
    """답이 없는 응답은 성공처럼 보이게 두지 않는다."""
    for payload in ({"action": "X"}, {"response_text": "   "}, {}):
        text, answered = _extract_text(payload)
        assert answered is False, payload
        assert "답을 돌려주지 않았습니다" in text, payload
