"""In-app notification provider (spec §7.3 initial implementation, §13.5).

메일 채널은 `notify_user` 가 알림 행을 만든 뒤 `app/notifications/mail.py::fan_out_mail` 로 붙인다(계획 3.4,
D-514). 받는 사람이 메일 알림을 켜 둔 유형만 메일이 되고, 메일이 실패해도 화면 알림은 남는다.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.db import DEFAULT_WRITE_CONFLICT_RETRIES, is_serialization_conflict, write_conflict_backoff
from app.core.errors import WriteUnavailableError
from app.notifications.models import AUDIENCE_ADMIN, AUDIENCE_USER, Notification
from app.users.models import ROLE_ADMIN, ROLE_SYSTEM_ADMIN, ROLE_USER, User

logger = logging.getLogger("app.notifications")

# 유형 자체가 명백히 관리자 전용인 이벤트 (0051). notify_admins가 이미 이 유형들만 보내
# audience="admin"을 넘기지만, 그건 "이 함수를 거쳐 갔다"는 사실에 기대는 것이다. 나중에
# 실수로 notify_user를 직접 호출해 같은 유형을 보내도(또는 새 호출부가 생겨도) 사용자
# 알림 벨에 새지 않도록 유형 자체로 한 번 더 못박는다.
_ADMIN_ONLY_TYPES = frozenset({"backup_failed"})

# ── 어느 콘솔의 일인가 (0060) ─────────────────────────────────────────────────
#
# 사용자 알림과 관리자 알림은 **경로부터 분리**된다. 어느 쪽인지는 두 가지가 정한다:
#
#   1. 유형이 가리키는 화면이 어느 콘솔에 사는가 (아래 표)
#   2. **받는 사람이 그 콘솔을 쓸 수 있는가**
#
# 2번이 없으면 안 된다. 관리자 콘솔이 없는 일반 사용자에게 관리자 알림을 보내면 그 사람은
# 그 알림을 **어디서도 볼 수 없다** — 결재를 위임받은 일반 사용자가 정확히 그 처지였다.
# 그래서 관리 콘솔 화면을 가리키는 유형이라도 수신자가 일반 사용자면 사용자 알림으로 간다
# (목적지도 그에 맞춰 갈린다, `app/notifications/destinations.py`).
_ADMIN_CONSOLE_TYPES = frozenset({
    "backup_failed", "account_locked",
    "job_failed", "schedule_failed",
    "approval_requested", "approval_overdue",
})


def audience_for(type_: str, recipient_role: str | None, fallback: str = AUDIENCE_USER) -> str:
    """이 알림을 어느 콘솔의 것으로 볼 것인가.

    `_ADMIN_ONLY_TYPES` 는 수신자와 무관하게 관리자 알림이다(백업 실패는 애초에
    일반 사용자에게 안 간다). 그 밖의 관리 콘솔 유형은 **수신자가 관리 콘솔을 쓸 수 있을
    때만** 관리자 알림이 된다 — 아니면 그 사람에게는 보이지 않는 알림이 된다.
    """
    if type_ in _ADMIN_ONLY_TYPES:
        return AUDIENCE_ADMIN
    if type_ in _ADMIN_CONSOLE_TYPES and recipient_role and recipient_role != ROLE_USER:
        return AUDIENCE_ADMIN
    return fallback


def notify_user(
    db: Session,
    user_id: str,
    *,
    type_: str,
    title: str,
    body: str | None = None,
    related: tuple[str, str] | None = None,
    now: datetime,
    audience: str = AUDIENCE_USER,
    recipient_role: str | None = None,
    context: dict | None = None,
) -> Notification:
    """알림 한 건. **어느 콘솔의 것인가는 여기 한 곳에서 정한다** (0060).

    호출부가 audience 를 신경 쓰지 않아도 되도록, 유형과 **수신자의 역할**로 판정한다
    (`audience_for`). 역할을 안 넘기면 여기서 한 번 읽는다 — 팬아웃 호출부는 이미 User
    객체를 들고 있으므로 그때는 넘겨서 조회를 아낀다.

    ``context`` 는 메일로도 보낼 때 보내기 직전의 유효성 재검사가 쓰는 참조다(티켓의 새 상태, 댓글 id).
    화면 알림 행에는 들어가지 않는다.
    """
    if recipient_role is None:
        recipient = db.get(User, user_id)
        recipient_role = getattr(recipient, "role", None)
    row = Notification(
        user_id=user_id,
        type=type_,
        title=title[:200],
        body=body,
        related_object_type=related[0] if related else None,
        related_object_id=related[1] if related else None,
        audience=audience_for(type_, recipient_role, fallback=audience),
        created_at=now,
    )
    db.add(row)
    db.flush()
    _fan_out_mail(db, row, now=now, context=context)
    return row


def _fan_out_mail(db: Session, row: Notification, *, now: datetime, context: dict | None) -> None:
    """메일로도 보낸다(계획 3.4). **실패해도 화면 알림과 본 작업은 남는다.**

    저장점 안에서 한다. 메일 쪽 질의 하나가 실패해도 바깥 트랜잭션이 깨지지 않는다 - 깨지면 이 알림을 만든 티켓
    저장이 함께 실패한다.
    """
    from app.profiles.prefs import MAILABLE_TYPES

    if row.type not in MAILABLE_TYPES:
        return
    try:
        from app.notifications.mail import fan_out_mail

        with db.begin_nested():
            fan_out_mail(db, row, now=now, context=context)
    except Exception:  # noqa: BLE001 - 메일이 알림과 본 작업을 막으면 안 된다
        logger.exception("알림 메일을 큐에 넣지 못했다 (notification=%s)", row.id)


def _related_user(db: Session, related: tuple[str, str] | None) -> User | None:
    """알림이 가리키는 대상이 **사람**이면 그 사람. 아니면 None.

    사람이 대상인 사건(계정 잠금 등)만 범위 판정이 가능하다 — 백업·잡처럼 사람이 아닌
    대상은 어느 부서의 것인지 자체가 정해져 있지 않으므로 예전처럼 관리자 전원에게 간다.
    """
    if not related or related[0] != "user" or not related[1]:
        return None
    return db.get(User, related[1])


def notify_admins(
    db: Session,
    *,
    type_: str,
    title: str,
    body: str | None = None,
    related: tuple[str, str] | None = None,
    now: datetime,
) -> int:
    """관리자에게 팬아웃. **사람이 대상인 사건은 그 사람을 관리하는 관리자에게만 간다.**

    ## 왜 역할만으로는 안 되는가

    부서 범위 관리자(`admin_scope=dept`)에게 범위 밖 계정의 잠금 알림이 그대로 갔다. 제목에
    그 사람의 이메일이 실려 있고, 「관련 항목 보기」를 누르면 그 관리자에게는 존재하지 않는
    대상이라 404 다 — 알고도 할 수 있는 일이 없다. 같은 사건을 감사 로그 쪽은 이미
    `app/core/scope.py` 의 범위로 가리고 있었으므로(범위 밖 행위자는 목록에도 단건에도 안
    나온다), 한 사건에 대해 두 화면이 서로 다른 범위 규칙을 쓰고 있었다.

    판정은 그 두 화면과 **같은 함수**(`management_scope` + `scope_allows_user`)로 한다.
    여기서 규칙을 다시 쓰면 셋이 갈라지고, 갈라지는 방향 하나는 유출이다. 전역 관리자는
    `scope_allows_user` 가 언제나 참이라 예전과 똑같이 전부 받는다.

    ## 아무에게도 안 가는 경우는 없다

    범위로 거르면 **0 명**이 남을 수 있다. 부서가 없는 계정(`department_id IS NULL` 은
    실제 상태다, `app/users/models.py`)은 부서 범위 관리자의 판정에서 언제나 거짓이고,
    조직이 다르거나 관리 서브트리가 빈 관리자도 마찬가지다. 활성 관리자가 전부 그런
    사람들이면 계정 잠금 한 건이 **아무 데도 안 남고 조용히 사라진다** — 두 호출부
    (`app/auth/router.py`, `app/backups/service.py`)는 반환값을 안 보고 로그도 없었다.

    그래서 한 사람도 안 남으면 관리자 전원에게 보낸다. 「이 계정은 아무의 범위도 아니다」는
    곧 「아무도 책임지지 않는다」는 뜻이고, 그때는 모두의 일이 되는 편이 맞다. 범위를 좁힌
    의미는 그대로다 — 범위 안 관리자가 한 명이라도 있으면 폴백은 돌지 않는다. 대신 그
    사실을 경고로 남긴다(제목은 안 적는다 — 대상의 이메일이 들어 있다).
    """
    from app.core.org_tree import DeptTree
    from app.core.scope import management_scope, scope_allows_user

    admins = (
        db.execute(
            select(User).where(
                User.role.in_([ROLE_ADMIN, ROLE_SYSTEM_ADMIN]), User.active.is_(True)
            )
        )
        .scalars()
        .all()
    )
    target = _related_user(db, related)
    # 부서 트리는 **한 번만** 읽는다 — 관리자 수만큼 다시 읽으면 잠금 한 건이 트리 질의
    # 여러 번이 된다.
    tree = DeptTree.load(db) if target is not None else None
    recipients = [
        admin
        for admin in admins
        if target is None
        or scope_allows_user(management_scope(db, admin, tree), target)
    ]
    if not admins:
        logger.error(
            "관리 알림을 받을 활성 관리자가 없다: type=%s related=%s", type_, related
        )
    elif not recipients:
        logger.warning(
            "관리 범위 안 관리자가 없어 관리자 전원에게 보낸다: "
            "type=%s related=%s admins=%d",
            type_, related, len(admins),
        )
        recipients = list(admins)
    sent = 0
    for admin in recipients:
        notify_user(
            db, admin.id, type_=type_, title=title, body=body, related=related, now=now,
            # 관리자 전용 발송 — 개인 알림과 섞이면 안 된다(0051).
            audience=AUDIENCE_ADMIN, recipient_role=admin.role,
        )
        sent += 1
    return sent


def approver_user_ids(db: Session, *, now: datetime) -> list[str]:
    """**지금 결재할 수 있는 사람 전원** = 관리자 ∪ 활성 위임을 받은 사람 (X7).

    "누가 결재할 수 있는가" 의 정의는 `delegation.resolve_authority` 한 곳에 있다.
    여기서 그 규칙을 다시 쓰지 않고 **활성 위임 표를 그대로 읽는다** — 두 벌이 되면
    한쪽만 고쳐지고, 그때 증상은 "어떤 사람만 알림을 못 받는다" 라 찾기가 매우 어렵다.

    **목록을 함수로 뽑아 둔 이유**(9-9 P4): 승인 요청을 메일로도 알리게 되면서 수신자
    목록이 필요한 곳이 둘이 됐다. 각자 조회를 쓰면 `notify_admins` 만 부르던 예전 결함
    (피위임자는 admin 이 아니라 영원히 못 받는다)이 메일 쪽에서 그대로 되살아난다.

    반환 순서는 관리자 먼저, 그다음 피위임자다(중복 없음).
    """
    from app.approvals.models import ApprovalDelegation

    admin_ids = list(
        db.execute(
            select(User.id).where(
                User.role.in_([ROLE_ADMIN, ROLE_SYSTEM_ADMIN]), User.active.is_(True)
            )
        ).scalars().all()
    )
    delegate_ids = set(
        db.execute(
            select(ApprovalDelegation.delegate_user_id).where(
                ApprovalDelegation.revoked_at.is_(None),
                ApprovalDelegation.starts_at <= now,
                ApprovalDelegation.ends_at > now,
            )
        ).scalars().all()
    )
    if not delegate_ids:
        return admin_ids
    # 이미 관리자인 사람은 두 번 받지 않는다(위임은 역할과 무관하게 걸 수 있다).
    extra = list(
        db.execute(
            select(User.id).where(
                User.id.in_(delegate_ids - set(admin_ids)), User.active.is_(True)
            )
        ).scalars().all()
    )
    return admin_ids + extra


def notify_active_users(
    db: Session,
    *,
    type_: str,
    title: str,
    body: str | None = None,
    related: tuple[str, str] | None = None,
    now: datetime,
) -> int:
    """notify_admins와 같은 팬아웃이지만 역할 제한 없이 활성 사용자 전체 대상이다 —
    유지보수 공지처럼 일반 사용자도 알아야 하는 이벤트에 쓴다(spec §13.5).

    audience는 기본값('user')을 그대로 쓴다(0051) — 이름과 달리 "관리자용"이 아니라
    "역할 제한 없는 전체 공지"라 사용자 콘솔에서 보여야 할 개인 알림에 가깝다.
    """
    users = db.execute(select(User).where(User.active.is_(True))).scalars().all()
    for user in users:
        notify_user(
            db, user.id, type_=type_, title=title, body=body, related=related, now=now,
            recipient_role=user.role,
        )
    return len(users)


def mark_read(db: Session, user_id: str, notification_id: str, *, now: datetime) -> bool:
    """Idempotent: marking an already-read notification is a success (not 404).
    Returns False only when the notification does not belong to the user or
    does not exist.

    `mark_types_read`와 같은 이유(잦은 동시 쓰기)로 같은 SAVEPOINT 재시도를 쓴다."""
    row = db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,  # 소유권 — 남의 알림 읽음 처리 불가
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    if row.read_at is None:
        for attempt in range(DEFAULT_WRITE_CONFLICT_RETRIES):
            try:
                with db.begin_nested():
                    row.read_at = now
                    db.flush()
                break
            except (IntegrityError, OperationalError) as exc:
                if not is_serialization_conflict(exc):
                    raise
                db.refresh(row)
                if row.read_at is not None:
                    break  # 다른 요청이 먼저 읽음 처리했다 — 목표 상태는 이미 달성됨
                if attempt < DEFAULT_WRITE_CONFLICT_RETRIES - 1:
                    time.sleep(write_conflict_backoff(attempt))
                else:
                    raise WriteUnavailableError()
    return True


def mark_all_read(
    db: Session, user_id: str, *, now: datetime, audience: str | None = None
) -> int:
    """현재 사용자의 안 읽은 알림을 한 번에 읽음 처리한다(소유권 범위 안에서만).
    반환값은 읽음 처리된 건수.

    `audience` 는 선택 필터다 — None(기본값)이면 예전과 똑같이 전체다. 부르는 쪽이 값을
    주면 **그 화면이 실제로 보여 준 것만** 읽음이 된다(`unread_count` 와 같은 규칙).
    이 인자가 없던 동안 「내 업무 > 알림」의 '모두 읽음' 한 번이 관리 알림까지 삼켰다.

    `mark_types_read`와 같은 이유(잦은 동시 쓰기)로 같은 SAVEPOINT 재시도를 쓴다."""
    where = [Notification.user_id == user_id, Notification.read_at.is_(None)]
    if audience:
        where.append(Notification.audience == audience)
    for attempt in range(DEFAULT_WRITE_CONFLICT_RETRIES):
        try:
            with db.begin_nested():
                result = db.execute(
                    update(Notification).where(*where).values(read_at=now)
                )
            db.flush()
            return int(result.rowcount or 0)
        except (IntegrityError, OperationalError) as exc:
            if not is_serialization_conflict(exc):
                raise
            if attempt < DEFAULT_WRITE_CONFLICT_RETRIES - 1:
                time.sleep(write_conflict_backoff(attempt))
    raise WriteUnavailableError()


def unread_by_type(
    db: Session, user_id: str, *, exclude: list[str] | None = None, audience: str | None = None
) -> dict[str, int]:
    """{알림 유형: 안 읽음 수}. 사이드바 항목별 배지가 이 값을 쓴다 (사용자 지적 S2).

    예전에는 합계(`unread`)만 돌려줬다. 그러면 화면은 "안 읽은 것이 12건" 까지만 알 수 있고
    **어느 메뉴에 생긴 일인지**는 모른다 — 사용자가 요구한 "왼쪽 사이드에 신규 표시" 를
    할 수가 없었다. 종류별로 세어 돌려주면 화면이 메뉴에 나눠 붙인다.

    `exclude` 는 뮤트한 유형이다. `unread_count_excluding` 과 같은 원칙으로 **빼는 것은
    '지금 눈길을 끌 것인가' 하나뿐**이고, 알림 자체는 목록에 그대로 남는다.

    `audience` 는 선택 필터다(0051). None(기본값)이면 예전과 똑같이 전체를 센다 — 기존
    호출부(방해금지 배지)의 계약을 건드리지 않는다.
    """
    from sqlalchemy import func

    stmt = (
        select(Notification.type, func.count())
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .group_by(Notification.type)
    )
    if exclude:
        stmt = stmt.where(Notification.type.notin_(exclude))
    if audience:
        stmt = stmt.where(Notification.audience == audience)
    return {t: int(n) for t, n in db.execute(stmt).all()}


def mark_types_read(db: Session, user_id: str, types: list[str], *, now: datetime) -> int:
    """그 유형들의 안 읽은 알림을 읽음 처리한다. 반환값은 처리 건수.

    사용자 지적 S2 의 뒷절반: "확인하면 자동으로 없애는 형태로". 화면을 열었다는 것은
    그 종류의 알림을 확인했다는 뜻이므로, 그 화면이 진입 시 자기 유형을 읽음 처리한다.
    **폴링이 아니라 화면 진입 이벤트**다 — 폴링으로 지우면 열지도 않은 알림이 사라진다.

    유형 목록이 비면 아무 일도 하지 않는다(빈 목록을 '전부'로 해석하면 화면 하나를 여는
    것이 모든 알림을 지우는 사고가 된다).

    화면 진입마다 호출되는 자리라 다른 요청의 쓰기와 부딪힐 일이 흔하다(whole-product
    Chrome E2E 710페이지 스윕에서 실측: `database is locked`가 그대로 500으로 샜다) —
    `app/core/db.py`의 공용 SAVEPOINT 재시도 관용(`team_chat/service.py::_append_message`와
    같은 패턴)을 그대로 쓴다. 경쟁할 로컬 카운터가 없는 단순 UPDATE라 `db.refresh()`는
    필요 없다.
    """
    if not types:
        return 0
    for attempt in range(DEFAULT_WRITE_CONFLICT_RETRIES):
        try:
            with db.begin_nested():
                result = db.execute(
                    update(Notification)
                    .where(
                        Notification.user_id == user_id,
                        Notification.read_at.is_(None),
                        Notification.type.in_(types),
                    )
                    .values(read_at=now)
                )
            db.flush()
            return int(result.rowcount or 0)
        except (IntegrityError, OperationalError) as exc:
            if not is_serialization_conflict(exc):
                raise
            if attempt < DEFAULT_WRITE_CONFLICT_RETRIES - 1:
                time.sleep(write_conflict_backoff(attempt))
    raise WriteUnavailableError()


def unread_count(db: Session, user_id: str, *, audience: str | None = None) -> int:
    """전체(또는 audience로 좁힌) 안 읽음 총계.

    `audience` 는 선택 필터다(0051) — None(기본값)이면 예전과 똑같은 총계를 돌려준다,
    벨 배지 등 기존 계약을 지키는 호출부는 인자를 안 넘기면 그만이다.
    """
    from sqlalchemy import func

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    if audience:
        stmt = stmt.where(Notification.audience == audience)
    return db.execute(stmt).scalar_one()


def unread_count_excluding(
    db: Session, user_id: str, types: list[str], *, audience: str | None = None
) -> int:
    """배지에 세는 안 읽음 — 사용자가 뮤트한 유형만 뺀다.

    **알림 자체를 지우거나 안 만드는 것이 아니다.** 뮤트한 유형도 `unread_count` 에는
    그대로 잡히고 목록에도 그대로 나온다. 여기서 빠지는 것은 '지금 눈길을 끌 것인가'
    하나뿐이다 — 방해금지와 같은 원칙이다(app/profiles/prefs.py 모듈 docstring).

    `audience` 는 선택 필터다(0051), `unread_count`와 같은 기본값 규칙을 따른다.
    """
    if not types:
        return unread_count(db, user_id, audience=audience)
    from sqlalchemy import func

    stmt = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
            Notification.type.notin_(types),
        )
    )
    if audience:
        stmt = stmt.where(Notification.audience == audience)
    return db.execute(stmt).scalar_one()
