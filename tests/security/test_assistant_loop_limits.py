"""🔴 도구를 끝없이 부르는 모델도 한 차례 안에서 멈춘다 (D-535).

언제나 도구를 부르는 제공자를 끼우고 상한을 잰다: 도구 라운드 넷 → 다섯째는 `tool_choice=none`, 라운드당 실행 넷 · 차례 합계
여덟, 모든 호출 id 에 결과, 같은 이름 · 같은 인자는 다시 쓰기, 결과 하나 8천 자 · 차례 3만 2천 자, 시간 예산, 슬롯 대기 상한.
DB 없이 도는 오프라인 런타임으로 잰다 - 상한은 런타임의 것이고 도구는 가짜다.
"""

from __future__ import annotations

import pytest

from app.ai import runtime as runtime_mod
from app.ai.assistant import results
from app.ai.providers import base
from app.ai.runtime import TurnInput
from tests.fakes.ai import ScriptedToolAdapter, offline_runtime, tool_call

TOOLS = (base.ToolSpec(name="probe", description="시험 도구", parameters={
    "type": "object", "properties": {"n": {"type": "integer", "description": "번호"}}, "required": ["n"],
    "additionalProperties": False,
}),)


class Recorder:
    """도구 실행 대역. 몇 번 실행됐는지와 인자를 든다."""

    def __init__(self, size: int = 10):
        self.calls: list = []
        self.size = size

    def __call__(self, call):
        self.calls.append(call.arguments)
        return results.ok("probe", [{"n": (call.arguments or {}).get("n"), "pad": "가" * self.size}])


def _always_calls(per_round: int):
    counter = {"n": 0}

    def step(request):
        if request["tool_choice"] == base.TOOL_CHOICE_NONE:
            return "끝냈습니다."
        calls = []
        for _ in range(per_round):
            counter["n"] += 1
            calls.append(tool_call("probe", {"n": counter["n"]}))
        return calls

    return step


def _turn(execute, **extra):
    return TurnInput(user_text="계속 찾아 줘", tools=TOOLS, execute=execute, **extra)


def test_rounds_stop_at_four_and_the_fifth_call_answers_without_tools():
    adapter = ScriptedToolAdapter([_always_calls(1)])
    execute = Recorder()
    outcome = offline_runtime(adapter).converse(None, action_key="assistant.chat", actor=None, turn=_turn(execute))

    choices = [c["tool_choice"] for c in adapter.converse_calls]
    assert choices == [base.TOOL_CHOICE_AUTO] * runtime_mod.MAX_TOOL_ROUNDS + [base.TOOL_CHOICE_NONE]
    assert outcome.ok and outcome.text == "끝냈습니다."
    assert (outcome.rounds, outcome.tool_calls) == (5, 4)
    # 마지막 라운드에도 도구 목록은 실린다 - 도구 호출이 든 대화는 목록이 있어야 받는 제공자가 있다.
    assert adapter.converse_calls[-1]["tools"] == TOOLS


def test_calls_are_capped_per_round_and_per_turn_but_every_call_gets_a_result():
    adapter = ScriptedToolAdapter([_always_calls(5)])
    execute = Recorder()
    outcome = offline_runtime(adapter).converse(None, action_key="assistant.chat", actor=None, turn=_turn(execute))

    assert len(execute.calls) == runtime_mod.MAX_CALLS_PER_TURN == outcome.tool_calls
    for index in range(1, runtime_mod.MAX_TOOL_ROUNDS + 1):
        asked = adapter.converse_calls[index - 1]
        results_turn = adapter.tool_results(index)
        assert len(results_turn) == 5, "결과 없는 호출 id 를 남겼다"
        if index <= 2:
            assert sum(r.is_error for r in results_turn) == 1, "라운드당 실행은 넷이다"
        assert asked is not None
    later = adapter.tool_results(3) + adapter.tool_results(4)
    assert all('"too_many_calls"' in r.content for r in later)


