"""작업 보드도 **범위를 지킨다** — 판·백로그·이동·해석 (D-194 · §0-A).

## 왜 새 화면마다 이 시험이 필요한가

이 저장소는 같은 실수를 **네 번** 했다(`scripts/check_scope_gates.py` 서문): 목록에는
범위를 걸고 **같은 모듈의 단건·쓰기에는 안 걸었다.** 보드는 그 함정이 특히 크다 —
카드를 옮기는 것은 쓰기인데 화면상으로는 목록을 만지는 것처럼 보이기 때문이다.

여기서 보는 것 넷:

1. **판·백로그**에 남의 프로젝트 티켓이 안 나온다.
2. **이동**이 404 다(403 이 아니다 — 존재를 알리면 id 를 찍어 목록을 열거할 수 있다).
3. **이름 해석**(`ABCDEF-142` → 티켓)이 범위 밖 티켓의 존재를 알려 주지 않는다.
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
from app.work import codes as work_codes

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

    # 코드는 제품의 생성기가 짓는다(D-282). 시험이 `"OURS"` 처럼 읽기 좋은 값을 고르면
    # 그 문자열은 정책의 여섯 글자 알파벳과 갈라지고, 갈라진 사실은 DB 의
    # `ck_projects_code_shape` 가 INSERT 를 거절할 때까지 안 보인다.
    ours = work_codes.insert_with_code(
        db,
        Project(
            name="우리 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=mine.id,
            notion_page_id="proj-ours",
        ),
    )
    theirs_project = work_codes.insert_with_code(
        db,
        Project(
            name="남의 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=theirs.id,
            notion_page_id="proj-theirs",
        ),
    )

    def _ticket(page_id, project, number):
        """티켓 한 건. **번호(`seq`)를 함께 준다.**

        번호가 있어야 트리거가 `<CODE>-<SEQ>` 를 파생하고, 그래야 판·백로그·해석이
        실제로 이름을 다룬다. 번호를 빼면 이름이 전부 `None` 이 되고, 아래 시험들은
        「남의 이름이 안 보인다」를 **아무 이름도 없어서** 통과한다.
        """
        row = Ticket(
            title=f"티켓 {page_id}", notion_page_id=page_id, project_uid=project.id,
            project_link=PROJECT_LINK_OK, status="계획", org_id=DEFAULT_ORG_ID,
            source="notion", notion_ticket_number=number, seq=number,
        )
        db.add(row)
        db.flush()
        # `canonical_key` 는 앱이 아니라 트리거가 채운다. 다시 읽지 않으면 ORM 쪽 값이
        # 비어 있어서 시험이 `None` 을 기대값으로 들고 다니게 된다.
        db.refresh(row)
        return row

    ours_ticket = _ticket("page-ours", ours, 11)
    theirs_ticket = _ticket("page-theirs", theirs_project, 22)
    db.commit()
    return {
        "ours": ours, "theirs": theirs_project,
        "ours_ticket": ours_ticket, "theirs_ticket": theirs_ticket,
        "ours_key": ours_ticket.canonical_key,
        "theirs_key": theirs_ticket.canonical_key,
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
    assert world["ours_key"] in keys, f"우리 팀 티켓이 판에 없다 — 검사가 헛돈다: {keys}"
    assert world["theirs_key"] not in keys, f"남의 팀 티켓이 판에 있다: {keys}"


def test_the_backlog_shows_ours_and_not_theirs(client, login_as, world):
    body = client.get("/api/work/backlog", headers=_hdr(login_as)).json()
    keys = {item["key"] for item in body["items"]}
    assert world["ours_key"] in keys, f"우리 팀 티켓이 백로그에 없다 — 검사가 헛돈다: {keys}"
    assert world["theirs_key"] not in keys, f"남의 팀 티켓이 백로그에 있다: {keys}"


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
    """티켓 이름을 아는 것만으로 남의 티켓에 닿을 수 없다.

    이름(`ABCDEF-22`)은 문서·대화·링크에 뿌려지는 값이라 **추측이 아니라 이미 아는
    값**이다. 해석이 범위를 안 보면 그 값 하나로 남의 부서 티켓의 id 와 제목이 나온다.

    기대값을 글자로 적지 않고 세계가 실제로 받은 이름을 쓰는 이유가 있다. 지금 정책에서
    없는 이름을 넣으면 해석이 **아무것도 못 찾아서** 404 를 돌려주고, 그 404 는 범위가
    막아서 나온 404 와 구별되지 않는다. 그러면 이 시험은 범위를 걷어내도 초록으로 남는다.
    """
    r = client.get(
        f"/api/work/resolve/{world['theirs_key']}", headers=_hdr(login_as)
    )
    assert r.status_code == 404, f"남의 티켓이 이름으로 해석됐다: {r.status_code} {r.text}"

    ours = client.get(
        f"/api/work/resolve/{world['ours_key']}", headers=_hdr(login_as)
    )
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


def test_the_project_key_surface_is_gone(client, login_as, world):
    """프로젝트 코드를 사람이 정하는 자리가 **아예 없다** (D-282).

    앞 정책에는 코드를 정하는 경로와 초안을 받아 보는 경로 둘이 있었고, 이 시험은 그
    자리에 일반 사용자가 못 들어간다는 것(403)을 봤다. 이제 코드는 서버가 짓고 아무도
    못 고치므로 그 경로 자체가 사라졌다.

    사라진 경로에 「일반 사용자는 403 을 받는다」를 계속 물으면 시험이 **없는 계약**을
    지키게 된다. 그 단정은 누군가 이 경로를 되살리는 날에도 권한 게이트만 붙어 있으면
    그대로 초록이고, 정작 「사람이 코드를 고치는 문이 다시 열렸다」는 사실은 아무도 못
    잡는다. 그래서 묻는 것을 바꾼다: 이 두 경로는 존재하지 않는다.

    권한을 가진 쪽(`PROJECT_ADMIN` 인 팀관리자)까지 함께 보는 이유는, 일반 사용자만
    보면 「권한 게이트가 막았다」와 「경로가 없다」가 구별되지 않기 때문이다. 문이 다시
    열리면 팀관리자 쪽이 먼저 200 을 받고 이 시험이 빨개진다.

    405 도 받아 주는 이유는 경로가 다른 메서드로 되살아나는 경우까지 「없다」로 읽기
    위해서다. 지금 앱은 둘 다 404 를 돌려준다.
    """
    for role, email in (("admin", BOSS), ("user", MATE)):
        headers = {"X-CSRF-Token": login_as(role, email=email)}
        put = client.put(
            f"/api/work/projects/{world['ours'].id}/key",
            json={"key": "ABCDEF"},
            headers=headers,
        )
        assert put.status_code in (404, 405), (
            f"코드를 정하는 경로가 아직 살아 있다({email}): {put.status_code} {put.text}"
        )

        suggest = client.get(
            f"/api/work/projects/{world['ours'].id}/key/suggest", headers=headers
        )
        assert suggest.status_code in (404, 405), (
            f"코드 초안 경로가 아직 살아 있다({email}): "
            f"{suggest.status_code} {suggest.text}"
        )


def test_a_plain_user_cannot_assign_a_migration_exception(client, login_as, world):
    """예외 배정은 「자동으로 안 하는 일을 사람이 하는 자리」다 — 아무나 하면 안 된다."""
    token = login_as("user", email=MATE)
    r = client.post(
        f"/api/work/exceptions/{world['ours_ticket'].id}/assign",
        json={"project_id": world["ours"].id},
        headers={"X-CSRF-Token": token},
    )
    assert r.status_code == 403, f"일반 사용자가 소속을 배정했다: {r.status_code}"
