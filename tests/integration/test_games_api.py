"""팀 공간 > 놀이 API 통합 테스트 (§5·§6·§13·§14).

방 생성/목록/입장/준비/관전/재접속 + 폴링(이벤트 시퀀스) + 서버 확정 랜덤 추첨 + 방장 권한
+ 채팅 + 인증/CSRF/기능플래그.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_TEST_PASSWORD, PROJECT_ROOT

# 이 파일의 시험은 **전용 DB** 가 필요하다(D-190) — 두 번째 커넥션이나 별도
# 프로세스가 이 시험의 데이터를 봐야 하기 때문이다. 공유 DB + 트랜잭션 되감기
# 계층에서는 그 데이터가 트랜잭션 밖으로 안 나가서 아무것도 증명하지 못한다.
pytestmark = [pytest.mark.integration, pytest.mark.real_db]


def _login_other(app, email):
    make = TestClient(app, raise_server_exceptions=False)
    make.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    return make, make.get("/api/me").json()["csrf_token"]


def _create(client, csrf, **over):
    body = {"title": "점심 추첨", "game_type": "random_draw", "max_players": 8}
    body.update(over)
    r = client.post("/api/games/rooms", json=body, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    return r.json()["room"]


def test_requires_auth(client):
    assert client.get("/api/games/rooms").status_code == 401


def test_create_requires_csrf(client, login_as):
    login_as("user", email="csrfg@goodmit.co.kr")
    assert client.post("/api/games/rooms", json={"title": "x", "game_type": "random_draw"}).status_code == 403


def test_create_list_join_ready_state(app, client, login_as, make_user):
    csrf = login_as("user", email="host@goodmit.co.kr")
    room = _create(client, csrf)
    rid = room["id"]
    assert room["status"] == "waiting" and room["player_count"] == 1
    assert any(r["id"] == rid for r in client.get("/api/games/rooms").json()["items"])

    make_user("p2@goodmit.co.kr")
    c2, csrf2 = _login_other(app, "p2@goodmit.co.kr")
    with c2:
        assert c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": csrf2}).json()["role"] == "player"
        c2.post(f"/api/games/rooms/{rid}/ready", json={"ready": True}, headers={"X-CSRF-Token": csrf2})

    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    assert len(st["members"]) == 2
    kinds = [e["kind"] for e in st["events"]]
    assert "join" in kinds and "ready" in kinds
    assert st["you"]["is_host"] is True
    # 커서 이후 새 이벤트 없음.
    assert client.get(f"/api/games/rooms/{rid}/state?since={st['seq']}").json()["events"] == []


def test_random_draw_server_picks_winner(app, client, login_as, make_user):
    csrf = login_as("user", email="drawhost@goodmit.co.kr")
    rid = _create(client, csrf, title="추첨", config={"winners": 1})["id"]
    for e in ("dp1@goodmit.co.kr", "dp2@goodmit.co.kr"):
        make_user(e)
        c, cs = _login_other(app, e)
        with c:
            c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})

    r = client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["room"]["status"] == "finished"
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    assert st["state"]["result"]
    result_ev = [e for e in st["events"] if e["kind"] == "result"]
    assert len(result_ev) == 1
    winners = result_ev[0]["payload"]["winners"]
    assert len(winners) == 1
    member_ids = {m["user_id"] for m in st["members"]}
    assert winners[0]["user_id"] in member_ids  # 당첨자는 실제 참여자 중 하나(서버 확정)


def test_only_host_can_start(app, client, login_as, make_user):
    csrf = login_as("user", email="h2@goodmit.co.kr")
    rid = _create(client, csrf, title="x")["id"]
    make_user("nothost@goodmit.co.kr")
    c, cs = _login_other(app, "nothost@goodmit.co.kr")
    with c:
        c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})
        assert c.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": cs}).status_code == 403


def test_chat_and_reset(client, login_as):
    csrf = login_as("user", email="chat@goodmit.co.kr")
    rid = _create(client, csrf, title="x")["id"]
    client.post(f"/api/games/rooms/{rid}/chat", json={"text": "안녕하세요"}, headers={"X-CSRF-Token": csrf})
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    chats = [e for e in st["events"] if e["kind"] == "chat"]
    assert chats and chats[0]["payload"]["text"] == "안녕하세요"
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    client.post(f"/api/games/rooms/{rid}/reset", headers={"X-CSRF-Token": csrf})
    assert client.get(f"/api/games/rooms/{rid}/state?since=0").json()["room"]["status"] == "waiting"


def test_spectate(app, client, login_as, make_user):
    csrf = login_as("user", email="sh@goodmit.co.kr")
    rid = _create(client, csrf, title="x", allow_spectators=True)["id"]
    make_user("spec@goodmit.co.kr")
    c, cs = _login_other(app, "spec@goodmit.co.kr")
    with c:
        r = c.post(f"/api/games/rooms/{rid}/join?spectate=true", headers={"X-CSRF-Token": cs})
        assert r.json()["role"] == "spectator"


def test_host_leaves_reassigns(app, client, login_as, make_user):
    csrf = login_as("user", email="lh@goodmit.co.kr")
    rid = _create(client, csrf, title="x")["id"]
    make_user("nexth@goodmit.co.kr")
    c, cs = _login_other(app, "nexth@goodmit.co.kr")
    with c:
        c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})
        # 원래 방장이 나감 → 남은 사람에게 위임.
        client.post(f"/api/games/rooms/{rid}/leave", headers={"X-CSRF-Token": csrf})
        st = c.get(f"/api/games/rooms/{rid}/state?since=0").json()
        assert st["you"]["is_host"] is True


def test_team_split_server_partitions_evenly(app, client, login_as, make_user):
    csrf = login_as("user", email="thost@goodmit.co.kr")
    rid = _create(client, csrf, title="팀", game_type="team_split", config={"teams": 2})["id"]
    for e in ("tp1@goodmit.co.kr", "tp2@goodmit.co.kr", "tp3@goodmit.co.kr"):
        make_user(e)
        c, cs = _login_other(app, e)
        with c:
            c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})

    r = client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["room"]["status"] == "finished"
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    teams = st["state"]["result"]["teams"]
    assert len(teams) == 2
    sizes = sorted(len(t) for t in teams)
    assert sizes == [2, 2]  # 방장 포함 4명 → 2·2 균등
    # 모든 참여자가 정확히 한 팀에만 배정(서버 확정).
    ids = [m["user_id"] for t in teams for m in t]
    member_ids = {m["user_id"] for m in st["members"]}
    assert len(ids) == 4 and set(ids) == member_ids and len(set(ids)) == 4


def test_ladder_assigns_each_player_one_outcome(app, client, login_as, make_user):
    csrf = login_as("user", email="lad@goodmit.co.kr")
    rid = _create(client, csrf, title="사다리", game_type="ladder",
                  config={"options": ["당첨", "꽝"]})["id"]
    for e in ("lp1@goodmit.co.kr", "lp2@goodmit.co.kr"):
        make_user(e)
        c, cs = _login_other(app, e)
        with c:
            c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})

    r = client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["room"]["status"] == "finished"
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    assigns = st["state"]["result"]["assignments"]
    member_ids = {m["user_id"] for m in st["members"]}
    # 참여자(방장 포함 3명) 각자 정확히 하나의 결과, 모두가 배정됨(꽝으로 채움).
    assert len(assigns) == 3 and {a["user_id"] for a in assigns} == member_ids
    assert all(a["outcome"] in {"당첨", "꽝"} for a in assigns)


def test_ladder_structure_is_honest(app, client, login_as, make_user):
    """사다리 결과에 실제 사다리 구조(세로줄·가로줄)가 담기고, 그 구조를 따라 걸으면
    서버가 확정한 도착지가 그대로 나온다(프런트가 정직하게 그릴 수 있다)."""
    csrf = login_as("user", email="ladh@goodmit.co.kr")
    rid = _create(client, csrf, title="사다리", game_type="ladder",
                  config={"options": ["커피", "차", "주스"]})["id"]
    for e in ("ls1@goodmit.co.kr", "ls2@goodmit.co.kr"):
        make_user(e)
        c, cs = _login_other(app, e)
        with c:
            c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    res = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    n = len(res["columns"])
    assert n == 3 and len(res["outcomes"]) == 3 and res["rows"] >= 6
    # 가로줄 구조를 따라 각 시작 열을 걸어 도착 열을 구하고, outcomes[end]가 배정과 일치하는지.
    rung_set = {(g["row"], g["col"]) for g in res["rungs"]}
    for i, a in enumerate(res["assignments"]):
        col = i
        for r in range(res["rows"]):
            if (r, col) in rung_set:
                col += 1
            elif col > 0 and (r, col - 1) in rung_set:
                col -= 1
        assert a["end_col"] == col and a["outcome"] == res["outcomes"][col]
    # 아미다쿠지는 항상 1:1 대응 — 도착 열이 모두 다르다.
    assert len({a["end_col"] for a in res["assignments"]}) == n


def test_rps_autofills_non_submitters_on_finish(app, client, login_as, make_user):
    """제한 시간 안에 안 낸 참여자는 서버가 무작위로 채워, 대기로 게임이 막히지 않는다."""
    csrf = login_as("user", email="rpsauto@goodmit.co.kr")
    rid = _create(client, csrf, title="가위바위보", game_type="rps", config={"timer_seconds": 10})["id"]
    make_user("rpa2@goodmit.co.kr")
    c2, cs2 = _login_other(app, "rpa2@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    # 진행 중 상태에 카운트다운 마감과 제출자 목록이 노출된다.
    playing = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert playing.get("deadline") and playing.get("timer_seconds") == 10
    assert playing["submitted"] == [] and playing["mode"] == "single"
    # 방장만 내고 참여자는 안 냄 → 방장이 종료하면 참여자 몫은 자동으로 채워진다.
    client.post(f"/api/games/rooms/{rid}/rps", json={"option": 1}, headers={"X-CSRF-Token": csrf})
    c2.close()
    client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    res = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    assert len(res["reveal"]) == 2  # 미제출자도 자동으로 채워져 공개에 포함
    autos = [p for p in res["reveal"] if p.get("auto")]
    assert len(autos) == 1  # 참여자 한 명이 자동 배정됨


def test_restart_after_finish_is_rejected(app, client, login_as, make_user):
    """끝난 방에 /start 를 다시 보내도 재추첨되지 않는다(공정성) — 초기화(reset)를 거쳐야 한다."""
    csrf = login_as("user", email="restarth@goodmit.co.kr")
    rid = _create(client, csrf, title="추첨", config={"winners": 1})["id"]
    make_user("rp9@goodmit.co.kr")
    c2, cs2 = _login_other(app, "rp9@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2}); c2.close()
    assert client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf}).json()["room"]["status"] == "finished"
    # 끝난 방 재시작 거부(409). 결과 이벤트도 하나뿐.
    assert client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf}).status_code == 409
    events = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["events"]
    assert len([e for e in events if e["kind"] == "result"]) == 1
    # 초기화하면 다시 시작할 수 있다.
    client.post(f"/api/games/rooms/{rid}/reset", headers={"X-CSRF-Token": csrf})
    assert client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_number_finish_excludes_departed_player(app, client, login_as, make_user):
    """나간 사람의 숫자는 종료 집계에서 빠진다(유령 승자 방지)."""
    csrf = login_as("user", email="ghosth@goodmit.co.kr")
    rid = _create(client, csrf, title="눈치", game_type="number", config={"min": 1, "max": 9})["id"]
    make_user("ghostp@goodmit.co.kr")
    c2, cs2 = _login_other(app, "ghostp@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    c2.post(f"/api/games/rooms/{rid}/pick", json={"value": 1}, headers={"X-CSRF-Token": cs2})  # B: 1(최저)
    client.post(f"/api/games/rooms/{rid}/pick", json={"value": 5}, headers={"X-CSRF-Token": csrf})  # A: 5
    c2.post(f"/api/games/rooms/{rid}/leave", headers={"X-CSRF-Token": cs2}); c2.close()  # B 나감
    client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    res = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    assert len(res["picks"]) == 1 and res["winner"]["number"] == 5  # B(1) 제외 → 승자는 A(5)


def test_quiz_scoreboard_includes_zero_scorers(app, client, login_as, make_user):
    """한 문제도 못 맞힌 참여자도 최종 점수판에 0점으로 남는다."""
    csrf = login_as("user", email="qz0h@goodmit.co.kr")
    rid = _create(client, csrf, title="퀴즈", game_type="quiz",
                  config={"questions": [{"q": "?", "options": ["a", "b"], "answer": 0}]})["id"]
    make_user("qz0p@goodmit.co.kr")
    c2, cs2 = _login_other(app, "qz0p@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    client.post(f"/api/games/rooms/{rid}/quiz-answer", json={"option": 0}, headers={"X-CSRF-Token": csrf})  # A 정답
    c2.post(f"/api/games/rooms/{rid}/quiz-answer", json={"option": 1}, headers={"X-CSRF-Token": cs2})  # B 오답
    c2.close()
    client.post(f"/api/games/rooms/{rid}/reveal", headers={"X-CSRF-Token": csrf})
    client.post(f"/api/games/rooms/{rid}/next", headers={"X-CSRF-Token": csrf})
    board = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]["scoreboard"]
    assert len(board) == 2 and sorted(b["score"] for b in board) == [0, 1]  # 0점자도 포함


def test_no_spectate_room_rejects_join_while_playing(app, client, login_as, make_user):
    """관전 불허 방이 진행 중이면 새 입장자를 관전자로도 받지 않는다(관전 불허 계약)."""
    csrf = login_as("user", email="nspech@goodmit.co.kr")
    rid = _create(client, csrf, title="가위바위보", game_type="rps", allow_spectators=False)["id"]
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})  # playing
    make_user("nspecp@goodmit.co.kr")
    c2, cs2 = _login_other(app, "nspecp@goodmit.co.kr")
    with c2:
        assert c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2}).status_code == 409


def test_ladder_keeps_duplicate_outcome_labels(app, client, login_as, make_user):
    """사다리 도착지에 같은 라벨(꽝 2개)을 넣으면 그대로 유지된다(스키마가 dedup 하지 않음)."""
    csrf = login_as("user", email="ladduph@goodmit.co.kr")
    rid = _create(client, csrf, title="사다리", game_type="ladder",
                  config={"options": ["당첨", "꽝", "꽝"]})["id"]
    for e in ("ld1@goodmit.co.kr", "ld2@goodmit.co.kr"):
        make_user(e)
        c, cs = _login_other(app, e)
        with c:
            c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    res = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    assert res["outcomes"].count("꽝") == 2  # 중복 꽝이 살아 있다


def test_config_numeric_string_does_not_crash(client, login_as):
    """조작된 문자열 숫자 설정이 와도 500 없이 처리된다(정수 강제, 아니면 기본값)."""
    csrf = login_as("user", email="cfgnum@goodmit.co.kr")
    r = client.post("/api/games/rooms", json={"title": "x", "game_type": "random_draw", "config": {"winners": "abc"}},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    rid = r.json()["room"]["id"]
    assert client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_cleanup_closes_idle_rooms(db, make_user):
    """폴링이 끊긴 지 오래된 열린 방은 자동으로 닫힌다(유령 방 방지). 방금 만든 방은 그대로."""
    from datetime import datetime, timedelta

    from app.games import repository, service
    from app.games.models import ROOM_FINISHED, GameRoom

    host = make_user(email="idle@goodmit.co.kr", display_name="유휴호스트")
    t0 = datetime(2026, 7, 29, 2, 0, 0)
    room = service.create_room(db, host=host, title="유휴방", game_type="random_draw",
                               max_players=8, allow_spectators=True, config={}, now=t0)
    db.flush()
    assert service.cleanup_idle_rooms(db, now=t0 + timedelta(seconds=30)) == 0
    assert repository.get_room(db, room.id) is not None
    assert service.cleanup_idle_rooms(db, now=t0 + timedelta(seconds=200)) == 1
    assert repository.get_room(db, room.id) is None
    # GM-01: closed_at만 찍고 status는 그대로 두면 status='playing'/'waiting'인데
    # 이미 닫힌 유령 행이 남는다(status로 세는 미래 질의가 그 유령을 영원히 센다) —
    # get_room은 closed_at 필터라 닫힌 방을 못 보므로 원시 조회로 status까지 함께 본다.
    raw = db.get(GameRoom, room.id)
    assert raw.status == ROOM_FINISHED


def test_tournament_seeding_excludes_stale_ghost(db, make_user):
    """GM-11: 가위바위보 토너먼트 시딩(_open_rps_tournament)이 나머지 6개 서버 확정 경로와
    같은 기준(_present_players — 활성 + 최근 폴링 90초 + 비관전)을 쓰는지 확인한다. 예전
    시딩 조건(m.active and role != spectator)은 탭만 닫고 '나가기'는 안 누른 사람을 걸러내지
    못했다 — 이 저장소에서 active는 어디서도 False가 되지 않아, row가 남아 있으면(last_seen
    만 오래됐어도) 그 조건은 사실상 항상 참이었다."""
    import json as _json
    from datetime import datetime, timedelta

    from app.games import service
    from app.games.models import GAME_RPS

    host = make_user(email="seed-h@goodmit.co.kr", display_name="호스트")
    fresh = make_user(email="seed-f@goodmit.co.kr", display_name="참여자")
    ghost = make_user(email="seed-g@goodmit.co.kr", display_name="유령")
    t0 = datetime(2026, 7, 29, 2, 0, 0)
    room = service.create_room(db, host=host, title="토너", game_type=GAME_RPS,
                               max_players=8, allow_spectators=True, config={"mode": "tournament"}, now=t0)
    db.flush()
    service.join_room(db, room, fresh, spectate=False, now=t0)
    ghost_member = service.join_room(db, room, ghost, spectate=False, now=t0)
    # 유령은 90초보다 훨씬 오래 조용하다 — 탭을 닫았을 뿐 '나가기'는 안 눌러 row는 남아 있다.
    ghost_member.last_seen = t0 - timedelta(seconds=200)
    db.flush()

    result = service.start_game(db, room, host, now=t0)
    state = _json.loads(result.state_json)
    entrants = {p for m in state["matches"] for p in (m.get("a"), m.get("b")) if p}
    assert ghost.id not in entrants, f"last_seen이 오래된 유령이 시딩에 들어갔다(GM-11): {state['matches']}"
    assert host.id in entrants and fresh.id in entrants


def test_tournament_force_finish_excludes_stale_ghost(db, make_user, monkeypatch):
    """GM-11: 강제 마감(_tournament_advance force=True)의 present 판정도 시딩과 같은 기준
    (_present_players)을 쓰는지 확인한다. 상대가 '나가기'는 안 눌러 row는 남아 있지만
    last_seen이 오래된 유령이면, 예전 기준(get_member(...) is not None — row 존재 여부만)
    으로는 "있다"로 잡혀(row가 지워지지 않았으니) 둘 다 '있다'가 되고 무작위 코인플립으로
    떨어졌다 — 실제로 남아 있는 쪽이 곧바로, 결정적으로 이겨야 한다.

    난수를 고정한다: 코인플립(rng.choice)이 실제로 걸리면 일부러 유령이 이기게(seq[-1])
    만들어, 예전 코드로 되돌렸을 때 이 검증이 우연히 통과하지 않고 반드시 실패하게 한다
    (patch 없이는 예전 코드도 반반 확률로 우연히 host가 이겨 회귀가 새는 것을 놓칠 수 있다)."""
    from datetime import datetime, timedelta

    from app.games import service

    class _AlwaysLast:
        def randint(self, a, b):
            return a

        def choice(self, seq):
            return seq[-1]

    monkeypatch.setattr(service.secrets, "SystemRandom", lambda: _AlwaysLast())

    host = make_user(email="fadv-h@goodmit.co.kr", display_name="호스트")
    ghost = make_user(email="fadv-g@goodmit.co.kr", display_name="유령")
    t0 = datetime(2026, 7, 29, 2, 0, 0)
    room = service.create_room(db, host=host, title="토너", game_type="rps",
                               max_players=8, allow_spectators=True, config={"mode": "tournament"}, now=t0)
    db.flush()
    ghost_member = service.join_room(db, room, ghost, spectate=False, now=t0)
    # 유령이 됨(row는 남아 있지만 조용히 사라진 지 오래) — 아무도 대전을 안 냈다.
    ghost_member.last_seen = t0 - timedelta(seconds=200)
    db.flush()
    # 대진은 손으로 짜서(호스트=a, 유령=b) 시딩 셔플의 비결정성과 무관하게 강제 마감
    # 로직만 정확히 겨냥한다.
    match_state = {
        "mode": "tournament", "round_idx": 0, "champion": None, "rounds": [],
        "matches": [{"a": host.id, "b": ghost.id, "a_name": "호스트", "b_name": "유령",
                     "a_choice": None, "b_choice": None, "winner": None, "done": False,
                     "bye": False, "replayed": 0}],
    }

    new_state = service._tournament_advance(db, room, match_state, now=t0, force=True)
    assert new_state["result"]["champion"]["user_id"] == host.id, (
        f"떠난 지 오래된 유령이 코인플립 대상이 됐다(GM-11): {new_state}"
    )


def test_host_disband_removes_room(app, client, login_as, make_user):
    """방장이 방을 파하면 방이 목록·조회에서 사라지고, 다른 참여자는 404를 받는다. 방장만 가능."""
    csrf = login_as("user", email="disbh@goodmit.co.kr")
    rid = _create(client, csrf, title="파할방")["id"]
    make_user("disbp@goodmit.co.kr")
    c2, cs2 = _login_other(app, "disbp@goodmit.co.kr")
    with c2:
        c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})
        # 참여자는 방을 파할 수 없다.
        assert c2.post(f"/api/games/rooms/{rid}/disband", headers={"X-CSRF-Token": cs2}).status_code == 403
        # 방장이 파한다.
        assert client.post(f"/api/games/rooms/{rid}/disband", headers={"X-CSRF-Token": csrf}).status_code == 200
        # 목록에서 사라지고, 조회는 404.
        assert not any(r["id"] == rid for r in client.get("/api/games/rooms").json()["items"])
        assert c2.get(f"/api/games/rooms/{rid}/state?since=0").status_code == 404


def test_quiz_rounds_scoring_and_hidden_answers(app, client, login_as, make_user):
    csrf = login_as("user", email="qzhost@goodmit.co.kr")
    questions = [
        {"q": "1+1?", "options": ["1", "2", "3"], "answer": 1},
        {"q": "하늘색?", "options": ["빨강", "파랑"], "answer": 1},
    ]
    rid = _create(client, csrf, title="퀴즈", game_type="quiz", config={"questions": questions})["id"]
    make_user("qp2@goodmit.co.kr")
    c2, cs2 = _login_other(app, "qp2@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})

    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert st["phase"] == "answering" and st["round"] == 0 and st["total"] == 2
    assert st["question"] == "1+1?" and "answer" not in st  # answering 중엔 정답 비공개

    # 1라운드: 방장 정답(2=idx1), 참여자 오답(idx0).
    client.post(f"/api/games/rooms/{rid}/quiz-answer", json={"option": 1}, headers={"X-CSRF-Token": csrf})
    c2.post(f"/api/games/rooms/{rid}/quiz-answer", json={"option": 0}, headers={"X-CSRF-Token": cs2})
    # answering 중 남의 답 비공개(내 답만).
    mid = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert mid["submitted_count"] == 2 and mid["your_answer"] == 1 and "answer" not in mid

    client.post(f"/api/games/rooms/{rid}/reveal", headers={"X-CSRF-Token": csrf})
    rev = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert rev["phase"] == "revealed" and rev["answer"] == 1 and rev["your_correct"] is True

    client.post(f"/api/games/rooms/{rid}/next", headers={"X-CSRF-Token": csrf})
    r2 = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert r2["round"] == 1 and r2["phase"] == "answering" and r2["your_answer"] is None  # 새 라운드 답 초기화

    # 2라운드: 둘 다 정답(idx1).
    client.post(f"/api/games/rooms/{rid}/quiz-answer", json={"option": 1}, headers={"X-CSRF-Token": csrf})
    c2.post(f"/api/games/rooms/{rid}/quiz-answer", json={"option": 1}, headers={"X-CSRF-Token": cs2})
    c2.close()
    client.post(f"/api/games/rooms/{rid}/reveal", headers={"X-CSRF-Token": csrf})
    r = client.post(f"/api/games/rooms/{rid}/next", headers={"X-CSRF-Token": csrf})
    assert r.json()["room"]["status"] == "finished"
    board = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]["scoreboard"]
    # 방장 2점(둘 다 정답), 참여자 1점(2라운드만). 방장이 1위.
    assert board[0]["score"] == 2 and board[1]["score"] == 1


def test_quiz_answer_blocked_after_reveal(app, client, login_as):
    csrf = login_as("user", email="qzblock@goodmit.co.kr")
    rid = _create(client, csrf, title="퀴즈", game_type="quiz",
                  config={"questions": [{"q": "?", "options": ["a", "b"], "answer": 0}]})["id"]
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    client.post(f"/api/games/rooms/{rid}/reveal", headers={"X-CSRF-Token": csrf})
    # revealed 상태에서 응답 시도 → 409(지금은 답을 낼 수 없음).
    assert client.post(f"/api/games/rooms/{rid}/quiz-answer", json={"option": 0}, headers={"X-CSRF-Token": csrf}).status_code == 409


def test_quiz_final_scoreboard_excludes_departed_player(app, client, login_as, make_user):
    """퀴즈 진행 중(정답 공개 후) 나간 참여자는 최종 점수판에서 빠져야 한다 — 숫자 눈치·가위바위보
    종료 집계가 이미 _present_players로 나간 사람(유령 승자·빈 이름)을 거르는 것과 같은 원칙
    (§13.1). next_quiz의 마지막 라운드 확정만 repository.members(전체 이력이 아니라 '지금 방에
    있는 사람')를 안 써서, 나간 사람이 빈 이름("")으로 점수판에 남고 심지어 '우승자'로도 뜰 수 있었다."""
    csrf = login_as("user", email="qzleaveh@goodmit.co.kr")
    rid = _create(client, csrf, title="퀴즈", game_type="quiz",
                  config={"questions": [{"q": "?", "options": ["a", "b"], "answer": 1}]})["id"]
    make_user("qzleavep@goodmit.co.kr")
    c2, cs2 = _login_other(app, "qzleavep@goodmit.co.kr")
    host_id = client.get("/api/me").json()["user"]["id"]
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})

    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    client.post(f"/api/games/rooms/{rid}/quiz-answer", json={"option": 0}, headers={"X-CSRF-Token": csrf})  # 방장 오답
    c2.post(f"/api/games/rooms/{rid}/quiz-answer", json={"option": 1}, headers={"X-CSRF-Token": cs2})  # 참여자 정답(1점)
    client.post(f"/api/games/rooms/{rid}/reveal", headers={"X-CSRF-Token": csrf})
    c2.post(f"/api/games/rooms/{rid}/leave", headers={"X-CSRF-Token": cs2})  # 마지막 라운드 확정 전에 나간다
    c2.close()

    r = client.post(f"/api/games/rooms/{rid}/next", headers={"X-CSRF-Token": csrf})  # 문제가 1개뿐 → 곧장 종료
    assert r.json()["room"]["status"] == "finished"
    result = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    assert {b["user_id"] for b in result["scoreboard"]} == {host_id}  # 나간 참여자는 빠진다
    assert "" not in result["winners"]  # 빈 이름이 '우승자'로 뜨면 안 된다


