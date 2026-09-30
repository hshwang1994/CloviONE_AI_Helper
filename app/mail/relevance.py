"""보낼 의미가 아직 있는가 — 발송 직전과 복구 재큐가 같은 판정을 쓴다 (계획 3.3 · 3.4, D-512).

## 원칙

**장애 때문에 이벤트를 조용히 잃지는 않지만, 이미 의미가 없어진 오래된 이벤트를 뒤늦게 보내지도 않는다.**
메일 서버가 하루 멈췄다가 살아나면 그 사이 쌓인 메일이 한꺼번에 나간다. 그중에는 이미 로그인한 사람의 초대,
이미 처리된 승인 요청, 이미 복구된 백업의 실패 알림이 섞여 있다. 그 메일은 받는 사람을 헷갈리게 한다.

그래서 메일마다 「보내기 직전에 아직 참인가」를 한 번 더 본다. 참이 아니면 보내지 않고 `superseded` 로 끝내며
까닭(`skip_reason`)을 남긴다. 판정은 종류마다 한 함수이고 표 하나(`RULES`)에 모인다 — 새 종류를 더하면서
판정을 빠뜨리면 시험(`test_every_mailable_kind_has_a_relevance_rule`)이 잡는다.

## 판정하지 않는 종류

비밀번호 재설정과 시험 메일은 사람이 방금 누른 결과라 늘 보낸다. 재설정 메일은 복구 재큐에서도 빠진다 — 보낼
때 새 토큰을 만들어 오래된 요청을 되살리기 때문이다(`app/mail/service.py::NOT_RESENDABLE_KINDS`).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.mail.models import MailDelivery
from app.mail.renderers import (
    KIND_APPROVAL_REQUESTED,
    KIND_BACKUP_FAILED,
    KIND_INVITE,
    KIND_PASSWORD_RESET,
    KIND_TEST,
)

# 이 나이를 넘은 이벤트는 보내지 않는다(모든 판정 종류 공통). 사람이 직접 다시 보내면 그 시각부터 센다.
MAX_AGE_DAYS = 7

REASON_TOO_OLD = "too_old"
REASON_ACCOUNT_GONE = "account_gone"
REASON_ARCHIVED = "archived"
REASON_ALREADY_ACTIVE = "already_active"
REASON_APPROVAL_GONE = "approval_gone"
REASON_APPROVAL_CLOSED = "approval_closed"
REASON_RECOVERED_SINCE = "recovered_since"

# 화면이 보여 줄 까닭 문장. 목록 칸과 상세가 같은 문장을 쓴다.
REASON_LABELS: dict[str, str] = {
    REASON_TOO_OLD: "이벤트가 너무 오래되어 보내지 않았습니다.",
    REASON_ACCOUNT_GONE: "받을 계정이 없어져 보내지 않았습니다.",
    REASON_ARCHIVED: "받을 계정이 보관되어 보내지 않았습니다.",
    REASON_ALREADY_ACTIVE: "이미 로그인한 계정이라 초대를 보내지 않았습니다.",
    REASON_APPROVAL_GONE: "승인 요청이 없어져 보내지 않았습니다.",
    REASON_APPROVAL_CLOSED: "승인 요청이 이미 처리되어 보내지 않았습니다.",
    REASON_RECOVERED_SINCE: "그 뒤 백업이 성공해 실패 알림을 보내지 않았습니다.",
    "cancelled_by_operator": "관리자가 취소했습니다.",
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


Rule = Callable[[Session, MailDelivery, dict, datetime], "str | None"]

# 종류 하나에 판정 하나. 알림 메일(계획 3.4)이 여기에 더해진다.
RULES: dict[str, Rule] = {
    KIND_INVITE: _rule_invite,
    KIND_APPROVAL_REQUESTED: _rule_approval_requested,
    KIND_BACKUP_FAILED: _rule_backup_failed,
}


def _age_origin(delivery: MailDelivery, params: dict) -> datetime:
    """나이를 세는 시각. 사람이 직접 다시 보냈으면 그 시각이다 - 관리자가 누른 재발송을 나이 규칙이 몰래 막지 않게."""
    from app.core.dates import parse_dt

    manual = parse_dt(params.get("manual_resend_at"))
    return manual or delivery.created_at


def still_relevant(db: Session, delivery: MailDelivery, now: datetime) -> tuple[bool, str | None]:
    """`(보낼까, 안 보내면 그 까닭)`. 판정 중 예외가 나면 보낸다 - 판정 실패로 메일을 잃는 쪽이 더 나쁘다."""
    if delivery.kind in ALWAYS_RELEVANT_KINDS:
        return True, None
    params = _params(delivery)
    if now - _age_origin(delivery, params) > timedelta(days=MAX_AGE_DAYS):
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
