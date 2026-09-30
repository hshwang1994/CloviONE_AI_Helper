"""AI 연결 상태 — 여섯 가지와 그 사이의 전이 (계획 2.4 · 3.15, D-515).

## 상태

  unconfigured     미설정          제공자, 인증 방식, 모델, 자격 중 비어 있는 것이 있다       사용자 호출 막음
  unverified       확인 전         설정을 바꾼 뒤 아직 성공한 호출이 없다                      허용(첫 성공이 곧 확인이다)
  ok               정상            마지막 호출이나 확인이 성공했다                              허용
  degraded         일시 장애       시간 초과, 연결 실패, 5xx, 속도 제한처럼 다시 하면 될 실패     허용(성공하면 저절로 정상)
  reauth_required  재로그인 필요   계정 연결의 갱신이 끊겼다(ChatGPT, A2)                        막음
  error            인증·구성 오류  키 거부, 없는 모델, 허용 목록 밖, 저장된 키 없음              막음

「값이 있다」와 「동작한다」를 같은 상태로 보이지 않는다. 정상은 실제 성공 뒤에만 쓴다.

## 전이

  성공                         → 정상(어느 상태에서든)
  일시 실패                    → 일시 장애(정상, 확인 전, 일시 장애에서만). 마지막 성공 시각은 남기고 연속 실패 수를 올린다
  인증 실패(API 키), 구성 실패  → 인증·구성 오류
  설정 저장, 키 저장           → 확인 전(설정 지문이 바뀐다)

미설정은 저장하지 않는다 - 설정에서 매번 판정한다. 설정 지문(제공자, 인증 방식, 모델, 자격 파일의 수정 시각)이
저장된 지문과 다르면 옛 기록은 확인 전이다.

## 막힌 상태는 사람이 고칠 때까지 자동으로 다시 시도하지 않는다

키가 틀렸는데 매 요청이 제공자에 닿으면 사람의 요청이 매번 거절을 기다린다. 사람이 설정이나 키를 저장하면 지문이
바뀌어 확인 전으로 돌아간다. 일시 장애는 반대다 - 다음 실제 호출이 다시 시도한다(폭주는 `breaker.py` 가 막는다).

## 알림

  인증·구성 오류, 재로그인 필요로 바뀌면   즉시 관리자에게 한 번
  일시 장애                                연속 실패가 10 번에 이르면 한 번(짧은 흔들림으로 알림을 뿌리지 않는다)
  위 셋 뒤에 정상으로 돌아오면             「복구됐다」 한 번
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime

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
    STATE_ERROR: "인증 또는 구성 오류",
}

BLOCKING_STATES = frozenset({STATE_UNCONFIGURED, STATE_REAUTH, STATE_ERROR})
HARD_STATES = frozenset({STATE_REAUTH, STATE_ERROR})
DEGRADED_NOTIFY_AFTER = 10

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
}
FALLBACK_REASON = "AI 호출이 실패했습니다."

STATE_MESSAGES: dict[str, str] = {
    STATE_UNCONFIGURED: "AI 제공자, 인증, 모델 중 아직 정하지 않은 것이 있습니다.",
    STATE_UNVERIFIED: "설정을 저장했지만 아직 연결을 확인하지 않았습니다. 연결 확인을 눌러 보세요.",
    STATE_OK: "마지막 호출이 성공했습니다.",
    STATE_DEGRADED: "제공자가 잠시 응답하지 못하고 있습니다. 다음 호출이 다시 시도하고, 성공하면 저절로 정상으로 돌아옵니다.",
    STATE_REAUTH: "계정 연결이 끊겼습니다. 다시 로그인해야 합니다.",
    STATE_ERROR: "AI 연결을 쓸 수 없습니다. 아래 까닭을 고친 뒤 연결 확인을 누르세요.",
}


def reason_text(code: str | None) -> str | None:
    if not code:
        return None
    if code.startswith("http_5"):
        return "제공자가 일시적으로 응답하지 못했습니다."
    return REASON_TEXTS.get(code, FALLBACK_REASON)


def _secret_marker(secrets, slot: str | None) -> str:
    """자격 파일의 수정 시각. 키를 새로 저장하면 바뀐다 - 키 값 자체는 지문에 넣지 않는다."""
    if not slot or secrets is None:
        return "none"
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


def view(db: Session, config, secrets, *, secret_slot: str | None, problems: list[str]) -> dict:
    """지금 상태 한 벌. 설정만 읽고 제공자에 붙지 않는다."""
    if problems:
        return {
            "state": STATE_UNCONFIGURED, "label": STATE_LABELS[STATE_UNCONFIGURED],
            "message": STATE_MESSAGES[STATE_UNCONFIGURED], "problems": list(problems),
            "reason_code": None, "reason": None, "checked_at": None, "last_success_at": None,
            "consecutive_failures": 0, "blocking": True,
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
        # 옛 설정의 기록이라도 마지막으로 확인한 시각과 성공 시각은 보인다 - 화면이 「언제 마지막으로 됐나」를 말한다.
        "checked_at": row.last_verified_at.isoformat() if row is not None and row.last_verified_at else None,
        "last_success_at": row.last_success_at.isoformat() if row is not None and row.last_success_at else None,
        "consecutive_failures": 0 if stale else int(row.consecutive_failures or 0),
        "blocking": state in BLOCKING_STATES,
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
        # 인증, 구성 실패. 계정 연결의 갱신 실패는 A2 가 재로그인 필요로 보낸다.
        row.status = STATE_REAUTH if result == "reauth" else STATE_ERROR
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


def _notify_if_needed(db: Session, row, *, now: datetime) -> None:
    """관리자 알림 - 상태가 알릴 만큼 바뀌었을 때 한 번만(머리말)."""
    target = None
    if row.status in HARD_STATES:
        target = row.status
    elif row.status == STATE_DEGRADED and int(row.consecutive_failures or 0) >= DEGRADED_NOTIFY_AFTER:
        target = STATE_DEGRADED
    elif row.status == STATE_OK and row.last_notified_state in (STATE_ERROR, STATE_REAUTH, STATE_DEGRADED):
        target = STATE_OK
    if target is None or target == row.last_notified_state:
        return
    from app.ai.providers.base import provider_spec
    from app.notifications.service import notify_admins

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
        notify_admins(db, type_="ai_provider_state", title=title, body=body, related=None, now=now)
    except Exception:  # noqa: BLE001 - 알림이 상태 기록을 막으면 안 된다
        logger.exception("AI 연결 상태 알림에 실패했다")
        return
    row.last_notified_state = target
    db.flush()
