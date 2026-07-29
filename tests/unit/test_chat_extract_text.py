"""_extract_text must prefer the runner/n8n canonical `response_text` field."""
import pytest

from app.jobs.handlers.chat_message import _extract_text

pytestmark = pytest.mark.unit


def test_prefers_response_text():
    assert _extract_text({"response_text": "진행 티켓 3건 요약", "reply": "generic"}) == "진행 티켓 3건 요약"


def test_falls_back_to_reply_then_default():
    assert _extract_text({"reply": "안녕하세요"}) == "안녕하세요"
    assert _extract_text({"action": "X"}) == "요청이 처리되었습니다."
    assert _extract_text({"response_text": "   "}) == "요청이 처리되었습니다."  # blank ignored
