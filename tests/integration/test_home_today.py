"""GET /api/home/today — 홈 '오늘' 커맨드 센터의 계약을 고정한다.

세 가지를 증명한다:
  1. **Notion 왕복 0회.** 미러가 채워져 있으면 이 엔드포인트는 로컬 SELECT 만으로 답한다.
     페이크 Notion 이 기록한 요청 수가 0 이어야 한다(계획서: "이 조합은 Notion 왕복 0회로 나가야").
  2. **숫자가 맞다.** 오늘 마감 / 지연 / 진행 중 / 곧 마감 + 스프린트 내 몫 + 안 읽은 알림·채팅
     + 최근 문서·게시판.
  3. **장애 격리.** 티켓 소스가 죽어도 200 이고, 알림·문서·게시판 블록은 그대로 나온다.
"""

from __future__ import annotations

from datetime import datetime

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
from tests.fakes.clock import FakeClock
from tests.fakes.notion import FakeNotionTasksDB

import pytest

# 2026-08-03 은 월요일 — 스프린트 창이 [08-03, 08-10) 이 된다.
# 시각은 KST 로 09:00(=UTC 00:00) 을 넘겨, '오늘'이 UTC 로 계산되면 하루 밀리는 상황을 만든다.
NOW = datetime(2026, 8, 3, 1, 0, 0)      # UTC → KST 2026-08-03 10:00
TODAY = "2026-08-03"
SYNCED_AT = datetime(2026, 8, 3, 0, 57, 0)
PASSWORD = "Home-Passw0rd!"
TOKEN_REF = "notion_report_token"

U_ME = "00000000-0000-4000-8000-0000000h0001"
U_MATE = "00000000-0000-4000-8000-0000000h0002"
N_ME = "notion-user-home-me"
N_MATE = "notion-user-home-mate"
EMAIL = "home-me@goodmit.co.kr"


@pytest.fixture()
def fake_clock():
    return FakeClock(NOW)


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    """행을 하나도 주지 않는다 — 실수로 실시간 경로를 타면 숫자가 0 이 되어 바로 드러난다."""
    return FakeNotionTasksDB(rows=[]).install(fake_http)


def _cache(uid, page, *, tid, title, status, due, people, est=None, priority=None):
    return TicketCache(
        id=uid, notion_page_id=page, notion_ticket_number=tid,
        url=f"https://www.notion.so/{page}", title=title, status=status,
        due_date=due, est_wd=est, priority=priority,
        project_ids="", project_names=join_names(["홈 프로젝트"]),
        assignee_notion_ids=join_names(people),
        synced_at=SYNCED_AT, created_at=SYNCED_AT, updated_at=SYNCED_AT,
    )


def _seed(db) -> None:
    db.add(User(id=U_ME, email=EMAIL, display_name="홈 나", role="user", active=True,
                password_hash=hash_password(PASSWORD), must_change_password=False))
    db.add(User(id=U_MATE, email="home-mate@goodmit.co.kr", display_name="홈 동료",
                role="user", active=True, password_hash=hash_password(PASSWORD),
                must_change_password=False))
    db.flush()
    for uid, nid, email in ((U_ME, N_ME, EMAIL), (U_MATE, N_MATE, "home-mate@goodmit.co.kr")):
        db.add(UserNotionMapping(user_id=uid, notion_user_id=nid, notion_email=email,
                                 status=STATUS_VERIFIED, source=SOURCE_MANUAL,
                                 last_verified_at=SYNCED_AT))
    db.add_all([
        _cache("h-uid-1", "h-1", tid=1, title="오늘 마감", status="진행",
               due=TODAY, people=[N_ME], est=1.0),
        _cache("h-uid-2", "h-2", tid=2, title="지연", status="진행",
               due="2026-07-30", people=[N_ME], est=2.0),
        _cache("h-uid-3", "h-3", tid=3, title="곧 마감", status="이슈",
               due="2026-08-06", people=[N_ME], est=0.5),
        _cache("h-uid-4", "h-4", tid=4, title="이번 주 완료", status="완료",
               due="2026-08-04", people=[N_ME], est=1.5),
        _cache("h-uid-5", "h-5", tid=5, title="먼 훗날", status="계획",
               due="2026-12-01", people=[N_ME]),
        _cache("h-uid-6", "h-6", tid=6, title="동료 것", status="진행",
               due=TODAY, people=[N_MATE]),
        _cache("h-uid-7", "h-7", tid=7, title="미할당", status="진행",
               due="2026-08-05", people=[], priority="긴급"),
    ])
    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status = SYNC_OK
    state.last_run_at = SYNCED_AT
    state.last_success_at = SYNCED_AT
    state.ticket_count = 7
    state.truncated = False
    state.error = None
    state.updated_at = SYNCED_AT
    db.add(state)

    db.add_all([
        Notification(user_id=U_ME, type="ticket_assigned", title="안 읽은 알림 1", created_at=SYNCED_AT),
        Notification(user_id=U_ME, type="ticket_assigned", title="안 읽은 알림 2", created_at=SYNCED_AT),
        Notification(user_id=U_ME, type="ticket_assigned", title="읽은 알림",
                     created_at=SYNCED_AT, read_at=SYNCED_AT),
        Notification(user_id=U_MATE, type="ticket_assigned", title="남의 알림", created_at=SYNCED_AT),
    ])
    db.add(Post(id="home-post-1", author_user_id=U_MATE, category="자유", title="최근 글",
                body="본문", created_at=SYNCED_AT, updated_at=SYNCED_AT))
    db.add(DocumentCache(notion_page_id="home-doc-1", title="최근 문서",
                         document_type="회의록", owner="홈 동료",
                         last_edited="2026-08-02T10:00:00.000Z", synced_at=SYNCED_AT))
    db.commit()


