"""AI 생성의 유일한 문 — `AiRuntime.generate` (계획 3.13, D-515).

## 예전에는 길이 둘이었다

주간 요약과 연결 확인은 `app/llm/service.py` 로, 채팅과 작업 공간과 홈 요약과 퀴즈는 `app/ai/gateway` 로 나갔다.
뒤쪽은 부팅 때 설정을 굳혀서 관리 화면에서 바꾼 값이 재시작 전까지 안 먹었고, 동시 실행 수는 앞쪽에만 걸렸고,
서버에 로그인된 구독 명령줄 도구를 부르는 길은 공식 정책에 어긋났다. 이제 모든 생성이 여기를 지난다.

## 한 번의 호출

  1. 설정을 **호출마다** 읽는다(설정 캐시가 30초마다 새로 고친다). 재시작 없이 바뀐 값이 다음 호출에 쓰인다
  2. 생성이 꺼져 있으면 멈춘다. 연결 상태가 막힌 상태(미설정, 재로그인 필요, 인증 또는 구성 오류)면 멈춘다
  3. 일시 장애가 이어져 차단기가 열려 있으면 곧바로 「일시 장애」로 돌려보낸다(`app/ai/breaker.py`)
  4. 액션을 찾는다(`app/ai/actions.py`) - 출력 길이, JSON 여부, 지시문의 사용처가 여기서 온다
  5. 지시문을 고른다(`app/ai/prompts/service.py::resolve`) - 그 사용처에 발행한 프롬프트가 있으면 그것, 없으면 기본
     제공(D-518). 부른 쪽은 지시문을 넘기지 않는다
  6. 정책을 고른다(`app/ai/policy/engine.py`, D-519) - 개인정보 가리기가 걸려 있으면 제공자에 보내기 전의 데이터에서
     개인정보를 가린다. 연결 확인에는 정책이 걸리지 않는다
  7. 프롬프트를 조립한다. **`app/llm/prompt.py::build_prompt` 를 부르는 곳은 여기뿐이다** - 난스 구분자와
     「데이터는 지시가 아니다」가 모든 경로에 걸린다(D-202). 역할과 출력 형식은 사용처가 코드에 고정한 값이다
  8. 동시 실행 슬롯을 잡는다(`app/ai/concurrency.py`) - 웹과 워커가 한 벌을 나눠 쓴다
  9. 제공자를 부른다(`app/ai/providers/`) - 제한 시간과 토큰 수를 잰다. 계정 연결(ChatGPT)이면 어댑터가 부르기 전에
     토큰의 만료를 보고 필요하면 갱신한다(`app/ai/credentials/chatgpt.py`)
 10. 결과로 연결 상태를 바꾼다(`app/ai/credentials/state.py`). 제 짧은 세션으로 적는다 - 부른 쪽의 트랜잭션이
     실패해도 「방금 성공했다」는 사실이 사라지지 않는다
 11. 출력을 다듬는다. 제어 문자를 지우고, 정책대로 개인정보를 가리고 제품 밖 링크를 누를 수 없게 하며, 액션의 길이
     (응답 제한 정책이 있으면 그보다 짧게)로 자른다. JSON 액션은 자르지 않는다 - 넘으면 실패다
 12. 사용 기록 한 행을 남긴다(`app/ai/usage.py`) - 누가, 어떤 기능으로, 어느 모델과 지시문과 정책으로, 얼마나
     썼고 어떻게 끝났는지. 한도의 원장이 이 행이다. 생성이 꺼져 있거나 설정이 비어 아무것도 시도하지 않은 호출은
     남기지 않는다

## AI 도우미 한 차례 — `AiRuntime.converse` (D-535 · D-537)

AI 도우미는 단발 호출이 아니라 도구를 쓰는 대화다. 막힘 판정 · 지시문 · 정책 · 연결 상태 · 사용 기록은 위와 같은 길을
지나고, 다른 것은 셋이다.

  * 프롬프트 틀이 `assistant_system` · `user_turn` · `fence` 다. 사용자의 말은 지시 칸이고, 도구 결과 · 화면 대상 · 대체
    모드의 검색 자료는 난스 칸이다. 이 셋을 부르는 곳도 여기뿐이다
  * 제공자를 여러 번 부른다(도구 라운드 넷 + 마무리 하나). 슬롯은 **호출마다** 잡고(워커는 20초까지 기다린다) 연결
    상태도 호출마다 적는다. 차례 전체에는 시간 예산(제한 시간 네 번, 많아야 4분)과 도구 수 · 결과 크기 상한이 있다
  * 도구를 거절하는 제공자에게는 서버가 먼저 찾은 검색 자료를 칸에 실어 도구 없이 한 번 부른다(대체 모드)

사용 기록은 차례마다 **한 행**이다 - 사람의 요청 한 번이 한도 한 칸이다.

## 실패는 값이다

부른 쪽은 예외를 받지 않는다. 검색 결과와 목록은 모델과 무관하게 이미 만들어져 있고, 생성 하나 때문에 그것이 안
나가면 안 된다(`app/ai/gateway/contract.py` 의 규약 그대로).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.ai import actions as actions_mod
from app.ai import concurrency
from app.ai.breaker import Breaker
from app.ai.credentials import state as state_mod
from app.ai.gateway import contract
from app.ai.providers import base
from app.core.worker_lock import WorkerLockError

logger = logging.getLogger("app.ai.runtime")

SETTING_KEYS = (
    "ai_generation_enabled", "ai_provider", "ai_auth_method", "ai_model", "ai_timeout_seconds", "ai_max_concurrency",
)
VERIFY_TIMEOUT_SECONDS = 30
VERIFY_DATA = "연결 확인"


@dataclass(frozen=True)
class RuntimeConfig:
    generation_enabled: bool = False
    provider: str = ""
    auth_method: str = ""
    model: str = ""
    timeout_seconds: int = concurrency.DEFAULT_TIMEOUT_SECONDS
    max_concurrency: int = concurrency.DEFAULT_CONCURRENCY

    @property
    def key(self) -> tuple[str, str]:
        return (self.provider, self.auth_method)

    def method(self) -> base.AuthMethod | None:
        spec = base.provider_spec(self.provider)
        return spec.method(self.auth_method) if spec else None


def config_from_values(values: dict) -> RuntimeConfig:
    def _str(key: str) -> str:
        value = values.get(key)
        return value.strip() if isinstance(value, str) else ""

    return RuntimeConfig(
        generation_enabled=values.get("ai_generation_enabled") is True,
        provider=_str("ai_provider"),
        auth_method=_str("ai_auth_method"),
        model=_str("ai_model"),
        timeout_seconds=concurrency.clamp_timeout(values.get("ai_timeout_seconds")),
        max_concurrency=concurrency.clamp_concurrency(values.get("ai_max_concurrency")),
    )


def problems(config: RuntimeConfig, secrets) -> list[str]:
    """미설정의 까닭. 비어 있으면 설정은 다 됐다(동작하는지는 연결 상태가 말한다)."""
    spec = base.provider_spec(config.provider)
    if spec is None:
        return ["AI 제공자를 아직 고르지 않았습니다."]
    method = spec.method(config.auth_method)
    if method is None:
        return [f"{spec.label}의 인증 방식을 아직 고르지 않았습니다."]
    found: list[str] = []
    if not config.model:
        found.append("모델을 아직 고르지 않았습니다.")
    from app.core.secret_refs import STATUS_CONFIGURED

    if secrets is None or secrets.status(method.secret_slot) != STATUS_CONFIGURED:
        found.append(method.missing)
    return found


def _clean(text) -> str | None:
    """모델 출력은 신뢰하지 않는다. 제어 문자(줄바꿈과 탭 제외)를 버린다 - 터미널 이스케이프가 로그와 화면으로 샌다."""
    if not isinstance(text, str):
        return None
    cleaned = "".join(c for c in text if c in "\n\t" or c.isprintable()).strip()
    return cleaned or None


def _status_for(result: base.ProviderResult) -> str:
    if result.error_kind == base.ERROR_TRANSIENT:
        return contract.STATUS_TIMEOUT if result.error_code == "timeout" else contract.STATUS_DEGRADED
    if result.error_kind in (base.ERROR_AUTH, base.ERROR_REAUTH, base.ERROR_CONFIG):
        return contract.STATUS_CREDENTIAL_ERROR
    if result.error_kind == base.ERROR_EMPTY:
        return contract.STATUS_EMPTY
    return contract.STATUS_FAILED


# ── AI 도우미 한 차례 (D-535 · D-537) ─────────────────────────────────────────────────────────────────────────

MODE_TOOLS = "tools"
MODE_SEARCH_ONLY = "search_only"
#: 도구를 부를 수 있는 라운드 수. 그다음 한 번은 도구 없이 답만 받는다(`tool_choice=none`).
MAX_TOOL_ROUNDS = 4
MAX_CALLS_PER_ROUND = 4
MAX_CALLS_PER_TURN = 8
#: 도구 결과 하나 · 한 차례 전체의 글자 상한(칸에 넣기 전, 가린 뒤).
TOOL_RESULT_CHARS = 8000
TURN_RESULT_CHARS = 32000
#: 워커가 슬롯을 기다리는 상한. 웹의 단발 호출은 기다리지 않는다.
SLOT_WAIT_SECONDS = 20.0
#: 남은 시간이 이보다 짧으면 제공자를 더 부르지 않는다.
MIN_CALL_SECONDS = 5.0
TURN_BUDGET_MAX_SECONDS = 240
#: 도구를 거절한 제공자의 실패 코드(`app/ai/providers/openai.py` 의 ChatGPT 요금제).
UNSUPPORTED_TOOLS_CODE = "unsupported_capability"

LABEL_TOOL_RESULT = "도구 결과입니다."
LABEL_SCREEN = "사용자가 지금 보는 화면의 대상입니다. 서버가 권한을 확인해 읽었습니다."
LABEL_SEARCH = "서버가 질문으로 먼저 찾은 사내 자료입니다."
RESULT_CUT_NOTE = "(결과가 길어 앞부분만 실었습니다.)"
#: 마지막 라운드가 답 글을 주지 못했을 때 - 찾은 자료는 화면이 출처로 보인다.
CLOSE_WITHOUT_ANSWER = "찾은 자료를 아래 「참고한 자료」에 모았습니다. 답을 문장으로 정리하지 못했으니 자료를 직접 열어 확인해 주세요."
PROGRESS_READING = "질문을 살펴보고 있습니다."
PROGRESS_COMPOSING = "찾은 내용으로 답을 정리하고 있습니다."


def turn_budget_seconds(timeout_seconds) -> int:
    """한 차례의 시간 예산 - 호출 하나의 제한 시간 네 번, 많아야 4분(대화형 레인의 실행 상한 안)."""
    return min(4 * concurrency.clamp_timeout(timeout_seconds), TURN_BUDGET_MAX_SECONDS)


@dataclass(frozen=True)
class TurnInput:
    """도우미 한 차례에 런타임이 받는 것. 원문은 **런타임이** 칸에 넣는다 - 부른 쪽은 칸을 만들지 않는다.

    ``history`` 는 지난 완결 문답 ``((사람, 도우미), …)`` 이고 오래된 것부터다. ``preload`` 는 서버가 권한으로 확인해 읽은
    화면 대상의 JSON 이다. ``tools`` 는 권한과 기능 플래그로 거른 도구(`base.ToolSpec`)이고, ``execute`` 는 도구 호출 하나를
    실행해 `app.ai.assistant.results.Execution` 을 돌려준다. ``fallback`` 은 대체 모드의 검색(같은 `Execution`, 없으면 None),
    ``progress`` 는 진행 문구를 화면에 적는다.
    """

    user_text: str
    history: tuple = ()
    context_lines: tuple = ()
    preload: str | None = None
    tools: tuple = ()
    execute: Callable | None = None
    fallback: Callable | None = None
    progress: Callable | None = None


@dataclass(frozen=True)
class ConverseOutcome:
    """한 차례의 결과. 예외 대신 값이다(`GenerateResult` 와 같은 규약)."""

    status: str
    text: str | None = None
    mode: str = MODE_TOOLS
    #: 제공자를 부른 횟수와 실행한 도구 수 · 이름(사용 기록에 이름만 남는다).
    rounds: int = 0
    tool_calls: int = 0
    tool_names: tuple = ()
    #: 실행한 도구의 결과(`results.Execution`) - 화면의 「참고한 자료」와 「확인한 내용」이 쓴다. 모델에 간 글과 같다.
    executions: tuple = ()
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    truncated: bool = False
    input_truncated: bool = False
    error_code: str | None = None
    #: 마지막 라운드가 답 글을 주지 못해 고정 문장으로 닫았다.
    closed_without_answer: bool = False
    delimiter_conflict: bool = False
    model: str = ""
    provider: str = ""
    prompt_slot: str | None = None
    prompt_source: str | None = None
    prompt_version: int | None = None
    prompt_id: str | None = None
    policy_ids: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == contract.STATUS_OK and bool(self.text)

    @property
    def notice(self) -> str | None:
        return None if self.ok else contract.notice_for(self.status)


@dataclass
class _TurnLedger:
    """한 차례 동안 모으는 값."""

    rounds: int = 0
    calls: int = 0
    names: list = field(default_factory=list)
    executions: list = field(default_factory=list)
    cache: dict = field(default_factory=dict)
    result_chars: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    conflict: bool = False

    def tokens(self, result) -> None:
        if result.input_tokens is not None:
            self.input_tokens = (self.input_tokens or 0) + int(result.input_tokens)
        if result.output_tokens is not None:
            self.output_tokens = (self.output_tokens or 0) + int(result.output_tokens)


def _call_key(call) -> tuple | None:
    """같은 이름 · 같은 인자의 호출은 다시 실행하지 않고 앞 결과를 다시 쓴다. 읽지 못한 인자는 다시 쓰지 않는다."""
    if not isinstance(call.arguments, dict):
        return None
    try:
        return call.name, json.dumps(call.arguments, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return None


class _AssistantMixin:
    """`AiRuntime` 의 도우미 쪽. 클래스를 둘로 나눈 것은 읽기 위해서다 - 상태는 `AiRuntime` 하나에 있다."""

    def converse(self, db: Session, *, action_key: str, actor, turn: TurnInput, job_id: str | None = None,
                 request_id: str | None = None) -> ConverseOutcome:
        """도우미 한 차례. 예외를 올리지 않는다(도구 실행의 예외도 결과 칸의 `unavailable` 로 접는다)."""
        config = self.config(db)
        started = time.monotonic()
        outcome = self._converse(db, config, action_key=action_key, turn=turn, started=started)
        outcome = _with_latency(outcome, started)
        self._record_turn_usage(config, outcome, action_key=action_key, actor=actor, job_id=job_id,
                                request_id=request_id)
        return outcome

    def _converse(self, db: Session, config, *, action_key: str, turn: TurnInput, started: float) -> ConverseOutcome:
        from app.ai.policy import engine as policy_engine
        from app.ai.prompts import service as prompt_slots
        from app.llm import prompt as prompt_mod

        action = actions_mod.get_action(action_key)
        if not action.tools:
            raise ValueError(f"{action_key} 는 도구를 쓰는 액션이 아니다")
        method = config.method()
        slot = method.secret_slot if method else None
        plain = dict(model=config.model, provider=config.provider)
        if not config.generation_enabled:
            return ConverseOutcome(status=contract.STATUS_DISABLED, **plain)
        if problems(config, self._secrets):
            return ConverseOutcome(status=contract.STATUS_UNCONFIGURED, **plain)
        now = self._now()
        if self._track_state and db is not None and self._blocked(db, config, slot):
            return ConverseOutcome(status=contract.STATUS_CREDENTIAL_ERROR, **plain)
        if not self._breaker.allow(config.key, now):
            return ConverseOutcome(status=contract.STATUS_DEGRADED, error_code="breaker_open", **plain)
        adapter = self.adapter(config)
        if adapter is None or not callable(getattr(adapter, "converse", None)):
            return ConverseOutcome(status=contract.STATUS_UNCONFIGURED, **plain)

        chosen = prompt_slots.resolve(db, action.prompt_slot)
        policies = policy_engine.resolve(db, action_key)
        origin = dict(prompt_slot=chosen.slot.key, prompt_source=chosen.source, prompt_version=chosen.version,
                      prompt_id=chosen.prompt_id, policy_ids=tuple(policies.ids()), **plain)

        raw_question = policies.mask(turn.user_text or "")
        question, conflict = prompt_mod.user_turn(raw_question)
        if not question:
            return ConverseOutcome(status=contract.STATUS_EMPTY, error_code="empty_question", **origin)
        ledger = _TurnLedger(conflict=conflict)
        input_truncated = len(raw_question.strip()) > prompt_mod.MAX_USER_TURN_CHARS

        tools = tuple(turn.tools or ())
        mode = MODE_SEARCH_ONLY if tools and self._tools_unsupported(db, config, slot) else MODE_TOOLS
        nonce = prompt_mod.new_nonce()

        def opening(search_only: bool):
            system = prompt_mod.assistant_system(
                role=chosen.slot.role, format_line=chosen.slot.format_line, instruction=chosen.instruction,
                grounding=chosen.slot.grounding, context_lines=tuple(turn.context_lines or ()), search_only=search_only,
            )
            turns: list = []
            for asked, answered in turn.history or ():
                past_q, c1 = prompt_mod.user_turn(policies.mask(asked or ""))
                past_a = prompt_mod.neutralize(policies.mask(answered or ""))[0].strip()
                ledger.conflict |= c1
                if past_q and past_a:
                    turns += [base.UserTurn(past_q), base.AssistantTurn(text=past_a)]
            parts = [question]
            if turn.preload:
                fenced, c2 = prompt_mod.fence(policies.mask(turn.preload)[:TOOL_RESULT_CHARS], nonce=nonce,
                                              label=LABEL_SCREEN)
                ledger.conflict |= c2
                parts.append(fenced)
            if search_only:
                found = self._fallback(turn)
                if found is not None:
                    ledger.executions.append(found)
                body = policies.mask(found.content if found is not None else '{"ok": true, "items": []}')
                fenced, c3 = prompt_mod.fence(body[:TURN_RESULT_CHARS], nonce=nonce, label=LABEL_SEARCH)
                ledger.conflict |= c3
                parts.append(fenced)
            turns.append(base.UserTurn("\n\n".join(parts)))
            return system, turns

        def done(status: str, **fields) -> ConverseOutcome:
            return ConverseOutcome(
                status=status, mode=mode, rounds=ledger.rounds, tool_calls=ledger.calls,
                tool_names=tuple(ledger.names), executions=tuple(ledger.executions),
                input_tokens=ledger.input_tokens, output_tokens=ledger.output_tokens,
                input_truncated=input_truncated, delimiter_conflict=ledger.conflict, **origin, **fields,
            )

        _progress(turn, PROGRESS_READING)
        system, turns = opening(mode == MODE_SEARCH_ONLY)
        offered = tools if mode == MODE_TOOLS else ()
        deadline = started + turn_budget_seconds(config.timeout_seconds)
        tool_rounds = 0
        while True:
            final = not offered or tool_rounds >= MAX_TOOL_ROUNDS
            left = deadline - time.monotonic()
            if left < MIN_CALL_SECONDS:
                return done(contract.STATUS_TIMEOUT, error_code="turn_budget")
            result = self._converse_call(
                config, slot, adapter, system=system, turns=tuple(turns), tools=offered,
                tool_choice=base.TOOL_CHOICE_NONE if final else base.TOOL_CHOICE_AUTO,
                max_output_tokens=action.max_output_tokens, left=left,
            )
            if result is None:
                return done(contract.STATUS_BUSY)
            ledger.rounds += 1
            ledger.tokens(result)
            if not result.ok:
                if (ledger.rounds == 1 and offered and result.error_code == UNSUPPORTED_TOOLS_CODE):
                    # 이 요금제 · 모델은 도구를 받지 않는다 - 적어 두고 대체 모드로 다시 한다(D-535).
                    self._set_tools_capability(config, slot, state_mod.TOOLS_UNSUPPORTED)
                    mode, offered = MODE_SEARCH_ONLY, ()
                    system, turns = opening(True)
                    continue
                if final and ledger.executions and result.error_kind == base.ERROR_REQUEST:
                    # 「이제 도구 없이 답하라」를 제공자가 받지 않았다 - 찾은 자료로 닫는다.
                    return done(contract.STATUS_OK, text=CLOSE_WITHOUT_ANSWER, closed_without_answer=True)
                return done(_status_for(result), error_code=result.error_code)
            if ledger.rounds == 1 and offered:
                self._note_tools_ok(db, config, slot)
            if result.tool_calls and not final:
                tool_rounds += 1
                turns.append(result.as_turn())
                turns.append(self._run_tools(result.tool_calls, turn, ledger, policies, nonce))
                _progress(turn, PROGRESS_COMPOSING)
                continue
            text = _clean(result.text)
            if text is None:
                if ledger.executions:
                    return done(contract.STATUS_OK, text=CLOSE_WITHOUT_ANSWER, closed_without_answer=True)
                return done(contract.STATUS_EMPTY)
            text = policies.limit_links(policies.mask(text), allowed_hosts=self._product_hosts())
            truncated = result.stop_reason == base.STOP_MAX_TOKENS
            cap = policies.output_cap(action.max_output_chars)
            if len(text) > cap:
                text, truncated = text[:cap], True
            return done(contract.STATUS_OK, text=text, truncated=truncated)

    def _converse_call(self, config, slot, adapter, *, system: str, turns: tuple, tools: tuple, tool_choice: str,
                       max_output_tokens: int, left: float):
        """제공자 한 번. 슬롯을 이 호출 동안만 잡는다. 슬롯을 못 잡으면 None(바쁨)."""
        lock = self._slot_lock(config)
        try:
            waiter = getattr(lock, "acquire_wait", None)
            wait = min(SLOT_WAIT_SECONDS, max(0.0, left - MIN_CALL_SECONDS))
            acquired = waiter(wait) if callable(waiter) else lock.acquire()
        except WorkerLockError:
            logger.exception("AI 동시 실행 슬롯을 잡지 못했다")
            return base.converse_failure(base.ERROR_REQUEST, "slot_unavailable")
        if not acquired:
            return None
        now = self._now()
        try:
            timeout = max(1.0, min(float(config.timeout_seconds), left - 1.0))
            try:
                result = adapter.converse(system=system, turns=turns, tools=tools, tool_choice=tool_choice,
                                          model=config.model, max_output_tokens=max_output_tokens, timeout=timeout)
            except Exception:  # noqa: BLE001 - 어댑터가 계약을 어겨도 차례는 값으로 끝난다
                logger.exception("AI 제공자 어댑터가 대화에서 예상 못 한 예외를 냈다")
                result = base.converse_failure(base.ERROR_REQUEST, "adapter_crashed")
        finally:
            lock.release()
        outcome = state_mod.RESULT_OK if result.ok else (result.error_kind or base.ERROR_TRANSIENT)
        self._record(config, slot, result=outcome, code=result.error_code, now=now, verified=False)
        if result.ok:
            self._breaker.success(config.key)
        elif result.error_kind == base.ERROR_TRANSIENT:
            self._breaker.failure(config.key, now)
        return result

    def _run_tools(self, calls, turn: TurnInput, ledger: _TurnLedger, policies, nonce: str):
        """도구 호출 묶음 → 결과 차례. **모든 호출 id 에 결과를 준다** - 상한을 넘은 호출에도 오류 결과를 준다."""
        from app.ai.assistant import results as results_mod
        from app.llm import prompt as prompt_mod

        out = []
        for index, call in enumerate(calls):
            if index >= MAX_CALLS_PER_ROUND or ledger.calls >= MAX_CALLS_PER_TURN:
                execution = results_mod.error(call.name, results_mod.ERROR_TOO_MANY_CALLS)
            elif ledger.result_chars >= TURN_RESULT_CHARS:
                execution = results_mod.error(call.name, results_mod.ERROR_BUDGET_EXHAUSTED)
            else:
                key = _call_key(call)
                execution = ledger.cache.get(key) if key is not None else None
                if execution is None:
                    execution = self._execute_tool(turn, call)
                    ledger.calls += 1
                    ledger.names.append(call.name)
                    ledger.executions.append(execution)
                    if key is not None:
                        ledger.cache[key] = execution
            content = policies.mask(execution.content)
            if execution.ok:
                # 상한은 읽어 온 자료에만 건다. 오류 결과(상한 초과 알림 포함)는 짧고, 잘리면 모델이 왜 멈췄는지 모른다.
                room = max(0, min(TOOL_RESULT_CHARS, TURN_RESULT_CHARS - ledger.result_chars))
                if len(content) > room:
                    content = content[:room] + "\n" + RESULT_CUT_NOTE
            ledger.result_chars += len(content)
            fenced, conflict = prompt_mod.fence(content, nonce=nonce, label=LABEL_TOOL_RESULT)
            ledger.conflict |= conflict
            out.append(base.ToolResult(call_id=call.id, content=fenced, is_error=not execution.ok))
        return base.ToolResultsTurn(results=tuple(out))

    def _execute_tool(self, turn: TurnInput, call):
        from app.ai.assistant import results as results_mod

        if turn.execute is None:
            return results_mod.error(call.name, results_mod.ERROR_UNAVAILABLE)
        try:
            execution = turn.execute(call)
        except Exception:  # noqa: BLE001 - 도구 하나가 터져도 차례는 이어진다
            logger.exception("도우미 도구 %s 가 예상 못 한 예외를 냈다", call.name)
            return results_mod.error(call.name, results_mod.ERROR_UNAVAILABLE)
        if not isinstance(execution, results_mod.Execution):
            return results_mod.error(call.name, results_mod.ERROR_UNAVAILABLE)
        return execution

    def _fallback(self, turn: TurnInput):
        from app.ai.assistant import results as results_mod

        if turn.fallback is None:
            return None
        try:
            found = turn.fallback()
        except Exception:  # noqa: BLE001 - 검색이 터지면 자료 없이 답한다
            logger.exception("도우미 대체 모드의 검색이 예상 못 한 예외를 냈다")
            return None
        return found if isinstance(found, results_mod.Execution) else None

    def tools_capability(self, db: Session) -> str:
        """지금 설정에서 재 둔 도구 지원(`ok` · `unsupported` · `unknown`). 화면의 「도구 호출 사용 가능」이 쓴다."""
        config = self.config(db)
        method = config.method()
        if not self._track_state or db is None or method is None or problems(config, self._secrets):
            return state_mod.TOOLS_UNKNOWN
        try:
            return state_mod.capabilities(db, config, self._secrets, secret_slot=method.secret_slot)["tools"]
        except Exception:  # noqa: BLE001 - 모르면 모른다고 한다
            logger.exception("AI 제공자 능력을 읽지 못했다")
            return state_mod.TOOLS_UNKNOWN

    def _tools_unsupported(self, db: Session, config, slot) -> bool:
        if not self._track_state or db is None:
            return False
        try:
            return state_mod.capabilities(db, config, self._secrets, secret_slot=slot)["tools"] \
                == state_mod.TOOLS_UNSUPPORTED
        except Exception:  # noqa: BLE001 - 모르면 도구를 보내 본다
            logger.exception("AI 제공자 능력을 읽지 못했다")
            return False

    def _note_tools_ok(self, db: Session, config, slot) -> None:
        """도구를 실어 보낸 첫 호출이 성공했다. 아직 모르는 상태였을 때만 적는다(차례마다 쓰지 않는다)."""
        if not self._track_state or db is None:
            return
        try:
            known = state_mod.capabilities(db, config, self._secrets, secret_slot=slot)["tools"]
        except Exception:  # noqa: BLE001
            return
        if known == state_mod.TOOLS_UNKNOWN:
            self._set_tools_capability(config, slot, state_mod.TOOLS_OK)

    def _set_tools_capability(self, config, slot, value: str) -> None:
        if self._session_factory is None or not self._track_state:
            return
        try:
            with self._session_factory() as session:
                state_mod.set_capability(session, config, self._secrets, secret_slot=slot, tools=value,
                                         now=self._now())
                session.commit()
        except Exception:  # noqa: BLE001 - 능력을 못 적어도 답은 나간다
            logger.exception("AI 제공자 능력을 적지 못했다")

    def _record_turn_usage(self, config, outcome: ConverseOutcome, *, action_key: str, actor, job_id: str | None,
                           request_id: str | None) -> None:
        """차례 하나를 사용 기록 **한 행**으로(D-537). 아무것도 시도하지 않은 차례(꺼짐, 미설정, 빈 질문)는 남기지 않는다."""
        if not self._track_state or outcome.status in (contract.STATUS_DISABLED, contract.STATUS_UNCONFIGURED):
            return
        if outcome.error_code == "empty_question":
            return
        from app.ai import usage
        from app.ai.models import USAGE_ERROR, USAGE_OK

        usage.record(
            self._session_factory, actor=usage.Actor.of(actor), action_key=action_key,
            status=USAGE_OK if outcome.ok else USAGE_ERROR, now=self._now(), provider=config.provider,
            auth_method=config.auth_method, model=config.model,
            error_code=None if outcome.ok else (outcome.error_code or outcome.status),
            input_tokens=outcome.input_tokens, output_tokens=outcome.output_tokens, latency_ms=outcome.latency_ms,
            truncated_input=outcome.input_truncated, truncated_output=outcome.truncated,
            prompt_slot=outcome.prompt_slot, prompt_version=outcome.prompt_version,
            prompt_source=outcome.prompt_source, prompt_id=outcome.prompt_id, policy_ids=list(outcome.policy_ids),
            request_id=request_id, job_id=job_id, rounds=outcome.rounds, tool_calls=outcome.tool_calls,
            tool_names=list(outcome.tool_names), mode=outcome.mode,
        )


def _with_latency(outcome: ConverseOutcome, started: float) -> ConverseOutcome:
    from dataclasses import replace

    return replace(outcome, latency_ms=int((time.monotonic() - started) * 1000))


def _progress(turn: TurnInput, label: str) -> None:
    if turn.progress is None:
        return
    try:
        turn.progress(label)
    except Exception:  # noqa: BLE001 - 진행 문구를 못 적어도 답은 나간다
        logger.exception("도우미 진행 문구를 적지 못했다")


class AiRuntime(_AssistantMixin):
    """프로세스에 하나. 설정은 들고 있지 않는다 - 호출마다 읽는다."""

    def __init__(
        self, *, settings, outbound=None, secrets=None, session_factory=None, settings_cache=None,
        clock=None, adapter_factory=None, breaker: Breaker | None = None, lock_factory=None,
        track_state: bool = True, chatgpt_tokens=None,
    ) -> None:
        self._settings = settings
        self._outbound = outbound
        self._secrets = secrets
        self._session_factory = session_factory
        self._settings_cache = settings_cache
        self._clock = clock
        # 시험이 가짜 제공자를 끼우는 자리. (제공자, 인증 방식) → 어댑터.
        self._adapter_factory = adapter_factory
        self._breaker = breaker or Breaker()
        self._lock_factory = lock_factory
        # 연결 상태를 읽고 적는가. 끄는 것은 DB 없이 프롬프트 경계만 보는 시험뿐이다.
        self._track_state = track_state
        self._models_cache: dict[tuple, tuple[float, base.ModelList]] = {}
        # 계정 연결의 토큰 관리자. 프로세스에 하나다 - 갱신 잠금은 DB 가 들고 있어 웹과 워커가 나눠 쓴다.
        self._chatgpt_tokens = chatgpt_tokens

    @property
    def secrets(self):
        return self._secrets

    @property
    def outbound(self):
        return self._outbound

    def chatgpt_tokens(self):
        """ChatGPT 계정 연결의 토큰 관리자. 처음 부를 때 만든다."""
        if self._chatgpt_tokens is None:
            from app.ai.credentials.chatgpt import ChatGptTokens
            from app.core.secret_store import SecretStore

            self._chatgpt_tokens = ChatGptTokens(
                secrets=self._secrets, store=SecretStore(self._secrets) if self._secrets is not None else None,
                outbound=self._outbound, session_factory=self._session_factory, clock=self._clock,
                settings_cache=self._settings_cache,
            )
        return self._chatgpt_tokens

    # ── 설정과 상태 ───────────────────────────────────────────────────────────

    def _now(self) -> datetime:
        if self._clock is not None:
            return self._clock.now()
        from app.core.models_base import utcnow

        return utcnow()

    def config(self, db: Session) -> RuntimeConfig:
        cache = self._settings_cache
        if cache is not None:
            try:
                cache.refresh_if_stale(db)
            except Exception:  # noqa: BLE001 - 새로 못 읽으면 가진 값으로 판정한다
                logger.exception("설정 캐시를 새로 읽지 못했다")
            return config_from_values(cache.current())
        if db is None:
            return RuntimeConfig()
        from app.settings.service import SettingsCache

        return config_from_values(SettingsCache().get_all(db))

    def adapter(self, config: RuntimeConfig):
        if self._adapter_factory is not None:
            return self._adapter_factory(config.provider, config.auth_method)
        method = config.method()
        tokens = self.chatgpt_tokens() if method is not None and method.account else None
        return base.build_adapter(config.provider, config.auth_method, outbound=self._outbound,
                                  secrets=self._secrets, tokens=tokens)

    def status(self, db: Session) -> dict:
        """화면과 초기 설정과 진단이 같은 값을 본다. 제공자에 붙지 않는다."""
        config = self.config(db)
        method = config.method()
        found = problems(config, self._secrets)
        view = state_mod.view(db, config, self._secrets, secret_slot=method.secret_slot if method else None,
                              problems=found)
        return {
            "generation_enabled": config.generation_enabled,
            "provider": config.provider,
            "auth_method": config.auth_method,
            "model": config.model,
            **view,
            # 사용자 호출이 지금 나갈 수 있는가. 일시 장애는 막지 않는다(차단기가 열린 30초만 빼고).
            "available": config.generation_enabled and not view["blocking"],
        }

    def capability(self, db: Session) -> contract.Capability:
        """`/api/ai/status` 의 생성 칸. 예전 Gateway 의 능력 보고와 같은 모양이다."""
        info = self.status(db)
        if not info["generation_enabled"]:
            return contract.unavailable(contract.CAP_GENERATE, contract.STATUS_DISABLED, model=info["model"])
        if info["state"] == state_mod.STATE_UNCONFIGURED:
            return contract.unavailable(contract.CAP_GENERATE, contract.STATUS_UNCONFIGURED,
                                        detail=" ".join(info["problems"]))
        if info["blocking"]:
            return contract.unavailable(contract.CAP_GENERATE, contract.STATUS_CREDENTIAL_ERROR,
                                        model=info["model"])
        return contract.available(contract.CAP_GENERATE, model=info["model"], detail=info["label"])

    # ── 생성 ─────────────────────────────────────────────────────────────────

    def generate(self, db: Session | None, *, action_key: str, data: str, actor=None,
                 verify: bool = False, job_id: str | None = None,
                 request_id: str | None = None) -> contract.GenerateResult:
        """액션의 지시문 + **신뢰하지 않는 내용**(`data`) → 문장. 예외를 올리지 않는다.

        지시문은 부른 쪽이 넘기지 않는다 - 액션의 사용처에서 런타임이 고른다(발행본이 있으면 발행본, D-518).

        ``verify`` 는 관리자의 연결 확인이다. 생성이 꺼져 있거나 막힌 상태여도 보낸다 - 막힌 것을 고치는 중인 사람이
        확인 단추를 누르는 것이다. ``db`` 가 없으면(세션 없이 부르는 자리) 제 짧은 세션으로 설정을 읽는다.
        ``actor`` 는 요청한 사람(`User`)이다. 없으면 시스템의 호출로 기록한다(연결 확인, 주기 작업).
        """
        if db is None and self._session_factory is not None:
            with self._session_factory() as session:
                config = self.config(session)
                result = self._generate(session, config, action_key=action_key, data=data, verify=verify)
        else:
            config = self.config(db)
            result = self._generate(db, config, action_key=action_key, data=data, verify=verify)
        self._record_usage(config, result, action_key=action_key, actor=None if verify else actor, job_id=job_id,
                           request_id=request_id)
        return result

    def _record_usage(self, config: RuntimeConfig, result: contract.GenerateResult, *, action_key: str, actor,
                      job_id: str | None, request_id: str | None) -> None:
        """호출 한 번을 사용 기록에 남긴다. 아무것도 시도하지 않은 호출(꺼짐, 미설정)은 남기지 않는다."""
        if not self._track_state or result.status in (contract.STATUS_DISABLED, contract.STATUS_UNCONFIGURED):
            return
        from app.ai import usage
        from app.ai.models import USAGE_ERROR, USAGE_OK

        usage.record(
            self._session_factory, actor=usage.Actor.of(actor), action_key=action_key,
            status=USAGE_OK if result.ok else USAGE_ERROR, now=self._now(), provider=config.provider,
            auth_method=config.auth_method, model=config.model,
            error_code=None if result.ok else (result.error_code or result.status),
            input_tokens=result.input_tokens, output_tokens=result.output_tokens, latency_ms=result.latency_ms,
            truncated_input=result.input_truncated, truncated_output=result.output_truncated,
            prompt_slot=result.prompt_slot, prompt_version=result.prompt_version, prompt_source=result.prompt_source,
            prompt_id=result.prompt_id, policy_ids=list(result.policy_ids), request_id=request_id, job_id=job_id,
        )

    def _generate(self, db: Session, config: RuntimeConfig, *, action_key: str, data: str,
                  verify: bool) -> contract.GenerateResult:
        action = actions_mod.get_action(action_key)
        method = config.method()
        slot = method.secret_slot if method else None
        if not verify and not config.generation_enabled:
            return contract.GenerateResult(status=contract.STATUS_DISABLED, model=config.model)
        if problems(config, self._secrets):
            return contract.GenerateResult(status=contract.STATUS_UNCONFIGURED, model=config.model)
        now = self._now()
        if not verify:
            if self._track_state and db is not None and self._blocked(db, config, slot):
                return contract.GenerateResult(status=contract.STATUS_CREDENTIAL_ERROR, model=config.model)
            if not self._breaker.allow(config.key, now):
                return contract.GenerateResult(status=contract.STATUS_DEGRADED, model=config.model,
                                               error_code="breaker_open")
        adapter = self.adapter(config)
        if adapter is None:
            return contract.GenerateResult(status=contract.STATUS_UNCONFIGURED, model=config.model)

        from app.ai.policy import engine as policy_engine
        from app.ai.prompts import service as prompt_slots
        from app.llm import prompt as prompt_mod

        chosen = prompt_slots.resolve(db, action.prompt_slot)
        # 연결 확인은 관리 동작이라 정책을 걸지 않는다. 정책을 못 읽으면 아무것도 걸지 않는다(엔진이 로그를 남긴다).
        policies = policy_engine.NONE if verify else policy_engine.resolve(db, action_key)
        data = policies.mask(data)
        origin = dict(prompt_slot=chosen.slot.key, prompt_source=chosen.source, prompt_version=chosen.version,
                      prompt_id=chosen.prompt_id, policy_ids=tuple(policies.ids()))
        try:
            built = prompt_mod.build_prompt(
                body=data, nonce=prompt_mod.new_nonce(), task=chosen.instruction, role=chosen.slot.role,
                format_line=chosen.slot.format_line, grounding=chosen.slot.grounding,
            )
        except prompt_mod.EmptyBodyError:
            return contract.GenerateResult(status=contract.STATUS_EMPTY, model=config.model, **origin)

        lock = self._slot_lock(config)
        try:
            acquired = lock.acquire()
        except WorkerLockError:
            # 슬롯 파일을 못 쓰는 환경이다(데이터 디렉터리 권한). 웹 요청이 500 이 되지 않게 값으로 접는다.
            logger.exception("AI 동시 실행 슬롯을 잡지 못했다")
            return contract.GenerateResult(status=contract.STATUS_FAILED, model=config.model,
                                           error_code="slot_unavailable")
        if not acquired:
            return contract.GenerateResult(status=contract.STATUS_BUSY, model=config.model)
        started = time.monotonic()
        try:
            timeout = min(config.timeout_seconds, VERIFY_TIMEOUT_SECONDS) if verify else config.timeout_seconds
            try:
                result = adapter.generate(
                    system=built.system, user=built.user, model=config.model,
                    max_output_tokens=action.max_output_tokens, timeout=float(timeout),
                )
            except Exception:  # noqa: BLE001 - 어댑터가 계약을 어겨도 부른 쪽은 값을 받는다
                # 우리 코드의 결함이지 제공자의 장애가 아니다 - 연결 상태를 바꾸지 않는다.
                logger.exception("AI 제공자 어댑터가 예상 못 한 예외를 냈다")
                result = base.failure(base.ERROR_REQUEST, "adapter_crashed")
        finally:
            lock.release()
        latency_ms = int((time.monotonic() - started) * 1000)

        outcome = state_mod.RESULT_OK if result.ok else (result.error_kind or base.ERROR_TRANSIENT)
        self._record(config, slot, result=outcome, code=result.error_code, now=now, verified=verify)
        if result.ok:
            self._breaker.success(config.key)
        elif result.error_kind == base.ERROR_TRANSIENT:
            self._breaker.failure(config.key, now)

        common = dict(
            model=config.model, delimiter_conflict=built.delimiter_conflict, input_tokens=result.input_tokens,
            output_tokens=result.output_tokens, provider=config.provider, latency_ms=latency_ms,
            input_truncated=built.truncated, **origin,
        )
        if not result.ok:
            return contract.GenerateResult(status=_status_for(result), error_code=result.error_code,
                                           truncated=built.truncated, **common)
        text = _clean(result.text)
        if text is None:
            return contract.GenerateResult(status=contract.STATUS_EMPTY, truncated=built.truncated, **common)
        text = policies.limit_links(policies.mask(text), allowed_hosts=self._product_hosts())
        truncated = built.truncated
        cap = policies.output_cap(action.max_output_chars)
        if len(text) > cap:
            if action.json_output:
                # 자른 JSON 은 쓸 수 없다. 조용히 자르면 부른 쪽의 파서가 원인 모를 실패를 낸다.
                return contract.GenerateResult(status=contract.STATUS_FAILED, error_code="output_too_long",
                                               truncated=True, output_truncated=True, **common)
            text, truncated = text[:cap], True
            return contract.GenerateResult(status=contract.STATUS_OK, text=text, truncated=truncated,
                                           output_truncated=True, **common)
        return contract.GenerateResult(status=contract.STATUS_OK, text=text, truncated=truncated, **common)

    def _product_hosts(self) -> set[str]:
        """제품 자신의 호스트. 응답 제한 정책이 이 호스트로 가는 링크는 그대로 둔다."""
        from urllib.parse import urlsplit

        base = getattr(self._settings, "app_base_url", None) or ""
        host = (urlsplit(base).hostname or "").lower() if isinstance(base, str) else ""
        return {host} if host else set()

    def _blocked(self, db: Session, config: RuntimeConfig, slot: str | None) -> bool:
        """저장된 연결 상태가 막힌 상태인가. 상태를 못 읽으면 막지 않는다 - 판정 실패로 답을 잃는 쪽이 더 나쁘다."""
        try:
            return state_mod.view(db, config, self._secrets, secret_slot=slot, problems=[])["blocking"]
        except Exception:  # noqa: BLE001
            logger.exception("AI 연결 상태를 읽지 못했다")
            return False

    def _slot_lock(self, config: RuntimeConfig):
        if self._lock_factory is not None:
            return self._lock_factory(config)
        return concurrency.concurrency_lock(
            getattr(self._settings, "data_dir", "var"),
            timeout_seconds=config.timeout_seconds, max_concurrency=config.max_concurrency,
        )

    def record(self, config: RuntimeConfig, *, result: str, code: str | None, now: datetime) -> None:
        """호출 밖에서 알게 된 결과를 연결 상태에 적는다(주기 확인, 토큰 갱신). 제 짧은 세션으로 적는다."""
        method = config.method()
        self._record(config, method.secret_slot if method else None, result=result, code=code, now=now,
                     verified=False)

    def check_credentials(self, config: RuntimeConfig) -> base.ModelList:
        """자격을 가볍게 확인한다 - 모델 목록을 한 번 묻는다(생성하지 않는다). 기억해 둔 목록을 쓰지 않는다."""
        adapter = self.adapter(config)
        if adapter is None:
            return base.ModelList(ok=False, error_kind=base.ERROR_CONFIG, error_code="unknown_provider")
        try:
            return adapter.list_models(timeout=10.0)
        except Exception:  # noqa: BLE001 - 어댑터 결함은 연결 상태를 바꾸지 않는다
            logger.exception("AI 제공자 어댑터가 모델 목록에서 예상 못 한 예외를 냈다")
            return base.ModelList(ok=False, error_kind=base.ERROR_REQUEST, error_code="adapter_crashed")

    def _record(self, config: RuntimeConfig, slot: str | None, *, result: str, code: str | None,
                now: datetime, verified: bool) -> None:
        if self._session_factory is None or not self._track_state:
            return
        try:
            with self._session_factory() as session:
                state_mod.record(session, config, self._secrets, secret_slot=slot, result=result, code=code,
                                 now=now, verified=verified)
                session.commit()
        except Exception:  # noqa: BLE001 - 상태를 못 적어도 답은 나간다
            logger.exception("AI 연결 상태를 적지 못했다")

    # ── 관리자 동작 ───────────────────────────────────────────────────────────

    def verify(self, db: Session) -> dict:
        """연결 확인 - 실제 생성 경로로 아주 짧은 답을 한 번 받는다. 결과가 연결 상태에 적힌다.

        **설정을 캐시가 아니라 DB 에서 다시 읽는다.** 연결 확인은 관리자가 방금 저장한 설정을 재는 동작인데, 확인이 도는
        워커는 웹과 다른 프로세스라 설정 캐시가 따로 있고 그 캐시는 30초(TTL)마다 새로 읽는다. 그래서 저장하고 곧바로
        「연결 확인」을 누르면 워커가 저장 전 값으로 확인해 「AI 제공자를 아직 고르지 않았습니다」라고 거짓으로 답했다
        (Release 리허설 실측). 확인은 드문 동작이라 DB 한 번 더 읽는 값이 싸다.
        """
        cache = self._settings_cache
        if cache is not None:
            try:
                # 짧은 새 세션으로 읽는다. 부른 쪽(잡)의 세션에 트랜잭션을 열어 두면 그 잡이 실패로 끝날 때 함께 되감긴다.
                if self._session_factory is not None:
                    with self._session_factory() as fresh:
                        cache.load(fresh)
                elif db is not None:
                    cache.load(db)
            except Exception:  # noqa: BLE001 - 새로 못 읽으면 가진 값으로 확인한다
                logger.exception("연결 확인 전에 설정을 새로 읽지 못했다")
        config = self.config(db)
        found = problems(config, self._secrets)
        if found:
            return {"ok": False, "status": contract.STATUS_UNCONFIGURED, "message": found[0]}
        result = self.generate(db, action_key=actions_mod.CONNECTION_TEST, data=VERIFY_DATA, verify=True)
        if result.ok:
            return {"ok": True, "status": result.status, "message": "AI 제공자에 연결해 답을 받았습니다."}
        reason = state_mod.reason_text(result.error_code) if result.error_code else None
        return {"ok": False, "status": result.status, "message": reason or result.notice or contract.FALLBACK_NOTICE}

    def list_models(self, db: Session, *, provider: str, auth_method: str, ttl_seconds: float = 600) -> base.ModelList:
        """제공자의 모델 목록. 10분 동안 기억한다 - 화면을 열 때마다 제공자에 묻지 않는다."""
        config = RuntimeConfig(provider=provider, auth_method=auth_method)
        adapter = self.adapter(config)
        if adapter is None:
            return base.ModelList(ok=False, error_kind=base.ERROR_CONFIG, error_code="unknown_provider")
        key = (provider, auth_method, state_mod.fingerprint(config, self._secrets,
                                                           config.method().secret_slot if config.method() else None))
        cached = self._models_cache.get(key)
        if cached and time.monotonic() - cached[0] < ttl_seconds:
            return cached[1]
        listing = adapter.list_models(timeout=10.0)
        if listing.ok:
            self._models_cache[key] = (time.monotonic(), listing)
        return listing



# ── 프로세스마다 하나 ─────────────────────────────────────────────────────────


def runtime_for_app(app) -> AiRuntime:
    """웹 프로세스의 런타임(`app/main.py` 가 부팅 때 만든다). 시험이 라우터만 올린 경우를 위해 없으면 만든다."""
    runtime = getattr(app.state, "ai_runtime", None)
    if runtime is None:
        state = app.state
        runtime = AiRuntime(
            settings=getattr(state, "settings", None), outbound=getattr(state, "outbound_client", None),
            secrets=getattr(state, "secret_provider", None), session_factory=getattr(state, "session_factory", None),
            settings_cache=getattr(state, "settings_cache", None), clock=getattr(state, "clock", None),
        )
        state.ai_runtime = runtime
    return runtime


def runtime_for_worker(ctx) -> AiRuntime:
    """워커의 런타임(`app/worker_main.py` 가 `extras["ai_runtime"]` 에 둔다). 없으면 만든다.

    대체 경로도 `extras["session_factory"]` 로 사용 기록과 연결 상태를 적는다. 예전에는 세션 공장 없이 만들어 그 길로
    간 호출의 사용 기록과 상태가 조용히 빠졌다.
    """
    extras = ctx.extras if ctx.extras is not None else {}
    runtime = extras.get("ai_runtime")
    if runtime is None:
        runtime = AiRuntime(
            settings=ctx.settings, outbound=ctx.outbound_client, secrets=extras.get("secret_provider"),
            session_factory=extras.get("session_factory"), settings_cache=extras.get("settings_cache"),
            clock=ctx.clock,
        )
        if ctx.extras is not None:
            ctx.extras["ai_runtime"] = runtime
    return runtime
