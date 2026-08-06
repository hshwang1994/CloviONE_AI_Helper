"""방해금지를 **밖에서도 보이게** 한다 (X3).

## 무엇이 문제였나

방해금지는 지금까지 **자기 배지만** 조용하게 했다. 밖에서는 표시가 없어서 동료는 초록 점을
보고 말을 걸고, 답이 없으면 이상하게 여긴다. 켠 사람은 방해를 받고, 거는 사람은 무시당했다고
느낀다 - 아무도 원하지 않은 결과다.

## 그린다면 어떻게 그려야 하나

**오프라인으로 그리면 안 된다.** 그건 거짓말이고, 거는 사람이 "자리에 없구나" 로 잘못 읽는다.
있는 그대로 "있지만 지금은 곤란함" 을 말한다. 반대로 접속해 있지 않으면 방해금지 딱지도
붙이지 않는다 - 어제 켜 두고 퇴근한 사람에게 딱지가 남아 있으면 그것도 사실이 아니다.

기존 온라인 점 테스트(`test_team_chat_presence_read.py`)의 방식을 그대로 따른다 -
실제 API 로 방을 만들고, 상대가 방을 여는 것으로 `last_seen` 을 만든다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.team_chat.service import ONLINE_SECONDS
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _login_other(app, email):
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return c


def _member(client, rid, user_id):
    body = client.get(f"/api/team-chat/rooms/{rid}/messages?since=0").json()
    return next(m for m in body["members"] if m["user_id"] == user_id)


def _direct(client, csrf, other_id):
    return client.post("/api/team-chat/rooms/direct", json={"user_id": other_id},
                       headers={"X-CSRF-Token": csrf}).json()["room"]["id"]


@pytest.fixture()
def world(app, client, login_as, make_user):
    """나 + 상대. 상대가 방을 열어 **접속 중**이 된 상태에서 시작한다."""
    csrf = login_as("user", email="dnd-me@goodmit.co.kr")
    other = make_user(email="dnd-other@goodmit.co.kr", display_name="상대")
    rid = _direct(client, csrf, other.id)
    with _login_other(app, "dnd-other@goodmit.co.kr") as c2:
        c2.get(f"/api/team-chat/rooms/{rid}/messages?since=0")
    return {"rid": rid, "other": other}


def _set_dnd(db, user, *, enabled, until=None, quiet=False):
    from app.profiles.models import UserPreference

    pref = db.query(UserPreference).filter_by(user_id=user.id).one_or_none()
    if pref is None:
        pref = UserPreference(user_id=user.id)
        db.add(pref)
    pref.dnd_enabled = enabled
    pref.dnd_until = until
    pref.quiet_hours_enabled = quiet
    if quiet:
        # 지금이 반드시 그 안에 들어가게 - 조용시간이 실제로 걸린 상태를 만들어야
        # "조용시간은 방해금지가 아니다" 를 증명할 수 있다.
        pref.quiet_start = "00:00"
        pref.quiet_end = "23:59"
    db.commit()
    return pref


def test_without_dnd_a_present_person_is_simply_online(client, world):
    """오탐 방지 - 기본 상태가 online 이 아니면 아래 검사들이 아무 뜻이 없다."""
    got = _member(client, world["rid"], world["other"].id)
    assert got["presence"] == "online", got
    assert got["online"] is True, "기존 계약(`online`)이 깨졌다"


def test_dnd_is_visible_to_the_other_person(client, db, world):
    """🔴 핵심 - 켰는데 밖에서 안 보이면 켠 의미가 없다."""
    _set_dnd(db, world["other"], enabled=True)
    got = _member(client, world["rid"], world["other"].id)
    assert got["presence"] == "dnd", f"방해금지가 밖에서 안 보인다: {got}"


def test_dnd_does_not_pretend_the_person_left(client, db, world):
    """오프라인으로 그리면 거는 사람이 "자리에 없구나" 로 잘못 읽는다."""
    _set_dnd(db, world["other"], enabled=True)
    got = _member(client, world["rid"], world["other"].id)
    assert got["presence"] != "offline", f"있는 사람을 없다고 그렸다: {got}"
    assert got["online"] is True, "기존 `online` 계약까지 바꿨다"


def test_an_expired_dnd_is_not_shown(client, db, world, fake_clock):
    """자동 해제 시각이 지났으면 더 이상 방해금지가 아니다."""
    from datetime import timedelta

    now = fake_clock.now()
    _set_dnd(db, world["other"], enabled=True, until=now - timedelta(hours=1))
    got = _member(client, world["rid"], world["other"].id)
    assert got["presence"] == "online", f"지난 방해금지가 남아 있다: {got}"


def test_dnd_on_someone_who_is_not_here_stays_offline(client, db, world, fake_clock):
    """어제 켜 두고 퇴근한 사람에게 방해금지 딱지가 붙으면 그것도 사실이 아니다."""
    _set_dnd(db, world["other"], enabled=True)
    fake_clock.advance(ONLINE_SECONDS + 60)   # 접속 판정 창을 확실히 벗어난다

    got = _member(client, world["rid"], world["other"].id)
    assert got["online"] is False, f"표본이 잘못됐다 - 아직 접속 중이다: {got}"
    assert got["presence"] == "offline", f"자리에 없는 사람에게 방해금지 딱지가 붙었다: {got}"


def test_quiet_hours_alone_do_not_look_like_dnd(client, db, world):
    """조용시간은 개인 일정이지 "말 걸지 마라" 가 아니다.

    23시에 방을 열어 두고 읽는 사람을 방해금지로 그리면 **사실이 아닌 것을 그리는 것**이다.
    """
    _set_dnd(db, world["other"], enabled=False, quiet=True)
    got = _member(client, world["rid"], world["other"].id)
    assert got["presence"] == "online", f"조용시간을 방해금지로 그렸다: {got}"


def test_reading_the_room_does_not_query_per_member(client, world, monkeypatch):
    """🔴 폴링 경로다 - 참여자마다 질의하면 그 비용이 매 초 반복된다."""
    from app.team_chat import service

    calls = {"n": 0}
    original = service.dnd_user_ids

    def _counted(db_, user_ids, *, now):
        calls["n"] += 1
        return original(db_, user_ids, now=now)

    monkeypatch.setattr(service, "dnd_user_ids", _counted)
    client.get(f"/api/team-chat/rooms/{world['rid']}/messages?since=0")

    assert calls["n"] == 1, f"참여자 수만큼 불렀다: {calls['n']}"
