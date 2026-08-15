"""AI-16: 대화 삭제 시 러너 미러(conversation_state)도 지우라고 알리는 호출.

app/assistant/narrate.py와 같은 원칙을 이 함수도 지킨다 — **절대 예외를 던지지 않는다**.
여기서는 그 계약(어떤 outbound 실패든 흡수한다 + 올바른 URL/페이로드로 부른다)만 가볍게
확인한다. 실제 HTTP 계층·시크릿 파일 존재 여부는
tests/integration/test_chat_api.py::test_rename_and_delete_conversation이 이미
(시크릿 없음 → FileNotFoundError 흡수 경로로) 확인하고 있다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.chat.service import notify_runner_conversation_deleted

pytestmark = pytest.mark.unit


class _FakeOutbound:
    def __init__(self, *, raises=None):
        self.calls = []
        self._raises = raises

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self._raises:
            raise self._raises
        return SimpleNamespace(status_code=200)


def _settings():
    return SimpleNamespace(
        assistant_context_delete_url="http://127.0.0.1:8789/v1/assistant/context/delete",
        assistant_context_delete_timeout_seconds=5,
        assistant_runner_token_ref="assistant_runner_token",
    )


def _user():
    return SimpleNamespace(id="u1", email="a@goodmit.co.kr", display_name="황형섭")


def test_calls_the_runner_with_the_right_url_and_payload():
    outbound = _FakeOutbound()
    conv = SimpleNamespace(id="cv-1", backend_conversation_id=None)
    notify_runner_conversation_deleted(outbound, _settings(), user=_user(), conversation=conv)

    assert len(outbound.calls) == 1
    method, url, kwargs = outbound.calls[0]
    assert method == "POST"
    assert url == "http://127.0.0.1:8789/v1/assistant/context/delete"
    assert kwargs["json"]["conversation_id"] == "cv-1"
    assert kwargs["json"]["requester"] == {"user_id": "u1", "email": "a@goodmit.co.kr", "name": "황형섭"}
    assert kwargs["secret_ref"] == "assistant_runner_token"


def test_prefers_backend_conversation_id_when_present():
    """_build_job_payload와 같은 폴백 — 러너가 그 턴을 저장할 때 실제로 쓴 키와 일치해야
    지운다. backend_conversation_id가 없으면 애초에 저장된 적 없는 키를 지우는 셈이라
    아무 효과가 없다."""
    outbound = _FakeOutbound()
    conv = SimpleNamespace(id="cv-1", backend_conversation_id="n8n-conv-77")
    notify_runner_conversation_deleted(outbound, _settings(), user=_user(), conversation=conv)

    assert outbound.calls[0][2]["json"]["conversation_id"] == "n8n-conv-77"


@pytest.mark.parametrize("exc", [FileNotFoundError(), ConnectionError("refused"), TimeoutError("timed out"), RuntimeError("boom")])
def test_never_raises_no_matter_how_the_call_fails(exc):
    """🔴 revert-to-verify 대상 — narrate.py와 같은 계약. 삭제 자체를 절대 막지 않는다."""
    outbound = _FakeOutbound(raises=exc)
    conv = SimpleNamespace(id="cv-1", backend_conversation_id=None)
    notify_runner_conversation_deleted(outbound, _settings(), user=_user(), conversation=conv)  # 예외 없이 반환해야 한다
