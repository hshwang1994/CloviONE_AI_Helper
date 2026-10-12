"""메일 설정의 일곱 단계와 「다음 할 일」 (기능 개선 회차 P4, D-560).

화면은 이 순서로 선다 — 사용자가 가진 것에서 출발해 실제 수신까지 한 줄로 이어진다:

  1 enable            메일 발송 켜기
  2 method            보내는 방법 고르기(로컬 릴레이가 기본 — 계정이 필요 없다)
  3 inputs            보내는 사람과 방식별 정보 입력
  4 applied           저장과 적용(로컬 릴레이면 구성 요소가 켜지고 저장한 설정이 적용됐는가)
  5 verified          연결 확인(메일을 보내지 않는다)
  6 test_sent         시험 메일(다음 서버가 접수함 — 도착이 아니다, D-555)
  7 inbox_confirmed   받은 편지함 확인(사람이 기록하는 사실)

단계마다 상태 넷 — `done` · `current` · `todo` · `blocked`(막힌 까닭이 있다). 「다음 할 일」은 첫 `current` 또는 `blocked` 다.
네트워크를 쓰지 않는다 — 전부 저장된 설정 · 건강 상태 · 릴레이 상태 · 발송 기록에서 계산한다(`health.py` 와 같은 규율).
받은 편지함 확인은 시험 메일 한 통에 대해 사람이 기록한다(`record_inbox`) — 제품은 도착을 잴 수 없다.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.mail.config import MODE_LOCAL_RELAY, MailConfig, configuration_problems
from app.mail.models import MAIL_FAILED, MAIL_QUEUED, MAIL_RETRYING, MAIL_SENT, MailDelivery

INBOX_COMPONENT = "mail_inbox"

DONE = "done"
CURRENT = "current"
TODO = "todo"
BLOCKED = "blocked"

STEP_ENABLE = "enable"
STEP_METHOD = "method"
STEP_INPUTS = "inputs"
STEP_APPLIED = "applied"
STEP_VERIFIED = "verified"
STEP_TEST_SENT = "test_sent"
STEP_INBOX = "inbox_confirmed"

STEPS: tuple[tuple[str, str], ...] = (
    (STEP_ENABLE, "메일 발송 켜기"),
    (STEP_METHOD, "보내는 방법 고르기"),
    (STEP_INPUTS, "보내는 사람과 방식별 정보 입력"),
    (STEP_APPLIED, "저장과 적용"),
    (STEP_VERIFIED, "연결 확인"),
    (STEP_TEST_SENT, "시험 메일"),
    (STEP_INBOX, "받은 편지함 확인"),
)
#: 단계가 가리키는 화면 자리. 모양은 화면이 정한다(구획으로 옮기거나 머리 단추를 누른다).
ANCHORS = {
    STEP_ENABLE: "section:enable", STEP_METHOD: "section:method", STEP_INPUTS: "section:inputs",
    STEP_APPLIED: "section:relay", STEP_VERIFIED: "action:verify", STEP_TEST_SENT: "action:test",
    STEP_INBOX: "action:inbox",
}
#: 「발송이 꺼져 있다」 · 「로컬 릴레이가 아직 켜지지 않았다」 는 입력 문제가 아니라 1단계 · 4단계의 일이다.
_ENABLE_MARK = "메일 발송이 꺼져"
_RELAY_OFF_MARK = "로컬 릴레이가 아직 켜지지"

HINTS = {
    STEP_ENABLE: "메일 발송을 켜고 저장하세요.",
    STEP_METHOD: "보내는 방법을 고르세요. 메일 계정이 없으면 로컬 릴레이가 기본입니다.",
    STEP_APPLIED: "로컬 릴레이를 활성화하세요.",
    "applied_stale": "저장한 설정을 로컬 릴레이에 다시 적용하세요.",
    STEP_VERIFIED: "연결 확인을 누르세요. 메일은 보내지 않습니다.",
    STEP_TEST_SENT: "시험 메일을 보내세요.",
    "test_sending": "시험 메일을 보내는 중입니다.",
    STEP_INBOX: "받은 편지함에서 시험 메일을 확인한 뒤 「받았습니다」를 누르세요.",
    "inbox_bounced": "수신측이 거부했습니다. 진단의 요청문을 담당자에게 보낸 뒤 시험 메일을 다시 보내세요.",
    "inbox_missing": "받은 편지함에 없다고 기록했습니다. 정크함과 격리함을 본 뒤 진단을 확인하세요.",
}


def _step(key: str, state: str, hint: str | None = None) -> dict:
    label = dict(STEPS)[key]
    return {"key": key, "label": label, "state": state, "hint": hint, "anchor": ANCHORS[key]}


def latest_test(db: Session) -> dict | None:
    """가장 새 시험 메일 한 통(발송 기록). 없으면 None."""
    from app.mail.renderers import KIND_TEST
    from app.mail.service import summarize_failure

    row = db.execute(
        select(MailDelivery).where(MailDelivery.kind == KIND_TEST).order_by(MailDelivery.created_at.desc()).limit(1)
    ).scalars().first()
    if row is None:
        return None
    return {
        "id": row.id, "status": row.status, "to_email": row.to_email, "created_at": row.created_at.isoformat(),
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "error_summary": summarize_failure(row.last_error) if row.status == MAIL_FAILED else None,
        "remote_status": getattr(row, "remote_status", None),
    }


def load_inbox(db: Session) -> dict | None:
    """사람이 기록한 받은 편지함 확인(`sync_status["mail_inbox"]`). 없으면 None."""
    from app.observability.models import SyncStatus

    row = db.get(SyncStatus, INBOX_COMPONENT)
    if row is None or not row.detail_json:
        return None
    try:
        value = json.loads(row.detail_json)
    except ValueError:
        return None
    return value if isinstance(value, dict) and value.get("delivery_id") else None


def record_inbox(db: Session, *, delivery_id: str, received: bool, user_id: str | None, now: datetime) -> dict:
    """시험 메일 한 통에 대한 사람의 기록 — 받았다 · 못 받았다. 한 행이고 새 기록이 옛 기록을 덮는다."""
    from app.observability.models import SYNC_ERROR, SYNC_OK
    from app.observability.service import upsert_sync_status

    detail = {"delivery_id": delivery_id, "received": bool(received), "by": user_id, "at": now.isoformat()}
    upsert_sync_status(db, INBOX_COMPONENT, status=SYNC_OK if received else SYNC_ERROR, now=now,
                       error=None if received else "받은 편지함에서 찾지 못했습니다.", detail=detail)
    return detail


def compute(config: MailConfig, secret_provider, *, health: dict, relay: dict | None, test: dict | None,
            inbox: dict | None) -> dict:
    """일곱 단계의 상태와 다음 할 일. 네트워크를 쓰지 않는다(머리말)."""
    local = getattr(config, "mode", "external") == MODE_LOCAL_RELAY
    problems = configuration_problems(config, secret_provider)
    input_problems = [p for p in problems if _ENABLE_MARK not in p and _RELAY_OFF_MARK not in p]
    relay_off = any(_RELAY_OFF_MARK in p for p in problems)
    component = (relay or {}).get("component") or {}
    steps: list[dict] = []

    enabled = bool(config.enabled)
    steps.append(_step(STEP_ENABLE, DONE if enabled else CURRENT, None if enabled else HINTS[STEP_ENABLE]))
    steps.append(_step(STEP_METHOD, DONE if enabled else TODO, None if enabled else HINTS[STEP_METHOD]))

    if not enabled:
        inputs_state, inputs_hint = TODO, None
    elif input_problems:
        inputs_state, inputs_hint = CURRENT, input_problems[0]
    else:
        inputs_state, inputs_hint = DONE, None
    steps.append(_step(STEP_INPUTS, inputs_state, inputs_hint))

    if inputs_state != DONE:
        applied_state, applied_hint = TODO, None
    elif not local:
        applied_state, applied_hint = DONE, None
    elif component.get("state") == "running" and not component.get("stale") and not relay_off:
        applied_state, applied_hint = DONE, None
    elif component.get("state") == "running" and component.get("stale"):
        applied_state, applied_hint = CURRENT, HINTS["applied_stale"]
    elif component.get("state") in ("not_installed", "foreign", "unavailable") and component.get("message"):
        applied_state, applied_hint = BLOCKED, component["message"]
    else:
        applied_state, applied_hint = CURRENT, HINTS[STEP_APPLIED]
    steps.append(_step(STEP_APPLIED, applied_state, applied_hint))

    state = (health or {}).get("state")
    if applied_state != DONE:
        verified_state, verified_hint = TODO, None
    elif state == "ok":
        verified_state, verified_hint = DONE, None
    elif state == "failing":
        verified_state = BLOCKED
        verified_hint = " ".join(p for p in ((health or {}).get("message"), (health or {}).get("hint")) if p) or None
    else:
        verified_state, verified_hint = CURRENT, HINTS[STEP_VERIFIED]
    steps.append(_step(STEP_VERIFIED, verified_state, verified_hint))

    if verified_state != DONE:
        test_state, test_hint = TODO, None
    elif test is None:
        test_state, test_hint = CURRENT, HINTS[STEP_TEST_SENT]
    elif test["status"] == MAIL_SENT:
        test_state, test_hint = DONE, None
    elif test["status"] in (MAIL_QUEUED, MAIL_RETRYING):
        test_state, test_hint = CURRENT, HINTS["test_sending"]
    elif test["status"] == MAIL_FAILED:
        test_state = BLOCKED
        test_hint = " ".join(p for p in ("시험 메일을 보내지 못했습니다.", test.get("error_summary")) if p)
    else:
        test_state, test_hint = CURRENT, HINTS[STEP_TEST_SENT]
    steps.append(_step(STEP_TEST_SENT, test_state, test_hint))

    if test_state != DONE:
        inbox_state, inbox_hint = TODO, None
    elif inbox and test and inbox.get("delivery_id") == test["id"]:
        if inbox.get("received"):
            inbox_state, inbox_hint = DONE, None
        else:
            inbox_state, inbox_hint = BLOCKED, HINTS["inbox_missing"]
    elif local and test and test.get("remote_status") in ("bounced", "expired"):
        inbox_state, inbox_hint = BLOCKED, HINTS["inbox_bounced"]
    else:
        inbox_state, inbox_hint = CURRENT, HINTS[STEP_INBOX]
    steps.append(_step(STEP_INBOX, inbox_state, inbox_hint))

    next_step = next((s for s in steps if s["state"] in (CURRENT, BLOCKED)), None)
    return {
        "steps": steps,
        "next": next_step,
        "done_count": sum(1 for s in steps if s["state"] == DONE),
        "total": len(steps),
        "complete": next_step is None,
    }