@pytest.fixture()
def home_client(client, db, settings, notion):
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    _seed(db)
    response = client.post("/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def _today(client) -> dict:
    response = client.get("/api/home/today")
    assert response.status_code == 200, response.text
    return response.json()


def test_today_answers_without_a_single_notion_round_trip(home_client, fake_http, notion):
    """계획서: '이 조합은 Notion 왕복 0회로 나가야 한다.'"""
    fake_http.requests.clear()
    body = _today(home_client)
    assert body["ok"] is True
    notion_calls = [r for r in fake_http.requests if str(r.url).startswith("https://api.notion.com")]
    assert notion_calls == [], f"Notion 을 {len(notion_calls)}회 불렀다"
    assert notion.queries == []


def test_today_buckets_my_tickets_by_kst_calendar_day(home_client):
    body = _today(home_client)
    assert body["today"] == TODAY            # UTC 로 계산했다면 2026-08-03 이 아니다
    t = body["tickets"]
    assert t["configured"] is True and t["ok"] is True and t["mapped"] is True
    assert t["due_today"]["count"] == 1
    assert t["overdue"]["count"] == 1
    assert t["due_soon"]["count"] == 1
    assert t["blocked"]["count"] == 1
    assert t["in_progress"]["count"] == 4    # 완료 1건 제외, 동료·미할당 제외
    assert t["done_total"] == 1
    assert [i["tid"] for i in t["due_today"]["items"]] == [1]


def test_today_reports_my_share_of_this_sprint(home_client):
    sprint = _today(home_client)["sprint"]
    assert sprint["window"] == {"start": "2026-08-03", "end_exclusive": "2026-08-10"}
    # 창 안(08-03~08-09) 내 티켓: 오늘 마감·곧 마감·이번 주 완료 = 3건, 그중 완료 1건.
    assert sprint["assigned"] == 3
    assert sprint["done"] == 1
    assert sprint["remaining"] == 2
    assert sprint["completion_rate"] == 33
    assert sprint["est_wd_total"] == 3.0
    assert sprint["est_wd_done"] == 1.5


def test_today_carries_unread_counts_and_recent_activity(home_client):
    body = _today(home_client)
    assert body["inbox"]["notifications_unread"] == 2       # 읽은 것·남의 것 제외
    assert isinstance(body["inbox"]["chat_unread"], int)    # 채팅 켜져 있음 → 숫자
    assert [d["title"] for d in body["recent"]["documents"]] == ["최근 문서"]
    assert [p["title"] for p in body["recent"]["board"]] == ["최근 글"]


def test_today_includes_mirror_freshness(home_client):
    sync = _today(home_client)["sync"]
    assert sync["status"] == "ok" and sync["ticket_count"] == 7 and sync["truncated"] is False


def test_today_survives_a_dead_ticket_source(home_client, notion, db):
    """티켓 미러를 비우고 Notion 도 죽이면 — 티켓 블록만 실패하고 화면은 계속 뜬다."""
    db.query(TicketCache).delete()
    db.commit()
    notion.fail_status = 502
    body = _today(home_client)
    assert body["ok"] is True
    assert body["tickets"]["ok"] is False and body["tickets"]["error"]
    assert body["sprint"] is None                     # 0건이 아니라 '모른다'
    assert body["inbox"]["notifications_unread"] == 2  # 나머지는 그대로
    assert [p["title"] for p in body["recent"]["board"]] == ["최근 글"]


def test_today_requires_authentication(client):
    assert client.get("/api/home/today").status_code == 401
