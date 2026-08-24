"""GET /api/home/today — 홈 '오늘' 커맨드 센터의 계약을 고정한다.

세 가지를 증명한다:
  1. **Notion 왕복 0회.** 미러가 채워져 있으면 이 엔드포인트는 로컬 SELECT 만으로 답한다.
     페이크 Notion 이 기록한 요청 수가 0 이어야 한다(계획서: "이 조합은 Notion 왕복 0회로 나가야").
  2. **숫자가 맞다.** 오늘 마감 / 지연 / 진행 중 / 곧 마감 + 스프린트 내 몫 + 안 읽은 알림·채팅
     + 최근 문서·게시판.
  3. **장애 격리.** 티켓 소스가 죽어도 200 이고, 알림·문서·게시판 블록은 그대로 나온다.

S14 가 미러를 걷어내면서 두 가지가 뒤집혔다(D-284). 신선도(`sync`) 블록은 **없어야**
하는 것이 되었고 — 낡을 사본이 없는데 그 배지를 그리면 영원히 늙는 시각이 화면에 남는다 —
「티켓만 못 읽는」 상황은 표를 비워서는 못 만들게 되어 읽는 자리를 직접 실패시킨다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.board.models import Post
from app.knowledge import blocks
from app.knowledge.models import Document, DocumentVersion, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.core.security import hash_password
from app.notifications.models import Notification
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
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
    # 소속(0060) — 조직 직속. 이 파일은 홈 집계를 보는 곳이라 소속 게이트에 걸리면
    # 정작 검사하려던 것을 못 본다(미지정 계정은 조직 데이터를 아무것도 못 본다).
    db.add(User(id=U_ME, email=EMAIL, display_name="홈 나", role="user", active=True,
                membership_kind="organization",
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
    # 문서의 정본은 `documents` 이고 소속은 **공간**이 든다 (S14 · D-245). 이 파일은 홈
    # 집계를 보므로 조직 공통 공간 하나에 문서 하나만 둔다.
    #
    # `legacy_page_id` 를 채우는 이유: 휴지통은 아직 옛 page id 로 담기고, 아래
    # 「휴지통 문서는 최근 문서에서 빠진다」 시험이 그 경로를 그대로 지난다.
    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="홈 공간", slug="home-space",
        owner_kind="organization",
    )
    db.add(space)
    db.flush()
    document = Document(
        space_id=space.id, title="최근 문서", doc_type="회의록",
        legacy_page_id="home-doc-1", created_by=U_MATE,
    )
    db.add(document)
    db.flush()
    derived = blocks.derive(blocks.from_plain_text("홈 문서 본문"))
    version = DocumentVersion(
        id=str(uuid.uuid4()), document_id=document.id, version_no=1,
        body=derived.body, body_markdown=derived.markdown, body_text=derived.text,
        author_id=U_MATE,
    )
    db.add(version)
    db.flush()
    document.current_version_id = version.id
    document.updated_at = SYNCED_AT
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
    assert t["configured"] is True and t["ok"] is True
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


def test_today_excludes_a_trashed_document_from_recent(home_client, db, fake_clock):
    """휴지통 문서는 '최근 문서'에서도 빠져야 한다 — 목록(GET /api/team-docs)은 이미
    trashed_page_ids 로 거르는데, 이 위젯(app/home/readers.py::recent_documents)은
    archived 만 보고 있었다. 지운 문서로 이어지는 링크가 홈에 남는 이유였다."""
    from app.trash.models import TRASH_DOCUMENT
    from app.trash.service import move_to_trash
    from app.users.service import get_user_by_email

    who = get_user_by_email(db, EMAIL)
    # 휴지통은 옛 page id 로 담는다. 정본 문서는 그 값을 `legacy_page_id` 에 들고 있어
    # 위젯이 둘을 맞춰 본다.
    move_to_trash(db, item_type=TRASH_DOCUMENT, notion_page_id="home-doc-1",
                  title="최근 문서", url=None, user=who, now=fake_clock.now())
    db.commit()

    body = _today(home_client)
    assert body["recent"]["documents"] == [], (
        f"휴지통 문서가 홈 '최근 문서'에 남아 있다: {body['recent']['documents']}"
    )


def test_today_no_longer_draws_a_freshness_badge(home_client):
    """🔴 **반대 방향의 단언이다** (S14). 응답에 `sync` 가 **없어야** 한다.

    예전에는 여기서 「지금 보는 값이 얼마나 낡았나」를 실어 화면이 「N분 전 동기화됨」을
    그렸다. 낡을 사본이 없어진 지금 그 배지를 그대로 두면 **영원히 늙는 시각**이 화면에
    남는다 — 그리고 그것은 오류가 아니라 그냥 오래된 숫자로 보인다.

    `app/tickets/repository_native.py::sync_state` 가 언제나 `None` 을 돌려주는 이유가
    정확히 이것이고, 이 단언이 그 결정을 계약으로 붙든다.
    """
    body = _today(home_client)
    assert "sync" not in body, f"신선도 블록이 돌아왔다: {body.get('sync')!r}"
    assert body["ok"] is True, "블록 하나를 뺐다고 화면이 안 뜨면 안 된다"
    assert "tickets" in body, "이 응답이 티켓을 아예 안 실으면 위 단언이 공짜다"


def test_today_folds_a_ticket_read_failure_into_its_block(home_client, monkeypatch):
    """티켓을 못 읽어도 화면은 계속 뜨고, **0 이 아니라 «모른다»** 로 그린다.

    지금 이 예외를 올리는 코드는 없다(S14 가 Notion 경로를 걷었다). 그래도 잡는 쪽은
    남아 있다 — 다섯 모듈이 그것으로 `ok=false` 응답 모양을 만들고 프런트가 그 모양을
    읽는다(D-284 가 「화면과 함께 움직여야 하는 API 계약」이라고 적어 둔 자리다). 그
    모양이 살아 있는 동안은 **실제로 접히는지**를 확인해 둔다. 접기가 깨지면 티켓 블록
    하나 때문에 홈 전체가 500 이 된다.
    """
    from app.core.errors import NotionQueryError
    from app.home import service as home_service

    def boom(*args, **kwargs):
        raise NotionQueryError("티켓을 읽지 못했습니다.")

    monkeypatch.setattr(home_service.tickets_service, "list_my_tickets", boom)

    body = _today(home_client)
    assert body["ok"] is True, "티켓 블록 하나가 화면 전체를 죽였다"
    assert body["tickets"]["ok"] is False and body["tickets"]["error"]
    assert body["sprint"] is None                     # 0건이 아니라 '모른다'
    for bucket in ("due_today", "overdue", "in_progress"):
        assert bucket not in body["tickets"], f"{bucket} 가 0 으로 그려졌다 — 「모른다」여야 한다"
    assert body["inbox"]["notifications_unread"] == 2  # 나머지는 그대로
    assert [p["title"] for p in body["recent"]["board"]] == ["최근 글"]


def test_today_answers_for_an_account_with_no_legacy_link(client, db, settings, notion, make_user):
    """옛 소스와 짝이 없는 계정도 **자기 버킷을 받는다** (S15 · D-285).

    예전에는 이 자리가 「매핑이 없으면 버킷을 아예 안 싣는다」였다(PA-RC-0027). 그때는
    담당자를 가리키는 값이 옛 소스의 user id 뿐이라 「이 사람 티켓이 무엇인지 모른다」가
    실제 상태였기 때문이다. 지금은 사람마다 가리킬 값이 언제나 있으므로(`assignee_token`)
    그 상태가 없다 — 0건은 「모른다」가 아니라 **사실**이고, 그때는 진짜 0을 그린다.

    「모른다」로 남는 갈래는 저장소가 실제로 실패했을 때 하나뿐이고, 그건 바로 위 시험이
    본다. 두 상태를 구별하는 것이 이 두 시험의 존재 이유다.
    """
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    make_user("home-nomap@goodmit.co.kr", password=PASSWORD)
    r = client.post("/login", json={"email": "home-nomap@goodmit.co.kr", "password": PASSWORD})
    assert r.status_code == 200
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]

    body = _today(client)
    assert body["ok"] is True
    assert body["tickets"]["ok"] is True
    for bucket in ("due_today", "overdue", "in_progress", "due_soon", "blocked"):
        assert bucket in body["tickets"], f"{bucket}가 없다 — 이 계정은 답을 못 받고 있다"
        assert body["tickets"][bucket]["count"] == 0
    # 장애 격리 — 티켓과 무관한 블록은 그대로 나온다.
    assert "inbox" in body and "recent" in body


def test_today_mapped_with_zero_tickets_still_shows_real_zero(home_client, db):
    """과잉 수정 방지 — 매핑은 됐고 실제로 담당 티켓이 0건이면 버킷은 여전히 진짜 0이다."""
    db.query(TicketCache).delete()
    db.commit()
    body = _today(home_client)
    assert body["tickets"]["ok"] is True
    assert body["tickets"]["due_today"]["count"] == 0
    assert body["tickets"]["in_progress"]["count"] == 0


def test_today_requires_authentication(client):
    assert client.get("/api/home/today").status_code == 401
