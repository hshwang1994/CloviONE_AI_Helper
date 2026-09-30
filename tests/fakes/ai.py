"""AI 생성 시험의 가짜 — **진짜 런타임에 가짜 제공자 하나만 끼운다** (D-515).

예전 시험들은 Gateway 에 가짜 생성 어댑터를 끼웠다. 이제 생성은 `app/ai/runtime.py::AiRuntime` 하나가 맡으므로
런타임 전체(설정 읽기, 연결 상태, 프롬프트 조립, 동시 실행 슬롯, 출력 정제)를 그대로 두고 제공자 자리만 바꾼다.
그래야 시험이 지나는 길이 제품이 지나는 길과 같다.

    adapter = ScriptedAdapter(["첫 답", "둘째 답"])
    install_runtime(app, adapter)                    # 설정을 켜고 키 파일을 두고 런타임을 갈아 끼운다
    ...
    adapter.calls[0]["user"]                          # 제공자가 받은 것(조립이 끝난 프롬프트)
"""

from __future__ import annotations

from app.ai.providers import base

DEFAULT_MODEL = "test-model"
TEST_KEY = "sk-ant-test-" + "k" * 24


class ScriptedAdapter:
    """부를 때마다 다음 답을 준다. 답은 글자이거나 `ProviderResult` 다. 목록이 끝나면 마지막 답을 되풀이한다."""

    provider = base.PROVIDER_ANTHROPIC
    auth_method = base.AUTH_API_KEY

    def __init__(self, replies=None, *, models=None) -> None:
        self.replies = list(replies if replies is not None else ["답입니다."])
        self.models = list(models or [])
        self.calls: list[dict] = []

    def generate(self, *, system, user, model, max_output_tokens, timeout):
        self.calls.append({"system": system, "user": user, "model": model,
                           "max_output_tokens": max_output_tokens, "timeout": timeout})
        index = min(len(self.calls) - 1, len(self.replies) - 1)
        reply = self.replies[index]
        if isinstance(reply, base.ProviderResult):
            return reply
        if isinstance(reply, Exception):
            raise reply
        return base.success(str(reply), input_tokens=10, output_tokens=5)

    def list_models(self, *, timeout):
        return base.ModelList(ok=True, models=tuple({"id": m, "label": m} for m in self.models))


def timeout_failure():
    return base.failure(base.ERROR_TRANSIENT, "timeout")


def auth_failure():
    return base.failure(base.ERROR_AUTH, "http_401", http_status=401)


def empty_reply():
    return base.ProviderResult(ok=False, error_kind=base.ERROR_EMPTY, error_code="empty")


def configure_ai(app, *, enabled=True, model=DEFAULT_MODEL, key=TEST_KEY) -> None:
    """AI 설정을 「채워진 설치」로 만든다 - 제공자, 인증 방식, 모델, 켜짐, 그리고 키 파일."""
    from app.settings.service import apply_setting

    if key is not None:
        (app.state.settings.secrets_dir / "ai.anthropic.api_key").write_text(key, encoding="utf-8")
    with app.state.session_factory() as db:
        for name, value in {
            "ai_provider": base.PROVIDER_ANTHROPIC, "ai_auth_method": base.AUTH_API_KEY, "ai_model": model,
            "ai_generation_enabled": enabled,
        }.items():
            apply_setting(db, app.state.settings_cache, key=name, value=value, updated_by=None,
                          now=app.state.clock.now())
        db.commit()


def install_runtime(app, adapter=None, *, enabled=True, model=DEFAULT_MODEL, lock_factory=None):
    """설정을 채우고, 가짜 제공자를 끼운 진짜 런타임을 `app.state.ai_runtime` 에 둔다. 그 런타임을 돌려준다."""
    from app.ai.runtime import AiRuntime

    configure_ai(app, enabled=enabled, model=model)
    adapter = adapter if adapter is not None else ScriptedAdapter()
    runtime = AiRuntime(
        settings=app.state.settings, outbound=app.state.outbound_client, secrets=app.state.secret_provider,
        session_factory=app.state.session_factory, settings_cache=app.state.settings_cache, clock=app.state.clock,
        adapter_factory=lambda provider, auth_method: adapter, lock_factory=lock_factory,
    )
    app.state.ai_runtime = runtime
    return runtime


class BusyLock:
    """슬롯이 전부 차 있는 상태."""

    def acquire(self):
        return False

    def release(self):
        pass


class FreeLock:
    """언제나 잡히는 슬롯 - 파일 락 없이 도는 시험용."""

    def acquire(self):
        return True

    def release(self):
        pass


class _Cache:
    """설정 캐시의 대역. 값은 시험이 정한다."""

    def __init__(self, values: dict) -> None:
        self._values = dict(values)

    def refresh_if_stale(self, db) -> None:
        pass

    def current(self) -> dict:
        return dict(self._values)


class _Secrets:
    """비밀 칸의 대역 - 키가 저장돼 있다고 답한다."""

    def status(self, name: str) -> str:
        return "configured"


def offline_runtime(adapter, *, enabled=True, model=DEFAULT_MODEL, lock_factory=None):
    """DB 도 앱도 없이 도는 런타임. 프롬프트 경계처럼 **제공자가 무엇을 받는가**만 보는 시험이 쓴다."""
    from types import SimpleNamespace

    from app.ai.runtime import AiRuntime

    values = {
        "ai_generation_enabled": enabled, "ai_provider": base.PROVIDER_ANTHROPIC, "ai_auth_method": base.AUTH_API_KEY,
        "ai_model": model, "ai_timeout_seconds": 60, "ai_max_concurrency": 2,
    }
    return AiRuntime(
        settings=SimpleNamespace(data_dir="var"), secrets=_Secrets(), settings_cache=_Cache(values),
        adapter_factory=lambda provider, auth_method: adapter,
        lock_factory=lock_factory or (lambda config: FreeLock()), track_state=False,
    )
