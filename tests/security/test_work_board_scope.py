"""작업 보드도 **범위를 지킨다** — 판·백로그·이동·해석 (D-194 · §0-A).

## 왜 새 화면마다 이 시험이 필요한가

이 저장소는 같은 실수를 **네 번** 했다(`scripts/check_scope_gates.py` 서문): 목록에는
범위를 걸고 **같은 모듈의 단건·쓰기에는 안 걸었다.** 보드는 그 함정이 특히 크다 —
카드를 옮기는 것은 쓰기인데 화면상으로는 목록을 만지는 것처럼 보이기 때문이다.

여기서 보는 것 다섯:

1. **판·백로그**에 남의 프로젝트 티켓이 안 나온다.
2. **이동**이 404 다(403 이 아니다 — 존재를 알리면 id 를 찍어 목록을 열거할 수 있다).
3. **이름 해석**(`ABCDEF-142` → 티켓)이 범위 밖 티켓의 존재를 알려 주지 않는다.
4. **관계 잇기**가 한쪽만 보이는 상태에서 통하지 않는다 — 통하면 안 보이는 티켓의
   id 가 존재한다는 사실이 새 나간다.
5. **여러 값 조건**(D-497)이 범위를 못 넓힌다 — 모르는 담당자는 목록을 닫고, 남의 프로젝트 ·
   다른 팀 프로젝트를 섞어 줘도 고른 팀의 보이는 티켓만 선다.

## 양쪽을 함께 본다

「안 보인다」만 확인하면 **전부 안 보이는 구현**도 통과한다. 그래서 각 단정에 「우리 팀
것은 보인다」를 함께 둔다.
"""

from __future__ import annotations

from decimal import Decimal

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


def _sprint_on(db, project, *, name, state="planned"):
    """시험 안에서만 쓰는 회차 한 줄 — **그 프로젝트의 팀**의 회차다(D-482). 픽스처에 넣지
    않는 이유는 위 활동 기록과 같다 — 회차가 있으면 판 시험들의 「회차 없음」 전제가 바뀐다."""
    from datetime import date, timedelta

    from app.work.models import Sprint

    row = Sprint(
        name=name, department_id=project.dept_id if project is not None else None,
        org_id=DEFAULT_ORG_ID,
        starts_on=date(2026, 8, 24), ends_on=date(2026, 8, 24) + timedelta(days=7),
        state=state,
    )
    db.add(row)
    db.flush()
    return row


def test_moving_into_an_invisible_sprint_is_404(client, login_as, world, db):
    """🔴 담는 쪽 문도 회차 게이트를 지난다 — 404 다(400 이 아니다).

    「다른 프로젝트의 스프린트에는 넣을 수 없습니다」(400)로 거절하면 그 응답 자체가
    「그 id 의 회차가 존재한다」를 알려 주는 오라클이다 — id 를 찍어 남의 팀 회차를
    열거할 수 있다. 안 보이는 회차는 **없는 것**이어야 한다.
    """
    theirs_sprint = _sprint_on(db, world["theirs"], name="남의팀 회차")
    db.commit()

    r = client.post(
        f"/api/work/board/{world['ours_ticket'].id}/move",
        json={"set_sprint": True, "sprint_id": theirs_sprint.id},
        headers=_hdr(login_as),
    )
    assert r.status_code == 404, f"범위 밖 회차가 404 가 아니다: {r.status_code} {r.text}"


def test_moving_into_a_visible_sprint_still_works(client, login_as, world, db):
    """반례 — 게이트가 「전부 못 담는 구현」이 아님을 확인한다."""
    ours_sprint = _sprint_on(db, world["ours"], name="우리팀 회차")
    db.commit()

    r = client.post(
        f"/api/work/board/{world['ours_ticket'].id}/move",
        json={"set_sprint": True, "sprint_id": ours_sprint.id},
        headers=_hdr(login_as),
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Ticket, world["ours_ticket"].id).sprint_id == ours_sprint.id


