"""티켓 로컬 미러의 두 가지 약속을 고정한다.

1. **write-through** — 티켓을 만들거나 고친 사람이 목록에서 그걸 바로 봐야 한다. 동기화 주기가
   기본 180초라, 쓰기 뒤에 캐시를 같은 요청에서 고치지 않으면 "방금 만든 티켓이 없어졌다"가 된다.
   그래서 여기서는 **동기화 tick 을 한 번도 돌리지 않고** 생성 → 즉시 조회를 확인한다.

2. **장애 격리** — 미러가 차 있으면 소스가 5xx 를 뱉든 말든 목록은 200 으로 뜬다. 그리고 그 응답에
   신선도(`sync`)가 실려 "지금 보는 건 마지막 정상 데이터"라는 사실이 화면에 드러난다. 500 은 금지.
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
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.regression

NOW = datetime(2026, 8, 3, 9, 0, 0)
SYNCED_AT = datetime(2026, 8, 3, 8, 57, 0)
PASSWORD = "Cache-Passw0rd!"
TOKEN_REF = "notion_report_token"

U_ME = "00000000-0000-4000-8000-0000000c0001"
N_ME = "notion-user-me"
P_ALPHA = "cache-proj-alpha"

# 미러에 이미 들어 있는(= 워커가 아까 넣어 둔) 티켓 한 건.
CACHED_PAGE_ID = "cache-0001"


@pytest.fixture()
def fake_clock():
    return FakeClock(NOW)


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[task_row(page_id=CACHED_PAGE_ID, tid=1, title="이미 있던 티켓", status="진행",
                       due="2026-08-04", people=[N_ME], project_ids=[P_ALPHA])],
        projects=[project_row(page_id=P_ALPHA, name="알파 프로젝트")],
        projects_db=DEFAULT_PROJECTS_DB,
        fail_message="캐시 테스트용 강제 오류",
    ).install(fake_http)


def _seed_user(db) -> None:
    db.add(User(id=U_ME, email="cache-me@goodmit.co.kr", display_name="캐시 나",
                role="user", active=True, password_hash=hash_password(PASSWORD),
                must_change_password=False))
    db.flush()
    db.add(UserNotionMapping(id="00000000-0000-4000-8000-0000000c0101", user_id=U_ME,
                             notion_user_id=N_ME, notion_email="cache-me@goodmit.co.kr",
                             status=STATUS_VERIFIED, source=SOURCE_MANUAL,
                             last_verified_at=SYNCED_AT))
    db.commit()


def _seed_mirror(db) -> None:
    """워커가 한 번 정상 동기화한 상태를 만든다(tick 은 이 테스트에서 한 번도 돌지 않는다)."""
    db.add(TicketCache(
        id="cache-uid-0001", notion_page_id=CACHED_PAGE_ID,
        notion_ticket_number=1, url=f"https://www.notion.so/{CACHED_PAGE_ID}",
        title="이미 있던 티켓", status="진행", due_date="2026-08-04",
        project_ids=join_names([P_ALPHA]), project_names=join_names(["알파 프로젝트"]),
        assignee_notion_ids=join_names([N_ME]),
        synced_at=SYNCED_AT, created_at=SYNCED_AT, updated_at=SYNCED_AT,
    ))
    state = db.get(TicketSyncState, SYNC_STATE_ID)
    if state is None:
        state = TicketSyncState(id=SYNC_STATE_ID)
        db.add(state)
    state.status = SYNC_OK
    state.last_run_at = SYNCED_AT
    state.last_success_at = SYNCED_AT
    state.ticket_count = 1
    state.truncated = False
    state.error = None
    state.updated_at = SYNCED_AT
    db.commit()


@pytest.fixture()
def cache_client(client, db, settings, notion):
    (settings.secrets_dir / TOKEN_REF).write_text("fake-notion-token", encoding="utf-8")
    _seed_user(db)
    _seed_mirror(db)
    response = client.post("/login", json={"email": "cache-me@goodmit.co.kr", "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def _mine(client) -> dict:
    response = client.get("/api/tickets/mine")
    assert response.status_code == 200, response.text
    return response.json()


def test_list_is_served_from_the_mirror_with_a_freshness_block(cache_client):
    body = _mine(cache_client)
    assert body["ok"] is True
    assert [t["tid"] for t in body["tickets"]] == [1]
    # 미러에서 답했으므로 자체 id 가 실린다(실시간 폴백이면 uid 는 null 이다).
    assert body["tickets"][0]["uid"] == "cache-uid-0001"
    assert body["tickets"][0]["id"] == CACHED_PAGE_ID  # 딥링크 키는 계속 page id
    assert body["sync"]["status"] == "ok"
    assert body["sync"]["last_success_at"] == SYNCED_AT.isoformat()


def test_created_ticket_is_visible_immediately_without_any_sync_tick(cache_client, db, notion):
    """POST 직후 GET /mine 에 보인다 — 동기화 tick 은 한 번도 돌지 않았다."""
    before = db.get(TicketSyncState, SYNC_STATE_ID).last_success_at

    created = cache_client.post("/api/tickets", json={
        "title": "방금 만든 티켓",
        "project_id": P_ALPHA,
        "status": "계획",
        "assignee_user_ids": [U_ME],
    })
    assert created.status_code == 200, created.text
    new_page_id = created.json()["ticket"]["id"]
    assert created.json()["ticket"]["uid"], "생성 응답에 자체 id 가 실려야 한다(write-through 증거)"

    body = _mine(cache_client)
    ids = [t["id"] for t in body["tickets"]]
    assert new_page_id in ids, "방금 만든 티켓이 목록에 없다 — write-through 가 안 됐다"
    titles = {t["id"]: t["title"] for t in body["tickets"]}
    assert titles[new_page_id] == "방금 만든 티켓"
    # 프로젝트 이름은 쓰기 왕복을 늘리지 않고 메타 캐시로 채운다(여기선 메타가 비어 있어 빈 값).
    assert body["sync"]["status"] == "ok"

    # 동기화는 정말로 안 돌았다.
    db.expire_all()
    assert db.get(TicketSyncState, SYNC_STATE_ID).last_success_at == before


def test_edited_ticket_shows_the_new_value_immediately(cache_client, db):
    patched = cache_client.patch(f"/api/tickets/{CACHED_PAGE_ID}", json={"status": "완료"})
    assert patched.status_code == 200, patched.text

    body = _mine(cache_client)
    row = {t["id"]: t for t in body["tickets"]}[CACHED_PAGE_ID]
    assert row["status"] == "완료", "편집 결과가 미러에 반영되지 않았다"


def test_source_outage_with_a_populated_mirror_answers_200_and_flags_staleness(
    cache_client, db, notion
):
    """소스가 죽어도 목록은 200 + 데이터. 500 이 나면 화면 전체가 오류 페이지가 된다."""
    notion.fail_status = 500

    body = _mine(cache_client)
    assert body["ok"] is True                       # 오류가 아니라 마지막 정상 데이터
    assert [t["tid"] for t in body["tickets"]] == [1]

    # 그 사이 워커가 한 번 더 돌아 실패를 기록했다면, 목록은 그대로이고 신선도만 error 로 바뀐다.
    from app.tickets.sync import sync_tickets

    sync_tickets(db, outbound=cache_client.app.state.outbound_client,
                 settings=cache_client.app.state.settings, now=NOW)
    db.commit()

    body = _mine(cache_client)
    assert body["ok"] is True
    assert [t["tid"] for t in body["tickets"]] == [1]
    assert body["sync"]["status"] == "error"
    assert body["sync"]["error"]
    assert body["sync"]["last_success_at"] == SYNCED_AT.isoformat()


def test_team_and_unassigned_also_answer_from_the_mirror(cache_client):
    team = cache_client.get("/api/tickets/team?active=true")
    assert team.status_code == 200
    assert [t["tid"] for t in team.json()["tickets"]] == [1]
    assert team.json()["sync"]["status"] == "ok"

    unassigned = cache_client.get("/api/tickets/unassigned")
    assert unassigned.status_code == 200
    assert unassigned.json()["tickets"] == []       # 캐시의 유일한 티켓은 담당자가 있다
    assert unassigned.json()["sync"]["status"] == "ok"