def test_rps_hidden_then_two_types_decide(app, client, login_as, make_user):
    csrf = login_as("user", email="rpshost@goodmit.co.kr")
    rid = _create(client, csrf, title="가위바위보", game_type="rps", config={})["id"]
    make_user("rp2@goodmit.co.kr")
    c2, cs2 = _login_other(app, "rp2@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})

    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    # 방장=바위(1), 참여자=가위(0). 바위가 가위를 이긴다 → 방장 승리.
    client.post(f"/api/games/rooms/{rid}/rps", json={"option": 1}, headers={"X-CSRF-Token": csrf})
    c2.post(f"/api/games/rooms/{rid}/rps", json={"option": 0}, headers={"X-CSRF-Token": cs2})
    # 진행 중 남의 선택 비공개.
    playing = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert "choices" not in playing and playing["submitted_count"] == 2 and playing["your_choice"] == 1
    c2.close()

    client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    res = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    assert res["outcome"] == "win" and res["win_choice"] == "바위"
    assert len(res["winners"]) == 1 and len(res["reveal"]) == 2


def test_rps_all_same_is_draw(app, client, login_as, make_user):
    csrf = login_as("user", email="rpsdraw@goodmit.co.kr")
    rid = _create(client, csrf, title="가위바위보", game_type="rps")["id"]
    make_user("rpd2@goodmit.co.kr")
    c2, cs2 = _login_other(app, "rpd2@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    client.post(f"/api/games/rooms/{rid}/rps", json={"option": 2}, headers={"X-CSRF-Token": csrf})
    c2.post(f"/api/games/rooms/{rid}/rps", json={"option": 2}, headers={"X-CSRF-Token": cs2})
    c2.close()
    client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    res = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    assert res["outcome"] == "draw" and res["winners"] == []


def test_timer_autoresolves_server_side_on_poll(app, client, login_as, fake_clock):
    """마감이 지나면 방장이 아무것도 안 해도 폴링 진입에서 서버가 자동 확정한다(방장 브라우저 비의존)."""
    csrf = login_as("user", email="autoresh@goodmit.co.kr")
    rid = _create(client, csrf, title="가위바위보", game_type="rps", config={"timer_seconds": 10})["id"]
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    assert client.get(f"/api/games/rooms/{rid}/state?since=0").json()["room"]["status"] == "playing"
    fake_clock.advance(11)  # 마감(10초) 넘김
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()  # 폴링 → 서버 자동 확정
    assert st["room"]["status"] == "finished" and st["state"]["result"] is not None


def test_roster_marks_stale_members_as_not_present(app, client, login_as, make_user, fake_clock):
    """명단은 남아 있어도(active) 90초 넘게 폴링이 없으면 추첨·팀나누기·사다리·투표
    대상 풀(_present_players)에서는 조용히 빠진다(step 9 #7) - 그 어긋남을 화면이 미리
    알 수 있어야 "5명이 보이는데 4명 중에서 뽑힌다"가 결과로만 드러나지 않는다.
    `_member_view`가 실어 보내는 `present` 플래그가 그 판정과 정확히 같아야 한다."""
    csrf = login_as("user", email="stay@goodmit.co.kr")
    rid = _create(client, csrf)["id"]
    make_user("ghost3@goodmit.co.kr")
    c2, cs2 = _login_other(app, "ghost3@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})

    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    members = {m["user_id"]: m for m in st["members"]}
    assert len(members) == 2 and all(m["present"] for m in members.values()), (
        "방금 폴링한 두 사람이 present:false 로 나온다"
    )

    # ghost3 은 더는 폴링하지 않는다(탭만 숨김 - 나가기는 안 눌렀다). 90초(PRESENCE_SECONDS)
    # 를 넘겨 stay 만 다시 폴링한다.
    from app.games.service import PRESENCE_SECONDS

    fake_clock.advance(PRESENCE_SECONDS + 1)
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    members = {m["user_id"]: m for m in st["members"]}
    assert len(members) == 2, "명단에서 통째로 사라졌다 — active 는 그대로 True 여야 한다"
    assert all(m["active"] for m in members.values()), "폴링을 멈춘 것뿐인데 active 가 꺼졌다"
    present_flags = sorted(m["present"] for m in members.values())
    assert present_flags == [False, True], (
        f"방금 폴링한 사람과 90초 넘게 조용한 사람이 구분되지 않는다: {members}"
    )


def test_rps_tournament_two_players_crowns_champion(app, client, login_as, make_user):
    """토너먼트 2인: 두 선택이 다르면 그 자리에서 승부가 나고 곧바로 챔피언이 확정된다."""
    csrf = login_as("user", email="tour2h@goodmit.co.kr")
    rid = _create(client, csrf, title="토너먼트", game_type="rps",
                  config={"mode": "tournament", "timer_seconds": 0})["id"]
    make_user("tour2p@goodmit.co.kr")
    c2, cs2 = _login_other(app, "tour2p@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert st["mode"] == "tournament" and len(st["matches"]) == 1 and st["champion"] is None
    # 방장=가위(0), 참여자=바위(1) → 바위 승 → 참여자 챔피언, 게임 종료.
    client.post(f"/api/games/rooms/{rid}/rps", json={"option": 0}, headers={"X-CSRF-Token": csrf})
    c2.post(f"/api/games/rooms/{rid}/rps", json={"option": 1}, headers={"X-CSRF-Token": cs2})
    c2.close()
    fin = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    assert fin["room"]["status"] == "finished"
    res = fin["state"]["result"]
    assert res["mode"] == "tournament" and res["champion"] and res["champion"]["name"]
    assert len(res["rounds"]) == 1


def test_rps_tournament_four_players_multi_round(app, client, login_as, make_user):
    """토너먼트 4인: 방장이 라운드를 강제 마감하면 미결 대진은 서버가 채우고 다음 라운드로,
    마지막에 챔피언 한 명이 남는다(라운드 히스토리 2개)."""
    csrf = login_as("user", email="tour4h@goodmit.co.kr")
    rid = _create(client, csrf, title="토너먼트4", game_type="rps",
                  config={"mode": "tournament", "timer_seconds": 0})["id"]
    for e in ("t4a@goodmit.co.kr", "t4b@goodmit.co.kr", "t4c@goodmit.co.kr"):
        make_user(e)
        c, cs = _login_other(app, e)
        with c:
            c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert st["round_idx"] == 0 and len(st["matches"]) == 2  # 4명 → 2대진
    # 1라운드 강제 마감 → 2라운드(승자 2명 → 1대진), 아직 진행 중.
    client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    st2 = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    assert st2["room"]["status"] == "playing"
    assert st2["state"]["round_idx"] == 1 and len(st2["state"]["matches"]) == 1
    # 2라운드 강제 마감 → 챔피언.
    client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    fin = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    assert fin["room"]["status"] == "finished"
    res = fin["state"]["result"]
    assert res["champion"] and len(res["rounds"]) == 2


def test_rps_tournament_departed_player_cannot_become_champion(app, client, login_as, make_user, monkeypatch):
    """대진 상대가 방을 나간 뒤 방장이 강제 마감하면, 남아 있는 참여자가 자동으로 이겨야 한다 —
    이미 나간 사람이 코인플립/무작위 선택으로 챔피언이 되면 안 된다(§13.1 서버 확정 공정성).
    숫자 눈치·가위바위보 단판은 종료 집계에서 _present_players로 나간 사람을 거르는데
    (test_number_finish_excludes_departed_player), 토너먼트 강제 마감(_tournament_advance)에는
    그 필터가 없었다 — 이 테스트로 그 구멍을 고정한다."""
    from app.games import service as game_service

    csrf = login_as("user", email="tourleaveh@goodmit.co.kr")
    rid = _create(client, csrf, title="토너먼트", game_type="rps",
                  config={"mode": "tournament", "timer_seconds": 0})["id"]
    make_user("tourleavep@goodmit.co.kr", display_name="나간사람")
    c2, cs2 = _login_other(app, "tourleavep@goodmit.co.kr")
    p2_id = c2.get("/api/me").json()["user"]["id"]
    host_id = client.get("/api/me").json()["user"]["id"]
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})

    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    match0 = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["matches"][0]
    p2_is_a = match0["a_name"] == "나간사람"

    # 참여자(p2)가 대진 상대와 붙기 전에 방을 나간다 — 멤버 row가 사라진다(leave_room).
    c2.post(f"/api/games/rooms/{rid}/leave", headers={"X-CSRF-Token": cs2})
    c2.close()

    # 강제 마감이 채우는 두 선택을 결정론적으로 고정해 "나간 사람 슬롯"이 이기는 가위바위보
    # 결과를 강제한다(고쳐지지 않았다면 나간 사람이 챔피언이 되는 걸 재현하기 위해서다).
    # 코드 순서상 첫 randint 호출이 a_choice, 둘째가 b_choice다.
    calls = {"n": 0}

    def fake_randint(self, lo, hi):
        calls["n"] += 1
        is_a_call = calls["n"] == 1
        # 나간 사람 슬롯 = 바위(1), 상대 슬롯 = 가위(0) → 바위가 이긴다.
        if p2_is_a:
            return 1 if is_a_call else 0
        return 0 if is_a_call else 1

    monkeypatch.setattr(game_service.secrets.SystemRandom, "randint", fake_randint)

    fin = client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    assert fin.status_code == 200
    res = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    assert res["champion"]["user_id"] == host_id  # 나간 사람(p2)은 챔피언이 될 수 없다
    assert res["champion"]["user_id"] != p2_id


def test_number_game_hides_picks_then_lowest_unique_wins(app, client, login_as, make_user):
    csrf = login_as("user", email="nhost@goodmit.co.kr")
    rid = _create(client, csrf, title="눈치", game_type="number", config={"min": 1, "max": 9})["id"]
    voters = []
    for e in ("np1@goodmit.co.kr", "np2@goodmit.co.kr"):
        make_user(e)
        c, cs = _login_other(app, e)
        c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})
        voters.append((c, cs))

    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    # 방장·참여자1 = 3(겹침), 참여자2 = 5(유일). 가장 낮은 유일 숫자는 5 → 참여자2 승리.
    client.post(f"/api/games/rooms/{rid}/pick", json={"value": 3}, headers={"X-CSRF-Token": csrf})
    voters[0][0].post(f"/api/games/rooms/{rid}/pick", json={"value": 3}, headers={"X-CSRF-Token": voters[0][1]})
    voters[1][0].post(f"/api/games/rooms/{rid}/pick", json={"value": 5}, headers={"X-CSRF-Token": voters[1][1]})

    # 진행 중엔 남의 선택이 감춰진다 — 방장이 보는 state엔 picks가 없고 제출 수만.
    playing = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert "picks" not in playing and playing["submitted_count"] == 3
    assert playing["you_submitted"] is True and playing["your_pick"] == 3
    for c, _ in voters:
        c.close()

    r = client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["room"]["status"] == "finished"
    res = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    assert res["winner"]["number"] == 5 and len(res["picks"]) == 3

    # 범위 밖 숫자는 거부(방 재사용 없이 간단 확인은 위 흐름으로 충분).