def test_a_foreign_neighbour_id_probes_no_rank(client, login_as, world, db):
    """🔴 이웃 id 는 클라이언트 입력이다 — 범위 밖 id 로 남의 순위를 탐침할 수 없다.

    범위 밖 이웃과 **없는 이웃**이 같은 모양(맨 뒤 폴백)으로 떨어져야 한다. 모양이
    다르면 그 차이 자체가 「그 id 가 존재한다」를 알려 주는 오라클이다.
    """
    from decimal import Decimal

    theirs = db.get(Ticket, world["theirs_ticket"].id)
    theirs.backlog_rank = Decimal(50)
    ours = db.get(Ticket, world["ours_ticket"].id)
    ours.backlog_rank = Decimal(100)
    db.commit()

    def move_with(before_id):
        r = client.post(
            f"/api/work/board/{world['ours_ticket'].id}/move",
            json={"reorder": True, "before_id": before_id, "after_id": None},
            headers=_hdr(login_as),
        )
        assert r.status_code == 200, r.text
        db.commit()
        db.expire_all()
        return db.get(Ticket, world["ours_ticket"].id).backlog_rank

    foreign = move_with(world["theirs_ticket"].id)
    # 남의 순위(50) 근처가 아니라 자기 목록 맨 뒤 폴백이다.
    assert foreign > Decimal(100), f"범위 밖 이웃의 순위가 계산에 쓰였다: {foreign}"
    missing = move_with("00000000-0000-0000-0000-000000000000")
    assert missing > foreign, f"없는 이웃과 다른 모양이다: {missing} vs {foreign}"


# ── 여러 값 조건도 범위를 못 넓힌다 (D-497) ───────────────────────────────────

NOBODY = "00000000-0000-0000-0000-000000000000"


def _three_lists(client, headers, params) -> dict[str, set[str]]:
    """판 · 열(「계획」) · 백로그의 티켓 이름. 세 목록이 같은 조건 규칙을 쓰므로 같은 답이어야 한다."""
    board = client.get("/api/work/board", params=params, headers=headers)
    column = client.get("/api/work/board/columns/계획", params=params, headers=headers)
    backlog = client.get("/api/work/backlog", params=params, headers=headers)
    for name, response in (("board", board), ("column", column), ("backlog", backlog)):
        assert response.status_code == 200, f"{name} {params}: {response.status_code} {response.text[:200]}"
    return {
        "board": _keys_on_board(board.json()),
        "column": {c["key"] for c in column.json()["cards"]},
        "backlog": {item["key"] for item in backlog.json()["items"]},
    }


def test_an_unknown_or_foreign_assignee_closes_the_lists_instead_of_opening_them(
    client, login_as, world, db, make_user,
):
    """🔴 담당자 id 가 아무도 가리키지 못하면 목록이 **닫힌다** — 예전에는 조건이 지워져 전부 열렸다.

    해석이 실패한 담당자 조건을 조용히 버리면 필터 없는 목록이 나가고, 사용자는 「그 사람의 일」을
    본다고 믿으면서 팀 전체를 본다. 티켓 목록(`build_filters`)은 이미 닫고 있었고 판 · 백로그만
    열려 있었다. 남의 팀 사람의 id 는 풀리지만 그 사람의 티켓이 범위 밖이라 역시 아무것도 안 나온다.
    """
    from app.core.models_base import join_names
    from app.users.service import get_user_by_email

    mate = get_user_by_email(db, MATE)
    gone = make_user(
        "board-scope-gone@goodmit.co.kr", role="user", display_name="비활성", active=False,
    )
    outsider = make_user("board-scope-outsider@goodmit.co.kr", role="user", display_name="남의팀원")
    outsider.department_id = world["theirs"].dept_id
    db.get(Ticket, world["ours_ticket"].id).assignee_notion_ids = join_names([mate.id])
    db.get(Ticket, world["theirs_ticket"].id).assignee_notion_ids = join_names([outsider.id])
    db.commit()
    headers = _hdr(login_as)

    # 반례 — 풀리는 사람으로 거르면 그 사람의 티켓이 세 목록에 다 보인다.
    for name, got in _three_lists(client, headers, {"assignee_user_id": mate.id}).items():
        assert got == {world["ours_key"]}, f"{name}: 풀리는 담당자로도 안 보인다 — 검사가 헛돈다: {got}"

    for label, value in (
        ("없는 id", NOBODY),
        ("비활성 계정", gone.id),
        ("남의 팀 사람", outsider.id),
        ("없는 id 둘", [NOBODY, "11111111-1111-1111-1111-111111111111"]),
    ):
        for name, got in _three_lists(client, headers, {"assignee_user_id": value}).items():
            assert got == set(), f"{label} 로 거른 {name} 이 열렸다: {got}"


