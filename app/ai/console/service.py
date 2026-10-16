"""AI 연결 화면의 판단 — 무엇을 보이고 무엇을 저장하는가 (계획 A3 · A8, D-515 · D-539).

화면(`/ai-connection`)은 한 열 흐름이다: 짧은 연결 상태 면 → 제공자와 인증 → 모델 → 실행 옵션 → AI 기능. 이 모듈이 그
흐름에 필요한 값을 한 번에 주고(`overview`), 저장을 한 트랜잭션으로 하며(`apply_config`), 연결 상태를 사람의 낱말로
옮긴다(`state_display` — 초기 설정의 AI 항목도 같은 함수를 쓴다).

## 「정상」의 뜻 (D-539)

정상은 지금 설정 지문으로 실제 생성이 성공한 뒤에만 선다(`app/ai/credentials/state.py`). 인증 방식 · 모델이 바뀌거나 AI
사용을 켜면 서버가 연결 확인을 저절로 시작하고(`verify_needed`), 그동안 화면은 「확인 중」이다. 주기 확인은 모델 목록만으로
상태를 올리지 않는다(`app/ai/health.py`).

## 비밀 값은 여기서 다루지 않는다

API 키는 비밀 칸 API(`/api/admin/secrets/{slot}`)가 쓰고 되읽지 않는다. 여기서는 저장돼 있는지와 끝 네 글자만 보인다.
ChatGPT 계정 연결은 붙여 넣기 로그인이 채운다(`app/ai/credentials/oauth.py`). 토큰 만료 시각 · 계정 주소 같은 값은
「기술 정보」(`technical`) 한 칸에 모아 화면이 접기 안에만 그린다.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import concurrency
from app.ai.providers import base
from app.core.errors import ValidationAppError

JOB_TYPE_VERIFY = "llm_connection_test"
OBJECT_TYPE = "ai_config"

FEATURE_KEYS = ("chat_enabled", "assistant_narrative_enabled", "game_ai_enabled")
CONFIG_KEYS = {
    "generation_enabled": "ai_generation_enabled",
    "provider": "ai_provider",
    "auth_method": "ai_auth_method",
    "model": "ai_model",
    "timeout_seconds": "ai_timeout_seconds",
    "max_concurrency": "ai_max_concurrency",
}
MODEL_MAX_CHARS = 200
#: 이 값이 바뀌면 연결 확인을 저절로 시작한다(D-539). 제한 시간 · 동시 실행 수는 연결의 성질이 아니다.
VERIFY_ON = frozenset({"ai_provider", "ai_auth_method", "ai_model"})

# 계정 연결의 토큰 수명 기본값(D-516). 제공자 응답에 수명이 없을 때만 쓴다 - 정본은 응답이다. 시스템 관리자만 바꾼다.
TOKEN_SETTING_KEYS = (
    "ai_openai_access_ttl_fallback_seconds", "ai_openai_refresh_ttl_fallback_days", "ai_token_refresh_lead_seconds",
)

# ── 연결 상태의 낱말 (D-539, A8) ──────────────────────────────────────────────
#
# 상태 면 · 초기 설정 · 진단이 같은 낱말을 쓴다. 키는 연결 상태(state.py)에 둘을 더한 것이다: 「확인 중」(연결 확인 잡이
# 큐에 있거나 도는 중)과 「꺼짐」(AI 사용이 꺼져 있다). 우선순위는 미설정 > 확인 중 > 막힘(연결 오류 · 재로그인 필요) >
# 꺼짐 > 나머지 연결 상태다 - 막힘은 AI 사용을 켜기 전에 고칠 일이라 꺼짐에 가리지 않는다.
DISPLAY_OFF = "off"
DISPLAY_VERIFYING = "verifying"
#: 자격은 아직 없는데 이 관리자의 로그인 시도가 열려 있다(ChatGPT 창에서 승인 → 주소 붙여 넣기 사이, D-558).
DISPLAY_AUTHENTICATING = "authenticating"
DISPLAY: dict[str, tuple[str, str]] = {
    "unconfigured": ("미설정", "muted"),
    DISPLAY_AUTHENTICATING: ("로그인 진행 중", "info"),
    DISPLAY_VERIFYING: ("확인 중", "info"),
    DISPLAY_OFF: ("비활성화", "muted"),
    "unverified": ("확인 전", "info"),
    "ok": ("정상", "ok"),
    "degraded": ("일시 장애", "warn"),
    "reauth_required": ("재로그인 필요", "error"),
    "error": ("연결 오류", "error"),
}
DISPLAY_MESSAGES: dict[str, str] = {
    "unconfigured": "AI 제공자, 인증, 모델 중 아직 정하지 않은 것이 있습니다.",
    DISPLAY_AUTHENTICATING: "ChatGPT 창에서 승인한 뒤 주소를 붙여 넣으면 연결됩니다.",
    DISPLAY_VERIFYING: "연결을 확인하고 있습니다.",
    DISPLAY_OFF: "AI 사용이 비활성화되어 있어 AI 기능이 답을 만들지 않습니다.",
    "unverified": "아직 연결을 확인하지 않았습니다.",
    "ok": "응답 확인 완료",
    "degraded": "제공자가 잠시 응답하지 못하고 있습니다. 다음 호출이 다시 시도하고, 성공하면 정상으로 돌아옵니다.",
    "reauth_required": "계정 연결이 끊겼습니다. 다시 로그인해야 합니다.",
    "error": "AI 연결을 쓸 수 없습니다.",
}
SETUP_DONE, SETUP_TODO, SETUP_UNKNOWN = "done", "todo", "unknown"
SEMANTIC_NOTE = "의미 검색 모델은 선택이며 지금은 낱말로 찾습니다."


def state_display(info: dict, *, verifying: bool = False, embed_available: bool | None = None,
                  login_open: bool = False) -> dict:
    """연결 상태 한 벌(`runtime.status`) → 화면 낱말 · 한 문장 · 초기 설정 판정.

    초기 설정(A8): 정상이면 완료(도구 지원을 알든 모르든). 의미 검색 모델이 없으면 완료에 메모를 단다 - 낱말 검색이
    자연어 질문을 덮으므로 막는 항목이 아니다. AI 사용 꺼짐 · 미설정 · 막힘은 할 일, 확인 전 · 확인 중 · 일시 장애는
    확인할 일이다. ``login_open`` 은 미설정인데 로그인 시도가 열려 있는 순간이다 — 「로그인 진행 중」(D-558).
    """
    state = info.get("state") or "unconfigured"
    if state == "unconfigured":
        key = DISPLAY_AUTHENTICATING if login_open else "unconfigured"
    elif verifying:
        key = DISPLAY_VERIFYING
    elif state in ("error", "reauth_required"):
        # 막힌 연결은 AI 사용이 꺼져 있어도 먼저 말한다 - 켜기 전에 고칠 일이다.
        key = state
    elif not info.get("generation_enabled"):
        key = DISPLAY_OFF
    else:
        key = state if state in DISPLAY else "error"
    label, kind = DISPLAY[key]
    message = DISPLAY_MESSAGES[key]
    problems = [p for p in info.get("problems") or [] if p]
    if key == "unconfigured" and problems:
        message = problems[0]
    reason = info.get("reason")
    if key in ("error", "reauth_required", "degraded") and reason:
        message = f"{message} {reason}" if key == "error" else reason

    note = SEMANTIC_NOTE if embed_available is False else None
    if key == "ok":
        setup = {"state": SETUP_DONE, "detail": "AI 연결이 정상입니다.", "note": note}
    elif key == DISPLAY_OFF:
        setup = {"state": SETUP_TODO, "detail": "AI 사용이 비활성화되어 있습니다.",
                 "action": "AI 연결 화면에서 AI 사용을 활성화하세요.", "note": note}
    elif key == "unconfigured":
        setup = {"state": SETUP_TODO, "detail": "AI 제공자를 아직 연결하지 않았습니다.",
                 "action": "AI 연결 화면에서 제공자와 인증을 정하세요. AI를 쓰지 않는다면 이 줄의 「사용하지 않음」을 고르세요.",
                 "note": note}
    elif key == DISPLAY_VERIFYING:
        setup = {"state": SETUP_UNKNOWN, "detail": "연결을 확인하고 있습니다.",
                 "question": "잠시 뒤 다시 확인하세요.", "note": note}
    elif key == DISPLAY_AUTHENTICATING:
        setup = {"state": SETUP_TODO, "detail": "ChatGPT 계정 로그인이 진행 중입니다.",
                 "action": "AI 연결 화면에서 승인 뒤의 주소를 붙여 넣어 연결을 끝내세요.", "note": note}
    elif key in ("unverified", "degraded"):
        setup = {"state": SETUP_UNKNOWN, "detail": message,
                 "question": "AI 연결 화면에서 연결 확인을 누르세요.", "note": note}
    else:
        setup = {"state": SETUP_TODO, "detail": f"AI 연결이 막혀 있습니다. {reason or ''}".strip(),
                 "action": "AI 연결 화면에서 다시 로그인하거나 키를 다시 넣으세요.", "note": note}
    return {"key": key, "label": label, "kind": kind, "message": message, "setup": setup}


def pending_verify(db: Session):
    """큐에 있거나 도는 연결 확인 잡 하나(가장 새 것). 없으면 None."""
    from app.jobs.models import STATUS_QUEUED, STATUS_RUNNING, Job

    try:
        return db.execute(
            select(Job).where(Job.job_type == JOB_TYPE_VERIFY, Job.status.in_((STATUS_QUEUED, STATUS_RUNNING)))
            .order_by(Job.created_at.desc()).limit(1)
        ).scalars().first()
    except Exception:  # noqa: BLE001 - 잡 표를 못 읽으면 확인 중이 아니라고 본다
        return None


def enqueue_verify(db: Session, *, user_id: str, now: datetime):
    """연결 확인 잡을 넣는다. 이미 큐에 있으면 그것을 쓴다(같은 설정을 두 번 재지 않는다).

    잡은 실행 직전에 설정을 DB 에서 다시 읽으므로(`runtime.verify`), 큐에 있던 잡도 마지막 저장 값을 잰다.
    """
    from app.jobs.models import STATUS_QUEUED
    from app.jobs.repository import enqueue

    waiting = pending_verify(db)
    if waiting is not None and waiting.status == STATUS_QUEUED:
        return waiting
    # 다시 시도하지 않는다. 키가 틀렸으면 5초 뒤에도 같은 답이다.
    return enqueue(db, job_type=JOB_TYPE_VERIFY, payload={}, now=now, user_id=user_id, max_attempts=1)


def config_complete(config, secrets) -> bool:
    """제공자 · 인증 · 자격 · 모델이 다 있는가(연결 확인을 돌릴 수 있는가)."""
    from app.ai.runtime import problems

    return not problems(config, secrets)


def verify_needed(changed: dict, config_after, secrets) -> bool:
    """저장한 바뀜이 연결 확인을 부르는가 — 인증 · 모델이 바뀌었거나 AI 사용을 켰고, 설정이 완결일 때."""
    if not config_complete(config_after, secrets):
        return False
    if VERIFY_ON & set(changed):
        return True
    return changed.get("ai_generation_enabled") is True


def _hint(secrets, slot: str) -> str | None:
    """저장된 키의 끝 네 글자. 짧은 값은 보이지 않는다 - 네 글자가 값의 큰 몫이 된다. 계정 연결 묶음은 보이지 않는다."""
    from app.core.secret_slots import KIND_JSON, SECRET_SLOTS

    if secrets is None or (SECRET_SLOTS.get(slot) and SECRET_SLOTS[slot].kind == KIND_JSON):
        return None
    try:
        value = secrets.get(slot)
    except Exception:  # noqa: BLE001 - 못 읽으면 보이지 않는다
        return None
    text = value.reveal() if value is not None else ""
    return f"끝자리 {text[-4:]}" if len(text) >= 16 else None


def providers_view(secrets, *, chatgpt_connected: bool = False) -> list[dict]:
    """제공자와 인증 방식의 표. `ready` 는 그 방식의 자격이 지금 갖춰졌는가다(키가 있다, 계정이 연결됐다).

    표의 방식은 설치와 무관하게 전부 선다(D-566) — ChatGPT 계정 연결도 API 키와 같은 정식 방식이다.
    """
    from app.core.secret_refs import STATUS_CONFIGURED

    out = []
    for spec in base.PROVIDERS.values():
        methods = []
        for m in spec.auth_methods:
            secret_set = bool(secrets is not None and secrets.status(m.secret_slot) == STATUS_CONFIGURED)
            methods.append({
                "key": m.key, "label": m.label, "help": m.help, "secret_slot": m.secret_slot,
                "account": m.account, "secret_set": secret_set, "issue_url": m.issue_url,
                "secret_hint": _hint(secrets, m.secret_slot),
                "ready": chatgpt_connected if m.account else secret_set,
            })
        out.append({"key": spec.key, "label": spec.label, "help": spec.help, "auth_methods": methods})
    return out


def chatgpt_view(runtime, db: Session) -> dict:
    """ChatGPT 계정 연결 칸 - 연결했는가, 다시 로그인해야 하는가. 계정 주소와 만료는 기술 정보로 간다."""
    from app.ai.credentials import chatgpt
    from app.ai.credentials import state as state_mod
    from app.ai.credentials.login_flow import CHATGPT_LOGIN_FLOW

    tokens = runtime.chatgpt_tokens()
    bundle = tokens.bundle()
    row = state_mod.credential_row(db, base.PROVIDER_OPENAI, base.AUTH_CHATGPT)
    account = state_mod.account_view(row) or {}
    return {
        "connected": tokens.connected(bundle),
        # 묶음은 있는데 토큰이 지워졌다 - 갱신이 거절돼 끊긴 연결이다. 다시 로그인해야 한다.
        "disconnected": bundle is not None and not tokens.connected(bundle),
        # 계정 이름은 연결 상태 행이 정본이고, 행이 비었으면(옮겨 온 묶음) 묶음의 주소다. 토큰은 어디에도 싣지 않는다.
        "account_label": account.get("label") or (bundle.get("email") if bundle else None),
        "access_expires_at": account.get("access_expires_at"),
        "refresh_expires_at": account.get("refresh_expires_at"),
        "expiry_source": account.get("expiry_source"),
        "manage_usage_url": chatgpt.MANAGE_USAGE_URL,
        "flow": CHATGPT_LOGIN_FLOW,
    }


# ── 문서 검색(의미 검색) 상태 (D-570) ──────────────────────────────────────────
#
# 예전에는 `index.semantic`(임베딩 능력이 있는가) 하나로 「낱말 검색(의미 검색 모델 없음)」을 골랐다. 랩은 모델 파일이 있는데
# AI 사용이 꺼져 있었고(설치기가 upgrade 마다 `AI_ENABLED=false` 를 다시 썼다), 화면은 「모델 없음」이라고 했다 — 고칠 사람이
# 엉뚱한 일을 하게 만드는 문장이다. 그래서 게이트웨이가 말하는 까닭(`Capability.status`)을 그대로 낱말로 옮기고, 꺼져 있을 때도
# 모델 파일이 이미 있는지를 값싼 파일 검사로 함께 말한다(모델을 올리지 않는다).
EMBED_OK = "ok"
EMBED_DISABLED = "disabled"
EMBED_UNCONFIGURED = "unconfigured"
EMBED_RUNTIME_MISSING = "runtime_missing"
EMBED_MODEL_MISSING = "model_missing"
EMBED_FAILED = "failed"
EMBED_STATUSES = (EMBED_DISABLED, EMBED_UNCONFIGURED, EMBED_RUNTIME_MISSING, EMBED_MODEL_MISSING, EMBED_FAILED, EMBED_OK)

#: 「문서 검색」 칸의 값(낱말). 준비 중(벡터를 채우는 중)은 `embed_label` 이 수를 붙인다.
EMBED_LABELS: dict[str, str] = {
    EMBED_OK: "낱말 검색 + 의미 검색",
    EMBED_DISABLED: "낱말 검색(의미 검색 비활성화)",
    EMBED_UNCONFIGURED: "낱말 검색(의미 검색 모델 미설치)",
    EMBED_RUNTIME_MISSING: "낱말 검색(의미 검색 실행 환경 미설치)",
    EMBED_MODEL_MISSING: "낱말 검색(의미 검색 모델 미설치)",
    EMBED_FAILED: "낱말 검색(의미 검색 오류)",
}
#: 의미 검색을 켜는 방법 — 서버에서 한 번 실행한다(글만, 화면에 단추가 없다). 설치 명령의 `ai` 부명령이 런타임 · 모델 확인 · 유닛
#: 재시작까지 한다(`deploy/install.sh`).
EMBED_HINT = (
    "의미 검색을 활성화하려면 서버에서 sudo clovirassist ai --with-ai 를 실행하세요. "
    "모델 파일이 없으면 --download-model 을 함께 줍니다."
)
EMBED_HINT_FAILED = "의미 검색이 실패하고 있습니다. 서버에서 sudo clovirassist ai-cli status 로 까닭을 확인하세요."
NEXT_SERVER = "server"


def embed_label(status: str, *, pending: int | None = None, embedded: int | None = None, chunks: int | None = None,
                model_installed: bool | None = None) -> str:
    """임베딩 상태 → 「문서 검색」 칸의 낱말. 켜졌고 아직 벡터를 채우는 중이면 그 수를 붙인다."""
    if status == EMBED_OK and pending:
        return f"낱말 검색 + 의미 검색 준비 중(색인 {int(embedded or 0)}/{int(chunks or 0)})"
    if status == EMBED_DISABLED and model_installed:
        return "낱말 검색(의미 검색 비활성화, 모델 설치됨)"
    return EMBED_LABELS.get(status, EMBED_LABELS[EMBED_FAILED])


def embed_hint(status: str) -> str | None:
    """의미 검색이 서지 않았을 때 서버에서 할 일 한 문장. 정상이면 None."""
    if status == EMBED_OK:
        return None
    if status == EMBED_FAILED:
        return EMBED_HINT_FAILED
    return EMBED_HINT


def _model_files_present(settings) -> bool | None:
    """꺼져 있을 때 모델 파일이 이미 있는가 — 설정의 모델 자리에서 필요한 파일이 다 있는지만 본다(읽지 않는다). 모르면 None."""
    try:
        from app.ai import catalog
        from app.ai.gateway import registry

        config = registry.resolve_config(settings)
        model = catalog.embedding_model(config.embed_model_id)
        if model is None or not config.model_root:
            return None
        folder = registry.model_dir(config, model)
        return all((folder / name).is_file() for name in model.required_files)
    except Exception:  # noqa: BLE001 - 파일 검사가 화면을 깨지 않는다
        return None


def embed_status_of(gateway) -> str:
    """게이트웨이의 임베딩 능력 → 여섯 낱말 중 하나. 게이트웨이가 없으면(시험 · 옛 설치) 꺼짐으로 본다."""
    if gateway is None:
        return EMBED_DISABLED
    try:
        status = gateway.capabilities().embed.status
    except Exception:  # noqa: BLE001
        return EMBED_FAILED
    return status if status in EMBED_STATUSES else EMBED_FAILED


def index_view(db: Session, gateway, *, settings=None) -> dict | None:
    """문서 색인과 의미 검색 상태. 못 세면 None(0 과 「못 셌다」는 다른 사실이다).

    `embed_status` 는 `disabled | unconfigured | runtime_missing | model_missing | failed | ok` 이고 `embed_status_label` 이 화면의
    「문서 검색」 낱말이다. `pending_embedding` 은 벡터가 아직 없는 조각 수다(켜진 뒤 색인 레인이 채운다). `semantic` 은 옛 화면이
    읽던 값이라 그대로 둔다(의미 검색이 지금 되는가).
    """
    from app.ai.index import service as index_service

    try:
        health = index_service.index_health(db)
    except Exception:  # noqa: BLE001 - 표가 아직 없는 설치도 있다
        return None
    status = embed_status_of(gateway)
    chunks = health.get("chunks")
    embedded = health.get("embedded")
    pending = health.get("pending_embedding")
    model_installed = _model_files_present(settings) if status == EMBED_DISABLED and settings is not None else None
    documents = health.get("documents") or {}
    return {
        "documents": documents,
        "documents_total": sum(int(v or 0) for v in documents.values()) if isinstance(documents, dict) else None,
        "chunks": chunks,
        "embedded": embedded,
        "pending_embedding": pending,
        "semantic": status == EMBED_OK,
        "embed_status": status,
        "embed_status_label": embed_label(status, pending=pending if status == EMBED_OK else None, embedded=embedded,
                                          chunks=chunks, model_installed=model_installed),
        "embed_hint": embed_hint(status),
        "model_installed": model_installed,
    }


#: 상태 면의 「다음 할 일」이 가리키는 자리(화면이 그 구획으로 옮긴다). 서버는 문장과 자리만 주고 모양은 화면이 정한다.
NEXT_CONFIGURE = "configure"
NEXT_API_KEY = "api_key"
NEXT_LOGIN = "login"
NEXT_PASTE = "paste"
NEXT_MODEL = "model"
NEXT_ENABLE = "enable"
NEXT_VERIFY = "verify"
NEXT_WAIT = "wait"

#: 사실 띠의 값은 낱말이다(문장은 상태 문장 · 다음 할 일의 몫이다).
TOOLS_FACT = {
    "ok": "사용 가능",
    "unsupported": "대체 모드(모델이 도구를 거절함)",
}


def credentials_view(config, secrets, *, chatgpt: dict) -> dict:
    """지금 인증 방식의 자격이 갖춰졌는가(D-558). 키 방식은 비밀 칸, 계정 방식은 토큰이 든 묶음이다."""
    from app.core.secret_refs import STATUS_CONFIGURED

    method = config.method()
    if method is None:
        return {"ready": False, "method": config.auth_method or None, "account_label": None}
    if method.account:
        ready = bool(chatgpt.get("connected"))
        return {"ready": ready, "method": method.key, "account_label": chatgpt.get("account_label") if ready else None}
    ready = bool(secrets is not None and secrets.status(method.secret_slot) == STATUS_CONFIGURED)
    return {"ready": ready, "method": method.key, "account_label": None}


def facts_view(config, status: dict, *, credentials: dict, caps: dict, index: dict | None) -> list[dict]:
    """상태 면이 그릴 줄만(D-558). 자격이 없으면 제공자 · 인증 방식(저장된 것만)이고 모델 · 최근 성공 · 능력 줄은 없다."""
    from app.ai.credentials import state as state_mod

    spec = base.provider_spec(config.provider)
    method = config.method()
    facts: list[dict] = []
    if spec is not None:
        facts.append({"key": "provider", "label": "제공자", "value": spec.label})
    if method is not None:
        value = method.label
        if method.account and credentials.get("account_label"):
            value = f"{method.label} · {credentials['account_label']}"
        facts.append({"key": "auth", "label": "인증 방식", "value": value})
    if not credentials.get("ready") or status.get("state") == state_mod.STATE_UNCONFIGURED:
        return facts
    if config.model:
        facts.append({"key": "model", "label": "모델", "value": config.model})
    if status.get("last_success_at"):
        facts.append({"key": "last_success", "label": "최근 성공", "value": status["last_success_at"], "kind": "time"})
    elif status.get("checked_at"):
        facts.append({"key": "checked", "label": "최근 확인", "value": status["checked_at"], "kind": "time"})
    tools = (caps or {}).get("tools")
    if tools in TOOLS_FACT:
        facts.append({"key": "tools", "label": "도구 호출", "value": TOOLS_FACT[tools]})
    if index and index.get("embed_status_label"):
        facts.append({"key": "search", "label": "문서 검색", "value": index["embed_status_label"]})
    return facts


def next_view(display: dict, config, status: dict, *, credentials: dict, index: dict | None = None) -> dict | None:
    """「다음 할 일」 한 문장과 자리(D-558). 정상이고 의미 검색도 섰으면 None — 할 일이 없다.

    연결이 정상인데 의미 검색이 서지 않았으면 서버에서 할 일 한 문장을 낸다(자리 `server` — 화면에는 단추가 없고 글만 선다, D-570).
    """
    key = display.get("key")
    method = config.method()
    account = bool(method is not None and method.account)
    if key == "unconfigured":
        problems = [p for p in status.get("problems") or [] if p]
        label = problems[0] if problems else DISPLAY_MESSAGES["unconfigured"]
        if method is None:
            action = NEXT_CONFIGURE
        elif not credentials.get("ready"):
            action = NEXT_LOGIN if account else NEXT_API_KEY
        elif not config.model:
            action = NEXT_MODEL
        else:
            action = NEXT_CONFIGURE
        return {"label": label, "action": action}
    if key == DISPLAY_AUTHENTICATING:
        return {"label": "ChatGPT 창에서 승인한 뒤 그 창의 주소를 붙여 넣으세요.", "action": NEXT_PASTE}
    if key == DISPLAY_VERIFYING:
        return {"label": "연결을 확인하고 있습니다. 끝나면 상태가 바뀝니다.", "action": NEXT_WAIT}
    if key == DISPLAY_OFF:
        return {"label": "AI 사용을 활성화하면 도우미와 요약이 답을 만듭니다.", "action": NEXT_ENABLE}
    if key == "unverified":
        return {"label": "연결 확인을 눌러 실제 답을 받는지 확인하세요.", "action": NEXT_VERIFY}
    if key == "degraded":
        return {"label": "잠시 뒤 연결 확인을 다시 누르세요.", "action": NEXT_VERIFY}
    if key == "reauth_required":
        return {"label": "ChatGPT 계정에 다시 로그인하세요.", "action": NEXT_LOGIN}
    if key == "error":
        if account:
            return {"label": "ChatGPT 계정에 다시 로그인한 뒤 연결 확인을 누르세요.", "action": NEXT_LOGIN}
        return {"label": "API 키를 확인해 다시 저장한 뒤 연결 확인을 누르세요.", "action": NEXT_API_KEY}
    hint = (index or {}).get("embed_hint")
    if key == "ok" and hint:
        return {"label": hint, "action": NEXT_SERVER}
    return None


def overview(db: Session, runtime, secrets, settings_cache, *, gateway=None, admin_user_id: str | None = None,
             now: datetime | None = None, settings=None) -> dict:
    """화면이 한 번에 받는 값. ``admin_user_id`` · ``now`` 가 있으면 그 관리자의 열린 로그인 시도를 「로그인 진행 중」으로 본다."""
    from app.ai.credentials import oauth
    from app.ai.credentials import state as state_mod

    config = runtime.config(db)
    values = settings_cache.current() if settings_cache is not None else {}
    outbound = runtime.outbound
    status = runtime.status(db)
    job = pending_verify(db)
    index = index_view(db, gateway, settings=settings)
    method = config.method()
    chatgpt = chatgpt_view(runtime, db)
    credentials = credentials_view(config, secrets, chatgpt=chatgpt)
    login = {"open": False, "transaction_id": None, "expires_at": None}
    if admin_user_id and now is not None:
        found = oauth.open_attempt(db, admin_user_id=admin_user_id, now=now)
        if found is not None:
            login = {"open": True, **found}
    login_open = bool(login["open"] and method is not None and method.account and not credentials["ready"])
    display = state_display(status, verifying=job is not None,
                            embed_available=(index or {}).get("semantic") if index else None,
                            login_open=login_open)
    caps = {"tools": state_mod.TOOLS_UNKNOWN, "checked_at": None, "model": None}
    if method is not None and not status.get("problems"):
        try:
            caps = state_mod.capabilities(db, config, secrets, secret_slot=method.secret_slot)
        except Exception:  # noqa: BLE001 - 모르면 모른다고 한다
            pass
    return {
        "config": {
            "generation_enabled": config.generation_enabled,
            "provider": config.provider,
            "auth_method": config.auth_method,
            "model": config.model,
            "timeout_seconds": config.timeout_seconds,
            "max_concurrency": config.max_concurrency,
        },
        "state": {
            **status,
            "verifying": job is not None,
            "verify_job_id": job.id if job is not None else None,
            "display": display,
        },
        # 상태 면은 이 셋만 그린다(D-558): 자격이 갖춰졌는가 · 그릴 줄 · 다음 할 일.
        "credentials": credentials,
        "facts": facts_view(config, status, credentials=credentials, caps=caps, index=index),
        "next": next_view(display, config, status, credentials=credentials, index=index),
        "login": login,
        "providers": providers_view(secrets, chatgpt_connected=bool(chatgpt["connected"])),
        "features": {key: values.get(key) is True for key in FEATURE_KEYS},
        "limits": {
            "timeout_seconds": [concurrency.MIN_TIMEOUT_SECONDS, concurrency.MAX_TIMEOUT_SECONDS],
            "max_concurrency": [1, concurrency.MAX_CONCURRENCY],
        },
        "chatgpt": chatgpt,
        "capabilities": {"tools": caps["tools"], "checked_at": caps.get("checked_at")},
        "index": index,
        "token_settings": {key: values.get(key) for key in TOKEN_SETTING_KEYS},
        # 화면이 「기술 정보」 접기 안에만 그리는 값들. 일반 화면에 토큰 만료 · 프록시 · 지문을 늘어놓지 않는다(5절).
        "technical": {
            # 프록시를 쓰면 `호스트:포트`. 시스템 설정의 프록시가 이 프로세스에 실제로 걸렸는지를 보인다.
            "proxy": getattr(outbound, "proxy_display", None) if outbound is not None else None,
            "account_label": chatgpt.get("account_label"),
            "access_expires_at": chatgpt.get("access_expires_at"),
            "refresh_expires_at": chatgpt.get("refresh_expires_at"),
            "reason_code": status.get("reason_code"),
            "tools_checked_model": caps.get("model"),
            "consecutive_failures": status.get("consecutive_failures"),
        },
        "proxy": getattr(outbound, "proxy_display", None) if outbound is not None else None,
    }


def validate_config(current, changes: dict) -> dict:
    """바꿀 값을 합친 뒤 **한 벌로** 검사한다. 저장할 `{설정 키: 값}` 을 돌려준다."""
    merged = {
        "generation_enabled": current.generation_enabled, "provider": current.provider,
        "auth_method": current.auth_method, "model": current.model,
        "timeout_seconds": current.timeout_seconds, "max_concurrency": current.max_concurrency,
    }
    for key, value in changes.items():
        if key in merged and value is not None:
            merged[key] = value.strip() if isinstance(value, str) else value
    provider = merged["provider"]
    spec = base.provider_spec(provider)
    if provider and spec is None:
        raise ValidationAppError("지원하지 않는 AI 제공자입니다.")
    if spec is not None:
        if not merged["auth_method"] and len(spec.auth_methods) == 1:
            # 방식이 하나뿐인 제공자는 사람이 고를 것이 없다.
            merged["auth_method"] = spec.auth_methods[0].key
        if merged["auth_method"] and spec.method(merged["auth_method"]) is None:
            raise ValidationAppError(f"{spec.label}에서 쓸 수 없는 인증 방식입니다.")
    elif merged["auth_method"]:
        raise ValidationAppError("제공자를 먼저 고르세요.")
    if len(merged["model"]) > MODEL_MAX_CHARS:
        raise ValidationAppError(f"모델 이름은 {MODEL_MAX_CHARS}자까지 넣을 수 있습니다.")
    timeout = merged["timeout_seconds"]
    if not isinstance(timeout, int) or not (concurrency.MIN_TIMEOUT_SECONDS <= timeout <= concurrency.MAX_TIMEOUT_SECONDS):
        raise ValidationAppError(
            f"제한 시간은 {concurrency.MIN_TIMEOUT_SECONDS}초에서 {concurrency.MAX_TIMEOUT_SECONDS}초 사이여야 합니다."
        )
    slots = merged["max_concurrency"]
    if not isinstance(slots, int) or not (1 <= slots <= concurrency.MAX_CONCURRENCY):
        raise ValidationAppError(f"동시 실행 수는 1에서 {concurrency.MAX_CONCURRENCY} 사이여야 합니다.")
    if merged["generation_enabled"] and not (merged["provider"] and merged["auth_method"] and merged["model"]):
        raise ValidationAppError("AI 사용을 활성화하려면 제공자, 인증 방식, 모델을 먼저 정하세요.")
    return {CONFIG_KEYS[k]: v for k, v in merged.items()}


def apply_config(db: Session, settings_cache, *, current, changes: dict, user_id: str, now: datetime) -> dict:
    """바뀐 값만 저장한다(설정 버전 기록이 남는다). 바뀐 `{설정 키: 새 값}` 을 돌려준다."""
    from app.settings.service import apply_setting

    target = validate_config(current, changes)
    values = settings_cache.current() if settings_cache is not None else {}
    changed = {}
    for key, value in target.items():
        if values.get(key) == value:
            continue
        apply_setting(db, settings_cache, key=key, value=value, updated_by=user_id, now=now)
        changed[key] = value
    return changed
