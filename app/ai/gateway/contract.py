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

`scripts/check_ai_prompt_boundary.py` 가 이 경계를 정적으로 지킨다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ai.catalog import KIND_PASSAGE, KIND_QUERY

__all__ = [
    "CAP_EMBED", "CAP_GENERATE", "CAP_RERANK",
    "KIND_PASSAGE", "KIND_QUERY",
    "Capabilities", "Capability", "EmbedAdapter", "EmbedResult",
    "GenerateAdapter", "GenerateResult", "Gateway",
    "STATUS_BUSY", "STATUS_DISABLED", "STATUS_EMPTY", "STATUS_FAILED",
    "STATUS_MODEL_MISSING", "STATUS_NOT_LOGGED_IN", "STATUS_OK",
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
STATUS_NOT_LOGGED_IN = "not_logged_in"
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
    STATUS_NOT_LOGGED_IN: "서버의 AI 명령줄 도구에 로그인되어 있지 않습니다.",
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


def notice_for(status: str) -> str | None:
    """성공이면 None, 실패면 **왜 못 쓰는지** 한 줄. 목록에 없는 상태도 안 숨긴다."""
    if status == STATUS_OK:
        return None
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

    @property
    def ok(self) -> bool:
        return self.status == STATUS_OK and bool(self.text)

    @property
    def notice(self) -> str | None:
        return None if self.ok else notice_for(self.status)


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


class GenerateAdapter:
    """생성 Adapter. **원문을 안 받는다** — 이미 조립된 (system, user) 쌍만 받는다.

    이 시그니처가 D-202 의 「전 AI 경로에 적용」을 구조로 만든다. Adapter 가 원문을
    받으면 언젠가 그것을 그대로 프롬프트에 붙이는 Adapter 가 하나 생기고, 그 하나가
    방어를 통째로 무효로 만든다.
    """

    name: str = ""
    model: str = ""

    def capability(self) -> Capability:  # pragma: no cover - 계약 선언
        raise NotImplementedError

    def generate(self, *, system: str, user: str) -> GenerateResult:  # pragma: no cover
        raise NotImplementedError


# ── Gateway ──────────────────────────────────────────────────────────────────


@dataclass
class Gateway:
    """호출부가 아는 유일한 문.

    Adapter 가 없으면 그 능력은 「어댑터 없음」이다. **Gateway 를 만드는 것 자체는
    절대 실패하지 않는다** — 만들다 죽으면 앱 기동과 워커 루프가 모델 설정 때문에
    멈춘다. 못 쓰는 상태는 `capabilities()` 가 말한다.
    """

    embed_adapter: EmbedAdapter | None = None
    generate_adapter: GenerateAdapter | None = None
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
            generate=(self.generate_adapter.capability() if self.generate_adapter
                      else unavailable(CAP_GENERATE, STATUS_UNCONFIGURED)),
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

    # ── generate ─────────────────────────────────────────────────────────────

    def generate(self, *, task: str, data: str) -> GenerateResult:
        """지시(`task`) + **신뢰하지 않는 내용**(`data`) → 문장.

        `data` 는 사용자가 쓴 글이거나 문서에서 온 내용이다. 여기서 난스 구분자로 가두고
        구분자 흉내를 걷어낸 뒤에야 Adapter 로 간다 (D-202).
        """
        cap = self.capabilities().generate
        if not cap.available:
            return GenerateResult(status=cap.status, model=cap.model)
        from app.llm import prompt as prompt_mod

        try:
            built = prompt_mod.build_prompt(
                body=data, nonce=prompt_mod.new_nonce(), task=task
            )
        except prompt_mod.EmptyBodyError:
            return GenerateResult(status=STATUS_EMPTY, model=cap.model)
        try:
            result = self.generate_adapter.generate(system=built.system, user=built.user)
        except Exception:  # noqa: BLE001
            _logger().exception("생성 어댑터가 예상 못 한 예외를 냈다")
            return GenerateResult(status=STATUS_FAILED, model=cap.model)
        return GenerateResult(
            status=result.status,
            model=result.model or cap.model,
            text=result.text,
            delimiter_conflict=built.delimiter_conflict,
            truncated=built.truncated,
        )

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
