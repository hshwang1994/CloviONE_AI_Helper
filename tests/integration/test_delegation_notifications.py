"""위임받은 사람이 **자기가 결재할 수 있다는 사실을 알게 된다** (X7).

`notify_admins` 는 admin 만 부른다. 그런데 **피위임자는 정의상 admin 이 아니다** — 그게
위임의 전부이기 때문이다(평소 결재할 수 없는 사람에게 권한을 빌려주는 것).
그래서 결재하라고 권한을 준 사람에게 **결재할 게 생겼다는 알림이 절대 안 갔다.**
위임받은 사실조차 통보되지 않았다. 승인 큐가 밀리는 이유가 여기 있었고, 위임 기능 자체가
반쯤 장식이었다.

세 가지를 본다:

1. 위임을 만들면 **당사자가 안다**
2. 새 승인 요청·기한 초과 알림이 **피위임자에게도** 간다
3. 위임이 끝난 뒤 첫 시도에 **"권한이 없습니다"** 가 아니라 **끝났다는 사실**을 말한다
   — 둘을 같은 문구로 뭉개면 어제까지 결재하던 사람이 시스템 고장으로 신고한다
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


def _notifications_for(db, user_id: str) -> list:
    from sqlalchemy import select

    from app.notifications.models import Notification

    return db.execute(
        select(Notification).where(Notification.user_id == user_id)
    ).scalars().all()


@pytest.fixture()
def pair(db, make_user):
    """결재 권한이 있는 관리자 A + 평소에는 결재할 수 없는 운영자 B."""
    a = make_user("deleg-a@goodmit.co.kr", role="admin", display_name="관리자A")
    b = make_user("deleg-b@goodmit.co.kr", role="operator", display_name="운영자B")
    db.commit()
    return a, b


def test_the_delegate_is_told_they_were_delegated(db, pair):
    from app.approvals import delegation

    a, b = pair
    now = datetime(2026, 8, 1, 9, 0)
    delegation.create(
        db, delegator=a, delegate=b,
        starts_at=now, ends_at=now + timedelta(days=3),
        reason="휴가", created_by=a.id, now=now, visible=None,
    )
    db.commit()

    types = {n.type for n in _notifications_for(db, b.id)}
    assert "approval_delegated" in types, (
        f"위임받은 사실을 당사자가 모른다 — 권한이 생긴 줄도 모른다: {types}"
    )


def test_a_new_approval_request_reaches_the_delegate(db, pair, make_user):
    from app.approvals import delegation, service

    a, b = pair
    requester = make_user("deleg-req@goodmit.co.kr", role="user", display_name="요청자")
    now = datetime(2026, 8, 1, 9, 0)
    delegation.create(
        db, delegator=a, delegate=b,
        starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=3),
        reason=None, created_by=a.id, now=now, visible=None,
    )
    db.commit()
    before = len([n for n in _notifications_for(db, b.id) if n.type == "approval_requested"])

    service.create_approval(
        db,
        request_type="user.role_change",
        object_type="user",
        object_id=requester.id,
        payload={"role": "admin"},
        requested_by=requester,
        now=now,
    )
    db.commit()

    after = len([n for n in _notifications_for(db, b.id) if n.type == "approval_requested"])
    assert after == before + 1, (
        "결재할 수 있게 만들어 준 사람에게 결재할 게 생겼다는 알림이 안 간다"
    )


def test_an_admin_does_not_get_the_same_thing_twice(db, pair, make_user):
    """위임은 역할과 무관하게 걸 수 있다 — 이미 관리자인 사람이 두 번 받으면 안 된다."""
    from app.approvals import delegation, service

    a, _ = pair
    other_admin = make_user("deleg-c@goodmit.co.kr", role="admin", display_name="관리자C")
    requester = make_user("deleg-req2@goodmit.co.kr", role="user", display_name="요청자2")
    now = datetime(2026, 8, 1, 9, 0)
    delegation.create(
        db, delegator=a, delegate=other_admin,
        starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=3),
        reason=None, created_by=a.id, now=now, visible=None,
    )
    db.commit()

    service.create_approval(
        db,
        request_type="user.role_change", object_type="user", object_id=requester.id,
        payload={"role": "admin"}, requested_by=requester, now=now,
    )
    db.commit()

    got = [n for n in _notifications_for(db, other_admin.id) if n.type == "approval_requested"]
    assert len(got) == 1, f"같은 알림을 두 번 받았다: {len(got)}건"


def test_an_expired_delegation_says_so_instead_of_permission_denied(db, pair):
    """어제까지 결재하던 사람이 오늘 "권한이 없습니다" 를 보면 고장으로 신고한다."""
    from app.approvals import delegation
    from app.core.errors import ForbiddenError

    a, b = pair
    start = datetime(2026, 8, 1, 9, 0)
    delegation.create(
        db, delegator=a, delegate=b,
        starts_at=start, ends_at=start + timedelta(days=1),
        reason=None, created_by=a.id, now=start, visible=None,
    )
    db.commit()

    after_end = start + timedelta(days=2)
    with pytest.raises(ForbiddenError) as exc:
        delegation.require_decider(db, b, after_end)

    assert "끝났" in exc.value.message, (
        f"위임이 끝난 것과 애초에 권한이 없는 것을 같은 말로 뭉갠다: {exc.value.message}"
    )


# ── 사람이 읽는 시각은 KST 다 (perm-04) ──────────────────────────────────────
#
# 저장은 naive UTC 이고 화면은 KST 로 그린다. 그런데 **서버가 완성된 문장을 만드는 세 자리**
# (위임 알림 본문 · 겹침 409 · 권한 없음 403)는 화면이 고칠 수 없어서, 대리인이 자기 권한
# 기간을 하루 어긋나게 알고 관리자는 9시간 어긋난 창을 피해 다시 시도하다 또 409 를 받았다.

# UTC 17:00 은 KST 로 **다음 날** 02:00 이다 — 이 경계가 어긋남을 눈에 보이게 한다.
_UTC_EVENING = datetime(2026, 8, 1, 17, 0)


def test_the_delegation_notice_speaks_in_kst(db, pair):
    a, b = pair
    from app.approvals import delegation

    delegation.create(
        db, delegator=a, delegate=b,
        starts_at=_UTC_EVENING, ends_at=_UTC_EVENING + timedelta(days=3),
        reason=None, created_by=a.id, now=_UTC_EVENING - timedelta(hours=1), visible=None,
    )
    db.commit()

    body = [n for n in _notifications_for(db, b.id) if n.type == "approval_delegated"][0].body
    assert "08월 02일부터 08월 05일까지" in body, (
        f"저장된 UTC 를 그대로 찍는다 — 대리인이 하루 어긋난 기간을 안다: {body}"
    )


def test_the_overlap_message_speaks_in_kst(db, pair):
    from app.approvals import delegation
    from app.core.errors import ConflictError

    a, b = pair
    now = _UTC_EVENING - timedelta(hours=1)
    delegation.create(
        db, delegator=a, delegate=b,
        starts_at=_UTC_EVENING, ends_at=_UTC_EVENING + timedelta(days=3),
        reason=None, created_by=a.id, now=now, visible=None,
    )
    db.commit()

    with pytest.raises(ConflictError) as exc:
        delegation.create(
            db, delegator=a, delegate=b,
            starts_at=_UTC_EVENING + timedelta(days=1),
            ends_at=_UTC_EVENING + timedelta(days=2),
            reason=None, created_by=a.id, now=now, visible=None,
        )
    assert "08월 02일 02시부터 08월 05일 02시까지" in exc.value.message, (
        f"겹침 안내가 실제와 9시간 다른 창을 알려 준다: {exc.value.message}"
    )


def test_a_revoked_delegation_says_it_was_revoked_not_that_it_ended(db, pair):
    """회수된 위임에 `ends_at` 을 말하면 **아직 오지 않은 시각**을 「끝난 시각」이라고 한다.
    「스스로 끝났다」와 「관리자가 거뒀다」는 다른 사건이라 다른 문장을 준다."""
    from app.approvals import delegation
    from app.core.errors import ForbiddenError

    a, b = pair
    start = datetime(2026, 8, 1, 9, 0)
    row = delegation.create(
        db, delegator=a, delegate=b,
        starts_at=start, ends_at=start + timedelta(days=30),
        reason=None, created_by=a.id, now=start, visible=None,
    )
    db.commit()

    revoked_at = start + timedelta(days=1)
    delegation.revoke(db, row, now=revoked_at)
    db.commit()

    with pytest.raises(ForbiddenError) as exc:
        delegation.require_decider(db, b, revoked_at + timedelta(hours=1))
    message = exc.value.message
    assert "거두었습니다" in message, f"거둔 위임을 「끝났다」고 말한다: {message}"
    assert "08월 31일" not in message, f"아직 오지 않은 종료 시각을 말한다: {message}"


# ── 지난 기간 · 끝난 위임 (perm-19 · perm-18) ────────────────────────────────


def test_a_delegation_that_is_already_over_cannot_be_created(db, pair):
    """만들자마자 「종료」인 위임은 아무 권한도 주지 않는데 대리인에게는 「승인할 수
    있습니다」 통보가 나가고 관리자는 성공 토스트를 본다 — 연도 오타가 조용히 통과한다."""
    from app.approvals import delegation
    from app.core.errors import ValidationAppError

    a, b = pair
    now = datetime(2026, 8, 10, 9, 0)
    with pytest.raises(ValidationAppError) as exc:
        delegation.create(
            db, delegator=a, delegate=b,
            starts_at=now - timedelta(days=40), ends_at=now - timedelta(days=35),
            reason=None, created_by=a.id, now=now, visible=None,
        )
    assert "지난 기간" in exc.value.message, exc.value.message
    assert not _notifications_for(db, b.id), "만들지 않은 위임의 통보가 나갔다"


def test_a_future_window_is_still_accepted(db, pair):
    """오탐 방지 — 예약 위임(아직 시작 전)까지 막히면 부재 대비가 불가능하다."""
    from app.approvals import delegation

    a, b = pair
    now = datetime(2026, 8, 10, 9, 0)
    row = delegation.create(
        db, delegator=a, delegate=b,
        starts_at=now + timedelta(days=5), ends_at=now + timedelta(days=8),
        reason=None, created_by=a.id, now=now, visible=None,
    )
    db.commit()
    assert delegation.state(row, now) == "scheduled"


def test_an_already_ended_delegation_cannot_be_revoked(db, pair):
    """「저절로 닫혔다」와 「관리자가 거뒀다」는 다른 사실인데 호출 한 번으로 뒤바뀌었다 —
    상태가 「거둠」이 되고 목록의 종료 시각도 오늘로 바뀐다."""
    from app.approvals import delegation
    from app.core.errors import ConflictError

    a, b = pair
    start = datetime(2026, 8, 1, 9, 0)
    row = delegation.create(
        db, delegator=a, delegate=b,
        starts_at=start, ends_at=start + timedelta(days=1),
        reason=None, created_by=a.id, now=start, visible=None,
    )
    db.commit()

    after_end = start + timedelta(days=5)
    with pytest.raises(ConflictError):
        delegation.revoke(db, row, now=after_end)
    db.refresh(row)
    assert row.revoked_at is None, "거둘 수 없다고 했는데 회수 시각이 찍혔다"
    assert delegation.state(row, after_end) == "ended"


def test_a_live_delegation_can_still_be_revoked(db, pair):
    """오탐 방지 — 진행 중·예약 위임의 회수는 그대로 된다."""
    from app.approvals import delegation

    a, b = pair
    start = datetime(2026, 8, 1, 9, 0)
    row = delegation.create(
        db, delegator=a, delegate=b,
        starts_at=start, ends_at=start + timedelta(days=3),
        reason=None, created_by=a.id, now=start, visible=None,
    )
    db.commit()

    delegation.revoke(db, row, now=start + timedelta(hours=2))
    db.commit()
    assert row.revoked_at == start + timedelta(hours=2)
    assert delegation.state(row, start + timedelta(hours=3)) == "revoked"


def test_someone_who_never_had_a_delegation_gets_the_plain_message(db, make_user):
    """오탐 방지 — 위임을 받은 적 없는 사람에게 "끝났습니다" 는 거짓말이다."""
    from app.approvals import delegation
    from app.core.errors import ForbiddenError

    stranger = make_user("deleg-none@goodmit.co.kr", role="operator", display_name="무관")
    db.commit()

    with pytest.raises(ForbiddenError) as exc:
        delegation.require_decider(db, stranger, datetime(2026, 8, 3, 9, 0))

    assert "끝났" not in exc.value.message, (
        f"받은 적 없는 위임이 끝났다고 말한다: {exc.value.message}"
    )