def test_the_same_call_is_answered_from_the_first_result():
    adapter = ScriptedToolAdapter([tool_call("probe", {"n": 1}), tool_call("probe", {"n": 1}), "끝"])
    execute = Recorder()
    outcome = offline_runtime(adapter).converse(None, action_key="assistant.chat", actor=None, turn=_turn(execute))
    assert execute.calls == [{"n": 1}]
    assert outcome.tool_calls == 1
    assert adapter.tool_results(1)[0].content == adapter.tool_results(2)[0].content


def test_a_huge_result_is_cut_and_the_turn_has_a_total_budget():
    adapter = ScriptedToolAdapter([_always_calls(4)])
    execute = Recorder(size=20_000)
    offline_runtime(adapter).converse(None, action_key="assistant.chat", actor=None, turn=_turn(execute))

    first = adapter.tool_results(1)
    for result in first:
        body = result.content.split("\n")[2:-2]
        assert len("\n".join(body)) <= runtime_mod.TOOL_RESULT_CHARS + 40
        assert runtime_mod.RESULT_CUT_NOTE in result.content
    total = sum(len(r.content) for i in range(1, 3) for r in adapter.tool_results(i))
    assert total < runtime_mod.TURN_RESULT_CHARS + 4000
    # 예산을 다 쓴 뒤의 호출은 실행하지 않고 그 사실을 결과로 말한다.
    assert any('"budget_exhausted"' in r.content for r in adapter.tool_results(2))


def test_the_turn_stops_when_its_time_budget_runs_out(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(runtime_mod.time, "monotonic", lambda: clock["t"])

    def slow(request):
        clock["t"] += 70  # 라운드마다 70초가 흐른다
        return tool_call("probe", {"n": len(request["turns"])})

    adapter = ScriptedToolAdapter([slow])
    outcome = offline_runtime(adapter).converse(None, action_key="assistant.chat", actor=None,
                                                turn=_turn(Recorder()))
    assert outcome.status == "timeout"
    assert outcome.error_code == "turn_budget"
    # 제한 시간 60초 × 4 = 240초 안에서 멈췄다(넷째 호출 전에 남은 시간이 모자란다).
    assert len(adapter.converse_calls) == 4


def test_the_slot_wait_is_bounded():
    waits: list = []

    class WaitLock:
        def acquire(self):
            return False

        def acquire_wait(self, seconds):
            waits.append(seconds)
            return False

        def release(self):
            pass

    adapter = ScriptedToolAdapter(["답"])
    outcome = offline_runtime(adapter, lock_factory=lambda config: WaitLock()).converse(
        None, action_key="assistant.chat", actor=None, turn=_turn(Recorder()))
    assert outcome.status == "busy"
    assert waits and max(waits) <= runtime_mod.SLOT_WAIT_SECONDS
    assert adapter.converse_calls == []


def test_a_tool_that_raises_becomes_an_unavailable_result_and_the_turn_goes_on():
    def broken(call):
        raise RuntimeError("터졌다")

    adapter = ScriptedToolAdapter([tool_call("probe", {"n": 1}), "답입니다."])
    outcome = offline_runtime(adapter).converse(None, action_key="assistant.chat", actor=None, turn=_turn(broken))
    assert outcome.ok
    assert '"unavailable"' in adapter.tool_results(1)[0].content


@pytest.mark.parametrize("final", [
    base.converse_failure(base.ERROR_REQUEST, "http_400", http_status=400),
    tool_call("probe", {"n": 99}),
])
def test_a_last_round_that_gives_no_text_closes_with_the_found_material(final):
    """「이제 도구 없이 답하라」를 거절하거나(400) 또 도구만 부르면, 찾은 자료로 닫는다."""
    adapter = ScriptedToolAdapter([_always_calls(1)] * 4 + [final])
    outcome = offline_runtime(adapter).converse(None, action_key="assistant.chat", actor=None,
                                                turn=_turn(Recorder()))
    assert outcome.ok
    assert outcome.closed_without_answer is True
    assert outcome.text == runtime_mod.CLOSE_WITHOUT_ANSWER
