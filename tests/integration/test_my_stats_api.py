"""GET /api/me/stats — 내 업무량·완료 통계의 계약을 고정한다.

세 가지를 증명한다:
  1. **티켓은 저장소 seam 으로만 읽는다.** 미러가 채워져 있으면 Notion 왕복 0회다
     (Notion 구현 모듈을 직접 import 하지 않는다는 규칙의 실행 시점 확인).
  2. **내 것만 센다.** 동료 티켓·미할당 티켓은 내 통계에 들어오지 않는다.
  3. **장애 격리.** 티켓을 못 읽어도 200 이고 `source.configured/ok` 로 이유를 말한다 —
     화면 전체가 오류로 덮이지 않는다(§17.4).

S14 가 미러를 걷어내면서 두 가지가 뒤집혔다(D-284). 신선도(`sync`) 블록은 **없어야**
하는 것이 되었고, 「소스가 설정되지 않았다」는 상태는 사라졌다 — 자체 DB 는 앱이 이미 붙어
있는 곳이라 사람이 채워 넣을 접속 설정이 없다. 남은 장애 격리는 읽는 자리를 직접
실패시켜 확인한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.security import hash_password
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

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 3, 1, 0, 0)   # UTC → KST 2026-08-03(월) 10:00
TODAY = "2026-08-03"
SYNCED_AT = datetime(2026, 8, 3, 0, 57, 0)
PASSWORD = "Stats-Passw0rd!"
TOKEN_REF = "notion_report_token"

U_ME = "00000000-0000-4000-8000-0000000s0001"
U_MATE = "00000000-0000-4000-8000-0000000s0002"
N_ME = "notion-user-stats-me"
N_MATE = "notion-user-stats-mate"
EMAIL = "stats-me@goodmit.co.kr"


@pytest.fixture()
def fake_clock():
    return FakeClock(NOW)


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    """행을 하나도 주지 않는다 — 실시간 경로를 타면 숫자가 0 이 되어 즉시 드러난다."""
    return FakeNotionTasksDB(rows=[]).install(fake_http)


def _cache(uid, page, *, tid, title, status, due, people, est=None, act=None, priority=None):
    return TicketCache(
        id=uid, notion_page_id=page, notion_ticket_number=tid,
        url=f"https://www.notion.so/{page}", title=title, status=status,
        due_date=due, est_wd=est, act_wd=act, priority=priority,
        project_ids="", project_names=join_names(["통계 프로젝트"]),
        assignee_notion_ids=join_names(people),
        synced_at=SYNCED_AT, created_at=SYNCED_AT, updated_at=SYNCED_AT,
    )


def _seed_users(db) -> None:
    db.add(User(id=U_ME, email=EMAIL, display_name="통계 나", role="user", active=True,
                password_hash=hash_password(PASSWORD), must_change_password=False))
    db.add(User(id=U_MATE, email="stats-mate@goodmit.co.kr", display_name="통계 동료",
                role="user", active=True, password_hash=hash_password(PASSWORD),
                must_change_password=False))
    db.flush()
    for uid, nid, email in ((U_ME, N_ME, EMAIL), (U_MATE, N_MATE, "stats-mate@goodmit.co.kr")):
        db.add(UserNotionMapping(user_id=uid, notion_user_id=nid, notion_email=email,
                                 status=STATUS_VERIFIED, source=SOURCE_MANUAL,
                                 last_verified_at=SYNCED_AT))
    db.commit()


def _seed(db) -> None:
    _seed_users(db)
    db.add_all([
        _cache("s-1", "sp-1", tid=1, title="오늘 마감", status="진행",
               due=TODAY, people=[N_ME], est=1.0, priority="높음"),
        _cache("s-2", "sp-2", tid=2, title="지연", status="진행",
               due="2026-07-30", people=[N_ME], est=2.0, priority="긴급"),
        _cache("s-3", "sp-3", tid=3, title="다음 주", status="계획",
               due="2026-08-12", people=[N_ME], est=3.0),
        _cache("s-4", "sp-4", tid=4, title="7월 완료", status="완료",
               due="2026-07-15", people=[N_ME], est=1.5, act=2.0),
        _cache("s-5", "sp-5", tid=5, title="7월 취소", status="취소",
               due="2026-07-20", people=[N_ME], est=1.0),
        _cache("s-6", "sp-6", tid=6, title="마감 없음", status="진행",
               due=None, people=[N_ME], est=0.5),
        # 내 것이 아닌 것들 — 통계에 들어오면 안 된다.
        _cache("s-7", "sp-7", tid=7, title="동료 것", status="진행",
               due=TODAY, people=[N_MATE], est=9.0),
        _cache("s-8", "sp-8", tid=8, title="미할당", status="진행",
               due=TODAY, people=[], est=9.0),
    ])
    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status = SYNC_OK
    state.last_run_at = SYNCED_AT
    state.last_success_at = SYNCED_AT
    state.ticket_count = 8
    state.truncated = False
    state.error = None
    state.updated_at = SYNCED_AT
    db.add(state)
    db.commit()


@pytest.fixture()
def stats_client(client, db, settings, notion):
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    _seed(db)
    response = client.post("/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def _stats(test_client, query: str = "") -> dict:
    response = test_client.get("/api/me/stats" + query)
    assert response.status_code == 200, response.text
    return response.json()


def test_stats_answer_without_a_single_notion_round_trip(stats_client, fake_http, notion):
    fake_http.requests.clear()
    body = _stats(stats_client)
    assert body["ok"] is True and body["source"]["ok"] is True
    notion_calls = [
        r for r in fake_http.requests if str(r.url).startswith("https://api.notion.com")
    ]
    assert notion_calls == [], f"Notion 을 {len(notion_calls)}회 불렀다"
    assert notion.queries == []


def test_totals_count_only_my_tickets(stats_client):
    totals = _stats(stats_client)["totals"]
    assert totals["all"] == 6            # 동료 것·미할당 제외
    assert totals["active"] == 4
    assert totals["done"] == 1 and totals["cancelled"] == 1
    assert totals["due_today"] == 1
    assert totals["overdue"] == 1
    assert totals["no_due"] == 1


def test_today_is_the_seoul_calendar_day(stats_client):
    # UTC 로 계산했다면 이 시각(01:00 UTC)은 여전히 08-03 이지만, 09:00 이전 시각을
    # 쓰는 다른 테스트와 함께 이 필드가 KST 기준임을 계약으로 남긴다.
    assert _stats(stats_client)["today"] == TODAY


def test_monthly_completion_uses_due_dates_and_drops_cancelled_from_the_denominator(stats_client):
    months = {m["month"]: m for m in _stats(stats_client, "?months=3")["months"]}
    july = months["2026-07"]
    assert july["assigned"] == 3 and july["done"] == 1 and july["cancelled"] == 1
    assert july["completion_rate"] == 0.5     # 1 / (3 - 1)
    assert july["act_wd"] == 2.0


def test_weekly_load_shows_where_the_remaining_work_sits(stats_client):
    load = _stats(stats_client, "?weeks=3")["workload"]
    by_label = {b["label"]: b for b in load["by_week"]}
    # 이번 주 = [08-03, 08-10), 다음 주 = [08-10, 08-17) — 08-12 는 다음 주다.
    assert by_label["이번 주"]["count"] == 1 and by_label["이번 주"]["est_wd"] == 1.0
    assert by_label["다음 주"]["count"] == 1 and by_label["다음 주"]["est_wd"] == 3.0
    assert by_label["2주 뒤"]["count"] == 0
    extra = load["by_week_extra"]
    assert extra["overdue"]["count"] == 1
    assert extra["no_due"]["count"] == 1


def test_stats_no_longer_report_mirror_freshness(stats_client):
    """🔴 **반대 방향의 단언이다** (S14). 응답에 `sync` 가 **없어야** 한다.

    신선도는 사본이 있을 때만 뜻이 있는 말이다. 사본이 없어진 뒤로도 그 블록을 실으면
    화면에 **영원히 늙는 시각**이 남고, 그것은 오류가 아니라 그냥 오래된 숫자로 보인다.
    """
    body = _stats(stats_client)
    assert "sync" not in body, f"신선도 블록이 돌아왔다: {body.get('sync')!r}"
    assert body["ok"] is True and "totals" in body, (
        "이 응답이 아무것도 안 실으면 위 단언이 공짜다"
    )


def test_stats_answer_for_an_account_with_no_legacy_link(client, db, settings, notion, make_user):
    """옛 소스와 짝이 없는 계정도 **진짜 숫자를 받는다** (S15 · D-285).

    예전에는 이 자리가 「매핑이 없으면 `totals` 자체를 안 싣는다」였다(PA-RC-0027).
    그때는 그 사람의 티켓이 무엇인지 정말 몰랐기 때문이다. 지금은 사람마다 담당자로
    가리킬 값이 언제나 있으므로 그 상태가 없다 — 0건은 「모른다」가 아니라 사실이고,
    사실을 「모른다」로 그리면 새 계정의 통계 화면이 영원히 비어 있다.

    「모른다」로 남는 갈래는 **티켓을 못 읽었을 때** 하나뿐이고, 그건 아래 시험이 본다.
    """
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    make_user("nomap@goodmit.co.kr")
    assert client.post(
        "/login", json={"email": "nomap@goodmit.co.kr", "password": "Str0ng-Passw0rd!"}
    ).status_code == 200
    body = _stats(client)
    assert body["source"]["ok"] is True
    assert body["totals"]["all"] == 0
    assert "workload" in body and "months" in body


def test_stats_fold_a_read_failure_instead_of_erroring_the_screen(client, db, monkeypatch):
    """티켓을 못 읽으면 503 이 아니라 200 + `ok: false` 다 — 화면을 오류로 덮지 않는다.

    지금 이 예외를 올리는 코드는 없다(S14 가 Notion 경로를 걷었다). 그래도 잡는 쪽은
    남아 있고 프런트가 그 응답 모양을 읽는다 — D-284 가 「화면과 함께 움직여야 하는 API
    계약」이라고 적어 둔 자리다. 그 모양이 살아 있는 동안은 **실제로 접히는지**를 확인해
    둔다. 접기가 깨지면 통계 화면 하나가 500 으로 덮인다.

    PA-RC-0027: 티켓을 못 읽으면 `usable = ok` 에 걸려 `totals` 등이 통째로 빠진다 —
    「모른다」와 「0건이다」를 가르는 자리가 이제 여기 하나뿐이다.
    """
    from app.core.errors import NotionQueryError
    from app.home import service as home_service

    _seed_users(db)
    assert client.post("/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200

    def boom(*args, **kwargs):
        raise NotionQueryError("티켓을 읽지 못했습니다.")

    monkeypatch.setattr(home_service.tickets_service, "list_my_tickets", boom)

    body = _stats(client)
    assert body["ok"] is True, "요청 자체는 성공이다 — 화면을 오류로 덮지 않는다"
    assert body["source"]["ok"] is False
    assert "totals" not in body
    assert "workload" not in body
    assert "months" not in body


def test_stats_totals_are_real_zero_when_mapped_with_no_tickets(client, db, settings, notion, make_user):
    """PA-RC-0027 acceptance (과잉 수정 방지): 옛 짝이 있고 실제로 티켓이 0건인 사용자는
    여전히 진짜 0을 본다 — "모른다"만 감추지 "0건이다"까지 감추면 반대 방향의 거짓말이 된다."""
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    user = make_user("mapped-empty@goodmit.co.kr")
    db.add(UserNotionMapping(
        user_id=user.id, notion_user_id="person-empty", notion_email=user.email,
        source=SOURCE_MANUAL, status=STATUS_VERIFIED, last_verified_at=datetime(2026, 1, 1),
    ))
    # get-or-create — 이 파일의 `_seed()`와 같은 이유(SYNC_STATE_ID가 싱글턴 PK라 다른
    # 테스트가 이미 만들어 둔 행이 있을 수 있다).
    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status = SYNC_OK
    state.last_success_at = datetime(2026, 1, 1)
    db.add(state)
    db.commit()
    assert client.post(
        "/login", json={"email": "mapped-empty@goodmit.co.kr", "password": "Str0ng-Passw0rd!"}
    ).status_code == 200
    body = _stats(client)
    assert body["source"]["ok"] is True
    assert body["totals"]["all"] == 0


def test_stats_require_login(app):
    from fastapi.testclient import TestClient

    anonymous = TestClient(app, raise_server_exceptions=False)
    assert anonymous.get("/api/me/stats").status_code == 401