def test_number_game_rejects_out_of_range(app, client, login_as):
    csrf = login_as("user", email="nrange@goodmit.co.kr")
    rid = _create(client, csrf, title="눈치", game_type="number", config={"min": 1, "max": 5})["id"]
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    r = client.post(f"/api/games/rooms/{rid}/pick", json={"value": 9}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422  # 범위(1~5) 밖 → ValidationAppError


def test_quick_vote_tally_server_confirms(app, client, login_as, make_user):
    csrf = login_as("user", email="vhost@goodmit.co.kr")
    rid = _create(client, csrf, title="점심", game_type="quick_vote",
                  config={"question": "점심 뭐?", "options": ["국밥", "파스타", "김밥"]})["id"]
    # 참여자 둘 합류.
    voters = []
    for e in ("vp1@goodmit.co.kr", "vp2@goodmit.co.kr"):
        make_user(e)
        c, cs = _login_other(app, e)
        c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})
        voters.append((c, cs))

    # 방장이 투표를 연다 → playing.
    r = client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["room"]["status"] == "playing"

    # 방장 + 참여자1은 파스타(1), 참여자2는 국밥(0). 파스타가 2표로 이겨야 한다(서버 확정).
    client.post(f"/api/games/rooms/{rid}/vote", json={"option": 1}, headers={"X-CSRF-Token": csrf})
    voters[0][0].post(f"/api/games/rooms/{rid}/vote", json={"option": 1}, headers={"X-CSRF-Token": voters[0][1]})
    voters[1][0].post(f"/api/games/rooms/{rid}/vote", json={"option": 0}, headers={"X-CSRF-Token": voters[1][1]})
    for c, _ in voters:
        c.close()

    r = client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["room"]["status"] == "finished"
    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()
    res = st["state"]["result"]
    assert res["counts"] == [1, 2, 0] and res["winners"] == ["파스타"] and res["total"] == 3


