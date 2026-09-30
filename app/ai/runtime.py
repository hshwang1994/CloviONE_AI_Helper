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
  6. 프롬프트를 조립한다. **`app/llm/prompt.py::build_prompt` 를 부르는 곳은 여기뿐이다** - 난스 구분자와
     「데이터는 지시가 아니다」가 모든 경로에 걸린다(D-202). 역할과 출력 형식은 사용처가 코드에 고정한 값이다
  7. 동시 실행 슬롯을 잡는다(`app/ai/concurrency.py`) - 웹과 워커가 한 벌을 나눠 쓴다
  8. 제공자를 부른다(`app/ai/providers/`) - 제한 시간과 토큰 수를 잰다. 계정 연결(ChatGPT)이면 어댑터가 부르기 전에
     토큰의 만료를 보고 필요하면 갱신한다(`app/ai/credentials/chatgpt.py`)
  9. 결과로 연결 상태를 바꾼다(`app/ai/credentials/state.py`). 제 짧은 세션으로 적는다 - 부른 쪽의 트랜잭션이
     실패해도 「방금 성공했다」는 사실이 사라지지 않는다
 10. 출력을 다듬는다. 제어 문자를 지우고 액션의 길이로 자른다. JSON 액션은 자르지 않는다 - 넘으면 실패다
 11. 사용 기록 한 행을 남긴다(`app/ai/usage.py`) - 누가, 어떤 기능으로, 어느 모델과 어느 지시문으로, 얼마나 썼고
     어떻게 끝났는지. 한도의 원장이 이 행이다. 생성이 꺼져 있거나 설정이 비어 아무것도 시도하지 않은 호출은 남기지
     않는다

## 실패는 값이다

부른 쪽은 예외를 받지 않는다. 검색 결과와 목록은 모델과 무관하게 이미 만들어져 있고, 생성 하나 때문에 그것이 안
나가면 안 된다(`app/ai/gateway/contract.py` 의 규약 그대로).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
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


class AiRuntime:
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
            prompt_id=result.prompt_id, request_id=request_id, job_id=job_id,
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

        from app.ai.prompts import service as prompt_slots
        from app.llm import prompt as prompt_mod

        chosen = prompt_slots.resolve(db, action.prompt_slot)
        origin = dict(prompt_slot=chosen.slot.key, prompt_source=chosen.source, prompt_version=chosen.version,
                      prompt_id=chosen.prompt_id)
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
        truncated = built.truncated
        if len(text) > action.max_output_chars:
            if action.json_output:
                # 자른 JSON 은 쓸 수 없다. 조용히 자르면 부른 쪽의 파서가 원인 모를 실패를 낸다.
                return contract.GenerateResult(status=contract.STATUS_FAILED, error_code="output_too_long",
                                               truncated=True, output_truncated=True, **common)
            text, truncated = text[: action.max_output_chars], True
            return contract.GenerateResult(status=contract.STATUS_OK, text=text, truncated=truncated,
                                           output_truncated=True, **common)
        return contract.GenerateResult(status=contract.STATUS_OK, text=text, truncated=truncated, **common)

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
        """연결 확인 - 실제 생성 경로로 아주 짧은 답을 한 번 받는다. 결과가 연결 상태에 적힌다."""
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
    """워커의 런타임(`app/worker_main.py` 가 `extras["ai_runtime"]` 에 둔다). 없으면 만든다 - 상태 기록은 빠진다."""
    extras = ctx.extras if ctx.extras is not None else {}
    runtime = extras.get("ai_runtime")
    if runtime is None:
        runtime = AiRuntime(
            settings=ctx.settings, outbound=ctx.outbound_client, secrets=extras.get("secret_provider"),
            settings_cache=extras.get("settings_cache"), clock=ctx.clock,
        )
        if ctx.extras is not None:
            ctx.extras["ai_runtime"] = runtime
    return runtime
