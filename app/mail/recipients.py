"""이 사람이 아직 이 메일을 받아도 되는가 — 보내기 직전의 받는 사람 · 권한 재검사 (D-547).

## 두 질문은 실패했을 때 반대로 움직인다

`app/mail/relevance.py` 는 「이 사건이 **아직 의미가 있는가**」를 묻는다. 그 판정이 터지면 보낸다(fail-open) -
판정 실패로 이벤트를 잃는 쪽이 더 나쁘다. 이 모듈은 「이 사람이 이 내용을 **받아도 되는가**」를 묻는다. 그 판정이
터지면 **보내지 않는다**(fail-closed) - 강등된 관리자에게 백업 실패 메일이, 열람 권한을 잃은 사람에게 티켓 제목이
가는 것은 되돌릴 수 없다. 보내지 않은 메일은 `cancelled` 로 끝나고 까닭이 남으므로, 사람이 확인하고 다시 보낼 수
있다.

예전에는 받는 사람 재검사가 알림 메일에만 있어서 승인 · 백업 · 초대 메일이 강등 · 보관된 사람에게 재시도 · 복구 재큐 ·
수동 재발송으로 계속 갔고, 티켓 알림의 열람 권한 확인은 fail-open 인 의미 판정 안에 있어 판정이 터지면 보냈다.

## 두 표

- `RECIPIENT_RULES`: 메일 **종류**마다 하나. 받는 사람 계정이 아직 그 메일을 받을 자격(활성 · 보관 아님 · 역할 ·
  결재 권한 · 지금의 주소)을 갖는가. 알림 메일은 알림 쪽 판정(`app/notifications/mail.py::recheck_recipient`)을 쓴다.
- `ACCESS_RULES`: 메일로 보낼 수 있는 알림 **유형**마다 하나. 받는 사람이 그 내용(티켓 · 문서 · 채팅방 · 승인)을 지금도
  볼 수 있는가.

종류나 유형이 표에 없으면 보내지 않는다(`check_failed`). 새 종류를 더하면서 판정을 빠뜨리면 시험
(`tests/unit/test_mail_relevance_rules.py`)이 잡는다.

## 워커의 순서 (`app/jobs/handlers/mail_send.py`)

상태 → 받는 사람(취소) → 의미(대체됨, fail-open) → 권한(취소) → 설정 → 그리기 → 보내기. 받는 사람을 의미보다 먼저 보는
까닭: 계정이 지워졌거나 보관됐으면 「사건이 지났다」보다 「받을 사람이 없다」가 더 정확한 까닭이다.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from app.mail.models import MailDelivery
from app.mail.renderers import (
    KIND_APPROVAL_REQUESTED,
    KIND_BACKUP_FAILED,
    KIND_INVITE,
    KIND_NOTIFICATION,
    KIND_NOTIFY_EMAIL_VERIFICATION,
    KIND_PASSWORD_RESET,
    KIND_TEST,
)

logger = logging.getLogger("app.mail.recipients")

REASON_ACCOUNT_GONE = "account_gone"
REASON_ARCHIVED = "archived"
REASON_INACTIVE = "inactive"
REASON_ADDRESS_CHANGED = "address_changed"
REASON_NO_LONGER_ADMIN = "no_longer_admin"
REASON_SENDER_NOT_ALLOWED = "sender_not_allowed"
REASON_VERIFICATION_CLOSED = "verification_closed"
REASON_NO_LONGER_DECIDER = "no_longer_decider"
REASON_NO_ACCESS = "no_access"
REASON_CHECK_FAILED = "check_failed"

# 화면이 보여 줄 까닭 문장. `app/mail/relevance.py::REASON_LABELS` 가 함께 싣는다.
RECIPIENT_CHECK_LABELS: dict[str, str] = {
    REASON_ADDRESS_CHANGED: "계정의 이메일 주소가 바뀌어 예전 주소로 보내지 않았습니다.",
    REASON_NO_LONGER_ADMIN: "받는 사람이 더 이상 관리자가 아니라 보내지 않았습니다.",
    REASON_SENDER_NOT_ALLOWED: "시험 메일을 보낸 사람에게 더 이상 메일 설정 권한이 없어 보내지 않았습니다.",
    REASON_VERIFICATION_CLOSED: "주소 확인이 이미 끝났거나 취소돼 보내지 않았습니다.",
    REASON_NO_LONGER_DECIDER: "받는 사람이 더 이상 이 승인 요청을 처리할 수 없어 보내지 않았습니다.",
    REASON_CHECK_FAILED: "받는 사람을 확인하지 못해 보내지 않았습니다.",
}


def _params(delivery: MailDelivery) -> dict:
    try:
        value = json.loads(delivery.params_json or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _recipient(db: Session, delivery: MailDelivery, params: dict):
    """받는 사람 계정. 행의 `recipient_user_id` 가 정본이고, 0043 이전에 쌓인 행은 params 의 `user_id` 를 본다."""
    from app.users.models import User

    user_id = delivery.recipient_user_id or params.get("user_id")
    return db.get(User, user_id) if user_id else None


def _account_block(user) -> str | None:
    if user is None:
        return REASON_ACCOUNT_GONE
    if user.archived_at is not None:
        return REASON_ARCHIVED
    if not user.active:
        return REASON_INACTIVE
    return None


def _rule_password_reset(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    user = _recipient(db, delivery, params)
    blocked = _account_block(user)
    if blocked:
        return blocked
    # 재설정 링크는 지금 계정의 주소로만 간다. 요청 뒤 주소가 바뀌었으면 예전 주소의 메일함이 계정을 가져가지 못하게 끊는다.
    if (user.email or "").strip().lower() != (delivery.to_email or "").strip().lower():
        return REASON_ADDRESS_CHANGED
    return None


def _rule_invite(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    user = _recipient(db, delivery, params)
    if user is None:
        return REASON_ACCOUNT_GONE
    if user.archived_at is not None:
        return REASON_ARCHIVED
    return None


def _rule_approval_requested(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from app.approvals.models import Approval
    from app.approvals.service import deciders_for
    from app.notifications.service import approver_user_ids

    user = _recipient(db, delivery, params)
    blocked = _account_block(user)
    if blocked:
        return blocked
    approval = db.get(Approval, params.get("approval_id")) if params.get("approval_id") else None
    if approval is not None:
        allowed = deciders_for(db, approval, now=now)
    else:
        # 승인 id 를 싣기 전에 쌓인 메일이다. 그 건의 범위는 잴 수 없어도 결재할 역할 · 위임은 지금도 있어야 한다.
        allowed = approver_user_ids(db, now=now)
    return None if user.id in set(allowed) else REASON_NO_LONGER_DECIDER


def _rule_backup_failed(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from app.users.models import ROLE_ADMIN, ROLE_SYSTEM_ADMIN

    user = _recipient(db, delivery, params)
    blocked = _account_block(user)
    if blocked:
        return blocked
    return None if user.role in (ROLE_ADMIN, ROLE_SYSTEM_ADMIN) else REASON_NO_LONGER_ADMIN


def _rule_test(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """시험 메일(D-554). 보낸 사람이 아직 활성이고, 다른 주소로 보낸 것이면 아직 메일 설정 권한(`SYSTEM_CONFIGURE`)이 있다.
    받는 주소가 어떤 사용자의 계정 주소면 그 사람도 활성이다. 보낸 사람 기록이 없는 옛 행은 받는 사람 계정만 본다."""
    from app.users.models import User

    sender_id = params.get("sender_id")
    if not sender_id:
        return _account_block(_recipient(db, delivery, params))
    blocked = _account_block(db.get(User, sender_id))
    if blocked:
        return blocked
    if not params.get("own"):
        from app.authz.permissions import SYSTEM_CONFIGURE
        from app.authz.service import effective_permissions

        if SYSTEM_CONFIGURE not in effective_permissions(db, db.get(User, sender_id)):
            return REASON_SENDER_NOT_ALLOWED
    if delivery.recipient_user_id:
        return _account_block(db.get(User, delivery.recipient_user_id))
    return None


def _rule_notify_verification(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """주소 확인 코드(M4). 요청한 사람이 아직 활성이고 그 확인이 아직 열려 있어야 보낸다(다시 요청했거나 확인을 마쳤으면 옛 메일은
    보내지 않는다)."""
    from app.profiles.notify_email import is_open

    blocked = _account_block(_recipient(db, delivery, params))
    if blocked:
        return blocked
    return None if is_open(db, params.get("verification_id")) else REASON_VERIFICATION_CLOSED


def _rule_notification(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """알림 쪽 판정을 그대로 쓴다 - 메일 알림을 껐거나 그 유형을 고르지 않았거나 계정이 닫혔다. 보내도 되면 받는 주소가
    지금 계정의 이메일로 고쳐진다."""
    from app.notifications.mail import recheck_recipient

    return recheck_recipient(db, delivery)


def _rule_security(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """계정 보안 메일(D-562) - 계정 사정만 본다. 메일 알림을 껐거나 유형을 고르지 않은 것은 막는 까닭이 아니다(끌 수 없는 메일).
    받는 주소는 계정 이메일 그대로다(다른 알림 주소로 고치지 않는다 - 그 주소가 계정의 것이라는 사실이 알릴 내용이다)."""
    return _account_block(_recipient(db, delivery, params))


Rule = Callable[[Session, MailDelivery, dict, datetime], "str | None"]

RECIPIENT_RULES: dict[str, Rule] = {
    KIND_PASSWORD_RESET: _rule_password_reset,
    KIND_INVITE: _rule_invite,
    KIND_APPROVAL_REQUESTED: _rule_approval_requested,
    KIND_BACKUP_FAILED: _rule_backup_failed,
    KIND_TEST: _rule_test,
    KIND_NOTIFICATION: _rule_notification,
    KIND_NOTIFY_EMAIL_VERIFICATION: _rule_notify_verification,
    "account_locked": _rule_security,
    "password_change_required": _rule_security,
}


# ── 알림 메일의 열람 권한 ──────────────────────────────────────────────────────

def _access_ticket(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from app.core.errors import NotFoundError
    from app.tickets.service import ensure_ticket_visible

    user = _recipient(db, delivery, params)
    if user is None:
        return REASON_ACCOUNT_GONE
    try:
        ensure_ticket_visible(db, params.get("related_id"), user)
    except NotFoundError:
        return REASON_NO_ACCESS
    return None


def _access_document(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from app.core.errors import NotFoundError
    from app.knowledge.service import get_scoped_document_or_404

    user = _recipient(db, delivery, params)
    if user is None:
        return REASON_ACCOUNT_GONE
    try:
        get_scoped_document_or_404(db, user, params.get("related_id"))
    except NotFoundError:
        return REASON_NO_ACCESS
    return None


def _access_chat_room(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from app.team_chat.models import ChatRoom
    from app.team_chat.repository import get_member

    user = _recipient(db, delivery, params)
    if user is None:
        return REASON_ACCOUNT_GONE
    room = db.get(ChatRoom, params.get("related_id")) if params.get("related_id") else None
    if room is None:
        return REASON_NO_ACCESS
    if not room.is_global and get_member(db, room.id, user.id) is None:
        return REASON_NO_ACCESS
    return None


def _access_approval_decided(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """결정 알림은 그 승인을 요청한 사람만 받는다."""
    from app.approvals.models import Approval

    user = _recipient(db, delivery, params)
    if user is None:
        return REASON_ACCOUNT_GONE
    approval = db.get(Approval, params.get("related_id")) if params.get("related_id") else None
    if approval is None or approval.requested_by != user.id:
        return REASON_NO_ACCESS
    return None


def _access_ai_provider_state(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """AI 연결 상태는 시스템 관리자의 일이다(`app/profiles/prefs.py::ADMIN_ONLY_TYPES`)."""
    from app.users.models import ROLE_SYSTEM_ADMIN

    user = _recipient(db, delivery, params)
    blocked = _account_block(user)
    if blocked:
        return blocked
    return None if user.role == ROLE_SYSTEM_ADMIN else REASON_NO_LONGER_ADMIN


def _access_account(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """받는 사람 본인에게 일어난 사건(인수인계 · 게시글 댓글 · 제안 상태 · AI 한도) - 볼 권한은 계정이 살아 있는가뿐이다."""
    return _account_block(_recipient(db, delivery, params))


def _access_approval_party(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """승인 지연 · 만료 · 위임 - 받는 사람은 결재자나 위임받은 사람이다(요청자가 아니다). 승인 건이 가리켜져 있으면 아직 있어야 한다."""
    from app.approvals.models import Approval

    blocked = _account_block(_recipient(db, delivery, params))
    if blocked:
        return blocked
    if params.get("related_type") == "approval" and params.get("related_id") and db.get(Approval, params["related_id"]) is None:
        return REASON_NO_ACCESS
    return None


ACCESS_RULES: dict[str, Rule] = {
    "ticket_assigned": _access_ticket,
    "ticket_status_changed": _access_ticket,
    "ticket_resolved": _access_ticket,
    "ticket_comment": _access_ticket,
    "offboarding_handover": _access_account,
    "approval_decided": _access_approval_decided,
    "approval_overdue": _access_approval_party,
    "approval_expired": _access_approval_party,
    "approval_cancelled": _access_approval_decided,
    "approval_delegated": _access_approval_party,
    "chat_invited": _access_chat_room,
    "chat_mentioned": _access_chat_room,
    "document_comment": _access_document,
    "board_comment": _access_account,
    "idea_status_changed": _access_account,
    "ai_quota_exhausted": _access_account,
    "ai_provider_state": _access_ai_provider_state,
}


def _guarded(rule: Rule | None, db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """판정 하나. 표에 없거나 판정이 터지면 보내지 않는다(모듈 머리말)."""
    if rule is None:
        return REASON_CHECK_FAILED
    try:
        return rule(db, delivery, params, now)
    except Exception:  # noqa: BLE001 - 받아도 되는지 모르면 보내지 않는다
        logger.exception("받는 사람 재검사가 실패해 보내지 않는다 (delivery=%s)", delivery.id)
        return REASON_CHECK_FAILED


def recipient_block(db: Session, delivery: MailDelivery, now: datetime) -> str | None:
    """받는 사람이 아직 이 종류의 메일을 받을 수 있는가. 보내면 안 되면 그 까닭."""
    return _guarded(RECIPIENT_RULES.get(delivery.kind), db, delivery, _params(delivery), now)


def access_block(db: Session, delivery: MailDelivery, now: datetime) -> str | None:
    """알림 메일이면 받는 사람이 그 내용을 지금도 볼 수 있는가. 알림이 아니면 볼 것이 없다."""
    if delivery.kind != KIND_NOTIFICATION:
        return None
    params = _params(delivery)
    return _guarded(ACCESS_RULES.get(str(params.get("type") or "")), db, delivery, params, now)
