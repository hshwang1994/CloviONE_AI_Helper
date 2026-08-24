"""목록의 부서 필터는 **좁히기만 한다** (0060 §32).

## 왜 보안 시험인가

필터는 보통 편의 기능이지만, 이 필터는 조회 범위와 같은 축을 건드린다. 두 가지가 틀릴 수
있고 둘 다 조용하다:

  1. **넓히는 방향** — 범위 밖 부서 id 를 넣었는데 그 부서 것이 나온다. 화면은 정상으로
     보이고 아무도 신고하지 않는다.
  2. **후보가 서버 판정보다 넓다** — 고를 수는 있는데 고르면 404 다. 이건 유출은 아니지만,
     사용자는 "권한이 있는데 안 된다" 로 읽는다.

그래서 세 목록(프로젝트·문서·팀 티켓)에 대해 같은 표를 돌린다. 판정은 한 함수
(`app/org/context.py::filter_scope`)를 지나므로, 한 곳이 틀리면 세 목록이 함께 빨개진다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.tickets.models import PROJECT_LINK_OK, SYNC_STATE_ID, TicketCache, TicketSyncState
from tests.fixtures.org_tree import (  # noqa: F401 — fixture 재수출
    D_A1,
    D_A2,
    D_B1,
    org_tree,
    people,
    resources,
)

pytestmark = pytest.mark.security

PASSWORD = "Str0ng-Passw0rd!"
NOW = datetime(2026, 8, 3, 9, 0, 0)


@pytest.fixture()
def tickets(db, resources):
    # 옛 동기화 싱글턴 행은 이관해 온 데이터베이스에 그대로 남아 있다. 일부러 채워 두는
    # 이유는 목록이 그 행을 읽지 **않는다**는 것까지 이 세계에서 보이게 하려는 것이다.
    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status = "ok"
    state.last_run_at = NOW
    state.last_success_at = NOW
    db.add(state)
    for i, (key, project) in enumerate(resources["projects"].items()):
        db.add(TicketCache(
            id=f"df-tc-{key}", notion_page_id=f"df-page-{key}", notion_ticket_number=800 + i,
            title=f"{key} 티켓", status="진행", assignee_notion_ids="",
            project_uid=project.id, project_link=PROJECT_LINK_OK,
            synced_at=NOW, created_at=NOW, updated_at=NOW,
        ))
    db.commit()


def _login(client, people, key):
    r = client.post("/login", json={"email": people[key].email, "password": PASSWORD})
    assert r.status_code == 200, r.text


def _names(client, path, **params):
    r = client.get(path, params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    body = r.json()
    return {i.get("name") or i.get("title") for i in body["items"]}, body


def test_the_filter_narrows_within_my_scope(client, people, resources, tickets):
    """A 사람은 줄기 전체를 보다가, A-1 을 고르면 A-1 것만 본다."""
    _login(client, people, "a")

    everything, body = _names(client, "/api/projects")
    assert {"a 프로젝트", "a1 프로젝트", "a2 프로젝트"} <= everything

    narrowed, _ = _names(client, "/api/projects", department_id=D_A1)
    assert narrowed == {"a1 프로젝트"}, f"부서 필터가 안 걸렸다: {narrowed}"

    # 후보는 서버가 준다. 없으면 화면이 스스로 만들 수밖에 없고, 그때 갈라진다.
    options = {o["id"] for o in body["departments"]["options"]}
    assert D_A1 in options and D_A2 in options


def test_the_filter_cannot_widen_beyond_my_scope(client, people, resources, tickets):
    """범위 밖 부서를 넣으면 **없는 부서와 똑같이 404** 다 (403 은 존재를 알려 준다)."""
    _login(client, people, "a1")

    r = client.get("/api/projects", params={"department_id": D_A2})
    assert r.status_code == 404, (
        f"형제 부서로 필터를 걸었는데 통과했다 — 조회 범위가 넓어졌다: {r.text}"
    )
    assert client.get("/api/team-docs", params={"department_id": D_B1}).status_code == 404
    assert client.get("/api/tickets/team", params={"department_id": D_B1}).status_code == 404


def test_the_option_list_never_offers_what_the_server_would_refuse(
    client, people, resources, tickets
):
    """고를 수 있는 것과 통과하는 것이 **정확히 같아야** 한다.

    후보가 넓으면 "고를 수는 있는데 누르면 404" 가 되고, 좁으면 볼 수 있는 부서를 못 고른다.
    둘 다 서버 판정과 화면이 갈라진 상태다.
    """
    _login(client, people, "a1")
    _, body = _names(client, "/api/projects")
    offered = {o["id"] for o in body["departments"]["options"]}

    assert D_A2 not in offered, "형제 부서가 후보에 있다 — 누르면 404 다"
    for dept_id in offered:
        assert client.get(
            "/api/projects", params={"department_id": dept_id}
        ).status_code == 200, f"후보에 있는 {dept_id} 가 서버에서 거부됐다"


def test_documents_and_team_tickets_use_the_same_judgement(
    client, people, resources, tickets
):
    """세 목록이 같은 함수를 지나는가 — 한 곳만 다르면 그 화면에서 새거나 비어 버린다."""
    _login(client, people, "a")

    docs, _ = _names(client, "/api/team-docs", department_id=D_A1)
    assert docs == {"a1 문서"}, f"문서 목록의 부서 필터가 다르게 동작한다: {docs}"

    r = client.get("/api/tickets/team", params={"page_size": 100, "department_id": D_A1})
    assert r.status_code == 200, r.text
    titles = {t["title"] for t in r.json()["items"]}
    assert titles == {"a1 티켓"}, f"팀 티켓의 부서 필터가 다르게 동작한다: {titles}"


def test_filtering_by_a_parent_includes_its_descendants(client, people, resources, tickets):
    """상위 부서를 고르면 **그 아래까지** 본다 — 위만 보면 본부 화면이 늘 비어 있다.

    조상은 포함하지 않는다. "A-1 팀 목록" 을 보면서 상위 A 공통 업무가 섞이면 그건
    A 목록이지 A-1 목록이 아니다.
    """
    _login(client, people, "a")
    names, _ = _names(client, "/api/projects", department_id=resources["projects"]["a"].dept_id)
    assert names == {"a 프로젝트", "a1 프로젝트", "a2 프로젝트"}, names
