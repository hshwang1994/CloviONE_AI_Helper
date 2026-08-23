"""생성 Adapter — `app/llm` 의 CLI/API 백엔드 하나를 감싼다 (D-201).

## 왜 `app/llm` 을 지우지 않는가

지우면 주간 리포트 요약이 그날로 멈춘다. 두 벌로 두면 프롬프트 방어가 한쪽에만 걸린다 —
D-202 가 지적한 상태가 바로 그것이다. 그래서 **감싼다**: 프로세스를 띄우는 자리도,
도구 차단도, 상태 어휘도 전부 `app/llm/cli_backend.py` 한 곳에 그대로 둔다.

`/usr/bin/claude` 는 **Adapter 하나일 뿐이다.** API 로 바꾸는 것은 `LLM_BACKEND=api`
한 줄이고, 그때 이 파일은 안 고친다 — `provider.select_backend()` 가 고른 것을 받는다.

## 이 Adapter 는 원문을 안 본다

`generate(system=, user=)` 만 받는다. 난스 구분자와 `neutralize()` 는 이미
`contract.Gateway.generate()` 가 걸었다. 여기서 다시 감싸면 구분자가 중첩되고,
안 감싸는 경로가 하나 생기면 방어가 통째로 없다.
"""

from __future__ import annotations

from app.ai.gateway import contract
from app.llm import provider as llm_provider

#: `app/llm` 의 상태 → Gateway 의 상태. 대부분 같은 글자이고, `missing_cli` 만
#: Gateway 어휘의 `runtime_missing` 으로 옮긴다 — 화면이 「실행 환경이 없다」를
#: 임베딩 런타임과 같은 문장으로 말할 수 있어야 한다.
_STATUS_MAP = {
    llm_provider.STATUS_OK: contract.STATUS_OK,
    llm_provider.STATUS_DISABLED: contract.STATUS_DISABLED,
    llm_provider.STATUS_NOT_LOGGED_IN: contract.STATUS_NOT_LOGGED_IN,
    llm_provider.STATUS_TIMEOUT: contract.STATUS_TIMEOUT,
    llm_provider.STATUS_BUSY: contract.STATUS_BUSY,
    llm_provider.STATUS_MISSING_CLI: contract.STATUS_RUNTIME_MISSING,
    llm_provider.STATUS_UNCONFIGURED: contract.STATUS_UNCONFIGURED,
    llm_provider.STATUS_EMPTY: contract.STATUS_EMPTY,
    llm_provider.STATUS_FAILED: contract.STATUS_FAILED,
}


class LlmBackendAdapter(contract.GenerateAdapter):
    """`app/llm` 백엔드 하나 = Gateway 의 생성 능력 하나."""

    def __init__(self, *, backend, config: llm_provider.LlmConfig) -> None:
        self._backend = backend
        self._config = config
        self.name = f"llm:{getattr(backend, 'name', '?')}"
        self.model = config.model or ""

    def capability(self) -> contract.Capability:
        if not self._config.enabled:
            return contract.unavailable(contract.CAP_GENERATE, contract.STATUS_DISABLED)
        # 🔴 모델 이름이 없으면 「설정 안 됨」이다. 기본값으로 메우지 않는다(P-19).
        model = self._config.api_model or self._config.model
        if not model:
            return contract.unavailable(
                contract.CAP_GENERATE, contract.STATUS_UNCONFIGURED,
                detail="모델 이름을 설정하십시오.",
            )
        # 「로그인되어 있는가」는 여기서 안 묻는다. 그것을 물으려면 프로세스를 띄워야 하고,
        # `capabilities()` 는 화면이 그릴 때마다 불린다. 실제 상태는 부른 결과가 말한다.
        return contract.available(contract.CAP_GENERATE, model=model)

    def generate(self, *, system: str, user: str) -> contract.GenerateResult:
        result = self._backend.run(system=system, user=user)
        return contract.GenerateResult(
            status=_STATUS_MAP.get(result.status, contract.STATUS_FAILED),
            model=self.model,
            text=result.text,
        )
