"""알림을 메일로도 보낸다 (계획 3.4, D-514).

## 메일을 만들지 않는 까닭은 「보내면 안 되는 사정」뿐이다

  * 메일로 보낼 수 있는 유형이 아니다(`app/profiles/prefs.py::MAILABLE_TYPES`)
  * 관리자가 그 유형을 허용하지 않았다(설정 `mail_notification_types`)
  * 받는 사람이 메일 알림을 켜지 않았거나 그 유형을 고르지 않았다
  * 받는 사람의 계정이 비활성이거나 보관됐거나 이메일이 없다

**메일 서버의 건강 상태는 보지 않는다.** 서버가 지금 실패하고 있어도 메일은 큐에 들어가고, 일시 실패는 재시도
일정(`app/mail/service.py`)이, 서버 탓 실패는 복구 재큐(`app/mail/health.py::on_recovered`)가 처리한다. 장애 때문에
이벤트를 조용히 잃지 않는다. 설정 자체가 없으면 행이 `unconfigured` 로 남고 잡은 만들지 않는다(`queue_mail`).

같은 판정(`block_reason`)을 보내기 직전에 다시 한다(`recheck_recipient`). 큐에 넣은 뒤 메일 알림을 끈 사람이나
보관된 계정에게는 보내지 않고 `cancelled` 로 끝낸다. 그 사건이 아직 의미가 있는지는 다른 질문이고
`app/mail/relevance.py` 가 답한다(`superseded`).

## 방해금지와 배지 끄기는 메일과 무관하다

둘 다 화면 알림의 규칙이다. 메일을 원하지 않으면 메일 알림을 끈다.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.profiles.prefs import MAILABLE_TYPES, parse_mail_types

logger = logging.getLogger("app.notifications.mail")

SETTING_TYPES = "mail_notification_types"
SETTING_MAX_AGE = "mail_notification_max_age_days"

# 받는 사람 쪽 사정. 보내기 직전에 걸리면 행은 `cancelled` 이고 이 까닭이 남는다.
REASON_NOT_MAILABLE = "not_mailable"
REASON_TYPE_NOT_ALLOWED = "type_not_allowed"
REASON_OPTED_OUT = "opted_out"
REASON_TYPE_OPTED_OUT = "type_opted_out"
REASON_ACCOUNT_GONE = "account_gone"
REASON_INACTIVE = "inactive"
REASON_ARCHIVED = "archived"
REASON_NO_EMAIL = "no_email"

RECIPIENT_REASON_LABELS: dict[str, str] = {
    REASON_NOT_MAILABLE: "메일로 보낼 수 없는 알림이라 보내지 않았습니다.",
    REASON_TYPE_NOT_ALLOWED: "관리자가 이 알림을 메일로 보내지 않기로 해 보내지 않았습니다.",
    REASON_OPTED_OUT: "받는 사람이 메일 알림을 꺼서 보내지 않았습니다.",
    REASON_TYPE_OPTED_OUT: "받는 사람이 이 알림을 메일로 받지 않기로 해 보내지 않았습니다.",
    REASON_INACTIVE: "받을 계정이 비활성이라 보내지 않았습니다.",
    REASON_NO_EMAIL: "받을 계정에 이메일이 없어 보내지 않았습니다.",
}


def _setting(db: Session, key: str):
    """설정 한 값. 캐시가 없는 서비스 깊은 곳에서 부르므로 행을 직접 읽는다(한 세션 안에서는 한 번만 읽힌다)."""
    from app.settings.models import AppSetting
    from app.settings.registry import REGISTRY

    row = db.get(AppSetting, key)
    if row is None:
        return REGISTRY[key].default
    try:
        return json.loads(row.value_json)
    except (TypeError, ValueError):
        return REGISTRY[key].default


def allowed_types(db: Session) -> tuple[str, ...]:
    """관리자가 메일로 보내도 된다고 한 유형. 순서는 화면 순서(`MAILABLE_TYPES`)다."""
    raw = _setting(db, SETTING_TYPES)
    chosen = set(raw) if isinstance(raw, list) else set()
    return tuple(t for t in MAILABLE_TYPES if t in chosen)


def max_age_days(db: Session) -> int:
    value = _setting(db, SETTING_MAX_AGE)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 7


def chosen_types(pref, allowed) -> list[str]:
    """이 사람이 메일로 받는 유형. 아직 고르지 않았으면 허용된 유형 전부다(`prefs.parse_mail_types`)."""
    picked = parse_mail_types(pref.mail_types) if pref is not None else None
    if picked is None:
        return list(allowed)
    return [t for t in allowed if t in picked]


def _preference(db: Session, user_id: str):
    from app.profiles.service import get_preference

    return get_preference(db, user_id)


def block_reason(db: Session, user, type_: str) -> str | None:
    """이 사람에게 이 유형을 지금 메일로 보내면 안 되는 까닭. 보내도 되면 None."""
    if type_ not in MAILABLE_TYPES:
        return REASON_NOT_MAILABLE
    allowed = allowed_types(db)
    if type_ not in allowed:
        return REASON_TYPE_NOT_ALLOWED
    if user is None:
        return REASON_ACCOUNT_GONE
    if user.archived_at is not None:
        return REASON_ARCHIVED
    if not user.active:
        return REASON_INACTIVE
    if not (user.email or "").strip():
        return REASON_NO_EMAIL
    pref = _preference(db, user.id)
    if pref is None or not pref.mail_enabled:
        return REASON_OPTED_OUT
    if type_ not in chosen_types(pref, allowed):
        return REASON_TYPE_OPTED_OUT
    return None


def fan_out_mail(db: Session, row, *, now: datetime, context: dict | None = None):
    """알림 한 건을 메일로도 보낸다. 만든 메일 행을 돌려준다(안 만들면 None).

    멱등 열쇠가 알림 id 라서 같은 알림이 두 번 팬아웃돼도 메일은 한 통이다. ``context`` 는 보내기 직전의 유효성
    재검사에 쓰는 참조다(티켓의 새 상태, 댓글 id 등). 본문에 넣지 않는다.
    """
    from app.mail.renderers import KIND_NOTIFICATION
    from app.mail.service import queue_mail
    from app.notifications.destinations import destination_for
    from app.users.models import User

    if row.type not in MAILABLE_TYPES:
        return None
    user = db.get(User, row.user_id)
    if block_reason(db, user, row.type) is not None:
        return None
    params = {
        **(context or {}),
        "notification_id": row.id,
        "user_id": row.user_id,
        "type": row.type,
        "title": row.title,
        "body": row.body or "",
        "audience": row.audience,
        "related_type": row.related_object_type,
        "related_id": row.related_object_id,
        "route": destination_for(row.related_object_type, row.related_object_id, row.audience),
    }
    return queue_mail(
        db, kind=KIND_NOTIFICATION, to_email=user.email, recipient_user_id=user.id, subject=row.title,
        params=params, now=now, idempotency_key=f"notification:{row.id}",
    )


def recheck_recipient(db: Session, delivery) -> str | None:
    """보내기 직전에 받는 사람 쪽 사정을 다시 본다. 보내면 안 되면 그 까닭을 돌려준다.

    보내도 되면 **받는 주소를 지금 계정의 이메일로 고친다** - 큐에 들어간 뒤 이메일을 바꾼 사람은 새 주소로 받는다.
    """
    from app.users.models import User

    try:
        params = json.loads(delivery.params_json or "{}")
    except ValueError:
        params = {}
    user = db.get(User, params.get("user_id")) if params.get("user_id") else None
    reason = block_reason(db, user, str(params.get("type") or ""))
    if reason is None and user is not None and user.email and user.email != delivery.to_email:
        delivery.to_email = user.email
    return reason


def recipient_view(db: Session, pref, *, admin: bool = True) -> dict:
    """내 설정 화면의 「메일로도 받기」 한 벌 - 켜짐, 받는 유형, 고를 수 있는 유형(`app/profiles/router.py`).

    일반 사용자에게는 관리자만 받는 유형(`ADMIN_ONLY_TYPES`)을 고를 칸으로 보이지 않는다.
    """
    from app.profiles.prefs import ADMIN_ONLY_TYPES, NOTIFICATION_TYPES

    allowed = tuple(t for t in allowed_types(db) if admin or t not in ADMIN_ONLY_TYPES)
    return {
        "enabled": bool(pref.mail_enabled) if pref is not None else False,
        "types": chosen_types(pref, allowed),
        "catalog": [
            {"key": key, "label": NOTIFICATION_TYPES[key][0], "help": NOTIFICATION_TYPES[key][1]}
            for key in allowed
        ],
    }


def admin_catalog(db: Session) -> dict:
    """관리 화면이 그리는 허용 목록 - 메일로 보낼 수 있는 유형 전부와 지금 허용한 것, 그리고 오래된 메일의 기준."""
    from app.profiles.prefs import NOTIFICATION_TYPES

    return {
        "allowed": list(allowed_types(db)),
        "catalog": [
            {"key": key, "label": NOTIFICATION_TYPES[key][0], "help": NOTIFICATION_TYPES[key][1]}
            for key in MAILABLE_TYPES
        ],
        "max_age_days": max_age_days(db),
    }
