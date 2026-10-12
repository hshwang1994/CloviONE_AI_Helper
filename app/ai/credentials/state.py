"""AI 연결 상태 — 여섯 가지와 그 사이의 전이 (계획 2.4 · 3.15, D-515).

## 상태

  unconfigured     미설정          제공자, 인증 방식, 모델, 자격 중 비어 있는 것이 있다       사용자 호출 막음
  unverified       확인 전         설정을 바꾼 뒤 아직 성공한 호출이 없다                      허용(첫 성공이 곧 확인이다)
  ok               정상            마지막 호출이나 확인이 성공했다                              허용
  degraded         일시 장애       시간 초과, 연결 실패, 5xx, 속도 제한처럼 다시 하면 될 실패     허용(성공하면 저절로 정상)
  reauth_required  재로그인 필요   계정 연결의 갱신이 끊겼다(ChatGPT)                            막음
  error            인증·구성 오류  키 거부, 없는 모델, 허용 목록 밖, 저장된 키 없음              막음

「값이 있다」와 「동작한다」를 같은 상태로 보이지 않는다. 정상은 실제 성공 뒤에만 쓴다.

## 전이

  성공                         → 정상(어느 상태에서든)
  일시 실패                    → 일시 장애(정상, 확인 전, 일시 장애에서만). 마지막 성공 시각은 남기고 연속 실패 수를 올린다
  인증 실패(API 키), 구성 실패  → 인증·구성 오류
  설정 저장, 키 저장           → 확인 전(설정 지문이 바뀐다)

미설정은 저장하지 않는다 - 설정에서 매번 판정한다. 설정 지문(제공자, 인증 방식, 모델, 자격 표식)이 저장된 지문과
다르면 옛 기록은 확인 전이다. 자격 표식은 API 키면 키 파일의 수정 시각이고, 계정 연결이면 묶음의 `login_id` 다 -
토큰 갱신은 한 시간마다 묶음을 다시 쓰지만 로그인은 그대로라 상태가 확인 전으로 돌아가면 안 된다(D-516).

## 막힌 상태는 사람이 고칠 때까지 자동으로 다시 시도하지 않는다

키가 틀렸는데 매 요청이 제공자에 닿으면 사람의 요청이 매번 거절을 기다린다. 사람이 설정이나 키를 저장하면 지문이
바뀌어 확인 전으로 돌아간다. 일시 장애는 반대다 - 다음 실제 호출이 다시 시도한다(폭주는 `breaker.py` 가 막는다).

## 알림

  인증·구성 오류, 재로그인 필요로 바뀌면   즉시 관리자에게 한 번
  일시 장애                                연속 실패가 10 번에 이르거나 30분 넘게 이어지면 한 번(짧은 흔들림으로 알림을
                                           뿌리지 않는다. 30분은 주기 확인 `app/ai/health.py` 가 잰다)
  위 셋 뒤에 정상으로 돌아오면             「복구됐다」 한 번
  계정 연결의 갱신 토큰이 곧 끝나면         한 번(갱신 토큰을 새로 받을 때마다 다시 셀 수 있다)
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger("app.ai.state")

STATE_UNCONFIGURED = "unconfigured"
STATE_UNVERIFIED = "unverified"
STATE_OK = "ok"
STATE_DEGRADED = "degraded"
STATE_REAUTH = "reauth_required"
STATE_ERROR = "error"

STATE_LABELS: dict[str, str] = {
    STATE_UNCONFIGURED: "미설정",
    STATE_UNVERIFIED: "확인 전",
    STATE_OK: "정상",
    STATE_DEGRADED: "일시 장애",
    STATE_REAUTH: "재로그인 필요",
    STATE_ERROR: "연결 오류",
}

BLOCKING_STATES = frozenset({STATE_UNCONFIGURED, STATE_REAUTH, STATE_ERROR})
HARD_STATES = frozenset({STATE_REAUTH, STATE_ERROR})
DEGRADED_NOTIFY_AFTER = 10
DEGRADED_NOTIFY_AFTER_TIME = timedelta(minutes=30)

RESULT_OK = "ok"

# 까닭 코드 → 관리자 화면의 한 문장. 제공자가 준 원문은 싣지 않는다(`app/ai/providers/base.py`).
REASON_TEXTS: dict[str, str] = {
    "api_key_missing": "API 키가 저장되어 있지 않습니다.",
    "http_401": "API 키가 거부되었습니다. 키를 다시 넣으세요.",
    "http_403": "이 API 키로는 요청할 권한이 없습니다. 키의 권한을 확인하세요.",
    "model_not_found": "모델을 찾지 못했습니다. 모델을 다시 골라야 합니다.",
    "host_not_allowed": "제공자 주소가 서버의 허용 목록에 없습니다.",
    "timeout": "제공자가 제한 시간 안에 답하지 않았습니다.",
    "connect": "제공자에 연결하지 못했습니다.",
    "http_429": "제공자의 속도 제한에 걸렸습니다.",
    "http_529": "제공자가 지금 과부하 상태입니다.",
    "breaker_open": "실패가 이어져 잠시 호출을 멈췄습니다. 곧 다시 시도합니다.",
    "proxy_connect": "프록시를 거쳐 제공자에 연결하지 못했습니다. 프록시 설정을 확인하세요.",
    "stream_incomplete": "제공자의 응답이 도중에 끊겼습니다.",
    # OpenAI (D-516)
    "insufficient_quota": "OpenAI API 계정의 크레딧이 없습니다. OpenAI 결제 설정을 확인하세요.",
    "plan_usage_limit": "ChatGPT 요금제 사용량 한도에 닿았습니다. 사용량 관리에서 한도를 확인하세요.",
    "plan_usage_unavailable": "ChatGPT 요금제 사용을 지금 확인할 수 없습니다. 잠시 뒤 다시 시도합니다.",
    "plan_not_eligible": "연결한 ChatGPT 계정으로는 이 앱에서 요금제를 쓸 수 없습니다. 다른 계정이나 API 키로 연결하세요.",
    "account_rejected": "ChatGPT 계정 연결이 거부되었습니다. 다시 로그인하세요.",
    "account_forbidden": "ChatGPT 계정으로 이 요청을 할 권한이 없습니다. 다시 로그인하거나 API 키로 연결하세요.",
    "account_not_connected": "ChatGPT 계정이 연결되어 있지 않습니다. 다시 로그인하세요.",
    "account_disconnected": "ChatGPT 계정 연결이 끊겼습니다. 다시 로그인하세요.",
    "invalid_client": "ChatGPT 연결 정보가 더 이상 유효하지 않습니다. 다시 로그인하세요.",
    "secret_store_unavailable": "비밀 저장 도우미에 연결할 수 없어 새 토큰을 저장하지 못했습니다.",
    "refresh_busy": "다른 요청이 토큰을 갱신하고 있습니다. 잠시 뒤 다시 시도합니다.",
}
# 갱신 토큰이 거절된 까닭들 - 사람에게는 모두 같은 한 문장이다(공식 오류표의 재로그인 목록).
for _code in ("invalid_grant", "invalid_refresh_token", "token_expired", "refresh_token_expired",
              "refresh_token_invalidated", "refresh_token_reused"):
    REASON_TEXTS[_code] = "ChatGPT 계정 연결이 만료되었습니다. 다시 로그인하세요."
FALLBACK_REASON = "AI 호출이 실패했습니다."

STATE_MESSAGES: dict[str, str] = {
    STATE_UNCONFIGURED: "AI 제공자, 인증, 모델 중 아직 정하지 않은 것이 있습니다.",
    STATE_UNVERIFIED: "아직 연결을 확인하지 않았습니다.",
    STATE_OK: "마지막 호출이 성공했습니다.",
    STATE_DEGRADED: "제공자가 잠시 응답하지 못하고 있습니다. 다음 호출이 다시 시도하고, 성공하면 저절로 정상으로 돌아옵니다.",
    STATE_REAUTH: "계정 연결이 끊겼습니다. 다시 로그인해야 합니다.",
    STATE_ERROR: "AI 연결을 쓸 수 없습니다.",
}


def reason_text(code: str | None) -> str | None:
    if not code:
        return None
    if code.startswith("http_5"):
        return "제공자가 일시적으로 응답하지 못했습니다."
    return REASON_TEXTS.get(code, FALLBACK_REASON)


def _secret_marker(secrets, slot: str | None) -> str:
    """자격 표식. API 키면 파일의 수정 시각이고(키 값 자체는 넣지 않는다), 계정 연결이면 묶음의 `login_id` 다."""
    if not slot or secrets is None:
        return "none"
    from app.core.secret_slots import KIND_JSON, SECRET_SLOTS

    spec = SECRET_SLOTS.get(slot)
    if spec is not None and spec.kind == KIND_JSON:
        try:
            value = secrets.get(slot)
        except Exception:  # noqa: BLE001
            return "unknown"
        if value is None:
            return "absent"
        try:
            data = json.loads(value.reveal())
        except ValueError:
            return "unreadable"
        return "login:" + str(data.get("login_id") or "none") if isinstance(data, dict) else "unreadable"
    try:
        path = secrets.directory / slot
        return str(path.stat().st_mtime_ns) if path.is_file() else "absent"
    except (OSError, AttributeError):
        return "unknown"


def fingerprint(config, secrets, secret_slot: str | None) -> str:
    raw = "|".join([config.provider, config.auth_method, config.model, _secret_marker(secrets, secret_slot)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _row(db: Session, provider: str, auth_method: str, *, lock: bool = False):
    from app.ai.models import AiCredentialState

    stmt = select(AiCredentialState).where(
        AiCredentialState.provider == provider, AiCredentialState.auth_method == auth_method,
    )
    if lock:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def account_view(row) -> dict | None:
    """계정 연결 칸(표시용). 토큰은 없다 - 계정 이름과 만료 시각만 있다."""
    if row is None:
        return None
    return {
        "label": row.account_label,
        "access_expires_at": row.access_expires_at.isoformat() if row.access_expires_at else None,
        "refresh_expires_at": row.refresh_expires_at.isoformat() if row.refresh_expires_at else None,
        "refresh_obtained_at": row.refresh_obtained_at.isoformat() if row.refresh_obtained_at else None,
        "expiry_source": row.expiry_source,
    }


def view(db: Session, config, secrets, *, secret_slot: str | None, problems: list[str]) -> dict:
    """지금 상태 한 벌. 설정만 읽고 제공자에 붙지 않는다."""
    if problems:
        return {
            "state": STATE_UNCONFIGURED, "label": STATE_LABELS[STATE_UNCONFIGURED],
            "message": STATE_MESSAGES[STATE_UNCONFIGURED], "problems": list(problems),
            "reason_code": None, "reason": None, "checked_at": None, "last_success_at": None,
            "consecutive_failures": 0, "blocking": True,
            "account": None,
        }
    row = _row(db, config.provider, config.auth_method)
    stale = row is None or row.config_fingerprint != fingerprint(config, secrets, secret_slot)
    state = STATE_UNVERIFIED if stale else row.status
    return {
        "state": state,
        "label": STATE_LABELS.get(state, state),
        "message": STATE_MESSAGES.get(state, ""),
        "problems": [],
        "reason_code": None if stale else row.reason_code,
        "reason": None if stale else row.reason_text,
        # 지금 설정 지문의 기록만 보인다(D-558). 지문이 바뀌었으면(키 · 로그인 · 모델이 바뀜) 옛 설정의 「최근 성공」이
        # 새 설정의 성공으로 읽히므로 비운다 — 「미설정」인데 「최근 성공 14:05」가 서던 자리다.
        "checked_at": None if stale else (row.last_verified_at.isoformat() if row.last_verified_at else None),
        "last_success_at": None if stale else (row.last_success_at.isoformat() if row.last_success_at else None),
        "consecutive_failures": 0 if stale else int(row.consecutive_failures or 0),
        "blocking": state in BLOCKING_STATES,
        "account": account_view(row),
    }


def record(db: Session, config, secrets, *, secret_slot: str | None, result: str, code: str | None,
           now: datetime, verified: bool = False) -> str:
    """호출이나 확인 한 번의 결과를 적는다. 바뀐 뒤의 상태를 돌려준다.

    ``result`` 는 `ok` 이거나 실패 종류(`app/ai/providers/base.py::ERROR_*`)다. 이 연결 상태와 무관한 실패(이 요청만
    틀렸다, 답이 비었다)는 상태를 바꾸지 않는다.
    """
    from app.ai.models import AiCredentialState
    from app.ai.providers import base

    if result in (base.ERROR_REQUEST, base.ERROR_EMPTY):
        return view(db, config, secrets, secret_slot=secret_slot, problems=[])["state"]
    stamp = fingerprint(config, secrets, secret_slot)
    row = _row(db, config.provider, config.auth_method, lock=True)
    if row is None:
        row = AiCredentialState(
            provider=config.provider, auth_method=config.auth_method, status=STATE_UNVERIFIED,
            config_fingerprint=stamp, consecutive_failures=0, created_at=now, updated_at=now,
        )
        db.add(row)
    if row.config_fingerprint != stamp:
        # 설정이 바뀌었다 - 옛 설정의 실패 기록을 새 설정에 물려주지 않는다.
        row.config_fingerprint = stamp
        row.status = STATE_UNVERIFIED
        row.consecutive_failures = 0
        row.reason_code = None
        row.reason_text = None
    before = row.status
    if result == RESULT_OK:
        row.status = STATE_OK
        row.consecutive_failures = 0
        row.reason_code = None
        row.reason_text = None
        row.last_success_at = now
    elif result == base.ERROR_TRANSIENT:
        if row.status in (STATE_OK, STATE_UNVERIFIED, STATE_DEGRADED):
            row.status = STATE_DEGRADED
        row.consecutive_failures = int(row.consecutive_failures or 0) + 1
        row.reason_code = code
        row.reason_text = reason_text(code)
        row.last_failure_at = now
    else:
        # 인증, 구성 실패. 계정 연결의 갱신 실패와 거절은 재로그인 필요다.
        row.status = STATE_REAUTH if result == base.ERROR_REAUTH else STATE_ERROR
        row.consecutive_failures = int(row.consecutive_failures or 0) + 1
        row.reason_code = code
        row.reason_text = reason_text(code)
        row.last_failure_at = now
    if verified:
        row.last_verified_at = now
    if row.status != before:
        row.last_changed_at = now
    row.updated_at = now
    db.flush()
    _notify_if_needed(db, row, now=now)
    return row.status


def _degraded_long(row, now: datetime) -> bool:
    since = row.last_changed_at
    return since is not None and now - since >= DEGRADED_NOTIFY_AFTER_TIME


def _notify_if_needed(db: Session, row, *, now: datetime) -> None:
    """관리자 알림 - 상태가 알릴 만큼 바뀌었을 때 한 번만(머리말)."""
    target = None
    if row.status in HARD_STATES:
        target = row.status
    elif row.status == STATE_DEGRADED and (
        int(row.consecutive_failures or 0) >= DEGRADED_NOTIFY_AFTER or _degraded_long(row, now)
    ):
        target = STATE_DEGRADED
    elif row.status == STATE_OK and row.last_notified_state in (STATE_ERROR, STATE_REAUTH, STATE_DEGRADED):
        target = STATE_OK
    if target is None or target == row.last_notified_state:
        return
    from app.ai.providers.base import provider_spec

    spec = provider_spec(row.provider)
    name = spec.label if spec else row.provider
    if target == STATE_OK:
        title, body = f"{name} AI 연결이 복구되었습니다", "AI 호출이 다시 성공했습니다."
    elif target == STATE_DEGRADED:
        title = f"{name} AI 연결이 불안정합니다"
        body = f"호출이 {row.consecutive_failures}번 이어서 실패했습니다. {row.reason_text or ''}".strip()
    else:
        title = f"{name} AI 연결을 쓸 수 없습니다"
        body = row.reason_text or STATE_MESSAGES[target]
    try:
        notify_ai_admins(db, title=title, body=body, now=now, context={
            "provider": row.provider, "auth_method": row.auth_method, "ai_state": target,
        })
    except Exception:  # noqa: BLE001 - 알림이 상태 기록을 막으면 안 된다
        logger.exception("AI 연결 상태 알림에 실패했다")
        return
    row.last_notified_state = target
    db.flush()


def credential_row(db: Session, provider: str, auth_method: str):
    """그 쌍의 행(없으면 None). 읽기만 한다."""
    return _row(db, provider, auth_method)


def notify_if_needed(db: Session, provider: str, auth_method: str, *, now: datetime) -> None:
    """주기 확인이 부른다 - 일시 장애가 30분 넘게 이어진 것처럼 호출 없이도 알릴 만한 상태를 알린다."""
    row = _row(db, provider, auth_method)
    if row is not None:
        _notify_if_needed(db, row, now=now)


# ── 제공자 능력 (D-535) ─────────────────────────────────────────────────────

TOOLS_OK = "ok"
TOOLS_UNSUPPORTED = "unsupported"
TOOLS_UNKNOWN = "unknown"
_TOOLS_VALUES = frozenset({TOOLS_OK, TOOLS_UNSUPPORTED})


def capabilities(db: Session, config, secrets, *, secret_slot: str | None) -> dict:
    """지금 설정(지문)에서 재 둔 능력. 다른 지문(모델 · 키 · 로그인이 바뀐 뒤)의 기록은 「모름」으로 읽는다.

    도구를 받는지는 연결 확인의 도구 시험이나 도우미의 첫 라운드가 잰다. 모르면 도구를 보내 본다 - 거절되면 그때 적는다.
    """
    unknown = {"tools": TOOLS_UNKNOWN, "checked_at": None, "model": None}
    row = _row(db, config.provider, config.auth_method)
    if row is None or not row.capabilities_json:
        return unknown
    try:
        data = json.loads(row.capabilities_json)
    except ValueError:
        return unknown
    if not isinstance(data, dict) or data.get("fingerprint") != fingerprint(config, secrets, secret_slot):
        return unknown
    tools = data.get("tools")
    return {
        "tools": tools if tools in _TOOLS_VALUES else TOOLS_UNKNOWN,
        "checked_at": data.get("checked_at") if isinstance(data.get("checked_at"), str) else None,
        "model": data.get("model") if isinstance(data.get("model"), str) else None,
    }


def set_capability(db: Session, config, secrets, *, secret_slot: str | None, tools: str, now: datetime) -> None:
    """능력 하나를 지금 지문으로 적는다. 연결 상태(status)는 바꾸지 않는다 - 도구를 거절하는 모델도 답은 한다."""
    from app.ai.models import AiCredentialState

    if tools not in _TOOLS_VALUES:
        raise ValueError(f"알 수 없는 도구 능력 값: {tools}")
    stamp = fingerprint(config, secrets, secret_slot)
    row = _row(db, config.provider, config.auth_method, lock=True)
    if row is None:
        row = AiCredentialState(
            provider=config.provider, auth_method=config.auth_method, status=STATE_UNVERIFIED,
            config_fingerprint=stamp, consecutive_failures=0, created_at=now, updated_at=now,
        )
        db.add(row)
    row.capabilities_json = json.dumps(
        {"tools": tools, "model": config.model, "checked_at": now.isoformat(), "fingerprint": stamp},
        ensure_ascii=False,
    )
    row.updated_at = now
    db.flush()


# ── 계정 연결 칸 (D-516) ─────────────────────────────────────────────────────


def account_row(db: Session, provider: str, auth_method: str, *, now: datetime):
    """그 쌍의 행. 없으면 만든다 - 로그인은 설정을 저장하기 전에도 할 수 있어 행이 먼저 필요하다.

    새 행의 지문은 비어 있다. `view` 는 그 행을 확인 전으로 읽고, 첫 호출이 지문을 채운다.
    """
    from app.ai.models import AiCredentialState

    row = _row(db, provider, auth_method, lock=True)
    if row is None:
        row = AiCredentialState(
            provider=provider, auth_method=auth_method, status=STATE_UNVERIFIED, config_fingerprint="",
            consecutive_failures=0, created_at=now, updated_at=now,
        )
        db.add(row)
        db.flush()
    return row


def host_id(db: Session, provider: str, auth_method: str, *, now: datetime) -> str:
    """이 설치의 `ext_agent_host_id`. 한 번 만들면 바꾸지 않는다 - 공식 안내가 호스트마다 고정된 값을 요구한다."""
    row = account_row(db, provider, auth_method, now=now)
    if not row.ext_agent_host_id:
        row.ext_agent_host_id = f"urn:uuid:{uuid.uuid4()}"
        row.updated_at = now
        db.flush()
    return row.ext_agent_host_id


ACCOUNT_FIELDS = frozenset({
    "account_label", "client_id", "access_expires_at", "refresh_obtained_at", "refresh_expires_at", "expiry_source",
    "refresh_warned_at",
})


def update_account(db: Session, provider: str, auth_method: str, *, now: datetime, **fields):
    """계정 칸만 고친다. 연결 상태(`status`)는 건드리지 않는다 - 상태는 실제 호출의 결과만 바꾼다."""
    unknown = set(fields) - ACCOUNT_FIELDS
    if unknown:
        raise ValueError(f"계정 칸이 아니다: {sorted(unknown)}")
    row = account_row(db, provider, auth_method, now=now)
    for key, value in fields.items():
        setattr(row, key, value)
    row.updated_at = now
    db.flush()
    return row


REFRESH_WARN_AHEAD = timedelta(days=5)


def warn_if_refresh_ending(db: Session, provider: str, auth_method: str, *, now: datetime) -> bool:
    """갱신 토큰이 곧 끝나면 관리자에게 한 번 알린다. 알렸으면 참이다.

    한 갱신 토큰에 한 번이다: 갱신 토큰을 새로 받으면(`refresh_obtained_at` 이 알린 시각보다 뒤) 다시 셀 수 있다.
    """
    row = _row(db, provider, auth_method)
    if row is None or row.refresh_expires_at is None:
        return False
    if row.refresh_expires_at - now > REFRESH_WARN_AHEAD:
        return False
    if row.refresh_warned_at is not None and (
        row.refresh_obtained_at is None or row.refresh_warned_at >= row.refresh_obtained_at
    ):
        return False
    days = max(0, (row.refresh_expires_at - now).days)
    body = (f"ChatGPT 계정 연결이 {days}일 안에 끝납니다. 계속 쓰려면 AI 설정에서 다시 로그인하세요."
            if days else "ChatGPT 계정 연결이 곧 끝납니다. 계속 쓰려면 AI 설정에서 다시 로그인하세요.")
    try:
        notify_ai_admins(db, title="ChatGPT 계정 연결이 곧 끝납니다", body=body, now=now, context={
            "provider": provider, "auth_method": auth_method, "ai_state": "refresh_expiring",
        })
    except Exception:  # noqa: BLE001
        logger.exception("ChatGPT 연결 만료 알림에 실패했다")
        return False
    row.refresh_warned_at = now
    db.flush()
    return True


def notify_ai_admins(db: Session, *, title: str, body: str, now: datetime, context: dict) -> int:
    """AI 연결 알림은 **시스템 관리자에게만** 간다 - AI 설정을 고칠 수 있는 사람이 그들뿐이다(D-516).

    부서 관리자에게 보내면 열 수 없는 화면을 가리키는 알림이 된다. 링크는 AI 설정 화면이다(`ai_config`). 메일로도
    받기로 한 사람에게는 메일이 가고, 보내기 직전에 상태가 바뀌었으면 가지 않는다(`app/mail/relevance.py`).
    """
    from app.notifications.models import AUDIENCE_ADMIN
    from app.notifications.service import notify_user
    from app.users.models import ROLE_SYSTEM_ADMIN, User

    people = db.execute(
        select(User.id).where(User.role == ROLE_SYSTEM_ADMIN, User.active.is_(True))
    ).scalars().all()
    if not people:
        logger.error("AI 연결 알림을 받을 활성 시스템 관리자가 없다")
    for user_id in people:
        notify_user(
            db, user_id, type_="ai_provider_state", title=title, body=body, related=("ai_config", "generation"),
            now=now, audience=AUDIENCE_ADMIN, recipient_role=ROLE_SYSTEM_ADMIN, context=context,
        )
    return len(people)
