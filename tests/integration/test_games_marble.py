"""구슬 레이스 API (기능 개선 회차 P5, D-564) — 참가자 · 시작 · 결과 제출 · 확인 창 · 확정 · 무결성.

못박는 성질:
1. 참가자: 2 ~ 100명, 이름 1 ~ 24자(NFC · 공백 접기), 중복은 422 와 「(2)」 제안, 방장만, 진행 중엔 409.
2. 시작은 방장만이고 서버가 race_id · seed · started_at · 배속을 발급한다. 참가자를 안 적었으면 지금 있는 구성원이 참가자다.
3. 제출 검증: 순열이 아니면 422, 다른 race_id 422, 최소 경과 전 422, 지문이 다르면 422, 같은 사람 두 번 409, 방 밖 403,
   방장이 아닌 finish 403.
4. 확정 시점은 하나다 — 첫 제출에 `verifying`, 방장 finish 뒤 10초(또는 전원 제출 즉시, 방장 없이 첫 attest 뒤 30초)에
   한 번 판정해 `finalized_at`. 같은 지문이면 `confirmed`, 대조할 제출이 없으면 `host_only`, 방장 없이 다수면 `host_absent`,
   하나라도 다르면 `disputed`(결과 없음 · 발표 없음). 확정 뒤 제출은 기록만 하고 결과 · 상태가 불변이다.
5. 제출 없이 10분이면 `abandoned`. 초기화하면 대기 중으로 돌아가고 참가자 · 설정은 남는다.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.games import marble
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = [pytest.mark.integration, pytest.mark.real_db]

RACE_SECONDS = marble.MIN_RACE_SECONDS + 1


def _login_other(app, email):
    client = TestClient(app, raise_server_exceptions=False)
    client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return client, client.get("/api/me").json()["csrf_token"]


def _create(client, csrf, **config):
    body = {"title": "구슬 레이스", "game_type": "marble_race", "max_players": 8, "config": config}
    r = client.post("/api/games/rooms", json=body, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    return r.json()["room"]


def _state(client, rid):
    return client.get(f"/api/games/rooms/{rid}/state?since=0").json()


def _result_for(state: dict, *, order=None):
    """이 경주의 참가자 열쇠로 순위 하나를 만든다(브라우저가 계산한 결과의 자리)."""
    keys = [p["key"] for p in state["participants"]]
    ranking = list(order) if order else list(keys)
    steps = [100 + i * 50 for i in range(len(ranking))]
    return {"race_id": state["race_id"], "ranking": ranking, "finish_steps": steps,
            "digest": marble.digest_of(state["race_id"], ranking, steps)}


def _room_with_two(app, client, login_as, make_user, **config):
    csrf = login_as("user", email="mhost@goodmit.co.kr")
    room = _create(client, csrf, **config)
    make_user("mp2@goodmit.co.kr")
    c2, csrf2 = _login_other(app, "mp2@goodmit.co.kr")
    assert c2.post(f"/api/games/rooms/{room['id']}/join", headers={"X-CSRF-Token": csrf2}).status_code == 200
    return room["id"], csrf, c2, csrf2


# ── 참가자 ───────────────────────────────────────────────────────────────────


def test_participants_are_validated_and_duplicates_get_a_suggestion(app, client, login_as, make_user):
    rid, csrf, c2, csrf2 = _room_with_two(app, client, login_as, make_user)
    h = {"X-CSRF-Token": csrf}
    put = lambda body, headers=h, c=client: c.put(f"/api/games/rooms/{rid}/marble/participants", json=body, headers=headers)  # noqa: E731
    dup = put({"participants": [{"name": "김하나"}, {"name": " 김하나 "}, {"name": "이두리"}]})
    assert dup.status_code == 422
    assert dup.json()["error"]["details"]["suggestions"] == {"김하나": "김하나 (2)"}
    assert put({"participants": [{"name": "혼자"}]}).status_code == 422, "2명 미만"
    assert put({"participants": [{"name": "가" * 25}, {"name": "나"}]}).status_code == 422, "24자 초과"
    assert put({"participants": [{"name": ""}, {"name": "나"}]}).status_code == 422, "빈 이름"
    assert put({"participants": [{"name": f"참가자 {i}"} for i in range(101)]}).status_code == 422, "100명 초과"
    ok = put({"participants": [{"name": "김하나", "user_id": "u-1"}, {"name": "이  두리"}, {"name": "Ćafe"}]})
    assert ok.status_code == 200, ok.text
    names = [p["name"] for p in ok.json()["participants"]]
    assert names == ["김하나", "이 두리", "Ćafe"], "공백 접기와 NFC"
    assert ok.json()["participants"][0]["key"] == "u:u-1"
    assert put({"participants": [{"name": "a"}, {"name": "b"}]}, headers={"X-CSRF-Token": csrf2}, c=c2).status_code == 403, "방장만"
    assert client.get(f"/api/games/rooms/{rid}/state?since=0").json()["room"]["status"] == "waiting"


def test_participants_default_to_present_members_and_config_is_clamped(app, client, login_as, make_user):
    rid, csrf, c2, csrf2 = _room_with_two(app, client, login_as, make_user)
    h = {"X-CSRF-Token": csrf}
    cfg = client.put(f"/api/games/rooms/{rid}/marble/config", json={"winners": 3, "pick_last": True, "speed": 2}, headers=h)
    assert cfg.status_code == 200 and cfg.json()["config"]["winners"] == 3 and cfg.json()["config"]["speed"] == 2
    assert client.put(f"/api/games/rooms/{rid}/marble/config", json={"speed": 3}, headers=h).status_code == 422
    assert client.put(f"/api/games/rooms/{rid}/marble/config", json={"winners": 0}, headers=h).status_code == 422
    assert client.put(f"/api/games/rooms/{rid}/marble/config", json={"map": "moon"}, headers=h).status_code == 422
    assert client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf2}).status_code == 403, "방장만 시작"
    started = client.post(f"/api/games/rooms/{rid}/start", headers=h)
    assert started.status_code == 200, started.text
    st = _state(client, rid)
    assert st["room"]["status"] == "playing" and st["state"]["phase"] == "running"
    assert st["state"]["race_id"] and len(st["state"]["seed"]) == 16 and st["state"]["speed"] == 2
    assert [p["user_id"] for p in st["state"]["participants"]] and len(st["state"]["participants"]) == 2, "구성원이 참가자다"
    assert st["state"]["winners_n"] == 2, "당첨 인원은 참가자 수를 넘지 않는다"
    assert st["state"]["pick_last"] is True
    assert "now" in st and st["state"]["started_at"]
    assert st["state"]["min_race_seconds"] == marble.MIN_RACE_SECONDS, "브라우저가 짧은 경주의 제출을 이 경과까지 미룬다(D-580)"
    # 진행 중엔 참가자 · 설정을 바꿀 수 없고 다시 시작할 수도 없다.
    assert client.put(f"/api/games/rooms/{rid}/marble/participants", json={"participants": [{"name": "a"}, {"name": "b"}]}, headers=h).status_code == 409
    assert client.post(f"/api/games/rooms/{rid}/start", headers=h).status_code == 409


# ── 제출과 확정 ─────────────────────────────────────────────────────────────


def test_submissions_are_validated_like_the_plan_says(app, client, login_as, make_user, fake_clock):
    rid, csrf, c2, csrf2 = _room_with_two(app, client, login_as, make_user)
    h = {"X-CSRF-Token": csrf}
    assert client.post(f"/api/games/rooms/{rid}/start", headers=h).status_code == 200
    st = _state(client, rid)["state"]
    good = _result_for(st)
    url = f"/api/games/rooms/{rid}/marble/finish"
    assert client.post(url, json=good, headers=h).status_code == 422, "최소 경과 전"
    fake_clock.advance(seconds=RACE_SECONDS)
    assert client.post(url, json={**good, "ranking": good["ranking"][:1], "finish_steps": good["finish_steps"][:1]}, headers=h).status_code == 422
    assert client.post(url, json={**good, "ranking": list(reversed(good["ranking"]))}, headers=h).status_code == 422, "순위가 바뀌면 지문이 다르다"
    assert client.post(url, json={**good, "race_id": "0" * 32}, headers=h).status_code == 422
    assert client.post(url, json={**good, "finish_steps": [-1] + good["finish_steps"][1:]}, headers=h).status_code == 422
    assert client.post(url, json={**good, "digest": "f" * 64}, headers=h).status_code == 422
    assert c2.post(url, json=good, headers={"X-CSRF-Token": csrf2}).status_code == 403, "방장이 아닌 finish"
    make_user("outsider@goodmit.co.kr")
    c3, csrf3 = _login_other(app, "outsider@goodmit.co.kr")
    assert c3.post(f"/api/games/rooms/{rid}/marble/attest", json=good, headers={"X-CSRF-Token": csrf3}).status_code == 403, "방 밖"
    ok = client.post(url, json=good, headers=h)
    assert ok.status_code == 200, ok.text
    assert ok.json()["recorded"] is True and ok.json()["state"]["phase"] == "verifying"
    assert client.post(url, json=good, headers=h).status_code == 409, "한 사람 한 번"


def test_matching_results_confirm_after_the_window_and_late_submissions_do_not_change_them(
    app, client, login_as, make_user, fake_clock, db,
):
    rid, csrf, c2, csrf2 = _room_with_two(app, client, login_as, make_user)
    make_user("mp3@goodmit.co.kr")
    c3, csrf3 = _login_other(app, "mp3@goodmit.co.kr")
    assert c3.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": csrf3}).status_code == 200
    h = {"X-CSRF-Token": csrf}
    assert client.post(f"/api/games/rooms/{rid}/start", headers=h).status_code == 200
    st = _state(client, rid)["state"]
    result = _result_for(st)
    fake_clock.advance(seconds=RACE_SECONDS)
    assert client.post(f"/api/games/rooms/{rid}/marble/finish", json=result, headers=h).status_code == 200
    assert c2.post(f"/api/games/rooms/{rid}/marble/attest", json=result, headers={"X-CSRF-Token": csrf2}).status_code == 200
    # 셋 중 둘만 제출했다 - 창이 닫히기 전에는 결과가 없다(발표 없음).
    mid = _state(client, rid)
    assert mid["room"]["status"] == "playing" and mid["state"]["phase"] == "verifying" and mid["state"]["result"] is None
    assert mid["state"]["announceable"] is False
    fake_clock.advance(seconds=marble.VERIFY_WINDOW_HOST_SECONDS + 1)
    done = _state(client, rid)  # 폴링이 창을 닫는다
    assert done["room"]["status"] == "finished" and done["state"]["phase"] == "finished"
    assert done["state"]["integrity"]["status"] == "confirmed"
    assert done["state"]["integrity"]["agree"] == 1 and done["state"]["integrity"]["disagree"] == 0
    assert done["state"]["result"]["ranking"] == result["ranking"] and done["state"]["result"]["winners"] == result["ranking"][:1]
    assert done["state"]["finalized_at"] and done["state"]["announceable"] is True
    assert done["result_seq"] == done["seq"], "결과 이벤트의 순번이 발표 열쇠다"
    assert [e["kind"] for e in done["events"]][-1] == "result"
    # 확정 뒤에 온(다른) 제출은 기록만 — 결과 · 상태 불변.
    other = _result_for(st, order=list(reversed(result["ranking"])))
    late = c3.post(f"/api/games/rooms/{rid}/marble/attest", json=other, headers={"X-CSRF-Token": csrf3})
    assert late.status_code == 200 and late.json()["late"] is True
    after = _state(client, rid)
    assert after["state"]["result"]["ranking"] == result["ranking"] and after["state"]["integrity"]["status"] == "confirmed"
    assert len(after["state"]["submissions"]) == 3 and after["result_seq"] == done["result_seq"]
    # 초기화 → 대기 중, 참가자 · 설정은 남는다.
    assert client.post(f"/api/games/rooms/{rid}/reset", headers=h).status_code == 200
    reset = _state(client, rid)
    assert reset["room"]["status"] == "waiting" and reset["state"]["phase"] == "idle"
    assert client.post(f"/api/games/rooms/{rid}/reset", headers=h).status_code == 200, "대기 중 초기화는 멱등"


def test_everyone_submitting_finalizes_at_once_and_a_dispute_is_never_announced(app, client, login_as, make_user, fake_clock):
    rid, csrf, c2, csrf2 = _room_with_two(app, client, login_as, make_user)
    h = {"X-CSRF-Token": csrf}
    assert client.post(f"/api/games/rooms/{rid}/start", headers=h).status_code == 200
    st = _state(client, rid)["state"]
    fake_clock.advance(seconds=RACE_SECONDS)
    mine = _result_for(st)
    theirs = _result_for(st, order=list(reversed(mine["ranking"])))
    assert client.post(f"/api/games/rooms/{rid}/marble/finish", json=mine, headers=h).status_code == 200
    r = c2.post(f"/api/games/rooms/{rid}/marble/attest", json=theirs, headers={"X-CSRF-Token": csrf2})
    assert r.status_code == 200
    st2 = _state(client, rid)
    assert st2["room"]["status"] == "finished", "지금 있는 구성원이 모두 올리면 창을 기다리지 않는다"
    assert st2["state"]["integrity"]["status"] == "disputed" and st2["state"]["result"] is None
    assert st2["state"]["announceable"] is False
    assert st2["events"][-1]["kind"] == "result" and st2["events"][-1]["payload"]["disputed"] is True
    assert st2["events"][-1]["payload"].get("winners") is None, "불일치는 발표하지 않는다"


def test_without_the_host_the_attesters_majority_is_promoted_and_no_submission_abandons(
    app, client, login_as, make_user, fake_clock,
):
    rid, csrf, c2, csrf2 = _room_with_two(app, client, login_as, make_user)
    h = {"X-CSRF-Token": csrf}
    assert client.post(f"/api/games/rooms/{rid}/start", headers=h).status_code == 200
    st = _state(client, rid)["state"]
    fake_clock.advance(seconds=RACE_SECONDS)
    result = _result_for(st)
    assert c2.post(f"/api/games/rooms/{rid}/marble/attest", json=result, headers={"X-CSRF-Token": csrf2}).status_code == 200
    waiting = _state(c2, rid)
    assert waiting["state"]["phase"] == "verifying"
    fake_clock.advance(seconds=marble.VERIFY_WINDOW_ATTEST_SECONDS + 1)
    done = _state(c2, rid)
    assert done["room"]["status"] == "finished" and done["state"]["integrity"]["status"] == "host_absent"
    assert done["state"]["result"]["winners"] == result["ranking"][:1]

    # 아무도 올리지 않은 경주는 10분 뒤에 버려진다.
    assert client.post(f"/api/games/rooms/{rid}/reset", headers=h).status_code == 200
    assert client.post(f"/api/games/rooms/{rid}/start", headers=h).status_code == 200
    fake_clock.advance(seconds=marble.ABANDON_SECONDS + 1)
    gone = _state(client, rid)
    assert gone["room"]["status"] == "finished" and gone["state"]["phase"] == "abandoned"
    assert gone["events"][-1]["payload"]["abandoned"] is True


def test_host_only_result_is_announced_with_that_mark_and_the_digest_matches_python(app, client, login_as, make_user, fake_clock):
    rid, csrf, c2, csrf2 = _room_with_two(app, client, login_as, make_user)
    h = {"X-CSRF-Token": csrf}
    assert client.post(f"/api/games/rooms/{rid}/start", headers=h).status_code == 200
    st = _state(client, rid)["state"]
    fake_clock.advance(seconds=RACE_SECONDS)
    result = _result_for(st)
    # 브라우저(engine/sha256.js)와 같은 글 — `race_id|키,키|스텝,스텝`.
    import hashlib

    material = f"{st['race_id']}|{','.join(result['ranking'])}|{','.join(str(s) for s in result['finish_steps'])}"
    assert result["digest"] == hashlib.sha256(material.encode()).hexdigest()
    assert client.post(f"/api/games/rooms/{rid}/marble/finish", json=result, headers=h).status_code == 200
    fake_clock.advance(seconds=marble.VERIFY_WINDOW_HOST_SECONDS + 1)
    done = _state(client, rid)
    assert done["state"]["integrity"] == {"status": "host_only", "agree": 0, "disagree": 0, "source": "host", "submissions": 1}
    assert done["state"]["announceable"] is True


def test_start_snapshots_people(app, client, login_as, make_user):
    """D-577 — 경주를 시작하면 구성원 전원의 신원이 상태에 박혀, 결과 뒤 나간 참가자의 구슬도 얼굴로 그린다."""
    rid, csrf, c2, csrf2 = _room_with_two(app, client, login_as, make_user)
    leaver_id = c2.get("/api/me").json()["user"]["id"]
    assert client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert c2.post(f"/api/games/rooms/{rid}/leave", headers={"X-CSRF-Token": csrf2}).status_code == 200
    st = _state(client, rid)
    assert leaver_id in st["people"] and st["people"][leaver_id]["name"]
    assert leaver_id in {p["user_id"] for p in st["state"]["participants"]}
    assert "people" not in st["state"]


def test_map_choices(app, client, login_as, make_user):
    """D-578 — 경주 판은 네 개(바퀴 · 항아리 · 비눗방울 · 밤을 달리다)이고 고른 판이 경주에 박힌다. 모르는 판은 422."""
    rid, csrf, c2, csrf2 = _room_with_two(app, client, login_as, make_user)
    h = {"X-CSRF-Token": csrf}
    assert marble.MAPS == ("wheel", "pot", "bubble", "yoru")
    for key in marble.MAPS:
        r = client.put(f"/api/games/rooms/{rid}/marble/config", json={"map": key}, headers=h)
        assert r.status_code == 200 and r.json()["config"]["map"] == key, r.text
    assert client.put(f"/api/games/rooms/{rid}/marble/config", json={"map": "moon"}, headers=h).status_code == 422
    assert _state(client, rid)["state"]["config"]["map"] == "yoru"
    assert client.post(f"/api/games/rooms/{rid}/start", headers=h).status_code == 200
    assert _state(client, rid)["state"]["map"] == "yoru"
