"""GET /api/me/stats — 내 업무량·완료 통계의 계약을 고정한다.

세 가지를 증명한다:
  1. **티켓은 저장소 seam 으로만 읽는다.** 미러가 채워져 있으면 Notion 왕복 0회다
     (Notion 구현 모듈을 직접 import 하지 않는다는 규칙의 실행 시점 확인).
  2. **내 것만 센다.** 동료 티켓·미할당 티켓은 내 통계에 들어오지 않는다.
  3. **장애 격리.** 소스가 죽어도 200 이고 `source.configured/ok/mapped` 로 이유를 말한다 —
     화면 전체가 오류로 덮이지 않는다(§17.4).
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
    assert body["ok"] is True and body["source"]["mapped"] is True
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


def test_stats_report_mirror_freshness(stats_client):
    sync = _stats(stats_client)["sync"]
    assert sync["status"] == "ok" and sync["ticket_count"] == 8


def test_stats_survive_an_unmapped_account(client, db, settings, notion, make_user):
    """Notion 연결이 없으면 숫자를 지어내지 않고 `mapped: false` 로 말한다.

    PA-RC-0027: 이 테스트가 원래 `totals["all"] == 0` 을 단언했다 — 그게 정확히 이
    Root Cause다("모른다"를 "0건"으로 지어내면 이 테스트가 그것을 green 으로 고정한다).
    이제는 `totals`/`workload`/`months` 자체가 응답에 없다 — 화면이 숫자 대신 "모른다"를
    그릴 수 있게, 있는 척(0)을 하지 않는다.
    """
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    make_user("nomap@goodmit.co.kr")
    assert client.post(
        "/login", json={"email": "nomap@goodmit.co.kr", "password": "Str0ng-Passw0rd!"}
    ).status_code == 200
    body = _stats(client)
    assert body["source"]["mapped"] is False
    assert "totals" not in body
    assert "workload" not in body
    assert "months" not in body


def test_stats_survive_a_dead_source(client, db, notion):
    """소스가 안 잡혀 있으면 503 이 아니라 200 + `configured: false` 다 — 화면을 오류로 덮지 않는다.

    이 경로를 타려면 **연결됐고(mapped) 미러도 비어 있어야** 한다. 미매핑 계정은 소스를
    부르기 전에 멈추고(`mapped: false`), 미러가 차 있으면 토큰 없이도 답이 나온다
    (그게 캐시의 존재 이유다) — 그래서 여기서는 사용자·매핑만 심고 티켓 미러는 비워 둔다.

    PA-RC-0027: `configured: false`도 `ok: false`(소스를 못 읽었다)를 동반하므로
    `usable = ok and mapped`에 걸려 totals 등이 마찬가지로 빠진다 — 위 미매핑 테스트와
    같은 원칙("소스 장애면 버킷 자체가 없다")의 다른 발생 지점이다.
    """
    _seed_users(db)  # 토큰 파일도 티켓 미러도 일부러 만들지 않는다
    assert client.post("/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    body = _stats(client)
    assert body["ok"] is True, "요청 자체는 성공이다"
    assert body["source"]["configured"] is False
    assert "totals" not in body
    assert "workload" not in body
    assert "months" not in body


def test_stats_totals_are_real_zero_when_mapped_with_no_tickets(client, db, settings, notion, make_user):
    """PA-RC-0027 acceptance (과잉 수정 방지): 매핑은 됐고 실제로 티켓이 0건인 사용자는
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
    assert body["source"]["mapped"] is True
    assert body["totals"]["all"] == 0


def test_stats_require_login(app):
    from fastapi.testclient import TestClient

    anonymous = TestClient(app, raise_server_exceptions=False)
    assert anonymous.get("/api/me/stats").status_code == 401