def test_quick_vote_only_players_vote_and_revote(app, client, login_as, make_user):
    csrf = login_as("user", email="vh2@goodmit.co.kr")
    rid = _create(client, csrf, title="투표", game_type="quick_vote",
                  config={"question": "?", "options": ["A", "B"]})["id"]
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    # 재투표: A(0) → B(1) 로 바꾸면 마지막 것만 센다.
    client.post(f"/api/games/rooms/{rid}/vote", json={"option": 0}, headers={"X-CSRF-Token": csrf})
    client.post(f"/api/games/rooms/{rid}/vote", json={"option": 1}, headers={"X-CSRF-Token": csrf})
    # 관전자는 투표 불가(403).
    make_user("vspec@goodmit.co.kr")
    c, cs = _login_other(app, "vspec@goodmit.co.kr")
    with c:
        c.post(f"/api/games/rooms/{rid}/join?spectate=true", headers={"X-CSRF-Token": cs})
        assert c.post(f"/api/games/rooms/{rid}/vote", json={"option": 0}, headers={"X-CSRF-Token": cs}).status_code == 403
    client.post(f"/api/games/rooms/{rid}/finish", headers={"X-CSRF-Token": csrf})
    res = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]["result"]
    assert res["counts"] == [0, 1] and res["winners"] == ["B"]


