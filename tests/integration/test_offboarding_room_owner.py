"""오프보딩이 **채팅방 방장직도** 넘긴다 (X8).

퇴사자가 그룹 방의 방장으로 남으면 **아무도 그 방을 관리할 수 없다** — 사람을 더 부르거나
방 이름을 바꾸거나 방을 파할 사람이 없다. 그런데 오프보딩은 티켓만 옮기고 방은 손대지 않은 채
**"완료"** 를 보고했다. 관리자는 끝났다고 믿는다.

경계 조건이 이 기능의 전부다:

* 후임이 **그 방 멤버면** 후임에게, 아니면 **가장 오래된 다른 멤버**에게
* 후임을 방에 **억지로 넣지 않는다** — 오프보딩은 남의 대화방에 사람을 밀어 넣는 일이 아니다
* 넘길 사람이 아무도 없으면 **그대로 둔다** — 받을 사람 없이 방장을 비우면 되살릴 방법이 없다
* **멤버십은 유지한다** — 지우면 지난 대화의 발신자가 참여자 목록에서 사라진다(N3)
* 1:1·전체 방은 건드리지 않는다 — 방장 개념이 뜻을 갖지 않는다
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest


def _room(db, *, name, kind="group", is_global=False):
    from app.team_chat.models import ChatRoom

    room = ChatRoom(title=name, kind=kind, is_global=is_global)
    db.add(room)
    db.flush()
    return room


def _member(db, room, user, *, role="member", joined_at=None):
    from app.team_chat.models import ChatRoomMember

    m = ChatRoomMember(
        room_id=room.id, user_id=user.id, role=role,
        joined_at=joined_at or datetime(2026, 1, 1),
    )
    db.add(m)
    db.flush()
    return m


def _role_of(db, room, user) -> str | None:
    from sqlalchemy import select

    from app.team_chat.models import ChatRoomMember

    row = db.execute(
        select(ChatRoomMember).where(
            ChatRoomMember.room_id == room.id, ChatRoomMember.user_id == user.id
        )
    ).scalar_one_or_none()
    return None if row is None else row.role


@pytest.fixture()
def cast(db, make_user):
    leaver = make_user("ob-leaver@goodmit.co.kr", role="user", display_name="퇴사자")
    successor = make_user("ob-succ@goodmit.co.kr", role="user", display_name="후임")
    mate = make_user("ob-mate@goodmit.co.kr", role="user", display_name="동료")
    db.commit()
    return leaver, successor, mate


def _transfer(db, leaver, successor):
    from app.team_chat.service import transfer_owned_rooms

    n = transfer_owned_rooms(db, target=leaver, successor=successor)
    db.commit()
    return n


def test_the_successor_takes_over_when_they_are_in_the_room(db, cast):
    leaver, successor, mate = cast
    room = _room(db, name="프로젝트방")
    _member(db, room, leaver, role="owner")
    _member(db, room, mate, joined_at=datetime(2026, 1, 2))
    _member(db, room, successor, joined_at=datetime(2026, 5, 1))
    db.commit()

    assert _transfer(db, leaver, successor) == 1
    assert _role_of(db, room, successor) == "owner", "후임이 방 멤버인데 방장이 안 됐다"
    assert _role_of(db, room, leaver) == "member", "퇴사자가 아직 방장이다"


def test_the_oldest_remaining_member_takes_over_when_the_successor_is_not_in_the_room(db, cast):
    """후임을 방에 억지로 넣지 않는다 — 남의 대화방에 사람을 밀어 넣는 일이 아니다."""
    leaver, successor, mate = cast
    room = _room(db, name="옛날방")
    _member(db, room, leaver, role="owner")
    _member(db, room, mate, joined_at=datetime(2026, 2, 1))
    db.commit()

    assert _transfer(db, leaver, successor) == 1
    assert _role_of(db, room, mate) == "owner", "남은 멤버가 방장이 안 됐다"
    assert _role_of(db, room, successor) is None, (
        "후임이 자기가 들어간 적 없는 방에 멤버로 밀어 넣어졌다"
    )


def test_a_room_with_nobody_else_is_left_alone(db, cast):
    """받을 사람 없이 방장을 비우면 그때부터는 **되살릴 방법도 없다.**"""
    leaver, successor, _ = cast
    room = _room(db, name="혼자방")
    _member(db, room, leaver, role="owner")
    db.commit()

    assert _transfer(db, leaver, successor) == 0
    assert _role_of(db, room, leaver) == "owner", "받을 사람이 없는데 방장을 비웠다"


def test_membership_is_kept_so_past_messages_still_have_a_sender(db, cast):
    """멤버십을 지우면 지난 대화의 발신자가 참여자 목록에서 사라진다(N3)."""
    leaver, successor, mate = cast
    room = _room(db, name="기록방")
    _member(db, room, leaver, role="owner")
    _member(db, room, mate, joined_at=datetime(2026, 3, 1))
    db.commit()

    _transfer(db, leaver, successor)
    assert _role_of(db, room, leaver) is not None, "퇴사자를 방에서 통째로 빼 버렸다"


def test_an_inactive_oldest_member_is_skipped_for_the_next_active_one(db, cast, make_user):
    """UA-26: 이 함수는 "로그인 못 하는 계정이 방장으로 남으면 아무도 관리 못 한다"는
    바로 그 문제를 막으려고 있다 — 넘겨받는 사람 자체가 로그인 못 하면 같은 문제가
    새 이름으로 재발한다. 가장 오래된 멤버가 이미 비활성이면 건너뛰고 그다음으로
    오래된 활성 멤버에게 넘어가야 한다."""
    leaver, successor, mate = cast
    ghost = make_user("ob-ghost@goodmit.co.kr", role="user", display_name="퇴사한동료",
                      active=False)
    db.commit()
    room = _room(db, name="유령방")
    _member(db, room, leaver, role="owner")
    _member(db, room, ghost, joined_at=datetime(2026, 1, 2))  # 가장 오래됐지만 비활성
    _member(db, room, mate, joined_at=datetime(2026, 3, 1))   # 그다음으로 오래됨, 활성

    assert _transfer(db, leaver, successor) == 1
    assert _role_of(db, room, mate) == "owner", "활성 멤버를 두고 비활성 계정에 넘어갔다"
    assert _role_of(db, room, ghost) != "owner", "비활성 계정이 방장이 됐다"


def test_a_room_where_the_only_other_member_is_inactive_is_left_alone(db, cast, make_user):
    """받을 사람이 전부 로그인 못 하면 "받을 사람이 아무도 없다"와 같은 결론이어야
    한다 — 받을 사람 없이 방장을 비우면 되살릴 방법이 없다."""
    leaver, successor, _mate = cast
    ghost = make_user("ob-ghost2@goodmit.co.kr", role="user", display_name="퇴사한동료2",
                      active=False)
    db.commit()
    room = _room(db, name="유령전용방")
    _member(db, room, leaver, role="owner")
    _member(db, room, ghost, joined_at=datetime(2026, 1, 2))

    assert _transfer(db, leaver, successor) == 0
    assert _role_of(db, room, leaver) == "owner", "받을 활성 계정이 없는데 방장을 비웠다"


def test_dm_and_global_rooms_are_untouched(db, cast):
    """방장 개념이 뜻을 갖지 않는 방이다."""
    leaver, successor, mate = cast
    dm = _room(db, name="1:1", kind="dm")
    _member(db, dm, leaver, role="owner")
    _member(db, dm, mate, joined_at=datetime(2026, 4, 1))
    everyone = _room(db, name="전체 채팅", is_global=True)
    _member(db, everyone, leaver, role="owner")
    _member(db, everyone, mate, joined_at=datetime(2026, 4, 1))
    db.commit()

    assert _transfer(db, leaver, successor) == 0
    assert _role_of(db, dm, leaver) == "owner"
    assert _role_of(db, everyone, leaver) == "owner"


def test_the_run_records_how_many_rooms_moved(client, login_as, db, cast, monkeypatch):
    """관리자가 "무엇을 했는가" 를 나중에 확인할 수 있어야 한다.

    응답에만 싣고 저장하지 않으면 **이력 화면이 방 이전을 영원히 모른다.**
    """
    from app.offboarding import service

    leaver, successor, mate = cast
    room = _room(db, name="이력방")
    _member(db, room, leaver, role="owner")
    _member(db, room, mate, joined_at=datetime(2026, 6, 1))
    db.commit()

    login_as("system_admin")
    monkeypatch.setattr(service, "_move_tickets", lambda *a, **k: [])

    from sqlalchemy import select

    from app.offboarding.models import OffboardingRun

    result = service.run_offboarding(
        db,
        outbound=None,
        settings=None,
        actor=db.execute(
            select(type(leaver)).where(type(leaver).email == "system-admin@goodmit.co.kr")
        ).scalar_one(),
        target=leaver,
        successor=successor,
        page_ids=[],
        deactivate=True,
        archive=False,
        session_service=client.app.state.session_service,
        now=datetime(2026, 8, 1, 9, 0) + timedelta(0),
    )
    assert result["run"]["rooms_transferred"] == 1, (
        f"실행 결과가 방 이전 건수를 말하지 않는다: {result['run']}"
    )
    db.expire_all()
    saved = db.get(OffboardingRun, result["run"]["id"])
    assert saved.rooms_transferred == 1, "응답에만 있고 저장되지 않았다 — 이력이 모른다"
