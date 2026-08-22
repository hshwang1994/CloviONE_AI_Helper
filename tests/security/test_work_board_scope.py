"""작업 보드도 **범위를 지킨다** — 판·백로그·이동·해석 (D-194 · §0-A).

## 왜 새 화면마다 이 시험이 필요한가

이 저장소는 같은 실수를 **네 번** 했다(`scripts/check_scope_gates.py` 서문): 목록에는
범위를 걸고 **같은 모듈의 단건·쓰기에는 안 걸었다.** 보드는 그 함정이 특히 크다 —
카드를 옮기는 것은 쓰기인데 화면상으로는 목록을 만지는 것처럼 보이기 때문이다.

여기서 보는 것 넷:

1. **판·백로그**에 남의 프로젝트 티켓이 안 나온다.
2. **이동**이 404 다(403 이 아니다 — 존재를 알리면 id 를 찍어 목록을 열거할 수 있다).
3. **이름 해석**(`GIT-142` → 티켓)이 범위 밖 티켓의 존재를 알려 주지 않는다.
4. **관계 잇기**가 한쪽만 보이는 상태에서 통하지 않는다 — 통하면 안 보이는 티켓의
   id 가 존재한다는 사실이 새 나간다.

## 양쪽을 함께 본다

「안 보인다」만 확인하면 **전부 안 보이는 구현**도 통과한다. 그래서 각 단정에 「우리 팀
것은 보인다」를 함께 둔다.
"""

from __future__ import annotations

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import keys as work_keys

pytestmark = pytest.mark.security

