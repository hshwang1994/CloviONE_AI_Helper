"""팀 공간 > 놀이 API 통합 테스트 (§5·§6·§13·§14).

방 생성/목록/입장/준비/관전/재접속 + 폴링(이벤트 시퀀스) + 서버 확정 랜덤 추첨 + 방장 권한
+ 채팅 + 인증/CSRF/기능플래그.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_TEST_PASSWORD, PROJECT_ROOT

pytestmark = pytest.mark.integration


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


def test_quiz_generate_flag_off_and_csrf(client, login_as):
    csrf = login_as("user", email="qgen@goodmit.co.kr")
    # CSRF 없음 → 403(require_csrf 먼저). 있으면 플래그 OFF(기본)라 404.
    assert client.post("/api/games/quiz/generate", json={"topic": "상식"}).status_code == 403
    assert client.post("/api/games/quiz/generate", json={"topic": "상식"},
                       headers={"X-CSRF-Token": csrf}).status_code == 404


def _ai_app(db_path, tmp_path, fake_clock, fake_http):
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
    (secrets_dir / "game_runner_token").write_text("test-runner-token", encoding="utf-8")
    settings = Settings(
        _env_file=None, app_env="test", database_url=f"sqlite:///{db_path.as_posix()}",
        session_secret="test-session-secret", cookie_secure=False,
        config_dir=cfg, secrets_dir=secrets_dir, data_dir=tmp_path,
    )
    app = create_app(settings, clock=fake_clock, outbound_transport=fake_http.transport())
    with app.state.session_factory() as s:
        create_user(s, email="qa@goodmit.co.kr", display_name="QA", password=DEFAULT_TEST_PASSWORD,
                    settings=settings, role="user", active=True, must_change_password=False)
        s.commit()
    return app, settings


def test_quiz_generate_flag_on_returns_cleaned(db_path, tmp_path, fake_clock, fake_http):
    app, settings = _ai_app(db_path, tmp_path, fake_clock, fake_http)
    # 러너가 정답이 보기에 있는 좋은 문제 + 정답 인덱스가 범위 밖인 나쁜 문제를 섞어 줘도,
    # 앱이 _clean_questions로 정제해 좋은 것만 남긴다(§11 모델 출력 불신).
    fake_http.on(settings.game_runner_url, json_body={"data": {"quiz": [
        {"q": "1+1?", "options": ["1", "2"], "answer": 1},
        {"q": "bad", "options": ["a", "b"], "answer": 9},
    ]}})
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "qa@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        csrf = c.get("/api/me").json()["csrf_token"]
        r = c.post("/api/games/quiz/generate", json={"topic": "상식", "count": 2},
                   headers={"X-CSRF-Token": csrf})
        assert r.status_code == 200, r.text
        assert r.json()["questions"] == [{"q": "1+1?", "options": ["1", "2"], "answer": 1}]


def test_quiz_generate_no_valid_questions_is_422(db_path, tmp_path, fake_clock, fake_http):
    app, settings = _ai_app(db_path, tmp_path, fake_clock, fake_http)
    fake_http.on(settings.game_runner_url, json_body={"data": {"quiz": [
        {"q": "보기부족", "options": ["a"], "answer": 0},
    ]}})
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "qa@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        csrf = c.get("/api/me").json()["csrf_token"]
        r = c.post("/api/games/quiz/generate", json={"topic": "x"}, headers={"X-CSRF-Token": csrf})
        assert r.status_code == 422 and r.json()["error"]["code"] == "quiz_generate_failed"


def test_feature_flag_off_hides_games(db_path, tmp_path, fake_clock, fake_http):
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
        _env_file=None, app_env="test", database_url=f"sqlite:///{db_path.as_posix()}",
        session_secret="test-session-secret", cookie_secure=False,
        config_dir=cfg, secrets_dir=secrets_dir, data_dir=tmp_path,
    )
    app = create_app(settings, clock=fake_clock, outbound_transport=fake_http.transport())
    with app.state.session_factory() as s:
        create_user(s, email="ff@goodmit.co.kr", display_name="FF", password=DEFAULT_TEST_PASSWORD,
                    settings=settings, role="user", active=True, must_change_password=False)
        s.commit()
    with TestClient(app, raise_server_exceptions=False) as c:
        c.post("/login", json={"email": "ff@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
        assert c.get("/api/games/rooms").status_code == 404