def test_an_unknown_assignee_closes_the_move_position_backlog_too(client, login_as, world, db):
    """「맨 위로」의 기준도 같은 규칙이다 — 모르는 담당자로 거른 백로그는 빈 목록이라 첫 값을 받는다.

    열렸다면 보이는 백로그(우리 티켓 순위 100)를 기준으로 그 바로 위 값이 나온다.
    """
    from app.work.rank import STEP

    mover = Ticket(
        title="옮길 카드", notion_page_id="page-mover", project_uid=world["ours"].id,
        project_link=PROJECT_LINK_OK, status="계획", org_id=DEFAULT_ORG_ID, source="notion",
        backlog_rank=Decimal(10_000),
    )
    db.add(mover)
    db.get(Ticket, world["ours_ticket"].id).backlog_rank = Decimal(100)
    db.commit()

    def top(extra):
        r = client.post(
            f"/api/work/board/{mover.id}/move",
            json={"reorder": True, "to_position": "top", **extra},
            headers=_hdr(login_as),
        )
        assert r.status_code == 200, r.text
        db.expire_all()
        return db.get(Ticket, mover.id).backlog_rank

    assert top({}) == Decimal(100) - STEP, "반례가 서지 않는다 — 전제가 깨졌다"
    assert top({"position_assignee_user_id": [NOBODY]}) == STEP, "모르는 담당자가 조건을 지웠다"


def test_multi_value_project_ids_cannot_widen_the_scope(client, login_as, world):
    """여러 프로젝트를 한꺼번에 줘도 필터는 **좁히기만** 한다 — 남의 프로젝트 id 를 섞어 넣어도
    그 프로젝트의 티켓은 안 나오고, 범위 밖 id 만 주면 아무것도 안 나온다."""
    headers = _hdr(login_as)
    mixed = {"project_id": [world["ours"].id, world["theirs"].id]}
    for name, got in _three_lists(client, headers, mixed).items():
        assert got == {world["ours_key"]}, f"{name}: 여러 값 프로젝트 필터로 범위가 넓어졌다: {got}"
    outside = {"project_id": [world["theirs"].id, NOBODY]}
    for name, got in _three_lists(client, headers, outside).items():
        assert got == set(), f"{name}: 범위 밖 프로젝트로만 걸렀는데 나온다: {got}"


def test_a_visible_project_of_another_team_stays_out_of_the_selected_team(
    client, login_as, world, db,
):
    """팀 문맥(D-482)도 여러 값 필터 아래에서 그대로다 — **보이는** 하위 팀 프로젝트를 섞어 줘도
    고른 팀의 판 · 백로그에는 그 팀 프로젝트의 티켓만 선다.

    하위 팀을 직접 고르면 그 티켓이 보인다(반례) — 막은 것이 가시성이 아니라 팀 절이라는 뜻이다.
    """
    part = Department(name="우리팀 파트", org_id=DEFAULT_ORG_ID, parent_id=world["ours"].dept_id)
    db.add(part)
    db.commit()
    part_project = work_codes.insert_with_code(
        db,
        Project(name="파트 프로젝트", org_id=DEFAULT_ORG_ID, dept_id=part.id, notion_page_id="proj-part"),
    )
    row = Ticket(
        title="파트 티켓", notion_page_id="page-part", project_uid=part_project.id,
        project_link=PROJECT_LINK_OK, status="계획", org_id=DEFAULT_ORG_ID, source="notion",
        notion_ticket_number=33, seq=33,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    part_key = row.canonical_key
    headers = _hdr(login_as)

    for name, got in _three_lists(client, headers, {"department_id": part.id}).items():
        assert got == {part_key}, f"{name}: 하위 팀을 골랐는데 그 팀 티켓이 안 보인다 — 검사가 헛돈다: {got}"

    both = {"project_id": [world["ours"].id, part_project.id]}
    for name, got in _three_lists(client, headers, both).items():
        assert got == {world["ours_key"]}, f"{name}: 다른 팀 프로젝트가 고른 팀에 섞였다: {got}"
    only_part = {"project_id": [part_project.id]}
    for name, got in _three_lists(client, headers, only_part).items():
        assert got == set(), f"{name}: 다른 팀 프로젝트만 걸렀는데 고른 팀 판에 나온다: {got}"
