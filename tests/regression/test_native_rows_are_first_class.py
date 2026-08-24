"""자체 DB 에서 만든 프로젝트와 티켓이 **일급 시민**이다 (S14 · D-284).

## 이 파일이 있는 이유

이관 전에는 모든 프로젝트와 티켓이 외부 소스에서 왔고 그래서 전부 `notion_page_id` 를
가졌다. 코드 곳곳이 그 사실에 기대어 **그 칸을 티켓·프로젝트의 이름처럼** 썼다.

Cutover 뒤로는 반대다. 새로 만드는 프로젝트에는 그 칸이 없고(`NULL`), 새 티켓도 마찬가지다
— 그 둘의 이름은 행의 uuid 다(`app/tickets/models.py::api_page_id`).

🔴 그래서 `notion_page_id` 만 읽는 자리는 전부 **`None` 을 받고, `None` 을 「그런 것 없음」
으로 읽는다.** 오류가 안 난다. 증상은 전부 조용하다:

* 프로젝트 진행률·헬스·WBS 트리가 영원히 비어 있다 (걸린 티켓을 못 찾는다)
* 새 프로젝트에 "티켓을 만들 수 없습니다" 가 뜬다
* 새 티켓이 검색에서 전역 관리자에게만 보인다 (소유 프로젝트 없이 색인된다)
* 판에서 카드를 눌러도 안 열리고, 상태를 옮기면 404 다
* 버린 티켓이 판에 계속 남는다
* 알림이 아무 데도 안 간다

이 시험들은 전부 **행을 하나 심고 화면이 부르는 경로를 그대로 태워서** 확인한다. 각각이
실제로 고친 결함 하나에 대응한다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.regression


def test_a_project_without_an_external_pair_still_finds_its_tickets(
    db, make_project, make_ticket
):
    """🔴 진행률·헬스·WBS 가 전부 이 한 질의를 지난다(`ticket_rows_for_project`).

    여기가 빈 목록을 돌려주면 세 화면이 동시에 "셀 것이 없다"고 답하는데, 같은 화면에
    티켓은 멀쩡히 붙어 있다.
    """
    from app.projects import repository

    project = make_project(name="자체 프로젝트")
    assert project.notion_page_id is None, "이 시험의 전제가 깨졌다"
    make_ticket(project=project, title="붙어 있는 티켓", status="진행")

    rows = repository.ticket_rows_for_project(db, project)
    assert [r.title for r in rows] == ["붙어 있는 티켓"], (
        "자체 프로젝트에 걸린 티켓을 못 찾는다 — 진행률·헬스·트리가 전부 빈다"
    )


def test_a_migrated_project_still_finds_its_tickets_by_the_old_relation(
    db, make_project, make_ticket
):
    """반대편 — 이관해 온 티켓은 옛 relation 목록으로만 맞출 수 있다.

    이 단언이 없으면 위 시험은 **옛 축을 지워 버린 세계**에서도 통과한다. 그 세계에서는
    이관해 온 1,133건이 전부 프로젝트를 잃는다.
    """
    from app.projects import repository

    project = make_project(name="이관 프로젝트", external_id="proj-legacy")
    make_ticket(
        page_id="page-legacy", external_project_ids=["proj-legacy"], title="옛 티켓",
    )

    rows = repository.ticket_rows_for_project(db, project)
    assert [r.title for r in rows] == ["옛 티켓"]


def test_the_screen_says_a_native_project_can_take_tickets(client, login_as, make_project):
    """작성 화면이 미리 읽는 칸이다. False 면 버튼 자체가 안 나온다."""
    login_as("system_admin", email="native-can-create@goodmit.co.kr")
    project = make_project(name="티켓 받을 프로젝트")

    items = client.get("/api/tickets/projects").json()["projects"]
    mine = [p for p in items if p["id"] == project.id]
    assert mine, f"방금 만든 프로젝트가 목록에 없다: {[p['name'] for p in items]}"
    assert mine[0]["can_create_ticket"] is True, (
        "자체 프로젝트에 티켓을 만들 수 없다고 말한다"
    )


def test_a_ticket_can_actually_be_created_in_a_native_project(client, login_as, make_project, db):
    """🔴 위 시험은 **화면이 뭐라고 말하는가**를 본다. 이건 실제로 되는가를 본다.

    둘을 나누지 않으면 「버튼은 보이는데 눌러도 안 된다」가 통과한다 — 그쪽이 더 나쁘다.
    사용자는 서버가 왜 거절하는지 화면에서 알 수 없다.
    """
    from app.tickets.models import TicketCache

    csrf = login_as("system_admin", email="native-create@goodmit.co.kr")
    project = make_project(name="티켓 만들 프로젝트")
    assert project.notion_page_id is None, "이 시험의 전제가 깨졌다"

    made = client.post(
        "/api/tickets",
        json={"title": "자체 프로젝트의 첫 티켓", "project_id": project.id},
        headers={"X-CSRF-Token": csrf},
    )
    assert made.status_code in (200, 201), (
        f"자체 프로젝트에 티켓을 못 만든다: {made.text}"
    )

    db.expire_all()
    row = db.query(TicketCache).filter(
        TicketCache.title == "자체 프로젝트의 첫 티켓"
    ).one()
    assert row.project_uid == project.id, (
        "만들어졌지만 프로젝트에 안 붙었다 — 그 티켓은 전역 관리자에게만 보인다"
    )
    assert row.canonical_key and row.canonical_key.startswith(f"{project.code}-"), (
        f"채번이 안 됐거나 이름이 프로젝트 코드를 안 따른다: {row.canonical_key!r}"
    )


def test_a_native_ticket_is_indexed_under_its_project(db, app, make_project, make_ticket):
    """🔴 검색 색인의 소유 프로젝트. 없으면 그 티켓은 전역 관리자에게만 보인다."""
    from app.reports.service import load_display_maps
    from app.search import indexer

    project = make_project(name="검색 확인용")
    make_ticket(project=project, title="검색될 티켓", status="진행")

    rows, _ = indexer._ticket_rows(
        db, app.state.repositories.tickets, load_display_maps(db)
    )
    found = [r for r in rows if r["title"] == "검색될 티켓"]
    assert found, "자체 티켓이 색인에 아예 안 들어갔다"
    assert found[0]["owner_kind"] == indexer.OWNER_PROJECT, (
        "색인에 소유 프로젝트가 없다 — 만든 사람에게조차 검색되지 않는다"
    )
    assert found[0]["owner_project_id"] == project.id


def test_the_team_list_filters_a_native_project_by_its_portal_id(
    client, login_as, db, make_project, make_ticket
):
    """프로젝트 상세의 티켓 탭이 서버에 거는 조건이다.

    화면은 `project_id` 로 **포털 프로젝트 id** 를 보낸다. 서버가 그 값을 두 축으로 맞춰야
    한다 — 해석된 `tickets.project_uid` 와 이관해 온 티켓의 옛 relation 목록. 한 축만 보면
    조용히 반쪽이 되고, 사용자에게는 「티켓 탭이 비었다」로만 보인다.
    """
    login_as("system_admin", email="native-filter@goodmit.co.kr")
    mine = make_project(name="내 프로젝트")
    other = make_project(name="남의 프로젝트")
    make_ticket(project=mine, title="내 프로젝트 티켓", status="진행")
    make_ticket(project=other, title="남의 프로젝트 티켓", status="진행")
    db.commit()

    body = client.get(f"/api/tickets/team?project_id={mine.id}&active=false").json()
    titles = [t["title"] for t in body["items"]]
    assert titles == ["내 프로젝트 티켓"], (
        f"자체 프로젝트로 거른 목록이 틀렸다: {titles}"
    )
    assert body["total"] == 1


def test_a_native_ticket_opens_moves_and_disappears_when_trashed(
    client, login_as, db, make_project, make_ticket, app
):
    """판이 실제로 하는 세 가지를 한 티켓으로 이어서 태운다.

    셋을 나누지 않는 이유: 카드가 `page_id` 를 안 실으면 그다음 두 개는 **시험할 값 자체가
    없다.** 이어서 태워야 「눌러서 옮기고 버린다」가 끊기는 자리가 드러난다.
    """
    csrf = login_as("system_admin", email="native-board@goodmit.co.kr")
    project = make_project(name="판 확인용")
    ticket = make_ticket(project=project, title="판에 오를 티켓", status="진행")
    db.commit()

    board = client.get(f"/api/work/board?project_id={project.id}").json()
    cards = [c for col in board["columns"] for c in col["cards"]]
    mine = [c for c in cards if c["title"] == "판에 오를 티켓"]
    assert mine, f"자체 티켓이 판에 안 올라온다: {[c['title'] for c in cards]}"
    assert mine[0]["page_id"], "카드에 page_id 가 없다 — 눌러도 안 열린다"

    moved = client.post(
        f"/api/work/board/{ticket.id}/move", json={"to_status": "완료"},
        headers={"X-CSRF-Token": csrf},
    )
    assert moved.status_code == 200, f"자체 티켓의 상태를 못 옮긴다: {moved.text}"
    db.expire_all()
    assert db.get(type(ticket), ticket.id).status == "완료"

    trashed = client.post(
        f"/api/tickets/{mine[0]['page_id']}/trash", headers={"X-CSRF-Token": csrf},
    )
    assert trashed.status_code in (200, 201), f"자체 티켓을 못 버린다: {trashed.text}"

    after = client.get(f"/api/work/board?project_id={project.id}").json()
    left = [c["title"] for col in after["columns"] for c in col["cards"]]
    assert "판에 오를 티켓" not in left, (
        "버린 티켓이 판에 남아 있다 — 휴지통은 API 이름으로 적는데 판은 옛 칸으로 비교한다"
    )
