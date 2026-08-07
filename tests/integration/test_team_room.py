"""부서 방('내 팀')이 기본으로 있는가 (Q6).

사용자 지적: "홈 및 채팅방에 default 로 만들어진 방은 기본적으로 내 팀임."
지금까지 기본으로 있던 방은 `전체 채팅` 하나뿐이었다 — 회사 전체는 매일 쓰는 단위가 아니다.

여기서 지키는 것:
  * 부서가 있는 사용자는 방 목록을 여는 것만으로 자기 팀 방을 갖는다(미리 만들지 않는다).
  * 그 방은 `items` 가 아니라 **따로** 실린다 — 목록에 섞이면 마지막 대화 시각 순으로
    밀려 내려가 "기본 방" 이라는 성격이 사라진다.
  * 부서가 없으면 만들지 않는다 — 없는 팀의 방을 만들어 주지 않는다.
  * 두 번 열어도 방이 두 개가 되지 않는다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _dept(db_session, name="플랫폼팀"):
    from app.org.models import Department

    row = Department(name=name, active=True)
    db_session.add(row)
    db_session.flush()
    return row


def test_user_without_department_gets_no_team_room(client, login_as):
    login_as("user")
    body = client.get("/api/team-chat/rooms").json()
    assert body.get("team") is None, "부서가 없는 사용자에게 팀 방을 만들면 안 된다"
    assert body.get("global") is not None, "전체 채팅은 그대로 있어야 한다"


def test_team_room_appears_for_a_user_with_a_department(client, login_as, make_user, app):
    from app.org.models import Department
    from app.users.models import User

    make_user("teamer@goodmit.co.kr")
    with app.state.session_factory() as db:
        dept = Department(name="플랫폼팀", active=True)
        db.add(dept)
        db.flush()
        user = db.query(User).filter(User.email == "teamer@goodmit.co.kr").one()
        user.department_id = dept.id
        db.commit()

    login_as("user", email="teamer@goodmit.co.kr")
    body = client.get("/api/team-chat/rooms").json()

    team = body.get("team")
    assert team is not None, "부서가 있는데 팀 방이 없다"
    assert team["title"] == "플랫폼팀", f"팀 방 이름은 부서 이름이어야 한다: {team}"
    assert team["department_id"] is not None, "화면이 '내 팀' 태그를 붙이려면 이 값이 필요하다"
    # 목록에 섞이면 안 된다 — 맨 위 고정 자리를 잃는다.
    assert all(r["id"] != team["id"] for r in body["items"]), "팀 방이 items 에도 들어 있다"


def test_opening_the_list_twice_does_not_create_two_rooms(client, login_as, make_user, app):
    from app.org.models import Department
    from app.team_chat.models import ChatRoom
    from app.users.models import User

    make_user("twice@goodmit.co.kr")
    with app.state.session_factory() as db:
        dept = Department(name="인프라팀", active=True)
        db.add(dept)
        db.flush()
        db.query(User).filter(User.email == "twice@goodmit.co.kr").one().department_id = dept.id
        db.commit()
        dept_id = dept.id

    login_as("user", email="twice@goodmit.co.kr")
    first = client.get("/api/team-chat/rooms").json()["team"]["id"]
    second = client.get("/api/team-chat/rooms").json()["team"]["id"]
    assert first == second

    with app.state.session_factory() as db:
        rooms = db.query(ChatRoom).filter(ChatRoom.department_id == dept_id).all()
    assert len(rooms) == 1, f"팀 방이 {len(rooms)}개 만들어졌다"


def test_renaming_the_department_renames_the_room(client, login_as, make_user, app):
    """팀 방의 이름은 팀 이름이지 따로 관리하는 값이 아니다."""
    from app.org.models import Department
    from app.users.models import User

    make_user("renamed@goodmit.co.kr")
    with app.state.session_factory() as db:
        dept = Department(name="옛이름팀", active=True)
        db.add(dept)
        db.flush()
        db.query(User).filter(User.email == "renamed@goodmit.co.kr").one().department_id = dept.id
        db.commit()
        dept_id = dept.id

    login_as("user", email="renamed@goodmit.co.kr")
    assert client.get("/api/team-chat/rooms").json()["team"]["title"] == "옛이름팀"

    with app.state.session_factory() as db:
        db.get(Department, dept_id).name = "새이름팀"
        db.commit()

    assert client.get("/api/team-chat/rooms").json()["team"]["title"] == "새이름팀"


def test_room_detail_also_carries_department_id(client, login_as, make_user, app):
    """방 목록(`GET /rooms`)의 팀 방 행에는 `department_id`가 있어 화면이 "내 팀" 태그를
    붙인다(위 `team_room_appears_for_a_user_with_a_department` 참고). 그런데 방 안에 들어가서
    보는 상세(`GET /rooms/{id}/messages`)의 `room`에는 이 값이 없었다 — 같은 방인데 목록에서는
    "내 팀"이라 하고 방 머리(ChatRoom.jsx RoomDetailPanel)에서는 "그룹 N"이라 해, 방에 들어가는
    순간 표식이 바뀌는 자기모순이 났다(화면 쪽 주석이 "목록에서 보던 표식이 방에 들어오면
    사라지면 안 된다"고 이미 말하고 있다)."""
    from app.org.models import Department
    from app.users.models import User

    make_user("detail-tag@goodmit.co.kr")
    with app.state.session_factory() as db:
        dept = Department(name="상세팀", active=True)
        db.add(dept)
        db.flush()
        db.query(User).filter(User.email == "detail-tag@goodmit.co.kr").one().department_id = dept.id
        db.commit()

    login_as("user", email="detail-tag@goodmit.co.kr")
    team = client.get("/api/team-chat/rooms").json()["team"]
    assert team["department_id"] is not None

    detail = client.get(f"/api/team-chat/rooms/{team['id']}/messages?since=0").json()
    assert detail["room"]["department_id"] == team["department_id"], (
        "방 상세의 room 에도 department_id 가 있어야 목록과 같은 '내 팀' 태그를 그릴 수 있다"
    )