def test_concurrent_votes_do_not_clobber_each_other(app, client, login_as, make_user):
    """두 참여자가 서로의 커밋 전에 같은 state_json을 읽은 채(거의 동시에) 투표를 제출하면,
    나중에 커밋되는 쪽이 앞서 커밋된 투표를 통째로 지워버리면 안 된다. 앱은 동기 핸들러를
    스레드풀에서 돌리므로(app/core/db.py) 두 참여자의 요청이 실제로 겹칠 수 있다 — 각자 독립된
    DB 세션이 같은 옛 state_json을 읽어 자기 제출만 반영한 새 state로 무조건 덮어쓰면(예전
    코드) 나중에 쓰는 쪽이 이긴다. service._cas_update_state가 WHERE state_json=읽은 값으로
    쓰고 충돌 시 최신 state에 다시 적용해(최대 5회) 이 유실을 막는다."""
    from app.games import service as game_service
    from app.games.models import GameRoom
    from app.users.models import User

    csrf = login_as("user", email="racehost@goodmit.co.kr")
    rid = _create(client, csrf, title="투표", game_type="quick_vote",
                  config={"question": "?", "options": ["A", "B"]})["id"]
    make_user("racep2@goodmit.co.kr")
    c2, cs2 = _login_other(app, "racep2@goodmit.co.kr")
    host_id = client.get("/api/me").json()["user"]["id"]
    p2_id = c2.get("/api/me").json()["user"]["id"]
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})
    c2.close()
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})

    now = app.state.clock.now()
    factory = app.state.session_factory
    # 두 세션이 투표 전(votes={}) state를 각자 읽는다 — 실제 동시 요청의 "둘 다 옛 값을 읽었다"
    # 상황을 그대로 재현한다.
    sa, sb = factory(), factory()
    room_a, room_b = sa.get(GameRoom, rid), sb.get(GameRoom, rid)
    game_service.submit_vote(sa, room_a, sa.get(User, host_id), option_index=0, now=now)
    sa.commit()
    game_service.submit_vote(sb, room_b, sb.get(User, p2_id), option_index=1, now=now)
    sb.commit()

    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert st["votes"] == {host_id: 0, p2_id: 1}  # 둘 다 살아 있어야 한다(유실 없음)


