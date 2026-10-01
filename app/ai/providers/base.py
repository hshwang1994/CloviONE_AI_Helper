"""AI 제공자 계약 — 런타임이 제공자에 대해 아는 것의 전부 (계획 3.14, D-515 · D-516).

## 제공자는 조립이 끝난 (system, user) 쌍만 받는다

프롬프트 방어(난스 구분자, 「데이터는 지시가 아니다」)는 런타임이 `app/llm/prompt.py` 로 한 번 건다. 제공자는
원문을 보지 못한다 - 새 제공자를 붙이는 사람이 방어를 빠뜨릴 자리가 없다(D-202).

도구를 쓰는 대화(`converse()`, D-535)도 같다 — 차례의 글과 도구 결과는 런타임이 이미 칸에 넣은 글이고, 제공자는 그것을 제공자의
요청 모양으로 옮기기만 한다(이 파일 끝의 「대화 계약」).

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

    def converse(self, *, system: str, turns, tools, tool_choice: str, model: str, max_output_tokens: int,
                 timeout: float) -> "ConverseResult":  # pragma: no cover - 계약 선언
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
                    "Claude 구독 계정으로는 연결할 수 없습니다. Anthropic 콘솔에서 발급한 API 키를 넣으세요.",
                    "API 키를 아직 넣지 않았습니다."),),
        help="Anthropic 은 콘솔에서 발급한 API 키로만 연결할 수 있습니다.",
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


# ── 추천 모델 (D-539) ─────────────────────────────────────────────────────────
#
# 인증이 끝나면 화면이 모델 목록을 저절로 받고, 모델이 비어 있을 때만 이 표가 고른 하나를 **명시적으로** 저장한다(감사에
# `auto: true`). 사람이 고른 모델을 바꾸지 않는다. 표는 이름의 앞머리 순서다 — 같은 앞머리 안에서는:
#   - Anthropic 은 서버가 준 순서(최신 먼저)의 첫 것을 쓴다(`GET /v1/models` 는 만든 날 내림차순이다).
#   - OpenAI API 키는 앞머리와 똑같은 이름(별칭)을 먼저, 없으면 `mini` · `nano` 가 아닌 가장 짧은 이름을 쓴다(날짜가 붙은
#     고정판보다 별칭이 짧다).
#   - ChatGPT 요금제는 표가 없다. 서버 순서의 첫 `visibility=list` 모델이다(목록이 이미 그것만 담는다, `openai.parse_models`).
#
# 이름 표 자체는 `app/ai/catalog.py::RECOMMENDED_MODEL_PREFIXES` 에 있다 - 모델 이름이 제품에 적히는 자리는 그 파일 하나다(D-201).
_SMALL_MARKERS = ("mini", "nano")


def recommend(provider: str, auth_method: str, models) -> str | None:
    """모델 목록(`[{id, label}]`, 서버 순서) → 추천 하나. 목록이 비면 None."""
    ids = [m.get("id") for m in models or () if isinstance(m, dict) and isinstance(m.get("id"), str) and m.get("id")]
    if not ids:
        return None
    from app.ai.catalog import RECOMMENDED_MODEL_PREFIXES

    prefixes = RECOMMENDED_MODEL_PREFIXES.get((provider, auth_method))
    if prefixes is None:
        return None
    if not prefixes:
        return ids[0]
    for prefix in prefixes:
        if provider == PROVIDER_ANTHROPIC:
            hit = next((i for i in ids if i.startswith(prefix)), None)
            if hit:
                return hit
            continue
        if prefix in ids:
            return prefix
        family = [i for i in ids if i.startswith(prefix + "-") and not any(m in i for m in _SMALL_MARKERS)]
        if family:
            return min(family, key=lambda i: (len(i), i))
    return None


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


# ── 대화 계약 — AI 도우미 한 차례 (D-535) ─────────────────────────────────────
#
# `generate()` 는 그대로다 — 주간 요약 · 홈 요약 · 퀴즈 · 연결 확인 같은 단발 기능은 도구 없이 (system, user) 한 쌍이다
# (`tests/security/test_prompt_injection_boundary.py` 가 그 서명을 지킨다). 도구를 쓰는 것은 AI 도우미 한 액션이고 그 길이
# `converse()` 다. 제공자는 여기서도 원문을 보지 않는다: 차례의 글과 도구 결과는 런타임이 이미 칸(난스 구분자)에 넣은 글이다.
#
# 도구 스키마는 두 제공자의 공용 모양이다 — `type · enum · description · properties · required · additionalProperties:false · items`
# 만 쓰고 모든 속성을 required 로 두며 선택은 `["T", "null"]` 이다(OpenAI `strict:true` 와 Anthropic `input_schema` 가 함께 받는다).
# 길이 · 패턴 같은 검증은 서버가 pydantic 으로 한다 — 스키마에 실으면 제공자마다 받는 키가 달라진다.

TOOL_CHOICE_AUTO = "auto"
TOOL_CHOICE_NONE = "none"
TOOL_CHOICE_REQUIRED = "required"
#: 도구 하나를 강제하는 선택은 `"tool:<이름>"` 이다(연결 확인의 도구 시험이 `ping` 하나를 강제한다).
TOOL_CHOICE_PREFIX = "tool:"

STOP_END = "end_turn"
STOP_TOOL_USE = "tool_use"
STOP_MAX_TOKENS = "max_tokens"


def forced_tool(name: str) -> str:
    return TOOL_CHOICE_PREFIX + name


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    #: JSON 스키마(`type: object`). 위 머리말의 공용 모양만 쓴다.
    parameters: dict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    #: 인자 JSON 을 읽은 값. 읽지 못하면 None 이다 — 런타임이 `invalid_arguments` 결과를 돌려준다(지어내지 않는다).
    arguments: dict | None
    raw_arguments: str = ""


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    #: 이미 칸에 든 글(데이터). 제공자는 이 글을 해석하지 않고 그대로 싣는다.
    content: str
    is_error: bool = False


@dataclass(frozen=True)
class UserTurn:
    text: str


@dataclass(frozen=True)
class AssistantTurn:
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    #: 제공자가 준 원래 항목 — 다음 요청에 **그대로** 되싣는다(Anthropic 의 content 블록, OpenAI 의 output 항목과 추론 항목).
    #: 없으면(지난 대화를 DB 에서 읽은 경우) 글과 도구 호출로 다시 만든다.
    replay: tuple = ()


@dataclass(frozen=True)
class ToolResultsTurn:
    results: tuple[ToolResult, ...]


@dataclass(frozen=True)
class ConverseResult:
    ok: bool
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    replay: tuple = ()
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error_kind: str | None = None
    error_code: str | None = None
    http_status: int | None = None

    def as_turn(self) -> AssistantTurn:
        """이 응답을 다음 요청의 assistant 차례로."""
        return AssistantTurn(text=self.text or "", tool_calls=self.tool_calls, replay=self.replay)


def converse_failure(kind: str, code: str, *, http_status: int | None = None) -> ConverseResult:
    return ConverseResult(ok=False, error_kind=kind, error_code=code, http_status=http_status)


def converse_from_failure(result: ProviderResult) -> ConverseResult:
    """`generate()` 와 같은 실패 분류(`classify_status` · 예외 표)를 대화 결과로 옮긴다 — 실패의 종류는 한 표다."""
    return ConverseResult(ok=False, error_kind=result.error_kind, error_code=result.error_code,
                          http_status=result.http_status, input_tokens=result.input_tokens,
                          output_tokens=result.output_tokens)


def parse_arguments(raw) -> dict | None:
    """도구 인자 JSON → 사전. 사전이 아니거나 JSON 이 아니면 None — 모델이 깨진 인자를 보내도 지어내서 채우지 않는다."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return None
    import json

    try:
        value = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def finish(text: str | None, calls: tuple[ToolCall, ...], replay: tuple, *, stop_reason: str | None,
           input_tokens=None, output_tokens=None) -> ConverseResult:
    """응답 하나 → 결과. 글도 도구 호출도 없으면 빈 답(`empty`)이다."""
    if not text and not calls:
        return ConverseResult(ok=False, error_kind=ERROR_EMPTY, error_code="empty",
                              input_tokens=input_tokens, output_tokens=output_tokens)
    return ConverseResult(ok=True, text=text or None, tool_calls=calls, replay=replay,
                          stop_reason=STOP_TOOL_USE if calls else (stop_reason or STOP_END),
                          input_tokens=input_tokens, output_tokens=output_tokens)
