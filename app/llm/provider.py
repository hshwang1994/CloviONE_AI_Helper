"""백엔드 인터페이스 + 어느 백엔드를 쓸지 고르기 + **결과 어휘** (§L).

## 왜 인터페이스를 두는가

지금 기본은 서버에 로그인된 구독 CLI 다(비용 때문에 그렇게 하기로 했다). 하지만 약관이나
rate limit 때문에 API 로 돌아가야 할 수 있고, 그때 **호출부를 고치면 안 된다.** 주간 리포트는
"요약을 달라" 고만 말하고, 그것이 CLI 인지 API 인지 몰라야 한다.

전환은 설정 한 줄이다: `LLM_BACKEND=api`. 다만 API 로 나가는 호스트는 SSRF allowlist 가
따로 승인한다(불변 §2-2). 스위치 하나로 새 바깥 호출이 열리지 않는 것이 이 저장소의 규칙이라,
그 두 번째 줄은 일부러 남겨 뒀다.

## 결과 어휘를 여기에 모으는 이유

화면이 "이 요약이 규칙인지 LLM 인지" 를 말해야 한다(주간 리포트 응답에 이미 `source` 자리가
있다). 그 문자열이 백엔드마다 따로 있으면 언젠가 갈라진다. 그래서 상태 목록과 **사용자에게
보이는 한국어 문구**를 한 곳에 둔다.

🔴 사용자에게 보이는 문구는 **우리가 쓴 것만** 나간다. CLI 나 API 가 준 오류 문자열을 그대로
옮기지 않는다. 이유가 셋이다: 내부 주소나 토큰 이름이 섞여 나올 수 있고, 영어라 읽히지
않고, 실제로 CLI 의 미로그인 메시지에는 이 저장소가 화면에서 쓰지 않기로 한 글자가 들어
있다(scripts/check_user_text.py 가 잡는 그 글자다).

## 설정을 어디서 읽는가

`Settings` 에 `llm_*` 필드가 생기면 그것이 이긴다. 아직 없으면 환경변수를 본다. 순서를
이렇게 잡은 이유: 설정 객체는 테스트가 명시적으로 주입할 수 있어 결정적이고, 환경변수는
그 필드가 생기기 전에도 운영자가 켤 수 있는 통로다. 둘 다 없으면 **꺼진 상태**가 기본이다
(fail-closed). AI 기능을 기본 ON 으로 두는 관례가 이 저장소에 없다 - game_ai_enabled 와
assistant_narrative_enabled 도 전부 기본 OFF 다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

BACKEND_CLI = "cli"
BACKEND_API = "api"

# 주간 리포트 응답의 `source` 와 **같은 어휘**다(app/projects/models.py::REPORT_SOURCE_*).
# 여기서 새 문자열을 만들면 화면이 두 어휘를 분기하게 된다.
SOURCE_RULE = "rule"
SOURCE_LLM = "llm"

STATUS_OK = "ok"
STATUS_DISABLED = "disabled"
STATUS_NOT_LOGGED_IN = "not_logged_in"
STATUS_TIMEOUT = "timeout"
STATUS_BUSY = "busy"
STATUS_MISSING_CLI = "missing_cli"
STATUS_UNCONFIGURED = "unconfigured"
STATUS_EMPTY = "empty"
STATUS_FAILED = "failed"

# 상태 → 화면에 그대로 실을 수 있는 한 줄. 전부 "그래서 지금 무엇을 보고 있는가" 로 끝난다.
# 사용자가 알아야 하는 것은 실패의 종류가 아니라 **지금 보는 숫자가 무엇으로 만들어졌는가**다.
NOTICES: dict[str, str] = {
    STATUS_DISABLED: "AI 요약이 꺼져 있어 규칙으로 만든 요약을 보여줍니다.",
    STATUS_NOT_LOGGED_IN: (
        "서버의 AI 명령줄 도구에 로그인되어 있지 않아 규칙으로 만든 요약을 보여줍니다."
    ),
    STATUS_TIMEOUT: "AI 요약이 제한 시간 안에 끝나지 않아 규칙으로 만든 요약을 보여줍니다.",
    STATUS_BUSY: "다른 AI 요약이 진행 중이라 규칙으로 만든 요약을 보여줍니다.",
    STATUS_MISSING_CLI: "서버에서 AI 명령줄 도구를 찾지 못해 규칙으로 만든 요약을 보여줍니다.",
    STATUS_UNCONFIGURED: "AI 요약이 아직 설정되지 않아 규칙으로 만든 요약을 보여줍니다.",
    STATUS_EMPTY: "AI 요약이 비어 있어 규칙으로 만든 요약을 보여줍니다.",
    STATUS_FAILED: "AI 요약을 만들지 못해 규칙으로 만든 요약을 보여줍니다.",
}

# 목록에 없는 상태가 들어와도 화면이 비지 않게. "무슨 일인지 모른다" 를 숨기지 않는다.
FALLBACK_NOTICE = "AI 요약을 쓸 수 없어 규칙으로 만든 요약을 보여줍니다."

# 🔴 **모델 이름의 기본값을 제품이 정하지 않는다** (D-201 · P-19).
# 예전에는 여기에 모델 이름 하나가 박혀 있었다. 그 한 줄이 「설정에서 모델을 지운다」와
# 「그 모델을 쓴다」를 같은 상태로 만들었다 — 운영자가 화면에서 모델 칸을 비우면 꺼지는
# 것이 아니라 우리가 정해 둔 이름으로 조용히 돌았다. 모델은 구독·약관·가격이 정하는
# 운영 선택이라 제품이 대신 고를 자리가 아니다.
#
# 비어 있으면 **설정 안 됨**이다(fail-closed). 백엔드가 그 사실을 값으로 돌려주고
# 화면이 "AI 요약이 아직 설정되지 않아 …" 를 말한다.
DEFAULT_MODEL = ""
DEFAULT_EXECUTABLE = "claude"
# 주간 리포트는 사람이 화면 앞에서 기다리는 것이 아니라 워커가 만든다. 그래서 채팅(25초)보다
# 넉넉하다. 그래도 무한은 아니다 - 상한은 cli_backend.MAX_TIMEOUT_SECONDS 가 강제한다.
DEFAULT_TIMEOUT_SECONDS = 120

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


@dataclass(frozen=True)
class LlmConfig:
    """한 번 정해지면 안 바뀐다(§2-7). 기본값은 전부 '꺼짐, CLI, 짧은 타임아웃'이다."""

    enabled: bool = False
    backend: str = BACKEND_CLI
    #: 비어 있으면 「안 정했다」이고, 그 상태로는 백엔드를 부르지 않는다 (P-19).
    model: str = DEFAULT_MODEL
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    executable: str = DEFAULT_EXECUTABLE
    # API 전환용. 비어 있으면 API 백엔드는 스스로 '설정 안 됨'을 돌려준다.
    api_url: str = ANTHROPIC_MESSAGES_URL
    api_model: str = ""
    api_secret_ref: str = ""
    api_max_tokens: int = 1024


@dataclass(frozen=True)
class LlmResult:
    """백엔드가 돌려주는 것의 전부. **예외가 아니라 값으로** 실패를 돌려준다.

    이유는 `app/assistant/narrate.py` 와 같다: 문장이 없어도 숫자와 목록은 그대로 나가야
    한다. 실패를 예외로 올리면 부르는 쪽이 감싸는 것을 잊는 날 워커 루프가 통째로 죽는다.
    """

    status: str
    backend: str
    text: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK and bool(self.text)

    @property
    def source(self) -> str:
        """화면과 저장 행이 쓰는 어휘. 실패는 전부 규칙 기반이다."""
        return SOURCE_LLM if self.ok else SOURCE_RULE

    @property
    def notice(self) -> str | None:
        """성공이면 None. 실패면 **왜 규칙 요약을 보는지** 한 줄."""
        if self.ok:
            return None
        return NOTICES.get(self.status, FALLBACK_NOTICE)

    def as_dict(self) -> dict:
        """주간 리포트 응답에 그대로 합칠 수 있는 모양(`source` 자리가 이미 있다)."""
        return {
            "source": self.source,
            "llm_summary": self.text if self.ok else None,
            "llm_notice": self.notice,
        }


def ok(text: str, backend: str) -> LlmResult:
    return LlmResult(status=STATUS_OK, backend=backend, text=text)


def failure(status: str, backend: str) -> LlmResult:
    return LlmResult(status=status, backend=backend, text=None)


class LlmBackend:
    """백엔드가 지켜야 하는 것의 전부. 이 한 메서드 말고는 밖에서 부르지 않는다.

    Protocol 대신 평범한 클래스로 둔 이유: 이 저장소는 sync 일관성(불변 §2-1)이 중요한데,
    Protocol 은 시그니처를 문서로만 강제하고 런타임에 아무것도 안 한다. 여기서는 상속하지
    않는 구현체도 받는다(덕 타이핑) - 이 클래스는 '계약을 적어 두는 자리'다.
    """

    name: str = ""

    def summarize(self, *, body: str) -> LlmResult:  # pragma: no cover - 계약 선언
        raise NotImplementedError

    def run(self, *, system: str, user: str) -> LlmResult:  # pragma: no cover - 계약 선언
        """**이미 조립된** (system, user) 쌍을 그대로 실행한다.

        `summarize()` 는 본문을 받아 `prompt.build_prompt()` 를 거친 뒤 이것을 부른다.
        둘로 나눈 이유는 D-202 다 — Model Gateway 가 프롬프트 방어를 **자기가** 걸고
        백엔드에는 조립이 끝난 것만 넘긴다. 그래야 새 호출 경로가 하나 생겨도 방어를
        빠뜨릴 자리가 없다.
        """
        raise NotImplementedError


def _first_str(*values) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _as_bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return None


def _as_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        # lstrip("-") 는 앞의 대시를 전부 지운다 - "--5" 도 여기를 통과하지만
        # int() 는 부호 하나만 받아 ValueError 를 던진다. 숫자처럼 보여도 진짜
        # int() 리터럴이 아니면 "설정 안 됨" 으로 떨어뜨린다(이 함수의 나머지와 같은
        # fail-safe 원칙).
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def resolve_config(settings=None, env=None) -> LlmConfig:
    """`Settings` 필드 → 환경변수 → 기본값 순으로 읽는다.

    `getattr` 로 읽는 이유는 정직하게 적어 둔다: 지금 `Settings` 에 `llm_*` 필드가 없다.
    필드가 생기면 이 함수를 고치지 않아도 그쪽이 이긴다. 없는 동안에는 환경변수로 켠다.
    """
    env = os.environ if env is None else env

    def field(name: str, env_key: str):
        return getattr(settings, f"llm_{name}", None) if settings is not None else None, env.get(env_key)

    enabled_setting, enabled_env = field("enabled", "LLM_ENABLED")
    backend_setting, backend_env = field("backend", "LLM_BACKEND")
    model_setting, model_env = field("model", "LLM_MODEL")
    timeout_setting, timeout_env = field("timeout_seconds", "LLM_TIMEOUT_SECONDS")
    exe_setting, exe_env = field("executable", "LLM_CLI_PATH")
    api_url_setting, api_url_env = field("api_url", "LLM_API_URL")
    api_model_setting, api_model_env = field("api_model", "LLM_API_MODEL")
    api_ref_setting, api_ref_env = field("api_secret_ref", "LLM_API_SECRET_REF")

    enabled = _as_bool(enabled_setting)
    if enabled is None:
        enabled = _as_bool(enabled_env)

    backend = _first_str(backend_setting, backend_env) or BACKEND_CLI
    if backend not in {BACKEND_CLI, BACKEND_API}:
        # 오타를 조용히 CLI 로 읽으면 "API 로 바꿨는데 왜 안 바뀌지" 가 된다. 끈다.
        return LlmConfig(enabled=False, backend=backend)

    timeout = _as_int(timeout_setting)
    if timeout is None:
        timeout = _as_int(timeout_env)

    return LlmConfig(
        enabled=bool(enabled),
        backend=backend,
        model=_first_str(model_setting, model_env) or DEFAULT_MODEL,
        timeout_seconds=timeout if timeout and timeout > 0 else DEFAULT_TIMEOUT_SECONDS,
        executable=_first_str(exe_setting, exe_env) or DEFAULT_EXECUTABLE,
        api_url=_first_str(api_url_setting, api_url_env) or ANTHROPIC_MESSAGES_URL,
        api_model=_first_str(api_model_setting, api_model_env) or "",
        api_secret_ref=_first_str(api_ref_setting, api_ref_env) or "",
    )


def select_backend(config: LlmConfig, *, outbound=None) -> LlmBackend | None:
    """설정 → 백엔드 하나. 모르는 값이면 None(부르는 쪽이 '설정 안 됨'으로 접는다).

    import 를 함수 안에서 하는 이유: `provider` 만 쓰는 곳이 subprocess 와 httpx 경계를
    함께 끌고 오지 않게. 층을 나눈 값을 여기서 지킨다.
    """
    if config.backend == BACKEND_CLI:
        from app.llm.cli_backend import ClaudeCliBackend

        return ClaudeCliBackend(config)
    if config.backend == BACKEND_API:
        from app.llm.api_backend import AnthropicApiBackend

        return AnthropicApiBackend(config, outbound=outbound)
    return None
