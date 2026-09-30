"""AI 제공자 계약 — 런타임이 제공자에 대해 아는 것의 전부 (계획 3.14, D-515 · D-516).

## 제공자는 조립이 끝난 (system, user) 쌍만 받는다

프롬프트 방어(난스 구분자, 「데이터는 지시가 아니다」)는 런타임이 `app/llm/prompt.py` 로 한 번 건다. 제공자는
원문을 보지 못한다 - 새 제공자를 붙이는 사람이 방어를 빠뜨릴 자리가 없다(D-202).

## 실패는 예외가 아니라 값이고, 종류가 있다

  transient  시간 초과, 연결 실패, 5xx, 속도 제한(429), 과부하, 요금제 사용량 한도. 다시 하면 될 수 있다. 다음 호출을
             막지 않는다
  auth       자격이 거부됐다(API 키가 틀렸거나 권한이 없다). 사람이 고칠 때까지 막는다
  reauth     계정 연결이 끊겼다(ChatGPT 의 갱신 토큰이 무효가 됐다). 다시 로그인할 때까지 막는다
  config     구성이 틀렸다(없는 모델, 허용 목록 밖, 저장된 키가 없다, 요금제 공유 대상이 아니다). 사람이 고칠 때까지 막는다
  request    이 요청만 틀렸다(너무 긴 입력 등). 연결 상태는 그대로다
  empty      답이 비었다

상태 전이는 이 종류로만 정한다(`app/ai/credentials/state.py`). 제공자가 준 오류 원문은 화면에 싣지 않는다 - 코드에서
고른 문장만 나간다(내부 주소나 키 이름이 섞일 수 있고, 영어라 읽히지 않는다).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.secret_slots import SLOT_ANTHROPIC_API_KEY, SLOT_OPENAI_API_KEY, SLOT_OPENAI_CHATGPT

ERROR_TRANSIENT = "transient"
ERROR_AUTH = "auth"
ERROR_REAUTH = "reauth"
ERROR_CONFIG = "config"
ERROR_REQUEST = "request"
ERROR_EMPTY = "empty"

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
AUTH_API_KEY = "api_key"
AUTH_CHATGPT = "chatgpt"


@dataclass(frozen=True)
class ProviderResult:
    ok: bool
    text: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_kind: str | None = None
    #: 기계가 읽는 짧은 코드(`http_429`, `timeout`, `model_not_found`). 사용 기록과 상태의 까닭에 쓴다.
    error_code: str | None = None
    http_status: int | None = None


@dataclass(frozen=True)
class ModelList:
    ok: bool
    models: tuple[dict, ...] = ()
    error_kind: str | None = None
    error_code: str | None = None


def success(text: str, *, input_tokens=None, output_tokens=None) -> ProviderResult:
    return ProviderResult(ok=True, text=text, input_tokens=input_tokens, output_tokens=output_tokens)


def failure(kind: str, code: str, *, http_status: int | None = None) -> ProviderResult:
    return ProviderResult(ok=False, error_kind=kind, error_code=code, http_status=http_status)


class ProviderAdapter:
    """제공자 하나가 지켜야 하는 것. 상속하지 않는 구현체도 받는다(덕 타이핑, 시험의 가짜가 그렇다)."""

    provider: str = ""
    auth_method: str = ""

    def generate(self, *, system: str, user: str, model: str, max_output_tokens: int,
                 timeout: float) -> ProviderResult:  # pragma: no cover - 계약 선언
        raise NotImplementedError

    def list_models(self, *, timeout: float) -> ModelList:  # pragma: no cover - 계약 선언
        raise NotImplementedError


# ── 제공자와 인증 방식의 표 ──────────────────────────────────────────────────
#
# 화면은 이 표대로만 단추를 그린다. 제공자가 공식으로 지원하지 않는 인증은 표에 없다 - Anthropic 은 제3자 앱의
# 계정 로그인을 공식 정책이 금지하므로 API 키 하나뿐이다. OpenAI 는 API 키와 공식 「Sign in with ChatGPT」(오픈
# 소스와 자체 호스팅 앱의 동적 클라이언트 등록)를 둘 다 지원한다(계획 3.14 조사 결과, D-516).


@dataclass(frozen=True)
class AuthMethod:
    key: str
    label: str
    #: 이 방식의 자격이 사는 비밀 칸(`app/core/secret_slots.py`).
    secret_slot: str
    help: str
    #: 자격이 없을 때의 한 문장(미설정의 까닭).
    missing: str
    #: 사람이 값을 붙여 넣는 칸이 아니라 계정 로그인으로 채우는 칸인가. 화면이 키 입력칸 대신 로그인 단추를 그린다.
    account: bool = False


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    auth_methods: tuple[AuthMethod, ...] = field(default_factory=tuple)
    help: str = ""

    def method(self, key: str) -> AuthMethod | None:
        return next((m for m in self.auth_methods if m.key == key), None)


PROVIDERS: dict[str, ProviderSpec] = {
    PROVIDER_ANTHROPIC: ProviderSpec(
        PROVIDER_ANTHROPIC, "Anthropic",
        (AuthMethod(AUTH_API_KEY, "API 키", SLOT_ANTHROPIC_API_KEY,
                    "Anthropic 콘솔에서 발급한 조직 API 키를 넣습니다.", "API 키를 아직 넣지 않았습니다."),),
        help="Anthropic 은 조직 API 키로만 연결할 수 있습니다.",
    ),
    PROVIDER_OPENAI: ProviderSpec(
        PROVIDER_OPENAI, "OpenAI",
        (
            AuthMethod(AUTH_API_KEY, "API 키", SLOT_OPENAI_API_KEY,
                       "OpenAI 플랫폼에서 발급한 API 키를 넣습니다.", "API 키를 아직 넣지 않았습니다."),
            AuthMethod(AUTH_CHATGPT, "ChatGPT 계정", SLOT_OPENAI_CHATGPT,
                       "연결한 사람의 ChatGPT 요금제로 답을 만듭니다. 여러 사람이 함께 쓰는 설치라면 API 키 연결이 알맞습니다.",
                       "ChatGPT 계정을 아직 연결하지 않았습니다.", account=True),
        ),
        help="OpenAI 는 API 키나 ChatGPT 계정으로 연결할 수 있습니다.",
    ),
}


def provider_spec(key: str | None) -> ProviderSpec | None:
    return PROVIDERS.get(key or "")


def build_adapter(provider: str, auth_method: str, *, outbound, secrets, tokens=None) -> ProviderAdapter | None:
    """제공자와 인증 방식 → 어댑터 하나. 모르는 쌍이면 None(런타임이 「미설정」으로 접는다).

    ``tokens`` 는 계정 연결의 토큰 관리자다(`app/ai/credentials/chatgpt.py::ChatGptTokens`). 계정 연결 방식만 쓴다.
    """
    spec = provider_spec(provider)
    method = spec.method(auth_method) if spec else None
    if method is None:
        return None
    if provider == PROVIDER_ANTHROPIC:
        from app.ai.providers.anthropic import AnthropicAdapter

        return AnthropicAdapter(outbound=outbound, secret_ref=method.secret_slot)
    if provider == PROVIDER_OPENAI:
        from app.ai.providers.openai import OpenAIAdapter

        return OpenAIAdapter(outbound=outbound, secret_ref=method.secret_slot, auth_method=auth_method,
                             tokens=tokens if method.account else None)
    return None  # pragma: no cover - 표와 분기가 어긋나면 시험이 잡는다