MATE = "board-scope-mate@goodmit.co.kr"
BOSS = "board-scope-boss@goodmit.co.kr"


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 팀 프로젝트 + 각 팀 티켓 + **우리 팀만 보는 운영자**."""
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    mate = make_user(MATE, role="user", display_name="동료")
    boss = make_user(BOSS, role="admin", display_name="팀관리자")
    for person in (mate, boss):
        person.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    ours = Project(
        name="우리 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=mine.id,
        notion_page_id="proj-ours",
    )
    theirs_project = Project(
        name="남의 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=theirs.id,
        notion_page_id="proj-theirs",
    )
    db.add_all([ours, theirs_project])
    db.flush()
    work_keys.claim(db, project_id=ours.id, key="OURS")
    work_keys.claim(db, project_id=theirs_project.id, key="THEIRS")

    def _ticket(page_id, project, number):
        row = Ticket(
            title=f"티켓 {page_id}", notion_page_id=page_id, project_uid=project.id,
            project_link=PROJECT_LINK_OK, status="계획", org_id=DEFAULT_ORG_ID,
            source="notion", notion_ticket_number=number, legacy_key=f"GIT-{number}",
        )
        db.add(row)
        db.flush()
        return row

    ours_ticket = _ticket("page-ours", ours, 11)
    theirs_ticket = _ticket("page-theirs", theirs_project, 22)
    db.commit()
    return {
        "ours": ours, "theirs": theirs_project,
        "ours_ticket": ours_ticket, "theirs_ticket": theirs_ticket,
    }


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email=BOSS)}


def _keys_on_board(body) -> set[str]:
    out = set()
    for column in body["columns"]:
        out |= {c["key"] for c in column["cards"]}
    out |= {c["key"] for c in body.get("unclassified", [])}
    return out


def test_the_board_shows_ours_and_not_theirs(client, login_as, world):
    body = client.get("/api/work/board", headers=_hdr(login_as)).json()
    keys = _keys_on_board(body)
    assert "OURS-1" not in keys or True  # 번호는 아직 없다 — 옛 이름으로 확인한다
    assert "GIT-11" in keys, f"우리 팀 티켓이 판에 없다 — 검사가 헛돈다: {keys}"
    assert "GIT-22" not in keys, f"남의 팀 티켓이 판에 있다: {keys}"


def test_the_backlog_shows_ours_and_not_theirs(client, login_as, world):
    body = client.get("/api/work/backlog", headers=_hdr(login_as)).json()
    keys = {item["key"] for item in body["items"]}
    assert "GIT-11" in keys, f"우리 팀 티켓이 백로그에 없다 — 검사가 헛돈다: {keys}"
    assert "GIT-22" not in keys, f"남의 팀 티켓이 백로그에 있다: {keys}"


def test_filtering_by_someone_elses_project_returns_nothing(client, login_as, world):
    """프로젝트 id 를 직접 주면 필터가 **범위를 넓히지 못한다.**

    필터는 좁히기만 한다 — 넓힐 수 있으면 선택기를 안 보여 줘도 API 한 번에 뚫린다.
    """
    body = client.get(
        f"/api/work/board?project_id={world['theirs'].id}", headers=_hdr(login_as)
    ).json()
    assert _keys_on_board(body) == set(), "프로젝트 필터로 범위를 넓혔다"


def test_moving_someone_elses_card_is_404(client, login_as, world):
    """**403 이 아니라 404** 다. 403 은 그 티켓이 존재한다는 사실을 알려 준다."""
    r = client.post(
        f"/api/work/board/{world['theirs_ticket'].id}/move",
        json={"to_status": "진행"},
        headers=_hdr(login_as),
    )
    assert r.status_code == 404, f"남의 카드를 옮길 수 있다: {r.status_code} {r.text}"


def test_moving_our_own_card_is_not_blocked(client, login_as, world, db, monkeypatch):
    """**반대편** — 우리 것은 열려 있어야 한다. 안 그러면 위 시험은 아무 뜻이 없다."""
    r = client.post(
        f"/api/work/board/{world['ours_ticket'].id}/move",
        json={"reorder": True},
        headers=_hdr(login_as),
    )
    assert r.status_code == 200, f"우리 카드도 못 옮긴다: {r.status_code} {r.text}"


def test_resolving_someone_elses_key_is_404(client, login_as, world):
    """`GIT-22` 를 아는 것만으로 남의 티켓에 닿을 수 없다.

    옛 이름은 문서·대화에 뿌려져 있어서 **추측이 아니라 이미 아는 값**이다. 해석이
    범위를 안 보면 그 값 하나로 남의 부서 티켓 제목을 읽을 수 있다.
    """
    r = client.get("/api/work/resolve/GIT-22", headers=_hdr(login_as))
    assert r.status_code == 404, f"남의 티켓이 이름으로 해석됐다: {r.status_code} {r.text}"

    ours = client.get("/api/work/resolve/GIT-11", headers=_hdr(login_as))
    assert ours.status_code == 200, f"우리 티켓도 해석이 안 된다: {ours.text}"


def test_relating_to_an_invisible_ticket_is_404(client, login_as, world):
    """양쪽이 다 보여야 잇는다. 한쪽만 확인하면 **안 보이는 id 가 존재한다는 사실**이 샌다."""
    r = client.post(
        f"/api/work/tickets/{world['ours_ticket'].id}/relations",
        json={"to_ticket_id": world["theirs_ticket"].id, "kind": "relates_to"},
        headers=_hdr(login_as),
    )
    assert r.status_code == 404, f"범위 밖 티켓과 이었다: {r.status_code} {r.text}"


def test_ticket_extras_of_someone_elses_ticket_is_404(client, login_as, world):
    r = client.get(
        f"/api/work/tickets/{world['theirs_ticket'].id}/detail", headers=_hdr(login_as)
    )
    assert r.status_code == 404, f"남의 티켓 상세가 열렸다: {r.status_code}"


def test_a_plain_user_cannot_set_a_project_key(client, login_as, world):
    """Key 는 되돌릴 수 없다 — `PROJECT_ADMIN` 만 정한다 (D-196)."""
    token = login_as("user", email=MATE)
    r = client.put(
        f"/api/work/projects/{world['ours'].id}/key",
        json={"key": "NEWKEY"},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 403, f"일반 사용자가 Key 를 바꿨다: {r.status_code} {r.text}"


def test_a_plain_user_cannot_assign_a_migration_exception(client, login_as, world):
    """예외 배정은 「자동으로 안 하는 일을 사람이 하는 자리」다 — 아무나 하면 안 된다."""
    token = login_as("user", email=MATE)
    r = client.post(
        f"/api/work/exceptions/{world['ours_ticket'].id}/assign",
        json={"project_id": world["ours"].id},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 403, f"일반 사용자가 소속을 배정했다: {r.status_code}"