# FN-20: 단판 가위바위보(submit_rps)·숫자 눈치(submit_number)는 이미 _cas_update_state를
# 쓰는데 토너먼트 제출(_tournament_submit)만 무조건 덮어쓰기였다 — 같은 결함을 같은 방식으로
# 고쳤다는 것을 위 test_concurrent_votes_do_not_clobber_each_other와 같은 기법으로 고정한다.
def test_concurrent_tournament_submits_do_not_clobber_each_other(app, client, login_as, make_user):
    """서로 다른 대진 두 곳의 제출이 거의 동시에 커밋되면, 나중에 커밋되는 쪽이 앞서 커밋된
    다른 대진의 선택을 지우면 안 된다(4인 토너먼트 1라운드 = 대진 2개)."""
    from app.games import service as game_service
    from app.games.models import GameRoom
    from app.users.models import User

    import json as _json

    csrf = login_as("user", email="tourrace-h@goodmit.co.kr")
    rid = _create(client, csrf, title="토너먼트 경합", game_type="rps",
                  config={"mode": "tournament", "timer_seconds": 0})["id"]
    for e in ("tourrace-p2@goodmit.co.kr", "tourrace-p3@goodmit.co.kr", "tourrace-p4@goodmit.co.kr"):
        make_user(e)
        c, cs = _login_other(app, e)
        with c:
            c.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})

    with app.state.session_factory() as peek:
        raw_matches = _json.loads(peek.get(GameRoom, rid).state_json)["matches"]
    assert len(raw_matches) == 2  # 4명 → 대진 2개
    uid_match0 = raw_matches[0]["a"]
    uid_match1 = raw_matches[1]["a"]

    now = app.state.clock.now()
    factory = app.state.session_factory
    # 두 세션이 제출 전(둘 다 미제출) state를 각자 읽는다 — 실제 동시 요청이 같은 옛
    # state_json을 읽는 상황을 그대로 재현한다.
    sa, sb = factory(), factory()
    room_a, room_b = sa.get(GameRoom, rid), sb.get(GameRoom, rid)
    game_service.submit_rps(sa, room_a, sa.get(User, uid_match0), choice=0, now=now)
    sa.commit()
    game_service.submit_rps(sb, room_b, sb.get(User, uid_match1), choice=1, now=now)
    sb.commit()

    with app.state.session_factory() as peek:
        after_matches = _json.loads(peek.get(GameRoom, rid).state_json)["matches"]
    # 두 대진 각각 정확히 한 슬롯(자기 자신)이 제출됐어야 한다 — 유실 없음.
    submitted = sum(
        1 for m in after_matches for k in ("a_choice", "b_choice") if m.get(k) is not None
    )
    assert submitted == 2, f"두 대진 중 하나의 제출이 유실됐다(lost update): {after_matches}"


