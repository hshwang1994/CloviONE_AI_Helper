"""`people` payload 가 화면이 필요한 것을 **전부** 싣는다 (N4 / N3 / X13).

이 payload 는 서버가 오래전부터 보내고 있었는데 **프런트가 한 번도 안 읽었다**(N4).
읽게 만들고 나니 세 가지가 더 필요했다:

* **소속**(dept/title/org) — 같은 이름 두 사람이 한 방에 있으면 말풍선만으로는 구분할 수 없다
* **`archived`**(N3) — 퇴사자가 영원히 발신자로 살아 있으면 보는 사람은 답이 안 오는 대화를
  며칠 기다린다. 시스템에서 가장 비싼 침묵이다
* **`avatar_url`**(X13) — 사진 기능이 있는데 **자기 우상단에만** 보였다. 서빙 경로
  (`/api/profile/avatar/{user_id}`)는 **이미 전 직원 대상**이고, 빠져 있던 것은 남의 주소를
  알려 주는 이 payload 하나뿐이었다

그리고 **한 번의 질의로** 모아 온다 — 이 응답은 메시지 폴링마다 나가므로 건별 조회면
가장 뜨거운 경로가 바로 N+1 이 된다(H4 가 지적한 그 모양).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _global_room(client):
    return client.get("/api/team-chat/rooms").json()["global"]["id"]


def test_people_carries_affiliation_and_archived_flag(client, login_as, make_user, db):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    dept = Department(name="ClovirONE팀", org_id=DEFAULT_ORG_ID)
    db.add(dept)
    db.commit()

    speaker = make_user("pp-speaker@goodmit.co.kr", role="user", display_name="김철수")
    speaker.department_id = dept.id
    db.commit()

    csrf = login_as("user", email="pp-speaker@goodmit.co.kr")
    gid = _global_room(client)
    assert client.post(
        f"/api/team-chat/rooms/{gid}/messages", json={"body": "안녕"},
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200

    person = client.get(f"/api/team-chat/rooms/{gid}/messages?since=0").json()["people"][speaker.id]
    assert person["dept"] == "ClovirONE팀", f"소속이 안 실린다: {person}"
    assert person["archived"] is False
    assert "avatar_url" in person, f"사진 자리가 아예 없다 — 화면이 그릴 수 없다: {person}"


def test_people_says_when_the_sender_is_gone(client, login_as, make_user, db):
    """퇴사자가 참여자·발신자로 영원히 살아 있으면 아무도 그 사실을 모른다 (N3)."""
    from datetime import datetime, timezone

    speaker = make_user("pp-gone@goodmit.co.kr", role="user", display_name="퇴사자")
    db.commit()
    csrf = login_as("user", email="pp-gone@goodmit.co.kr")
    gid = _global_room(client)
    client.post(f"/api/team-chat/rooms/{gid}/messages", json={"body": "마지막 인사"},
                headers={"X-CSRF-Token": csrf})

    speaker.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    speaker.active = False
    db.commit()

    reader = login_as("system_admin")
    assert reader
    person = client.get(f"/api/team-chat/rooms/{gid}/messages?since=0").json()["people"][speaker.id]
    assert person["archived"] is True, f"떠난 사람인데 화면이 그 사실을 모른다: {person}"


def test_people_carries_the_avatar_url_when_there_is_one(client, login_as, make_user, db):
    """X13 — 사진 주소를 안 실으면 남의 아바타를 그릴 방법이 없다."""
    from datetime import datetime

    from app.profiles.models import UserPreference

    speaker = make_user("pp-face@goodmit.co.kr", role="user", display_name="사진있음")
    db.add(UserPreference(
        user_id=speaker.id, avatar_stored_name="abc.png",
        avatar_updated_at=datetime(2026, 8, 1, 0, 0, 0),
    ))
    db.commit()

    csrf = login_as("user", email="pp-face@goodmit.co.kr")
    gid = _global_room(client)
    client.post(f"/api/team-chat/rooms/{gid}/messages", json={"body": "안녕"},
                headers={"X-CSRF-Token": csrf})

    person = client.get(f"/api/team-chat/rooms/{gid}/messages?since=0").json()["people"][speaker.id]
    assert person["avatar_url"], f"사진이 있는데 주소가 안 실린다: {person}"
    assert person["avatar_url"].startswith(f"/api/profile/avatar/{speaker.id}?v="), (
        f"지문(?v=)이 없으면 사진을 바꿔도 5분 동안 옛 사진이 보인다: {person['avatar_url']}"
    )


def test_a_person_without_a_photo_gets_null_not_a_broken_url(client, login_as, make_user, db):
    """오탐 방지 — 없는 사진에 주소를 주면 화면에 깨진 이미지가 뜬다."""
    speaker = make_user("pp-nopic@goodmit.co.kr", role="user", display_name="사진없음")
    db.commit()
    csrf = login_as("user", email="pp-nopic@goodmit.co.kr")
    gid = _global_room(client)
    client.post(f"/api/team-chat/rooms/{gid}/messages", json={"body": "안녕"},
                headers={"X-CSRF-Token": csrf})

    person = client.get(f"/api/team-chat/rooms/{gid}/messages?since=0").json()["people"][speaker.id]
    assert person["avatar_url"] is None, f"없는 사진의 주소를 줬다: {person}"
