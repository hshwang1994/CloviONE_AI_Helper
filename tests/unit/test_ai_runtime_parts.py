"""AI 런타임의 부품 — 액션 표, 제공자 표, Anthropic 오류 분류, 차단기 (계획 3.13 · 3.14 · 3.15, D-515).

런타임 전체의 흐름은 `tests/integration/test_ai_runtime.py` 가 잰다. 여기서는 표와 규칙이 서 있는지만 본다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.ai import actions
from app.ai.breaker import COOLDOWN, THRESHOLD, WINDOW, Breaker
from app.ai.providers import anthropic, base

pytestmark = pytest.mark.unit


# ── 액션 표 ──────────────────────────────────────────────────────────────────

def test_every_action_has_positive_limits():
    for action in actions.ACTIONS.values():
        assert action.max_output_chars > 0 and action.max_output_tokens > 0, action.key
        assert action.kind in (actions.KIND_READ, actions.KIND_WRITE), action.key


def test_only_the_connection_test_is_outside_the_quota():
    outside = {a.key for a in actions.ACTIONS.values() if not a.counts_quota}
    assert outside == {actions.CONNECTION_TEST}


def test_the_quiz_is_the_json_action():
    assert {a.key for a in actions.ACTIONS.values() if a.json_output} == {actions.GAME_QUIZ}


def test_an_unknown_action_is_refused_not_defaulted():
    with pytest.raises(KeyError):
        actions.get_action("chat.anwser")


# ── 제공자 표 ────────────────────────────────────────────────────────────────

def test_anthropic_offers_only_an_api_key():
    """제3자 앱의 계정 로그인은 Anthropic 의 공식 정책이 금지한다(계획 3.14) - 표에 그 방식이 없어야 화면도 없다."""
    spec = base.provider_spec("anthropic")
    assert [m.key for m in spec.auth_methods] == [base.AUTH_API_KEY]
    assert spec.method(base.AUTH_API_KEY).secret_slot == "ai.anthropic.api_key"


def test_every_auth_method_points_at_a_known_secret_slot():
    from app.core.secret_slots import SECRET_SLOTS

    for spec in base.PROVIDERS.values():
        for method in spec.auth_methods:
            assert method.secret_slot in SECRET_SLOTS, (spec.key, method.key)
            assert method.missing.endswith("다."), method.missing


def test_an_unknown_pair_builds_no_adapter():
    assert base.build_adapter("anthropic", "chatgpt", outbound=None, secrets=None) is None
    assert base.build_adapter("nobody", "api_key", outbound=None, secrets=None) is None


# ── Anthropic 오류 분류 ──────────────────────────────────────────────────────


class _Response:
    def __init__(self, status: int, body=None) -> None:
        self.status_code = status
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


@pytest.mark.parametrize("status,body,kind,code", [
    (401, {"error": {"type": "authentication_error"}}, base.ERROR_AUTH, "http_401"),
    (403, {"error": {"type": "permission_error"}}, base.ERROR_AUTH, "http_403"),
    (404, {"error": {"type": "not_found_error", "message": "model: claude-x"}}, base.ERROR_CONFIG, "model_not_found"),
    (400, {"error": {"type": "invalid_request_error", "message": "model: nope is not valid"}}, base.ERROR_CONFIG,
     "model_not_found"),
    (400, {"error": {"type": "invalid_request_error", "message": "prompt is too long"}}, base.ERROR_REQUEST,
     "invalid_request_error"),
    (429, {"error": {"type": "rate_limit_error"}}, base.ERROR_TRANSIENT, "http_429"),
    (529, {"error": {"type": "overloaded_error"}}, base.ERROR_TRANSIENT, "http_529"),
    (500, None, base.ERROR_TRANSIENT, "http_500"),
])
def test_http_errors_are_classified_by_what_a_person_must_do(status, body, kind, code):
    result = anthropic.classify_status(_Response(status, body))
    assert (result.ok, result.error_kind, result.error_code) == (False, kind, code)


def test_text_is_taken_only_from_text_blocks():
    assert anthropic.extract_text({"content": [{"type": "text", "text": "가"}, {"type": "tool_use", "text": "x"},
                                               {"type": "text", "text": "나"}]}) == "가\n나"
    assert anthropic.extract_text({"content": "모양이 다르다"}) is None
    assert anthropic.extract_text([]) is None


# ── 차단기 ───────────────────────────────────────────────────────────────────

T0 = datetime(2026, 9, 30, 9, 0, 0)
KEY = ("anthropic", "api_key")


def test_the_breaker_opens_after_repeated_transient_failures_and_half_opens_after_the_cooldown():
    breaker = Breaker()
    for i in range(THRESHOLD):
        assert breaker.allow(KEY, T0 + timedelta(seconds=i))
        breaker.failure(KEY, T0 + timedelta(seconds=i))
    opened = T0 + timedelta(seconds=THRESHOLD - 1)
    assert not breaker.allow(KEY, opened + timedelta(seconds=1)), "세 번 이어진 실패 뒤에도 곧바로 보냈다"
    later = opened + COOLDOWN + timedelta(seconds=1)
    assert breaker.allow(KEY, later), "쉬는 시간이 지난 첫 호출을 막았다 - 복구가 늦어진다"
    assert not breaker.allow(KEY, later), "반쯤 열린 동안 두 번째 호출도 보냈다"
    breaker.success(KEY)
    assert breaker.allow(KEY, later)


def test_failures_spread_beyond_the_window_do_not_open_it():
    breaker = Breaker()
    for i in range(THRESHOLD):
        breaker.failure(KEY, T0 + i * (WINDOW + timedelta(seconds=1)))
    assert breaker.allow(KEY, T0 + THRESHOLD * WINDOW)


def test_a_failed_probe_reopens_for_another_cooldown():
    breaker = Breaker()
    for i in range(THRESHOLD):
        breaker.failure(KEY, T0)
    later = T0 + COOLDOWN + timedelta(seconds=1)
    assert breaker.allow(KEY, later)
    breaker.failure(KEY, later)
    assert not breaker.allow(KEY, later + timedelta(seconds=5))
    assert breaker.allow(KEY, later + COOLDOWN + timedelta(seconds=1))


def test_an_unwritable_slot_directory_is_a_failed_result_not_a_crash():
    """슬롯 파일을 못 쓰는 환경(데이터 디렉터리 권한)에서도 웹 요청은 500 이 아니라 실패 결과를 받는다."""
    from app.ai.gateway import contract
    from app.core.worker_lock import WorkerLockError
    from tests.fakes.ai import ScriptedAdapter, offline_runtime

    class _Broken:
        def acquire(self):
            raise WorkerLockError("리스 파일을 쓸 수 없다")

        def release(self):
            pass

    adapter = ScriptedAdapter()
    runtime = offline_runtime(adapter, lock_factory=lambda config: _Broken())
    result = runtime.generate(None, action_key="chat.answer", task="t", data="d")
    assert result.status == contract.STATUS_FAILED and result.error_code == "slot_unavailable"
    assert adapter.calls == []