def test_concurrent_autoresolve_does_not_recompute_a_different_winner(app, client, login_as, make_user):
    """GM-10: 마감이 지난 방에 폴링(room_state) 두 요청이 거의 동시에 도착하면(각자 독립된 DB
    세션이 '아직 result 없음'인 같은 state를 읽는다), 예전 코드는 방어 없이(read-then-write
    가드 하나뿐) 둘 다 결과를 계산해 무조건 덮어썼다 — 나중에 커밋되는 쪽이 그 사이 바뀐
    입력(예: 다른 참여자가 나감)으로 다시 계산하면, 이미 첫 번째 요청이 계산해 응답으로
    돌려준 값과 실제로 저장되는 값이 달라진다(클라이언트마다 다른 승자).

    호스트·참여자2가 같은 숫자(3)를 내 무승부(유일 숫자 없음)로 확정돼야 하는 상황을 만든다.
    첫 세션이 그 무승부를 계산·커밋한 *뒤에* 참여자2가 방을 나가면, 예전 코드로 두 번째
    세션이 다시 계산할 경우 참여자2가 사라져 호스트의 3이 유일해져 "호스트 승리"로 뒤집힌다
    — 무승부라는 이미 확정된 사실이 나중 요청 때문에 조용히 바뀌면 안 된다."""
    from datetime import timedelta

    from app.games import service as game_service
    from app.games.models import GameRoom

    csrf = login_as("user", email="racenum-h@goodmit.co.kr")
    rid = _create(client, csrf, title="숫자경합", game_type="number",
                  config={"min": 1, "max": 9, "timer_seconds": 1})["id"]
    make_user("racenum-p2@goodmit.co.kr")
    c2, cs2 = _login_other(app, "racenum-p2@goodmit.co.kr")
    c2.post(f"/api/games/rooms/{rid}/join", headers={"X-CSRF-Token": cs2})
    client.post(f"/api/games/rooms/{rid}/start", headers={"X-CSRF-Token": csrf})
    # 둘 다 3을 낸다 — 유일 숫자가 없어 무승부로 확정돼야 한다.
    client.post(f"/api/games/rooms/{rid}/pick", json={"value": 3}, headers={"X-CSRF-Token": csrf})
    c2.post(f"/api/games/rooms/{rid}/pick", json={"value": 3}, headers={"X-CSRF-Token": cs2})

    later = app.state.clock.now() + timedelta(seconds=5)  # 마감을 지난 시각
    factory = app.state.session_factory
    # 두 세션이 확정 전(아직 result 없음) state를 각자 읽는다 — 실제 동시 폴링 요청이 같은
    # 옛 state를 읽는 상황을 그대로 재현한다.
    sa, sb = factory(), factory()
    room_a, room_b = sa.get(GameRoom, rid), sb.get(GameRoom, rid)
    game_service.maybe_autoresolve(sa, room_a, now=later)
    sa.commit()

    # 첫 세션이 무승부를 커밋한 *뒤에* 참여자2가 나간다 — 두 번째 세션이 다시 계산하면
    # (예전 코드) 입력이 달라져 있다.
    c2.post(f"/api/games/rooms/{rid}/leave", headers={"X-CSRF-Token": cs2})
    c2.close()

    game_service.maybe_autoresolve(sb, room_b, now=later)
    sb.commit()

    st = client.get(f"/api/games/rooms/{rid}/state?since=0").json()["state"]
    assert st["result"]["winner"] is None, (
        f"이미 확정된 무승부가 나중 요청 때문에 뒤집혔다(유령우승): {st['result']}"
    )


