"""보낼 의미가 아직 있는가 — 발송 직전과 복구 재큐가 같은 판정을 쓴다 (계획 3.3 · 3.4, D-512).

## 원칙

**장애 때문에 이벤트를 조용히 잃지는 않지만, 이미 의미가 없어진 오래된 이벤트를 뒤늦게 보내지도 않는다.**
메일 서버가 하루 멈췄다가 살아나면 그 사이 쌓인 메일이 한꺼번에 나간다. 그중에는 이미 로그인한 사람의 초대,
이미 처리된 승인 요청, 이미 복구된 백업의 실패 알림이 섞여 있다. 그 메일은 받는 사람을 헷갈리게 한다.

그래서 메일마다 「보내기 직전에 아직 참인가」를 한 번 더 본다. 참이 아니면 보내지 않고 `superseded` 로 끝내며
까닭(`skip_reason`)을 남긴다. 판정은 종류마다 한 함수이고 표 하나(`RULES`)에 모인다 — 새 종류를 더하면서
판정을 빠뜨리면 시험(`test_every_mailable_kind_has_a_relevance_rule`)이 잡는다.

알림 메일(계획 3.4)은 알림 유형마다 판정이 다르다. 그 표가 `NOTIFICATION_RULES` 이고, 메일로 보낼 수 있는 유형이
전부 들어 있어야 한다(`test_every_mailable_type_has_a_relevance_rule`). 장애 동안 한 티켓이 계획, 진행 중, 검증,
완료로 바뀌었다면 마지막 상태의 메일 하나만 나간다 - 앞의 셋은 더 새로운 사건이 있거나 상태가 그 뒤 바뀌었다.

받는 사람 쪽 사정(메일 알림을 껐다, 계정이 보관됐다, 결재 권한을 잃었다)과 열람 권한은 다른 질문이다. 그 판정은
`app/mail/recipients.py` 에 있고, 터지면 보내지 않으며(이 모듈과 반대), 그 메일은 `cancelled` 로 끝난다(D-547).

## 판정하지 않는 종류

비밀번호 재설정과 시험 메일은 사람이 방금 누른 결과라 늘 보낸다. 재설정 메일은 복구 재큐에서도 빠진다 — 보낼
때 새 토큰을 만들어 오래된 요청을 되살리기 때문이다(`app/mail/service.py::NOT_RESENDABLE_KINDS`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from sqlalchemy import select

from app.mail.models import MailDelivery
from app.mail.renderers import (
    KIND_APPROVAL_REQUESTED,
    KIND_BACKUP_FAILED,
    KIND_INVITE,
    KIND_NOTIFICATION,
    KIND_PASSWORD_RESET,
    KIND_TEST,
)
from app.mail.recipients import RECIPIENT_CHECK_LABELS
from app.notifications.mail import RECIPIENT_REASON_LABELS

# 이 나이를 넘은 이벤트는 보내지 않는다(모든 판정 종류 공통). 사람이 직접 다시 보내면 그 시각부터 센다. 관리자가
# 설정(`mail_notification_max_age_days`)으로 바꿀 수 있고, 이 값은 설정이 없을 때의 기본이다.
MAX_AGE_DAYS = 7

REASON_TOO_OLD = "too_old"
REASON_ACCOUNT_GONE = "account_gone"
REASON_ARCHIVED = "archived"
REASON_ALREADY_ACTIVE = "already_active"
REASON_APPROVAL_GONE = "approval_gone"
REASON_APPROVAL_CLOSED = "approval_closed"
REASON_RECOVERED_SINCE = "recovered_since"
# 알림 메일(계획 3.4)
REASON_NEWER_EVENT = "newer_status_event"
REASON_STATUS_MOVED_ON = "status_moved_on"
REASON_TICKET_GONE = "ticket_gone"
REASON_REOPENED = "reopened"
REASON_REQUESTER_CHANGED = "requester_changed"
REASON_NO_LONGER_ASSIGNEE = "no_longer_assignee"
REASON_TICKET_CLOSED = "ticket_closed"
REASON_SOURCE_DELETED = "source_deleted"
REASON_NO_ACCESS = "no_access"
REASON_AI_STATE_MOVED_ON = "ai_state_moved_on"

# 화면이 보여 줄 까닭 문장. 목록 칸과 상세가 같은 문장을 쓴다.
REASON_LABELS: dict[str, str] = {
    REASON_AI_STATE_MOVED_ON: "AI 연결 상태가 그 뒤 바뀌어 보내지 않았습니다.",
    REASON_TOO_OLD: "이벤트가 너무 오래되어 보내지 않았습니다.",
    REASON_ACCOUNT_GONE: "받을 계정이 없어져 보내지 않았습니다.",
    REASON_ARCHIVED: "받을 계정이 보관되어 보내지 않았습니다.",
    REASON_ALREADY_ACTIVE: "이미 로그인한 계정이라 초대를 보내지 않았습니다.",
    REASON_APPROVAL_GONE: "승인 요청이 없어져 보내지 않았습니다.",
    REASON_APPROVAL_CLOSED: "승인 요청이 이미 처리되어 보내지 않았습니다.",
    REASON_RECOVERED_SINCE: "그 뒤 백업이 성공해 실패 알림을 보내지 않았습니다.",
    REASON_NEWER_EVENT: "같은 티켓에 더 새로운 상태 변경이 있어 보내지 않았습니다.",
    REASON_STATUS_MOVED_ON: "티켓 상태가 그 뒤 다시 바뀌어 보내지 않았습니다.",
    REASON_TICKET_GONE: "티켓이 휴지통에 있거나 없어져 보내지 않았습니다.",
    REASON_REOPENED: "티켓이 다시 열려 결과 알림을 보내지 않았습니다.",
    REASON_REQUESTER_CHANGED: "받는 사람이 더 이상 요청자가 아니라 보내지 않았습니다.",
    REASON_NO_LONGER_ASSIGNEE: "받는 사람이 더 이상 담당자가 아니라 보내지 않았습니다.",
    REASON_TICKET_CLOSED: "티켓이 이미 끝나 배정 알림을 보내지 않았습니다.",
    REASON_SOURCE_DELETED: "원래 글이 지워져 보내지 않았습니다.",
    REASON_NO_ACCESS: "받는 사람이 더 이상 볼 수 없는 내용이라 보내지 않았습니다.",
    "cancelled_by_operator": "관리자가 취소했습니다.",
    # 받는 사람 쪽 사정(`cancelled`) - 판정은 `app/notifications/mail.py` 와 `app/mail/recipients.py` 에 있고 문장만
    # 여기서 함께 보인다.
    **RECIPIENT_REASON_LABELS,
    **RECIPIENT_CHECK_LABELS,
}

# 판정하지 않고 늘 보내는 종류(모듈 머리말).
ALWAYS_RELEVANT_KINDS = frozenset({KIND_PASSWORD_RESET, KIND_TEST})


def _params(delivery: MailDelivery) -> dict:
    try:
        value = json.loads(delivery.params_json or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _rule_invite(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from app.users.models import User

    user = db.get(User, params.get("user_id")) if params.get("user_id") else None
    if user is None:
        return REASON_ACCOUNT_GONE
    if user.archived_at is not None:
        return REASON_ARCHIVED
    if user.last_login_at is not None:
        return REASON_ALREADY_ACTIVE
    return None


def _rule_approval_requested(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from app.approvals.models import APPROVAL_PENDING, Approval

    approval_id = params.get("approval_id")
    if not approval_id:
        # 승인 id 를 싣기 전에 쌓인 메일이다. 판정할 근거가 없으면 보낸다 - 나이 규칙이 오래된 것을 거른다.
        return None
    row = db.get(Approval, approval_id)
    if row is None:
        return REASON_APPROVAL_GONE
    if row.status != APPROVAL_PENDING:
        return REASON_APPROVAL_CLOSED
    return None


def _rule_backup_failed(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from sqlalchemy import select

    from app.backups.models import STATUS_SUCCEEDED, STATUS_VERIFIED, Backup
    from app.core.dates import parse_dt

    failed_at = parse_dt(params.get("at")) or delivery.created_at
    recovered = db.execute(
        select(Backup.id).where(
            Backup.status.in_([STATUS_SUCCEEDED, STATUS_VERIFIED]), Backup.started_at > failed_at,
        ).limit(1)
    ).scalar_one_or_none()
    return REASON_RECOVERED_SINCE if recovered else None


# ── 알림 메일 (계획 3.4) ─────────────────────────────────────────────────────
#
# 알림 메일의 params 에는 알림 id, 받는 사람, 유형, 관련 대상(`related_type`, `related_id`)과 호출부가 넘긴 참조
# (티켓의 새 상태 `to_status`, 댓글 id, 메시지 id)가 있다(`app/notifications/mail.py::fan_out_mail`).

# 한 티켓의 「상태 사건」 가족. 요청자는 끝날 때 결과 알림을, 관찰자와 담당자는 상태 변경 알림을 받으므로 둘을
# 한 줄로 세워야 무엇이 더 새로운지 가릴 수 있다.
STATUS_EVENT_TYPES = ("ticket_status_changed", "ticket_resolved")


def _ticket(db: Session, params: dict):
    from app.tickets.service import ticket_row_for

    page_id = params.get("related_id")
    return ticket_row_for(db, page_id) if page_id else None


def _ticket_gone(db: Session, row) -> bool:
    """영구 삭제됐거나, 휴지통에 있거나, 옛 소스에서 사라진 티켓."""
    if row is None or row.notion_missing_at is not None:
        return True
    from app.tickets.models import api_page_id
    from app.trash.models import TRASH_TICKET, TrashItem

    return db.execute(
        select(TrashItem.id).where(
            TrashItem.item_type == TRASH_TICKET, TrashItem.notion_page_id == api_page_id(row),
        ).limit(1)
    ).first() is not None


def _closed(row) -> bool:
    from app.work import workflow

    return workflow.category_of(row.status) in workflow.TERMINAL_CATEGORIES


def _newer_status_event(db: Session, delivery: MailDelivery, params: dict) -> bool:
    """같은 사람에게 같은 티켓의 더 새로운 상태 사건 알림이 있는가."""
    from app.notifications.models import Notification

    note = db.get(Notification, params.get("notification_id")) if params.get("notification_id") else None
    since = note.created_at if note is not None else delivery.created_at
    return db.execute(
        select(Notification.id).where(
            Notification.user_id == params.get("user_id"),
            Notification.type.in_(STATUS_EVENT_TYPES),
            Notification.related_object_type == "ticket",
            Notification.related_object_id == params.get("related_id"),
            Notification.created_at > since,
        ).limit(1)
    ).first() is not None


def _rule_ticket_status_changed(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    row = _ticket(db, params)
    if _ticket_gone(db, row):
        return REASON_TICKET_GONE
    if _newer_status_event(db, delivery, params):
        return REASON_NEWER_EVENT
    to_status = params.get("to_status")
    if to_status and row.status != to_status:
        return REASON_STATUS_MOVED_ON
    return None


def _rule_ticket_resolved(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    row = _ticket(db, params)
    if _ticket_gone(db, row):
        return REASON_TICKET_GONE
    if _newer_status_event(db, delivery, params):
        return REASON_NEWER_EVENT
    if not _closed(row):
        return REASON_REOPENED
    if row.requester_user_id != params.get("user_id"):
        return REASON_REQUESTER_CHANGED
    return None


def _rule_ticket_assigned(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from app.core.models_base import split_names
    from app.tickets.service import resolve_assignee_user_ids

    row = _ticket(db, params)
    if _ticket_gone(db, row):
        return REASON_TICKET_GONE
    if params.get("user_id") not in resolve_assignee_user_ids(db, split_names(row.assignee_notion_ids or "")):
        return REASON_NO_LONGER_ASSIGNEE
    if _closed(row):
        return REASON_TICKET_CLOSED
    return None


def _rule_ticket_comment(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """댓글이 아직 있고 티켓이 아직 있는가. 받는 사람이 그 티켓을 볼 수 있는지는 의미가 아니라 권한의 질문이라
    `app/mail/recipients.py::ACCESS_RULES` 가 따로 본다(판정이 터지면 보내지 않는 쪽, D-547)."""
    from app.tickets.models import TicketComment

    comment_id = params.get("comment_id")
    if comment_id:
        comment = db.get(TicketComment, comment_id)
        if comment is None or comment.deleted_at is not None:
            return REASON_SOURCE_DELETED
    if _ticket_gone(db, _ticket(db, params)):
        return REASON_TICKET_GONE
    return None


def _rule_document_comment(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """댓글과 문서가 아직 있는가. 열람 권한은 `app/mail/recipients.py::ACCESS_RULES` 가 본다."""
    from app.knowledge.models import Document, DocumentComment

    comment_id = params.get("comment_id")
    if comment_id:
        comment = db.get(DocumentComment, comment_id)
        if comment is None or comment.deleted_at is not None:
            return REASON_SOURCE_DELETED
    document = db.get(Document, params.get("related_id")) if params.get("related_id") else None
    if document is None or document.archived:
        return REASON_SOURCE_DELETED
    return None


def _rule_chat_mentioned(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """메시지와 채팅방이 아직 있는가. 방 구성원인지는 `app/mail/recipients.py::ACCESS_RULES` 가 본다."""
    from app.team_chat.models import ChatMessage, ChatRoom

    message_id = params.get("message_id")
    if message_id:
        message = db.get(ChatMessage, message_id)
        if message is None or message.deleted_at is not None:
            return REASON_SOURCE_DELETED
    room = db.get(ChatRoom, params.get("related_id")) if params.get("related_id") else None
    if room is None or room.deleted_at is not None:
        return REASON_SOURCE_DELETED
    return None


def _rule_approval_decided(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    from app.approvals.models import Approval

    approval_id = params.get("related_id")
    if approval_id and db.get(Approval, approval_id) is None:
        return REASON_APPROVAL_GONE
    return None


def _rule_ai_provider_state(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    """AI 연결 상태 메일은 그 상태가 아직일 때만 간다. 막힘을 알리는 메일이 복구 뒤에 도착하면 틀린 말이다(D-516)."""
    from app.ai.credentials.state import credential_row

    row = credential_row(db, str(params.get("provider") or ""), str(params.get("auth_method") or ""))
    wanted = params.get("ai_state")
    if row is None or not wanted:
        return REASON_AI_STATE_MOVED_ON
    if wanted == "refresh_expiring":
        renewed = row.refresh_warned_at is None or (
            row.refresh_obtained_at is not None and row.refresh_obtained_at > row.refresh_warned_at
        )
        return REASON_AI_STATE_MOVED_ON if renewed else None
    return None if row.status == wanted else REASON_AI_STATE_MOVED_ON


Rule = Callable[[Session, MailDelivery, dict, datetime], "str | None"]

# 알림 유형 하나에 판정 하나. 메일로 보낼 수 있는 유형(`app/profiles/prefs.py::MAILABLE_TYPES`)이 전부 있어야 한다.
NOTIFICATION_RULES: dict[str, Rule] = {
    "ticket_assigned": _rule_ticket_assigned,
    "ticket_status_changed": _rule_ticket_status_changed,
    "ticket_resolved": _rule_ticket_resolved,
    "ticket_comment": _rule_ticket_comment,
    "document_comment": _rule_document_comment,
    "chat_mentioned": _rule_chat_mentioned,
    "approval_decided": _rule_approval_decided,
    "ai_provider_state": _rule_ai_provider_state,
}


def _rule_notification(db: Session, delivery: MailDelivery, params: dict, now: datetime) -> str | None:
    rule = NOTIFICATION_RULES.get(str(params.get("type") or ""))
    return rule(db, delivery, params, now) if rule is not None else None


# 종류 하나에 판정 하나.
RULES: dict[str, Rule] = {
    KIND_INVITE: _rule_invite,
    KIND_APPROVAL_REQUESTED: _rule_approval_requested,
    KIND_BACKUP_FAILED: _rule_backup_failed,
    KIND_NOTIFICATION: _rule_notification,
}


def _age_origin(delivery: MailDelivery, params: dict) -> datetime:
    """나이를 세는 시각. 사람이 직접 다시 보냈으면 그 시각이다 - 관리자가 누른 재발송을 나이 규칙이 몰래 막지 않게."""
    from app.core.dates import parse_dt

    manual = parse_dt(params.get("manual_resend_at"))
    return manual or delivery.created_at


def _max_age_days(db: Session) -> int:
    try:
        from app.notifications.mail import max_age_days

        return max_age_days(db)
    except Exception:  # noqa: BLE001 - 설정을 못 읽으면 기본값으로 판정한다
        return MAX_AGE_DAYS


def still_relevant(db: Session, delivery: MailDelivery, now: datetime) -> tuple[bool, str | None]:
    """`(보낼까, 안 보내면 그 까닭)`. 판정 중 예외가 나면 보낸다 - 판정 실패로 메일을 잃는 쪽이 더 나쁘다."""
    if delivery.kind in ALWAYS_RELEVANT_KINDS:
        return True, None
    params = _params(delivery)
    if now - _age_origin(delivery, params) > timedelta(days=_max_age_days(db)):
        return False, REASON_TOO_OLD
    rule = RULES.get(delivery.kind)
    if rule is None:
        return True, None
    try:
        reason = rule(db, delivery, params, now)
    except Exception:  # noqa: BLE001 - 판정 실패는 보내는 쪽으로 넘어간다(머리말)
        import logging

        logging.getLogger("app.mail.relevance").exception("relevance rule crashed for %s", delivery.id)
        return True, None
    return (reason is None), reason
