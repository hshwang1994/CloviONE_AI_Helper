"""티켓 목록이 **방금 한 일을 바로 보여 주는가** — 그리고 낡음 배지가 안 남는가.

## 원래 이 파일이 지키던 두 가지

1. **write-through** — 티켓을 만들거나 고친 사람이 목록에서 그걸 바로 봐야 한다. 미러의
   동기화 주기가 180초라, 쓰기 뒤에 같은 요청에서 미러를 고치지 않으면 "방금 만든 티켓이
   없어졌다" 가 됐다.
2. **장애 격리** — 미러가 차 있으면 소스가 5xx 를 뱉든 말든 목록은 200 이고, 응답의
   신선도(`sync`) 블록이 "지금 보는 건 마지막 정상 데이터" 라고 말한다.

## 지금 (S14)

정본이 이 서버의 표 하나로 옮겨 오면서 둘째는 대상이 사라졌다 — 낡을 수 있는 사본이 없고,
죽을 수 있는 바깥 소스도 없다. 그 자리에 **반대 방향의 약속**이 생겼다: 응답에 신선도
블록이 **실리지 않아야 한다.** 실리면 화면이 「N분 전 동기화」 배지를 그리는데, 그 시각은
더 이상 돌지 않는 동기화의 마지막 시각이라 매일 조금씩 더 낡아 보인다. 그건 정보가 아니라
거짓말이고, 사용자는 고칠 방법이 없다.

첫째는 그대로 남는다. 「방금 만든 티켓이 목록에 있다」는 저장소가 어디든 사용자가 기대하는
것이고, 쓰기가 같은 트랜잭션에서 표를 안 고치면 지금도 똑같이 깨진다.

qa-contract-change: 미러 장애 격리 시험 두 건이 대상을 잃었다 — 낡을 수 있는 사본과 죽을 수 있는 바깥 소스가 함께 사라져 「소스가 죽어도 200」과 「신선도가 error 로 바뀐다」를 만들 수단이 없다. 대신 그 자리에 생긴 반대 약속, 곧 신선도 블록이 응답에 아예 실리지 않는다는 것을 목록 네 곳에서 새로 못박는다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.tickets.models import TicketCache, join_names
from app.users.models import User
from tests.fakes.clock import FakeClock

pytestmark = pytest.mark.regression

NOW = datetime(2026, 8, 3, 9, 0, 0)
SYNCED_AT = datetime(2026, 8, 3, 8, 57, 0)
PASSWORD = "Cache-Passw0rd!"

U_ME = "00000000-0000-4000-8000-0000000c0001"
N_ME = "notion-user-me"
P_ALPHA = "cache-proj-alpha"

# 이관해 온 티켓 한 건.
CACHED_PAGE_ID = "cache-0001"


@pytest.fixture()
def fake_clock():
    return FakeClock(NOW)


@pytest.fixture()
def notion(fake_http):
    """가짜 Notion 서버를 붙이되 **티켓은 한 건도 놓지 않는다**.

    반례 장치다. 목록 경로가 다시 바깥을 읽기 시작하면 이 빈 작업 DB 가 티켓을 못 찾아
    아래 단언들이 소리 내어 깨진다 — 페이크를 안 붙이면 그 회귀는 조용히 지나간다.
    """
    from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB

    return FakeNotionTasksDB(
        rows=[], projects=[], projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


def _seed_user(db) -> None:
    from app.org.constants import DEFAULT_ORG_ID

    db.add(User(id=U_ME, email="cache-me@goodmit.co.kr", display_name="캐시 나",
                role="user", active=True, password_hash=hash_password(PASSWORD),
                # 소속(0060) — 조직 직속. 미지정이면 조직 데이터를 아무것도 못 본다.
                membership_kind="organization", org_id=DEFAULT_ORG_ID,
                must_change_password=False))
    db.flush()
    db.add(UserNotionMapping(id="00000000-0000-4000-8000-0000000c0101", user_id=U_ME,
                             notion_user_id=N_ME, notion_email="cache-me@goodmit.co.kr",
                             status=STATUS_VERIFIED, source=SOURCE_MANUAL,
                             last_verified_at=SYNCED_AT))
    db.commit()


def _seed_ticket(db) -> None:
    """이관해 온 티켓 한 건과 그 프로젝트.

    0060 부터 티켓의 소속은 프로젝트가 정하고, 짝이 없으면 그 티켓은 `unresolved` 라
    아무에게도 안 보인다 — 그러면 이 파일이 검사하려는 것을 확인할 수가 없다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.projects.models import Project
    from app.tickets.models import PROJECT_LINK_OK

    project = Project(name="알파 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id=P_ALPHA)
    db.add(project)
    db.flush()
    db.add(TicketCache(
        id="cache-uid-0001", notion_page_id=CACHED_PAGE_ID, org_id=DEFAULT_ORG_ID,
        notion_ticket_number=1, url=f"https://www.notion.so/{CACHED_PAGE_ID}",
        title="이미 있던 티켓", status="진행", due_date="2026-08-04",
        project_ids=join_names([P_ALPHA]), project_names=join_names(["알파 프로젝트"]),
        project_uid=project.id, project_link=PROJECT_LINK_OK,
        assignee_notion_ids=join_names([N_ME]),
        synced_at=SYNCED_AT, created_at=SYNCED_AT, updated_at=SYNCED_AT,
    ))
    db.commit()


@pytest.fixture()
def cache_client(client, db, settings, notion):
    _seed_user(db)
    _seed_ticket(db)
    response = client.post("/login", json={"email": "cache-me@goodmit.co.kr", "password": PASSWORD})
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return client


def _mine(client) -> dict:
    response = client.get("/api/tickets/mine")
    assert response.status_code == 200, response.text
    return response.json()


def test_list_answers_from_the_record_without_a_freshness_block(cache_client):
    body = _mine(cache_client)
    assert body["ok"] is True
    assert [t["tid"] for t in body["tickets"]] == [1]
    assert body["tickets"][0]["uid"] == "cache-uid-0001"
    assert body["tickets"][0]["id"] == CACHED_PAGE_ID  # 딥링크 키는 계속 page id
    # **신선도 블록이 없다.** 있으면 화면이 영영 낡아 가는 「N분 전 동기화」 배지를 그린다.
    assert "sync" not in body


def test_created_ticket_is_visible_immediately(cache_client, db):
    """POST 직후 GET /mine 에 보인다 — 쓰기가 같은 트랜잭션에서 표를 고쳤다는 뜻이다."""
    from app.projects.models import Project

    # `project_id` 는 **Portal 프로젝트 id** 다 (0060) — 외부 page id 가 아니다. 티켓의
    # 소속을 정하는 값이라 정본이 Portal 이어야 한다.
    portal_project_id = db.execute(
        select(Project.id).where(Project.notion_page_id == P_ALPHA)
    ).scalar_one()
    created = cache_client.post("/api/tickets", json={
        "title": "방금 만든 티켓",
        "project_id": portal_project_id,
        "status": "계획",
        "assignee_user_ids": [U_ME],
    })
    assert created.status_code == 200, created.text
    new_page_id = created.json()["ticket"]["id"]
    assert created.json()["ticket"]["uid"], "생성 응답에 자체 id 가 실려야 한다"

    body = _mine(cache_client)
    titles = {t["id"]: t["title"] for t in body["tickets"]}
    assert new_page_id in titles, "방금 만든 티켓이 목록에 없다"
    assert titles[new_page_id] == "방금 만든 티켓"
    assert "sync" not in body


def test_edited_ticket_shows_the_new_value_immediately(cache_client, db):
    patched = cache_client.patch(f"/api/tickets/{CACHED_PAGE_ID}", json={"status": "완료"})
    assert patched.status_code == 200, patched.text

    body = _mine(cache_client)
    row = {t["id"]: t for t in body["tickets"]}[CACHED_PAGE_ID]
    assert row["status"] == "완료", "편집 결과가 목록에 반영되지 않았다"


def test_team_and_unassigned_also_answer_from_the_record(cache_client):
    team = cache_client.get("/api/tickets/team?active=true")
    assert team.status_code == 200
    assert [t["tid"] for t in team.json()["tickets"]] == [1]
    assert "sync" not in team.json()

    unassigned = cache_client.get("/api/tickets/unassigned")
    assert unassigned.status_code == 200
    assert unassigned.json()["tickets"] == []       # 유일한 티켓은 담당자가 있다
    assert "sync" not in unassigned.json()


def test_no_request_left_the_process_while_answering(cache_client, fake_http):
    """반례 확인 — 위 목록 네 곳이 정말 우리 표에서만 답했는가.

    계측기가 0 을 세는지 확인하려면 그 계측기가 1 도 셀 수 있어야 한다. 그 검증은
    `tests/unit/test_fake_notion.py` 가 따로 한다.
    """
    _mine(cache_client)
    cache_client.get("/api/tickets/team?active=true")
    cache_client.get("/api/tickets/unassigned")
    assert fake_http.requests == [], "티켓 목록이 바깥으로 나갔다"
