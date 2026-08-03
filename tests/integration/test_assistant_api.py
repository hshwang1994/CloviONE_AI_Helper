"""AI 도우미 심화 API — 브리핑 / 스탠드업 / 주간 다이제스트 / 미할당 트리아지.

계획서 Phase 5 의 두 약속을 계약으로 고정한다:

  1. **숫자 먼저, 문장은 나중.** 문장 생성이 꺼져 있어도(기본) 네 엔드포인트 모두 완전한
     숫자를 낸다. 러너를 부르지도 않는다.
  2. **러너가 죽어도 숫자는 그대로.** `?narrate=true` 로 부르고 러너가 타임아웃/연결거부/
     5xx/빈 응답을 내도, 응답의 숫자 필드는 문장을 안 켰을 때와 **완전히 동일**하고
     `narrative.text` 만 None 이 된다. 이 동치를 dict 비교로 직접 확인한다.

  그리고 트리아지는 **제안만** 한다 — `auto_assign: false` 이고 쓰기 라우트가 없다.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from app.board.models import Post
from app.core.security import hash_password
from app.notifications.models import Notification
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.team_docs.models import DocumentCache
from app.tickets.models import (
    SYNC_OK,
    SYNC_STATE_ID,
    TicketCache,
    TicketSyncState,
    join_names,
)
from app.users.models import User
from tests.conftest import DEFAULT_TEST_PASSWORD
from tests.fakes.clock import FakeClock
from tests.fakes.notion import FakeNotionTasksDB

PROJECT_ROOT = Path(__file__).resolve().parents[2]

NOW = datetime(2026, 8, 3, 1, 0, 0)      # UTC → KST 2026-08-03(월) 10:00
TODAY = "2026-08-03"
SYNCED_AT = datetime(2026, 8, 3, 0, 57, 0)
TOKEN_REF = "notion_report_token"

U_ME = "00000000-0000-4000-8000-0000000a0001"
U_MATE = "00000000-0000-4000-8000-0000000a0002"
N_ME = "notion-user-asst-me"
N_MATE = "notion-user-asst-mate"
EMAIL = "asst-me@goodmit.co.kr"
MATE_EMAIL = "asst-mate@goodmit.co.kr"


@pytest.fixture()
def fake_clock():
    return FakeClock(NOW)


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(rows=[]).install(fake_http)


def _cache(uid, page, *, tid, title, status, due, people, est=None, priority=None):
    return TicketCache(
        id=uid, notion_page_id=page, notion_ticket_number=tid,
        url=f"https://www.notion.so/{page}", title=title, status=status,
        due_date=due, est_wd=est, priority=priority,
        project_ids="", project_names=join_names(["도우미 프로젝트"]),
        assignee_notion_ids=join_names(people),
        synced_at=SYNCED_AT, created_at=SYNCED_AT, updated_at=SYNCED_AT,
    )


def _seed(db) -> None:
    for uid, email, name in ((U_ME, EMAIL, "도우미 나"), (U_MATE, MATE_EMAIL, "도우미 동료")):
        db.add(User(id=uid, email=email, display_name=name, role="user", active=True,
                    password_hash=hash_password(DEFAULT_TEST_PASSWORD),
                    must_change_password=False))
    db.flush()
    for uid, nid, email in ((U_ME, N_ME, EMAIL), (U_MATE, N_MATE, MATE_EMAIL)):
        db.add(UserNotionMapping(user_id=uid, notion_user_id=nid, notion_email=email,
                                 status=STATUS_VERIFIED, source=SOURCE_MANUAL,
                                 last_verified_at=SYNCED_AT))
    db.add_all([
        _cache("a-uid-1", "a-1", tid=1, title="오늘 마감", status="진행",
               due=TODAY, people=[N_ME], est=1.0),
        _cache("a-uid-2", "a-2", tid=2, title="지연", status="진행",
               due="2026-07-30", people=[N_ME], est=2.0),
        _cache("a-uid-3", "a-3", tid=3, title="막힘", status="이슈",
               due="2026-08-06", people=[N_ME]),
        _cache("a-uid-4", "a-4", tid=4, title="이번 주 완료", status="완료",
               due="2026-08-04", people=[N_ME], est=1.5),
        # 동료는 활성 2건 — 트리아지 후보 정렬에서 '나'(활성 3건)보다 앞서야 한다.
        _cache("a-uid-5", "a-5", tid=5, title="동료 1", status="진행",
               due="2026-08-05", people=[N_MATE]),
        _cache("a-uid-6", "a-6", tid=6, title="동료 2", status="진행",
               due="2026-08-07", people=[N_MATE]),
        # 미할당 3건 — 지연 > 긴급 > 나머지 순으로 제안돼야 한다.
        _cache("a-uid-7", "a-7", tid=7, title="미할당 보통", status="진행",
               due="2026-08-20", people=[], priority="보통"),
        _cache("a-uid-8", "a-8", tid=8, title="미할당 긴급", status="진행",
               due="2026-08-20", people=[], priority="긴급"),
        _cache("a-uid-9", "a-9", tid=9, title="미할당 지연", status="진행",
               due="2026-07-20", people=[], priority="낮음"),
    ])
    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status = SYNC_OK
    state.last_run_at = SYNCED_AT
    state.last_success_at = SYNCED_AT
    state.ticket_count = 9
    state.truncated = False
    state.error = None
    db.add(state)
    db.add(Notification(user_id=U_ME, type="ticket_assigned", title="알림", created_at=SYNCED_AT))
    db.add(Post(id="asst-post-1", author_user_id=U_MATE, category="자유", title="이번 주 글",
                body="본문", created_at=SYNCED_AT, updated_at=SYNCED_AT))
    db.add(DocumentCache(notion_page_id="asst-doc-1", title="이번 주 문서",
                         document_type="회의록", owner="도우미 동료",
                         last_edited="2026-08-03T02:00:00.000Z", synced_at=SYNCED_AT))
    db.commit()


def _login(client, settings):
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    response = client.post("/login", json={"email": EMAIL, "password": DEFAULT_TEST_PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


@pytest.fixture()
def asst_client(client, db, settings, notion):
    _seed(db)
    return _login(client, settings)


# ── 문장 생성이 꺼진 기본 상태: 숫자만 나온다 ──────────────────────────────────

def _get(client, path) -> dict:
    response = client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


def test_briefing_gives_the_same_numbers_as_home_today(asst_client):
    briefing = _get(asst_client, "/api/assistant/briefing")
    home = _get(asst_client, "/api/home/today")
    assert briefing["kind"] == "briefing"
    # 브리핑이 홈과 다른 숫자를 말하면 사용자는 둘 중 하나를 거짓말로 받아들인다.
    assert briefing["tickets"] == home["tickets"]
    assert briefing["sprint"] == home["sprint"]
    assert briefing["narrative"] is None      # narrate 를 안 켰으면 블록 자체가 없다


def test_standup_splits_done_plan_blocked_without_any_llm(asst_client, fake_http):
    fake_http.requests.clear()
    body = _get(asst_client, "/api/assistant/standup")
    assert body["kind"] == "standup"
    assert body["author"]["display_name"] == "도우미 나"
    assert body["recently_done"]["count"] == 1             # 창 안 완료 1건
    assert {i["tid"] for i in body["today_plan"]["items"]} == {1, 2}  # 오늘 마감 + 지연
    assert body["blocked"]["count"] == 1
    assert fake_http.requests == []                        # 외부 호출 0회


def test_weekly_digest_reports_mine_team_and_changed_content(asst_client):
    body = _get(asst_client, "/api/assistant/weekly-digest")
    assert body["window"] == {"start": "2026-08-03", "end_exclusive": "2026-08-10"}
    assert body["mine"]["assigned"] == 3 and body["mine"]["done"] == 1
    # 팀 합계는 창 안 티켓 전체 = 내 3건 + 동료 2건. 미할당 3건은 마감이 창 밖이라 안 센다
    # (팀 합계는 티켓 단위 중복 없이 — 담당자별 합과 다른 게 정상이다).
    assert body["team"]["total"] == 5
    assert body["team"]["done"] == 1
    assert [c["name"] for c in body["top_contributors"]][:1] == ["도우미 나"]
    assert body["documents_changed"]["count"] == 1
    assert body["board"]["count"] == 1


def test_triage_suggests_order_and_candidates_but_assigns_nothing(asst_client, db):
    before = {
        row.notion_page_id: row.assignee_notion_ids
        for row in db.query(TicketCache).all()
    }
    body = _get(asst_client, "/api/assistant/triage")
    assert body["auto_assign"] is False
    assert body["total"] == 3
    # 지연 → 긴급 → 보통. 우선순위가 낮아도 지연이 맨 앞이다.
    assert [i["tid"] for i in body["items"]] == [9, 8, 7]
    assert body["items"][0]["overdue"] is True
    # 후보는 활성 담당이 적은 순 — 동료(2건)가 나(3건)보다 앞이다.
    assert [c["display_name"] for c in body["candidates"]][:2] == ["도우미 동료", "도우미 나"]
    assert body["candidates"][0]["active_tickets"] == 2
    db.expire_all()
    after = {
        row.notion_page_id: row.assignee_notion_ids
        for row in db.query(TicketCache).all()
    }
    assert after == before, "트리아지가 담당자를 건드렸다 — '제안만' 계약 위반"


def test_narrate_flag_off_by_default_never_calls_the_runner(asst_client, fake_http):
    fake_http.requests.clear()
    body = _get(asst_client, "/api/assistant/briefing?narrate=true")
    # 기능 플래그(assistant_narrative_enabled)가 기본 false 라 호출 자체가 나가지 않는다.
    assert body["narrative"]["enabled"] is False
    assert body["narrative"]["text"] is None
    assert fake_http.requests == []


def test_assistant_requires_authentication(client):
    for path in ("/briefing", "/standup", "/weekly-digest", "/triage"):
        assert client.get("/api/assistant" + path).status_code == 401


# ── 문장 생성을 켠 상태: 러너가 죽어도 숫자는 살아남는다 ───────────────────────

def _narrative_app(db_path, tmp_path, fake_clock, fake_http):
    """assistant_narrative_enabled=true 로 켠 별도 앱(+ 러너 토큰)."""
    from app.core.config import Settings
    from app.main import create_app

    cfg = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg)
    flags = json.loads((cfg / "feature-flags.json").read_text(encoding="utf-8"))
    flags["assistant_narrative_enabled"] = True
    (cfg / "feature-flags.json").write_text(json.dumps(flags), encoding="utf-8")
    secrets_dir = tmp_path / "secrets"
    secrets_dir.mkdir(exist_ok=True)
    (secrets_dir / "assistant_runner_token").write_text("test-runner-token", encoding="utf-8")
    (secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    settings = Settings(
        _env_file=None, app_env="test", database_url=f"sqlite:///{db_path.as_posix()}",
        session_secret="test-session-secret", cookie_secure=False,
        config_dir=cfg, secrets_dir=secrets_dir, data_dir=tmp_path,
    )
    app = create_app(settings, clock=fake_clock, outbound_transport=fake_http.transport())
    with app.state.session_factory() as session:
        _seed(session)
    return app, settings


@pytest.fixture()
def narrative_client(db_path, tmp_path, fake_clock, fake_http, notion):
    from fastapi.testclient import TestClient

    app, settings = _narrative_app(db_path, tmp_path, fake_clock, fake_http)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post("/login", json={"email": EMAIL, "password": DEFAULT_TEST_PASSWORD})
        assert response.status_code == 200, response.text
        test_client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield test_client, settings


def _facts_only(body: dict) -> dict:
    return {k: v for k, v in body.items() if k != "narrative"}


def test_narrative_is_added_when_the_runner_answers(narrative_client, fake_http):
    client, settings = narrative_client
    fake_http.on(settings.assistant_runner_url,
                 json_body={"data": {"text": "오늘 마감 1건, 지연 1건입니다."}})
    body = _get(client, "/api/assistant/briefing?narrate=true")
    assert body["narrative"]["enabled"] is True
    assert body["narrative"]["text"] == "오늘 마감 1건, 지연 1건입니다."
    assert body["narrative"]["error"] is None
    assert body["tickets"]["due_today"]["count"] == 1


@pytest.mark.parametrize("break_runner", ["timeout", "connect_error", "server_error", "empty"])
def test_numbers_survive_every_runner_failure_mode(narrative_client, fake_http, break_runner):
    """계획서 Phase 5: '러너가 죽어도 숫자는 그대로 보여야 한다(문장만 빠진다).'

    문장을 끄고 받은 응답과 러너가 죽은 채로 받은 응답의 **사실 부분이 바이트 동일**한지
    dict 비교로 직접 확인한다. 한 필드라도 사라지면 여기서 깨진다.
    """
    client, settings = narrative_client
    baseline = _facts_only(_get(client, "/api/assistant/briefing"))

    url = settings.assistant_runner_url
    if break_runner == "timeout":
        fake_http.on_timeout(url)
    elif break_runner == "connect_error":
        fake_http.on_connect_error(url)
    elif break_runner == "server_error":
        fake_http.on(url, status=503, json_body={"error": "runner down"})
    else:
        fake_http.on(url, json_body={"data": {}})       # 2xx 인데 문장이 없다

    body = _get(client, "/api/assistant/briefing?narrate=true")
    assert _facts_only(body) == baseline               # 숫자는 한 글자도 안 변했다
    assert body["narrative"]["enabled"] is True
    assert body["narrative"]["text"] is None
    assert body["narrative"]["error"]                  # 왜 문장이 없는지 화면이 말할 수 있다


def test_runner_output_is_not_trusted_verbatim(narrative_client, fake_http):
    """모델 출력 불신(§11): 제어문자는 버리고 길이는 자른다."""
    from app.assistant.narrate import MAX_TEXT_CHARS

    client, settings = narrative_client
    fake_http.on(settings.assistant_runner_url,
                 json_body={"text": "머리\x1b[31m글\x00자" + "가" * (MAX_TEXT_CHARS + 500)})
    text = _get(client, "/api/assistant/briefing?narrate=true")["narrative"]["text"]
    assert "\x1b" not in text and "\x00" not in text
    assert len(text) == MAX_TEXT_CHARS


def test_runner_receives_only_precomputed_facts(narrative_client, fake_http):
    """러너는 숫자를 다시 세지 않는다 — 우리가 계산한 사실만 넘어간다."""
    client, settings = narrative_client
    fake_http.on(settings.assistant_runner_url, json_body={"text": "요약"})
    _get(client, "/api/assistant/standup?narrate=true")
    sent = [r for r in fake_http.requests if str(r.url).startswith(settings.assistant_runner_url)]
    assert len(sent) == 1
    payload = json.loads(sent[0].content.decode("utf-8"))
    assert payload["kind"] == "standup"
    assert payload["locale"] == "ko-KR"
    assert payload["facts"]["blocked"]["count"] == 1
    # 원본 Notion 사용자 id 는 절대 나가지 않는다(§12.3).
    assert N_ME not in json.dumps(payload, ensure_ascii=False)


def test_narrate_is_rate_limited_per_user(narrative_client, fake_http):
    client, settings = narrative_client
    fake_http.on(settings.assistant_runner_url, json_body={"text": "요약"})
    statuses = [client.get("/api/assistant/briefing?narrate=true").status_code for _ in range(9)]
    assert 429 in statuses, "문장 생성에 레이트리밋이 걸려 있지 않다"
    # 문장을 끄면 리미터를 지나지 않으므로 계속 200 이다(숫자는 언제나 볼 수 있어야 한다).
    assert client.get("/api/assistant/briefing").status_code == 200
