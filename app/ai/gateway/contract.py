"""Model Gateway 계약 — **Business Logic 이 아는 것의 전부** (D-201).

    embed() · rerank() · generate() · capabilities()

## 왜 계약을 먼저 적는가

지금 생성은 서버에 로그인된 구독 CLI 다. 내일은 API 일 수 있고, 임베딩은 CPU ONNX 다.
호출부가 그중 무엇인지 알면 백엔드를 바꾸는 날 호출부를 전부 고쳐야 하고, 그러면
안 고친 한 곳이 남는다. 이 저장소는 그 사고를 `app/llm/provider.py` 에서 한 번 겪었다 —
그래서 이번에는 **계약을 먼저** 두고 그 뒤에 Adapter 를 붙인다.

## 실패를 예외가 아니라 값으로 돌려준다

`app/llm/provider.py` 와 같은 규약이다. 검색 결과와 목록은 모델과 무관하게 이미
만들어져 있다. 생성 하나가 안 됐다고 그것이 안 나가면 안 된다. 그리고 **모델이 없는
것은 사고가 아니라 정상 상태**다 — 생성 Provider 없이도 검색·Retrieval·권한 필터·
Source 조회는 동작한다(D-201). 다만 요약·분석·문서생성까지 된다고는 **적지 않는다.**

## 🔴 프롬프트 방어가 Adapter 밖에 있다 (D-202)

`generate()` 는 **`task`(우리가 쓴 지시)와 `data`(사용자·문서에서 온 내용)를 따로 받는다.**
Adapter 는 이미 조립된 `system`/`user` 쌍만 본다 — 원문을 못 본다. 그래서 새 Adapter 를
붙이는 사람이 방어를 빠뜨릴 자리 자체가 없다. `app/llm/prompt.py` 의 난스 구분자 +
`neutralize()` 가 여기서 **전 경로에** 걸린다.

생성은 D-515 부터 AI 런타임(`app/ai/runtime.py`)이 맡고 Gateway 는 임베딩만 한다. 프롬프트 조립을 부를 수 있는
자리는 `scripts/check_domain_single_source.py` 의 「프롬프트 조립」 규칙이 정적으로 지킨다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.catalog import KIND_PASSAGE, KIND_QUERY

__all__ = [
    "CAP_EMBED", "CAP_GENERATE", "CAP_RERANK",
    "KIND_PASSAGE", "KIND_QUERY",
    "Capabilities", "Capability", "EmbedAdapter", "EmbedResult",
    "GenerateResult", "Gateway",
    "STATUS_BUSY", "STATUS_CREDENTIAL_ERROR", "STATUS_DEGRADED", "STATUS_DISABLED", "STATUS_EMPTY",
    "STATUS_FAILED", "STATUS_MODEL_MISSING", "STATUS_OK", "with_generation",
    "STATUS_RUNTIME_MISSING", "STATUS_TIMEOUT", "STATUS_UNCONFIGURED",
    "STATUS_UNSUPPORTED",
]

# ── 능력 이름 ────────────────────────────────────────────────────────────────
CAP_EMBED = "embed"
CAP_RERANK = "rerank"
CAP_GENERATE = "generate"
CAPABILITIES = (CAP_EMBED, CAP_RERANK, CAP_GENERATE)

# ── 상태 어휘 ────────────────────────────────────────────────────────────────
# `app/llm/provider.py` 의 어휘를 그대로 쓰고 **세 개만 더한다**. 새 어휘를 만들면
# 화면이 두 벌을 분기하게 된다.
STATUS_OK = "ok"
STATUS_DISABLED = "disabled"
#: 연결이 막혔다(키 거부, 없는 모델, 재로그인 필요). 사람이 고칠 때까지 호출하지 않는다(D-515).
STATUS_CREDENTIAL_ERROR = "credential_error"
#: 제공자가 잠시 응답하지 못한다. 다음 호출이 다시 시도한다(D-515).
STATUS_DEGRADED = "degraded"
STATUS_TIMEOUT = "timeout"
STATUS_BUSY = "busy"
STATUS_UNCONFIGURED = "unconfigured"
STATUS_EMPTY = "empty"
STATUS_FAILED = "failed"
#: 파이썬 런타임(onnxruntime·tokenizers)이 안 깔려 있다. Stage 12 가 그것을 깐다.
STATUS_RUNTIME_MISSING = "runtime_missing"
#: 런타임은 있는데 모델 파일이 없다. 「안 깔림」과 「안 넣음」은 다른 사실이다.
STATUS_MODEL_MISSING = "model_missing"
#: 이 능력을 하는 Adapter 가 아예 없다. rerank 가 지금 그렇다 (D-212).
STATUS_UNSUPPORTED = "unsupported"

#: 상태 → 화면에 그대로 실을 수 있는 한 줄. 「그래서 지금 무엇을 보고 있는가」로 끝난다.
NOTICES: dict[str, str] = {
    STATUS_DISABLED: "AI 기능이 꺼져 있습니다.",
    STATUS_CREDENTIAL_ERROR: "AI 연결이 끊겨 있습니다. 관리자에게 알려 주세요.",
    STATUS_DEGRADED: "AI 연결이 잠시 불안정합니다. 잠시 뒤 다시 시도해 주세요.",
    STATUS_TIMEOUT: "AI 응답이 제한 시간 안에 끝나지 않았습니다.",
    STATUS_BUSY: "다른 AI 작업이 진행 중입니다.",
    STATUS_UNCONFIGURED: "AI 모델이 아직 설정되지 않았습니다.",
    STATUS_EMPTY: "AI 응답이 비어 있습니다.",
    STATUS_FAILED: "AI 응답을 만들지 못했습니다.",
    STATUS_RUNTIME_MISSING: "서버에 AI 실행 환경이 설치되어 있지 않습니다.",
    STATUS_MODEL_MISSING: "서버에 AI 모델 파일이 없습니다.",
    STATUS_UNSUPPORTED: "이 기능을 하는 AI 어댑터가 없습니다.",
}

FALLBACK_NOTICE = "AI 기능을 쓸 수 없습니다."

#: 실패의 기계 코드가 상태보다 더 정확히 말해 주는 경우(P3 ④). 같은 「미설정」 · 「일시 장애」 · 「시간 초과」라도 까닭이 다르면 다음 행동이
#: 다르다 — 본인만 쓰는 설치(D-559), 요금제 한도, 차단기가 열린 30초, 차례 예산. 코드는 런타임 · 제공자 어댑터가 적는 값이다.
ERROR_CODE_NOTICES: dict[str, str] = {
    "personal_only": "이 설치의 AI 는 연결한 사람 본인만 쓸 수 있습니다. 관리자가 API 키로 연결하면 모두 쓸 수 있습니다.",
    "plan_usage_limit": "ChatGPT 요금제 사용 한도에 닿았습니다. 잠시 뒤 다시 시도하거나 ChatGPT 설정의 사용량을 확인하세요.",
    "plan_usage_unavailable": "ChatGPT 요금제 사용량을 지금 확인할 수 없습니다. 잠시 뒤 다시 시도해 주세요.",
    "plan_not_eligible": "연결한 ChatGPT 계정은 이 기능을 쓸 수 없는 요금제입니다. 관리자에게 알려 주세요.",
    "insufficient_quota": "AI 제공자의 사용 한도나 잔액이 바닥났습니다. 관리자에게 알려 주세요.",
    "account_not_connected": "ChatGPT 계정 연결이 끊겨 있습니다. 관리자가 다시 로그인해야 합니다.",
    "breaker_open": "AI 연결이 잠시 불안정해 쉬고 있습니다. 30초 뒤 다시 시도해 주세요.",
    "turn_budget": "답을 만드는 데 시간이 너무 걸려 멈췄습니다. 질문을 조금 좁혀 다시 시도해 주세요.",
    "slot_unavailable": "다른 AI 작업이 진행 중입니다. 잠시 뒤 다시 시도해 주세요.",
}


def notice_for(status: str, error_code: str | None = None) -> str | None:
    """성공이면 None, 실패면 **왜 못 쓰는지** 한 줄. 목록에 없는 상태도 안 숨긴다. 기계 코드가 더 정확히 말하면 그 문장이다."""
    if status == STATUS_OK:
        return None
    if error_code and error_code in ERROR_CODE_NOTICES:
        return ERROR_CODE_NOTICES[error_code]
    return NOTICES.get(status, FALLBACK_NOTICE)


# ── 능력 보고 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Capability:
    """능력 하나가 **지금** 되는가, 안 되면 왜 안 되는가.

    `available` 만 두면 화면이 「안 됩니다」밖에 못 쓴다. 운영자가 고칠 수 있는 것과
    (모델 파일을 안 넣었다) 못 고치는 것을(어댑터가 없다) 구별하지 못한다.
    """

    name: str
    available: bool
    status: str
    #: 지금 쓰는 모델 이름. 설정에서 온다 — 이 계약에는 어떤 모델 이름도 안 적힌다.
    model: str = ""
    #: 사람이 읽는 보충 한 줄. 경로나 토큰이 섞이지 않는 문장만 넣는다(OPS-05).
    detail: str = ""

    @property
    def notice(self) -> str | None:
        return notice_for(self.status)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "available": self.available,
            "status": self.status,
            "model": self.model,
            "notice": self.notice,
            "detail": self.detail,
        }


def unavailable(name: str, status: str, *, model: str = "", detail: str = "") -> Capability:
    return Capability(name=name, available=False, status=status, model=model, detail=detail)


def available(name: str, *, model: str = "", detail: str = "") -> Capability:
    return Capability(name=name, available=True, status=STATUS_OK, model=model, detail=detail)


@dataclass(frozen=True)
class Capabilities:
    """세 능력의 현재 상태. 호출부는 부르기 **전에** 이것을 본다."""

    embed: Capability
    rerank: Capability
    generate: Capability

    def get(self, name: str) -> Capability:
        return {CAP_EMBED: self.embed, CAP_RERANK: self.rerank, CAP_GENERATE: self.generate}[name]

    def as_dict(self) -> dict:
        return {
            CAP_EMBED: self.embed.as_dict(),
            CAP_RERANK: self.rerank.as_dict(),
            CAP_GENERATE: self.generate.as_dict(),
        }


# ── 결과 ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EmbedResult:
    """임베딩 결과. 실패해도 예외가 아니라 값이다.

    `vectors` 는 입력과 **같은 길이**이거나 비어 있다. 부분 성공을 돌려주면 부르는 쪽이
    어느 chunk 가 어느 벡터인지 다시 맞춰야 하고, 그 자리가 곧 어긋난 벡터를 저장하는
    자리가 된다.
    """

    status: str
    model: str = ""
    dim: int = 0
    vectors: tuple[tuple[float, ...], ...] = ()
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK

    @property
    def notice(self) -> str | None:
        return notice_for(self.status)


@dataclass(frozen=True)
class GenerateResult:
    """생성 결과. `app/llm/provider.py::LlmResult` 와 같은 모양이다."""

    status: str
    model: str = ""
    text: str | None = None
    #: 본문에서 구분자 흉내를 걷어냈는가. 조용히 고치면 아무도 추적하지 못한다.
    delimiter_conflict: bool = False
    truncated: bool = False
    #: 실패의 기계 코드(`http_401`, `timeout`, `output_too_long`). 화면 문장은 `notice` 가 준다.
    error_code: str | None = None
    provider: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    #: 입력(검색된 문맥)을 한도에 맞춰 잘랐는가, 출력을 액션의 길이로 잘랐는가. 사용 기록이 따로 남긴다(D-517).
    input_truncated: bool = False
    output_truncated: bool = False
    #: 이 호출이 쓴 지시문의 사용처와 출처(기본 제공이거나 관리자가 발행한 버전, D-518). 사용 기록이 남긴다.
    prompt_slot: str | None = None
    prompt_source: str | None = None
    prompt_version: int | None = None
    prompt_id: str | None = None
    #: 이 호출에 걸린 정책의 id(D-519). 사용 기록이 남기고 정책 사용 통계가 센다.
    policy_ids: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK and bool(self.text)

    @property
    def notice(self) -> str | None:
        return None if self.ok else notice_for(self.status, self.error_code)


# ── Adapter 계약 ─────────────────────────────────────────────────────────────


class EmbedAdapter:
    """임베딩 Adapter 가 지켜야 하는 것의 전부.

    `Protocol` 이 아니라 평범한 클래스인 이유는 `app/llm/provider.py::LlmBackend` 와 같다 —
    이 저장소는 sync 일관성이 중요한데 `Protocol` 은 런타임에 아무것도 강제하지 않는다.
    여기서는 상속하지 않는 구현체도 받는다(덕 타이핑).
    """

    name: str = ""
    model: str = ""
    dim: int = 0

    def capability(self) -> Capability:  # pragma: no cover - 계약 선언
        raise NotImplementedError

    def embed(self, texts, *, kind: str = KIND_PASSAGE) -> EmbedResult:  # pragma: no cover
        raise NotImplementedError


def with_generation(caps: Capabilities, generate: Capability) -> Capabilities:
    """Gateway 의 능력 보고에 AI 런타임의 생성 판정을 끼운다 - 화면이 받는 모양은 예전 그대로 세 칸이다."""
    return Capabilities(embed=caps.embed, rerank=caps.rerank, generate=generate)


# ── Gateway ──────────────────────────────────────────────────────────────────


@dataclass
class Gateway:
    """호출부가 아는 유일한 문.

    Adapter 가 없으면 그 능력은 「어댑터 없음」이다. **Gateway 를 만드는 것 자체는
    절대 실패하지 않는다** — 만들다 죽으면 앱 기동과 워커 루프가 모델 설정 때문에
    멈춘다. 못 쓰는 상태는 `capabilities()` 가 말한다.
    """

    embed_adapter: EmbedAdapter | None = None
    #: 꺼져 있으면 Adapter 가 있어도 안 부른다. AI 를 기본 ON 으로 두는 관례가
    #: 이 저장소에 없다(`llm_enabled` · `game_ai_enabled` · `assistant_narrative_enabled`).
    enabled: bool = False
    _rerank: Capability = field(
        default_factory=lambda: unavailable(
            CAP_RERANK, STATUS_UNSUPPORTED,
            detail="RRF 융합으로 대신합니다(D-212).",
        )
    )

    # ── 능력 ─────────────────────────────────────────────────────────────────

    def capabilities(self) -> Capabilities:
        if not self.enabled:
            off = lambda name: unavailable(name, STATUS_DISABLED)  # noqa: E731
            return Capabilities(embed=off(CAP_EMBED), rerank=off(CAP_RERANK),
                                generate=off(CAP_GENERATE))
        return Capabilities(
            embed=(self.embed_adapter.capability() if self.embed_adapter
                   else unavailable(CAP_EMBED, STATUS_UNCONFIGURED)),
            rerank=self._rerank,
            # 생성은 AI 런타임이 맡는다(D-515). 부르는 쪽이 `with_generation` 으로 런타임의 판정을 끼운다.
            generate=unavailable(CAP_GENERATE, STATUS_UNSUPPORTED, detail="답변 생성은 AI 런타임이 맡습니다."),
        )

    def can(self, name: str) -> bool:
        return self.capabilities().get(name).available

    # ── embed ────────────────────────────────────────────────────────────────

    def embed(self, texts, *, kind: str = KIND_PASSAGE) -> EmbedResult:
        """문자열 여러 개 → 벡터 여러 개. 어떤 경우에도 예외를 올리지 않는다."""
        if kind not in (KIND_QUERY, KIND_PASSAGE):
            # 오타를 조용히 passage 로 읽으면 질의 벡터가 본문 접두사로 만들어진다 —
            # 오류는 안 나고 검색 품질만 조용히 떨어진다.
            return EmbedResult(status=STATUS_UNCONFIGURED, detail="kind 는 query 또는 passage 입니다.")
        items = [t for t in (texts or [])]
        if not items:
            return EmbedResult(status=STATUS_EMPTY)
        cap = self.capabilities().embed
        if not cap.available:
            return EmbedResult(status=cap.status, model=cap.model, detail=cap.detail)
        try:
            result = self.embed_adapter.embed(items, kind=kind)
        except Exception:  # noqa: BLE001 - 색인 루프는 임베딩 하나 때문에 죽지 않는다
            _logger().exception("임베딩 어댑터가 예상 못 한 예외를 냈다")
            return EmbedResult(status=STATUS_FAILED, model=cap.model)
        if result.ok and len(result.vectors) != len(items):
            # 부분 결과는 성공이 아니다. 여기서 안 막으면 chunk 와 벡터가 한 칸씩
            # 밀린 채 저장되고, 그 사실은 검색이 이상해질 때까지 안 드러난다.
            _logger().error(
                "임베딩 개수가 입력과 다르다(입력=%d 결과=%d)", len(items), len(result.vectors)
            )
            return EmbedResult(status=STATUS_FAILED, model=result.model)
        return result

    # ── rerank ───────────────────────────────────────────────────────────────

    def rerank(self, query: str, passages):
        """**쓰지 않는다** (D-212). 계약에는 남기고 능력은 「어댑터 없음」이다.

        지우지 않는 이유: D-201 이 적은 네 함수 중 하나이고, CPU 실측이 뒤집힌 날
        (또는 GPU 가 생긴 날) 붙일 자리가 여기다. 지금 부르면 원래 순서를 그대로
        돌려준다 — 조용히 순서를 바꾸는 것보다 아무것도 안 하는 편이 정직하다.
        """
        return tuple(range(len(passages or ())))


def _logger():
    import logging

    return logging.getLogger("app.ai.gateway")