def test_quiz_generate_flag_off_and_csrf(client, login_as):
    csrf = login_as("user", email="qgen@goodmit.co.kr")
    # CSRF 없음 → 403(require_csrf 먼저). 있으면 플래그 OFF(기본)라 404.
    assert client.post("/api/games/quiz/generate", json={"topic": "상식"}).status_code == 403
    assert client.post("/api/games/quiz/generate", json={"topic": "상식"},
                       headers={"X-CSRF-Token": csrf}).status_code == 404


def _ai_app(db_url, tmp_path, fake_clock, fake_http):
    import shutil

    from app.core.config import Settings
    from app.main import create_app
    from app.users.service import create_user

    cfg = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg)
    flags = json.loads((PROJECT_ROOT / "config" / "feature-flags.json").read_text(encoding="utf-8"))
    flags["game_ai_enabled"] = True
    (cfg / "feature-flags.json").write_text(json.dumps(flags), encoding="utf-8")
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    settings = Settings(
        _env_file=None, app_env="test", database_url=db_url,
        session_secret="test-session-secret", cookie_secure=False,
        config_dir=cfg, secrets_dir=secrets_dir, data_dir=tmp_path,
    )
    app = create_app(settings, clock=fake_clock, outbound_transport=fake_http.transport())
    with app.state.session_factory() as s:
        create_user(s, email="qa@goodmit.co.kr", display_name="QA", password=DEFAULT_TEST_PASSWORD,
                    settings=settings, actor_role="system_admin", role="user", active=True,
                    must_change_password=False)
        s.commit()
    return app, settings


class _ScriptedGenerate:
    """S11 이후 퀴즈는 `Gateway.generate()` 를 지난다(D-266) — 가짜를 세울 자리도 거기다."""

    name = "scripted"
    model = "scripted-model"

    def __init__(self, *, text="", status=None):
        from app.ai.gateway import contract

        self._text = text
        self._status = status or contract.STATUS_OK

    def capability(self):
        from app.ai.gateway import contract

        if self._status != contract.STATUS_OK:
            return contract.unavailable(contract.CAP_GENERATE, self._status, model=self.model)
        return contract.available(contract.CAP_GENERATE, model=self.model)

    def generate(self, *, system, user):
        from app.ai.gateway import contract

        return contract.GenerateResult(
            status=self._status, model=self.model,
            text=self._text if self._status == contract.STATUS_OK else None,
        )


def _use_model(app, adapter):
    from app.ai.gateway import contract

    app.state.ai_gateway = contract.Gateway(enabled=True, generate_adapter=adapter)


def test_quiz_generate_flag_on_returns_cleaned(db_url, tmp_path, fake_clock, fake_http):
    app, settings = _ai_app(db_url, tmp_path, fake_clock, fake_http)
    # 모델이 정답이 보기에 있는 좋은 문제 + 정답 인덱스가 범위 밖인 나쁜 문제를 섞어 줘도,
    # 앱이 _clean_questions로 정제해 좋은 것만 남긴다(§11 모델 출력 불신).
    # 그리고 모델은 **글로 답한다** — ```json 울타리째 줘도 파서가 배열을 꺼낸다.
    fenced = "\n".join([
        "네, 만들었습니다.",
        "```json",
        json.dumps([
            {"q": "1+1?", "options": ["1", "2"], "answer": 1},
            {"q": "bad", "options": ["a", "b"], "answer": 9},
        ], ensure_ascii=False),
        "```",
    ])
    _use_model(app, _ScriptedGenerate(text=fenced))
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "qa@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        csrf = c.get("/api/me").json()["csrf_token"]
        r = c.post("/api/games/quiz/generate", json={"topic": "상식", "count": 2},
                   headers={"X-CSRF-Token": csrf})
        assert r.status_code == 200, r.text
        assert r.json()["questions"] == [{"q": "1+1?", "options": ["1", "2"], "answer": 1}]


def test_quiz_generate_no_valid_questions_is_422(db_url, tmp_path, fake_clock, fake_http):
    app, settings = _ai_app(db_url, tmp_path, fake_clock, fake_http)
    _use_model(app, _ScriptedGenerate(text=json.dumps(
        [{"q": "보기부족", "options": ["a"], "answer": 0}], ensure_ascii=False)))
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "qa@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        csrf = c.get("/api/me").json()["csrf_token"]
        r = c.post("/api/games/quiz/generate", json={"topic": "x"}, headers={"X-CSRF-Token": csrf})
        assert r.status_code == 422 and r.json()["error"]["code"] == "quiz_generate_failed"


def test_quiz_generate_with_prose_only_answer_is_422_not_a_500(db_url, tmp_path, fake_clock, fake_http):
    """모델이 「못 만들겠습니다」라고 글로만 답할 수 있다. 그것을 파싱 실패로 흘리면 500 이다."""
    app, settings = _ai_app(db_url, tmp_path, fake_clock, fake_http)
    _use_model(app, _ScriptedGenerate(text="죄송합니다. 그 주제로는 문제를 만들 수 없습니다."))
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "qa@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        csrf = c.get("/api/me").json()["csrf_token"]
        r = c.post("/api/games/quiz/generate", json={"topic": "x"}, headers={"X-CSRF-Token": csrf})
        assert r.status_code == 422 and r.json()["error"]["code"] == "quiz_generate_failed"


def test_quiz_generate_without_a_model_reports_unconfigured_not_generic_failure(
    db_url, tmp_path, fake_clock, fake_http
):
    """「아직 설정 안 됨」과 「지연/실패」는 사용자가 할 일이 다르다 — 앞은 다시 시도해도
    소용없다. 러너 시절에는 그 구별이 토큰 파일 유무였고, 지금은 Gateway 의 상태 어휘가
    들고 온다."""
    from app.ai.gateway import contract

    app, settings = _ai_app(db_url, tmp_path, fake_clock, fake_http)
    app.state.ai_gateway = contract.Gateway(enabled=True, generate_adapter=None)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "qa@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        csrf = c.get("/api/me").json()["csrf_token"]
        r = c.post("/api/games/quiz/generate", json={"topic": "상식", "count": 2},
                   headers={"X-CSRF-Token": csrf})
        assert r.status_code == 422
        assert "관리자에게 문의하세요" in r.json()["error"]["message"]


def test_feature_flag_off_hides_games(db_url, tmp_path, fake_clock, fake_http):
    import shutil

    from app.core.config import Settings
    from app.main import create_app
    from app.users.service import create_user

    cfg = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg)
    (cfg / "feature-flags.json").write_text(json.dumps({"games_enabled": False}), encoding="utf-8")
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir()
    settings = Settings(
        _env_file=None, app_env="test", database_url=db_url,
        session_secret="test-session-secret", cookie_secure=False,
        config_dir=cfg, secrets_dir=secrets_dir, data_dir=tmp_path,
    )
    app = create_app(settings, clock=fake_clock, outbound_transport=fake_http.transport())
    with app.state.session_factory() as s:
        create_user(s, email="ff@goodmit.co.kr", display_name="FF", password=DEFAULT_TEST_PASSWORD,
                    settings=settings, actor_role="system_admin", role="user", active=True,
                    must_change_password=False)
        s.commit()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "ff@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        assert c.get("/api/games/rooms").status_code == 404
