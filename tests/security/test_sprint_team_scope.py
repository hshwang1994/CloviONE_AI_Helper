"""회차는 **팀의 것**이다 — 조회 · 편성 · 담기 · 과거 기록, 네 문이 API 에서 어떻게 갈리는가 (D-482).

## 이 파일이 지키는 것

회차(`sprints.department_id`)에는 서로 다른 질문이 넷 있고, 넷이 서로 다른 답을 낸다.
한 함수에 섞이면 한쪽을 고칠 때 다른 쪽이 조용히 넓어진다 — 그래서 넷을 **한 세계에서
같이** 본다.

  1. **조회** — 자기 팀과 그 아래 ∪ 관리 범위. 상위 본부·형제 팀의 회차는 없는 것(404)이다.
     프로젝트 줄기(조상 ∪ 후손)와 다르다: A-1 사람은 A 본부의 회차를 못 본다.
  2. **편성** — 관리 범위가 그 팀을 덮어야 한다. 보이는데 못 고치면 403 이다(404 가 아니다 —
     목록에 나오는 회차에 「없습니다」로 답하면 화면이 거짓말을 한다).
  3. **담기** — 티켓의 팀(프로젝트의 부서) == 회차의 팀, 정확 일치. 하위·상위·형제 팀도,
     조직 공통 프로젝트도 안 된다. 열린 회차에만 적용된다.
  4. **과거 기록** — 닫힌 회차는 담기·빼기·순서·상태·기간·목표 어느 것도 안 바뀐다(이름만).
     프로젝트 팀 이동도 닫힌 회차의 membership 은 건드리지 않고 오류로도 세지 않는다.

## 양쪽을 함께 본다

「안 보인다·안 된다」만 확인하면 **전부 막는 구현**도 통과한다. 그래서 각 단정에 같은
사람이 **되는 것**을 함께 둔다.

부서 세계는 `tests/fixtures/org_tree.py` 를 그대로 쓴다 — GMI › A{A-1, A-2} · B{B-1, B-2}.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department, Organization
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_MISSING, PROJECT_LINK_OK, Ticket
from app.users.models import MEMBERSHIP_DEPARTMENT
from app.work import codes as work_codes
from app.work.models import Sprint
from tests.fixtures.org_tree import (  # noqa: F401 — fixture 재수출
    D_A, D_A1, D_A2, D_B, D_B1, D_B2, org_tree, people, resources,
)

pytestmark = pytest.mark.security

TODAY = date(2026, 8, 27)
ROLE_OF = {
    "org_direct": "user", "a": "user", "a1": "user", "a2": "user", "b1": "user",
    "unassigned": "user", "a_admin": "admin", "a1_admin": "admin", "org_admin": "admin",
    "global_admin": "system_admin", "sub_admin": "admin", "auditor": "auditor",
    "operator": "operator", "stranger": "user",
}


def _hdr(login_as, key: str) -> dict:
    return {"X-CSRF-Token": login_as(ROLE_OF[key], email=f"{key}@goodmit.co.kr")}


@pytest.fixture()
def world(db, make_user, org_tree, people, resources):
    """팀별 회차 + 팀별 백로그 티켓 + 닫힌 회차의 기록 + 추가 인물 넷.

    추가 인물: `sub_admin`(A 소속·A-1 관리 — 보이지만 못 고치는 사람), `auditor`(조직 감사자),
    `operator`(조직 운영자 — 기본 관리 범위가 조직), `stranger`(다른 조직 사람).
    """
    projects = resources["projects"]

    sub_admin = make_user("sub_admin@goodmit.co.kr", role="admin", display_name="파트장")
    sub_admin.org_id = DEFAULT_ORG_ID
    sub_admin.department_id = D_A
    sub_admin.membership_kind = MEMBERSHIP_DEPARTMENT
    sub_admin.admin_scope = "dept"
    sub_admin.scope_dept_id = D_A1
    sub_admin.scope_org_id = DEFAULT_ORG_ID
    auditor = make_user("auditor@goodmit.co.kr", role="auditor", display_name="감사자")
    auditor.org_id = DEFAULT_ORG_ID
    operator = make_user("operator@goodmit.co.kr", role="operator", display_name="운영자")
    operator.org_id = DEFAULT_ORG_ID

    other_org = Organization(id="sprint-team-other-org", slug="other-sprint-org", name="다른 조직")
    db.add(other_org)
    db.flush()
    other_team = Department(name="다른 조직 팀", org_id=other_org.id)
    db.add(other_team)
    db.flush()
    stranger = make_user("stranger@goodmit.co.kr", role="user", display_name="타조직")
    stranger.org_id = other_org.id
    stranger.department_id = other_team.id
    stranger.membership_kind = MEMBERSHIP_DEPARTMENT
    db.commit()

    def sprint(name, team, state, *, start, days=7):
        row = Sprint(
            name=name, department_id=team, org_id=DEFAULT_ORG_ID,
            starts_on=start, ends_on=start + timedelta(days=days), state=state,
        )
        db.add(row)
        db.flush()
        return row

    sprints = {
        "a_91": sprint("9-1", D_A, "closed", start=TODAY - timedelta(days=14)),
        "a_92": sprint("9-2", D_A, "active", start=TODAY - timedelta(days=3)),
        "a_93": sprint("9-3", D_A, "planned", start=TODAY + timedelta(days=5)),
        "a1_91": sprint("9-1", D_A1, "active", start=TODAY - timedelta(days=3)),
        "a2_90": sprint("9-0", D_A2, "closed", start=TODAY - timedelta(days=21)),
        "b_92": sprint("9-2", D_B, "active", start=TODAY - timedelta(days=3)),
        "b1_93": sprint("9-3", D_B1, "planned", start=TODAY + timedelta(days=5)),
        "none": sprint("팀 미정 회차", None, "planned", start=TODAY - timedelta(days=3)),
    }

    counter = {"n": 900}

    def ticket(title, project, *, status="계획", sprint_id=None, link=PROJECT_LINK_OK):
        counter["n"] += 1
        n = counter["n"]
        row = Ticket(
            title=title, notion_page_id=f"st-page-{n}",
            project_uid=project.id if project is not None else None, project_link=link,
            status=status, org_id=DEFAULT_ORG_ID, source="notion",
            # 프로젝트 없는 예외 티켓은 번호도 없다(D-197) — 트리거가 그 조합을 거절한다.
            notion_ticket_number=n, seq=n if project is not None else None, sprint_id=sprint_id,
            est_wd=2.0, due_date=TODAY + timedelta(days=2),
        )
        db.add(row)
        db.flush()
        db.refresh(row)
        return row

    tickets = {
        "ta": ticket("A 백로그", projects["a"]),
        "ta_in": ticket("A 진행", projects["a"], status="진행", sprint_id=sprints["a_92"].id),
        "ta1": ticket("A-1 백로그", projects["a1"]),
        "ta1_in": ticket("A-1 진행", projects["a1"], status="진행", sprint_id=sprints["a1_91"].id),
        "ta2_closed": ticket("A-2 옛 일", projects["a2"], status="완료", sprint_id=sprints["a2_90"].id),
        "tb": ticket("B 백로그", projects["b"]),
        "torg": ticket("조직 공통 백로그", projects["org"]),
        "closed_open": ticket("닫힌 회차에 남은 일", projects["a"], status="진행",
                              sprint_id=sprints["a_91"].id),
        "closed_done": ticket("닫힌 회차의 끝난 일", projects["a"], status="완료",
                              sprint_id=sprints["a_91"].id),
        "no_project": ticket("프로젝트 없는 예외", None, link=PROJECT_LINK_MISSING),
    }
    db.commit()
    return {
        "projects": projects, "sprints": sprints, "tickets": tickets,
        "other_org": other_org, "other_team": other_team,
    }


def _list(client, login_as, key, team):
    return client.get(
        "/api/work/sprints", params={"department_id": team} if team else {},
        headers=_hdr(login_as, key),
    )


def _meeting(client, login_as, key, sprint_id):
    return client.get(f"/api/work/sprints/{sprint_id}/meeting", headers=_hdr(login_as, key))


def _move(client, login_as, key, ticket_id, **body):
    return client.post(
        f"/api/work/board/{ticket_id}/move", json=body, headers=_hdr(login_as, key)
    )


def _names(res) -> set[str]:
    assert res.status_code == 200, res.text
    return {s["name"] for s in res.json()["sprints"]}


# ── 1 · 조회 — 자기 팀과 그 아래, 그리고 관리 범위 ──────────────────────────


@pytest.mark.parametrize(
    "key, visible, hidden",
    [
        # 팀 사람은 자기 팀만. 상위 본부(A)도, 형제(A-2)도, 사촌(B-1)도 없는 것이다.
        ("a1", [D_A1], [D_A, D_A2, D_B, D_B1]),
        # 본부 사람은 본부와 그 아래 — 다른 본부는 없다.
        ("a", [D_A, D_A1, D_A2], [D_B, D_B1]),
        # A-1 관리자(A-1 소속)는 A-1 뿐이다 — 관리 범위는 아래로만 간다.
        ("a1_admin", [D_A1], [D_A, D_A2, D_B]),
        # A 관리자는 A 와 그 아래.
        ("a_admin", [D_A, D_A1, D_A2], [D_B, D_B1]),
        # A 소속 + A-1 관리 — 소속으로 A 줄기를 보고, 관리로 A-1 을 고친다.
        ("sub_admin", [D_A, D_A1, D_A2], [D_B]),
        # 조직 관리자 · 전역 · 조직 직속 · 운영자 · 감사자는 조직의 모든 팀.
        ("org_admin", [D_A, D_A1, D_A2, D_B, D_B1, D_B2], []),
        ("global_admin", [D_A, D_A1, D_B1], []),
        ("org_direct", [D_A, D_A1, D_B], []),
        ("operator", [D_A, D_A1, D_B], []),
        ("auditor", [D_A, D_A1, D_B], []),
        ("b1", [D_B1], [D_B, D_A, D_A1]),
        # 소속 미지정과 다른 조직 사람은 아무 팀도 없다.
        ("unassigned", [], [D_A, D_A1, D_B]),
        ("stranger", [], [D_A, D_A1, D_B]),
    ],
)
def test_sprint_lists_follow_team_visibility(client, login_as, world, key, visible, hidden):
    for team in visible:
        res = _list(client, login_as, key, team)
        assert res.status_code == 200, f"{key} 가 {team} 의 회차를 못 본다: {res.text}"
    for team in hidden:
        res = _list(client, login_as, key, team)
        assert res.status_code == 404, f"{key} 에게 {team} 이 보인다: {res.status_code} {res.text}"


def test_a_team_member_sees_only_their_own_teams_sprints_by_id(client, login_as, world):
    """🔴 목록에서 가린 회차는 **id 로도 없다** — 회의 · 집계 · 판 전부 404 다."""
    s = world["sprints"]
    for hidden in ("a_92", "a_93", "b_92"):
        assert _meeting(client, login_as, "a1", s[hidden].id).status_code == 404, hidden
        scope = client.get(f"/api/work/sprints/{s[hidden].id}/scope", headers=_hdr(login_as, "a1"))
        assert scope.status_code == 404, hidden
        board = client.get(
            "/api/work/board", params={"sprint_id": s[hidden].id}, headers=_hdr(login_as, "a1"),
        )
        assert board.status_code == 404, hidden
    # 반례 — 자기 팀 회차는 셋 다 열린다.
    assert _meeting(client, login_as, "a1", s["a1_91"].id).status_code == 200
    scope = client.get(f"/api/work/sprints/{s['a1_91'].id}/scope", headers=_hdr(login_as, "a1"))
    assert scope.status_code == 200 and scope.json()["tickets"] == 1, scope.text
    board = client.get(
        "/api/work/board", params={"sprint_id": s["a1_91"].id}, headers=_hdr(login_as, "a1"),
    )
    assert board.status_code == 200, board.text


def test_a_parent_unit_member_sees_child_team_sprints(client, login_as, world):
    """본부 사람은 하위 팀의 회차를 본다 — 하지만 편성은 못 한다(아래 §2)."""
    s = world["sprints"]
    assert _meeting(client, login_as, "a", s["a1_91"].id).status_code == 200
    assert _names(_list(client, login_as, "a", D_A1)) == {"9-1"}
    assert _names(_list(client, login_as, "a", D_A)) == {"9-1", "9-2", "9-3"}


def test_another_organization_sees_nothing_at_all(client, login_as, world):
    s = world["sprints"]
    for sid in (s["a_92"].id, s["b_92"].id, s["none"].id):
        assert _meeting(client, login_as, "stranger", sid).status_code == 404
    res = _list(client, login_as, "stranger", None)
    assert res.status_code == 200, res.text
    # 자기 조직의 팀만 후보다 — 우리 조직의 여섯 팀은 하나도 없고, 회차도 없다.
    assert {o["id"] for o in res.json()["team"]["options"]} == {world["other_team"].id}
    assert res.json()["sprints"] == []
    for team in (D_A, D_A1, D_B):
        assert _list(client, login_as, "stranger", team).status_code == 404, team


def test_unassigned_sprints_are_for_org_scope_only(client, login_as, world):
    """팀 미정(레거시) 회차는 조직·전역 범위에만 보인다 — 팀 사람의 주기가 아니다."""
    assert _names(_list(client, login_as, "org_admin", "none")) == {"팀 미정 회차"}
    assert _names(_list(client, login_as, "global_admin", "none")) == {"팀 미정 회차"}
    assert _names(_list(client, login_as, "a_admin", "none")) == set()
    assert _names(_list(client, login_as, "a", "none")) == set()
    none_id = world["sprints"]["none"].id
    assert _meeting(client, login_as, "a_admin", none_id).status_code == 404
    assert _meeting(client, login_as, "org_admin", none_id).status_code == 200


def test_the_team_envelope_offers_visible_teams_and_marks_manageable_ones(client, login_as, world):
    """팀 선택기의 후보 = 조회 집합, `manageable` = 편성 집합. 두 집합이 다르다는 것이 요점이다."""
    a = _list(client, login_as, "a", None).json()["team"]
    assert a["selected"] == D_A
    assert {o["id"] for o in a["options"]} == {D_A, D_A1, D_A2}
    assert not any(o["manageable"] for o in a["options"])
    assert a["manageable"] is False

    sub = _list(client, login_as, "sub_admin", None).json()["team"]
    assert {o["id"]: o["manageable"] for o in sub["options"]} == {D_A: False, D_A1: True, D_A2: False}
    assert [p["name"] for p in next(o for o in sub["options"] if o["id"] == D_A1)["path"]] == ["A본부", "A-1팀"]

    a1 = _list(client, login_as, "a1", None).json()
    assert a1["team"]["selected"] == D_A1 and len(a1["team"]["options"]) == 1
    assert {s["name"] for s in a1["sprints"]} == {"9-1"}

    direct = _list(client, login_as, "org_direct", None).json()
    # 조직 직속 — 후보는 여섯이고 기본 선택은 없다. 「전체」라는 회차 목록은 없다.
    assert direct["team"]["selected"] is None and len(direct["team"]["options"]) == 6
    assert direct["sprints"] == []


# ── 2 · 편성 — 관리 범위 ∧ PROJECT_WRITE, 조회와 다른 문 ─────────────────────


def test_seeing_a_sprint_does_not_let_you_plan_it(client, login_as, world):
    """🔴 보이는데 관리 범위 밖이면 **403** — 404 가 아니다. 자기 범위는 그대로 된다."""
    s = world["sprints"]
    assert _meeting(client, login_as, "sub_admin", s["a_93"].id).status_code == 200
    # 로그인은 요청마다 새로 한다(`_hdr`) — 세션이 바뀌면 앞서 받은 CSRF 토큰은 죽는다.
    res = client.patch(f"/api/work/sprints/{s['a_93'].id}", json={"name": "9-3 개명"}, headers=_hdr(login_as, "sub_admin"))
    assert res.status_code == 403, res.text
    res = client.post(f"/api/work/sprints/{s['a_93'].id}/state", json={"state": "active"}, headers=_hdr(login_as, "sub_admin"))
    assert res.status_code == 403, res.text
    res = client.delete(f"/api/work/sprints/{s['a_93'].id}", headers=_hdr(login_as, "sub_admin"))
    assert res.status_code == 403, res.text
    res = client.post(f"/api/work/sprints/{s['a_92'].id}/close", json={"target_sprint_id": None}, headers=_hdr(login_as, "sub_admin"))
    assert res.status_code == 403, res.text
    res = client.post(
        "/api/work/sprints",
        json={"name": "A 새 회차", "starts_on": "2026-10-01", "ends_on": "2026-10-08", "department_id": D_A},
        headers=_hdr(login_as, "sub_admin"),
    )
    assert res.status_code == 403, res.text
    # 반례 — A-1 은 관리 범위다.
    res = client.patch(f"/api/work/sprints/{s['a1_91'].id}", json={"name": "9-1 개명"}, headers=_hdr(login_as, "sub_admin"))
    assert res.status_code == 200 and res.json()["name"] == "9-1 개명", res.text
    res = client.post(
        "/api/work/sprints",
        json={"name": "A-1 새 회차", "starts_on": "2026-10-01", "ends_on": "2026-10-08", "department_id": D_A1},
        headers=_hdr(login_as, "sub_admin"),
    )
    assert res.status_code == 200 and res.json()["department_id"] == D_A1, res.text


def test_an_invisible_sprint_is_not_found_even_for_a_manager(client, login_as, world):
    """A 관리자가 B 회차를 만지면 403 이 아니라 **404** — 존재를 알리지 않는다."""
    s = world["sprints"]
    hdr = _hdr(login_as, "a_admin")
    res = client.patch(f"/api/work/sprints/{s['b_92'].id}", json={"name": "x"}, headers=hdr)
    assert res.status_code == 404, res.text
    res = client.post(
        "/api/work/sprints",
        json={"name": "B 에 만들기", "starts_on": "2026-10-01", "ends_on": "2026-10-08", "department_id": D_B},
        headers=hdr,
    )
    assert res.status_code == 404, res.text


def test_plain_members_and_auditors_cannot_plan_but_can_read(client, login_as, world):
    """일반 팀원은 판의 상태 이동은 되고 편성(담기·빼기·회차 쓰기)은 403 이다. 감사자는
    읽기만 된다 — 상태 이동 · 담기 · 회의록 전부 403."""
    s, t = world["sprints"], world["tickets"]
    # 일반 팀원 — 담기는 403, 상태 이동은 200.
    res = _move(client, login_as, "a", t["ta"].id, set_sprint=True, sprint_id=s["a_92"].id)
    assert res.status_code == 403, res.text
    res = _move(client, login_as, "a", t["ta_in"].id, to_status="검증")
    assert res.status_code == 200, res.text
    res = client.post(f"/api/work/sprints/{s['a_93'].id}/state", json={"state": "active"}, headers=_hdr(login_as, "a"))
    assert res.status_code == 403, res.text
    # 감사자 — 목록·회의 200, 나머지 403.
    assert _list(client, login_as, "auditor", D_A).status_code == 200
    assert _meeting(client, login_as, "auditor", s["a_92"].id).status_code == 200
    res = _move(client, login_as, "auditor", t["ta_in"].id, to_status="완료")
    assert res.status_code == 403, res.text
    res = _move(client, login_as, "auditor", t["ta_in"].id, reorder=True, on_board=True)
    assert res.status_code == 403, res.text
    res = _move(client, login_as, "auditor", t["ta"].id, set_sprint=True, sprint_id=s["a_92"].id)
    assert res.status_code == 403, res.text
    res = client.post(f"/api/work/sprints/{s['a_92'].id}/close", json={"target_sprint_id": None}, headers=_hdr(login_as, "auditor"))
    assert res.status_code == 403, res.text
    res = client.post(
        f"/api/work/sprints/{s['a_92'].id}/decisions",
        json={"kind": "decision", "body": "감사자가 적은 줄"}, headers=_hdr(login_as, "auditor"),
    )
    assert res.status_code == 403, res.text
    # 반례 — 회차가 보이는 팀원은 회의록을 적는다.
    res = client.post(
        f"/api/work/sprints/{s['a_92'].id}/decisions",
        json={"kind": "decision", "body": "팀원이 적은 줄"}, headers=_hdr(login_as, "a"),
    )
    assert res.status_code == 200, res.text


def test_an_operator_manages_every_team_in_the_organization(client, login_as, world):
    """운영자의 기본 관리 범위는 조직이다 — 어느 팀의 회차든 편성한다."""
    s = world["sprints"]
    res = client.post(f"/api/work/sprints/{s['b1_93'].id}/state", json={"state": "active"}, headers=_hdr(login_as, "operator"))
    assert res.status_code == 200 and res.json()["state"] == "active", res.text


# ── 3 · 팀별 활성 · 같은 이름 · 정렬 ───────────────────────────────────────


def test_teams_run_active_sprints_side_by_side_and_names_collide_only_within_a_team(client, login_as, world):
    s = world["sprints"]
    listed = _list(client, login_as, "global_admin", D_A).json()["sprints"]
    # 정렬은 (starts_on DESC, created_at DESC, id) — 9-3 · 9-2 · 9-1.
    assert [x["name"] for x in listed] == ["9-3", "9-2", "9-1"], listed
    active = {(x["department_id"], x["name"]) for team in (D_A, D_A1, D_B)
              for x in _list(client, login_as, "global_admin", team).json()["sprints"]
              if x["state"] == "active"}
    assert active == {(D_A, "9-2"), (D_A1, "9-1"), (D_B, "9-2")}
    # 같은 팀의 둘째 활성은 409, A 의 「9-2」와 B 의 「9-2」는 서로 다른 회차다.
    res = client.post(f"/api/work/sprints/{s['a_93'].id}/state", json={"state": "active"}, headers=_hdr(login_as, "global_admin"))
    assert res.status_code == 409, res.text
    assert s["a_92"].id != s["b_92"].id
    res = client.post(
        "/api/work/sprints",
        json={"name": "9-2", "starts_on": "2026-10-01", "ends_on": "2026-10-08", "department_id": D_A},
        headers=_hdr(login_as, "global_admin"),
    )
    assert res.status_code == 409, res.text
    res = client.post(
        "/api/work/sprints",
        json={"name": "9-2", "starts_on": "2026-10-01", "ends_on": "2026-10-08", "department_id": D_B2},
        headers=_hdr(login_as, "global_admin"),
    )
    assert res.status_code == 200, res.text


def test_a_unit_without_projects_can_still_own_a_sprint(client, login_as, world):
    """「프로젝트가 있어야 팀」이라는 규칙은 없다 — B-2 에는 프로젝트가 없다."""
    res = client.post(
        "/api/work/sprints",
        json={"name": "B-2 첫 회차", "starts_on": "2026-10-01", "ends_on": "2026-10-08", "department_id": D_B2},
        headers=_hdr(login_as, "org_admin"),
    )
    assert res.status_code == 200 and res.json()["department_id"] == D_B2, res.text


# ── 4 · 담기 — 정확 일치, 열린 회차만 ─────────────────────────────────────


def test_eligibility_is_an_exact_team_match(client, login_as, world):
    """🔴 하위 팀 · 상위 본부 · 형제 · 다른 본부 · 조직 공통 — 전부 422. 같은 팀만 200."""
    s, t = world["sprints"], world["tickets"]
    cases = [
        ("A-1 티켓을 A 회차에", t["ta1"].id, s["a_92"].id),
        ("A 티켓을 A-1 회차에", t["ta"].id, s["a1_91"].id),
        ("B 티켓을 A 회차에", t["tb"].id, s["a_92"].id),
        ("조직 공통 티켓을 A 회차에", t["torg"].id, s["a_92"].id),
        ("프로젝트 없는 티켓을 A 회차에", t["no_project"].id, s["a_92"].id),
    ]
    for label, ticket_id, sprint_id in cases:
        res = _move(client, login_as, "global_admin", ticket_id, set_sprint=True, sprint_id=sprint_id)
        assert res.status_code == 422, f"{label}: {res.status_code} {res.text}"
    res = _move(client, login_as, "global_admin", t["ta"].id, set_sprint=True, sprint_id=s["a_92"].id)
    assert res.status_code == 200, res.text
    assert res.json()["ticket"]["sprint_id"] == s["a_92"].id


def test_the_backlog_is_the_teams_projects_exactly(client, login_as, world):
    """백로그 = 그 팀 프로젝트(정확 일치)의 미담김 티켓. 담을 수 있는 것과 같은 집합이다."""
    res = client.get("/api/work/backlog", params={"department_id": D_A}, headers=_hdr(login_as, "a_admin"))
    assert res.status_code == 200, res.text
    titles = {i["title"] for i in res.json()["items"]}
    assert titles == {"A 백로그"}, titles
    assert res.json()["team"]["selected"] == D_A and res.json()["team"]["manageable"] is True
    res = client.get("/api/work/backlog", params={"department_id": D_A1}, headers=_hdr(login_as, "a_admin"))
    assert {i["title"] for i in res.json()["items"]} == {"A-1 백로그"}
    # 조직 공통·프로젝트 없는 티켓은 어느 팀 백로그에도 없다.
    everything = set()
    for team in (D_A, D_A1, D_A2, D_B, D_B1, D_B2):
        res = client.get("/api/work/backlog", params={"department_id": team}, headers=_hdr(login_as, "global_admin"))
        everything |= {i["title"] for i in res.json()["items"]}
    assert "조직 공통 백로그" not in everything and "프로젝트 없는 예외" not in everything


def test_a_ticket_already_in_another_sprint_is_not_moved_silently(client, login_as, world):
    """🔴 다른 회차에 든 티켓 담기는 409 — 먼저 빼고 담는다. 같은 회차는 no-op 이다."""
    s, t = world["sprints"], world["tickets"]
    res = _move(client, login_as, "global_admin", t["ta_in"].id, set_sprint=True, sprint_id=s["a_93"].id)
    assert res.status_code == 409, res.text
    before = _move(client, login_as, "global_admin", t["ta_in"].id, set_sprint=True, sprint_id=s["a_92"].id)
    assert before.status_code == 200, before.text
    again = _move(client, login_as, "global_admin", t["ta_in"].id, set_sprint=True, sprint_id=s["a_92"].id)
    assert again.json()["ticket"]["version"] == before.json()["ticket"]["version"], "no-op 이 버전을 올렸다"
    removed = _move(client, login_as, "global_admin", t["ta_in"].id, set_sprint=True, sprint_id=None)
    assert removed.status_code == 200 and removed.json()["ticket"]["sprint_id"] is None, removed.text
    added = _move(client, login_as, "global_admin", t["ta_in"].id, set_sprint=True, sprint_id=s["a_93"].id)
    assert added.status_code == 200 and added.json()["ticket"]["sprint_id"] == s["a_93"].id, added.text


def test_creating_a_ticket_inside_a_sprint_passes_the_same_gates(client, login_as, world, db):
    s, p = world["sprints"], world["projects"]

    def create(key, project, sprint):
        return client.post(
            "/api/tickets",
            json={"title": "새 일", "project_id": project.id, "est_wd": 1, "due_date": "2026-09-30",
                  "sprint_id": sprint.id},
            headers=_hdr(login_as, key),
        )

    assert create("global_admin", p["a1"], s["a_92"]).status_code == 422       # 다른 팀
    assert create("global_admin", p["org"], s["a_92"]).status_code == 422      # 조직 공통
    assert create("global_admin", p["a"], s["a_91"]).status_code == 422        # 닫힌 회차
    assert create("global_admin", p["a"], s["none"]).status_code == 422        # 팀 미정
    assert create("a", p["a"], s["a_92"]).status_code == 403                   # 편성 권한 없음
    assert create("sub_admin", p["a"], s["a_92"]).status_code == 403           # 관리 범위 밖
    ok = create("a_admin", p["a"], s["a_92"])
    assert ok.status_code == 200, ok.text
    db.expire_all()
    assert db.get(Ticket, ok.json()["ticket"]["uid"]).sprint_id == s["a_92"].id


def test_an_unassigned_sprint_takes_nothing_until_it_gets_a_team(client, login_as, world):
    s, t = world["sprints"], world["tickets"]
    res = _move(client, login_as, "org_admin", t["ta"].id, set_sprint=True, sprint_id=s["none"].id)
    assert res.status_code == 422, res.text
    res = client.post(f"/api/work/sprints/{s['none'].id}/state", json={"state": "active"}, headers=_hdr(login_as, "org_admin"))
    assert res.status_code == 422, res.text
    # 팀을 정해 주면 보통 회차가 된다 — 그 뒤로는 A 의 규칙을 따른다.
    res = client.patch(f"/api/work/sprints/{s['none'].id}", json={"department_id": D_A}, headers=_hdr(login_as, "org_admin"))
    assert res.status_code == 200 and res.json()["department_id"] == D_A, res.text
    res = _move(client, login_as, "org_admin", t["ta"].id, set_sprint=True, sprint_id=s["none"].id)
    assert res.status_code == 200, res.text
    assert _names(_list(client, login_as, "a", D_A)) == {"9-1", "9-2", "9-3", "팀 미정 회차"}


# ── 5 · 닫힌 회차는 과거 기록이다 ───────────────────────────────────────────


def test_a_closed_sprint_rejects_every_change_but_its_name(client, login_as, world):
    s, t = world["sprints"], world["tickets"]
    closed = s["a_91"].id

    def hdr():
        # 로그인은 요청마다 새로 한다 — 세션이 바뀌면 앞서 받은 CSRF 토큰은 죽는다.
        return _hdr(login_as, "global_admin")

    # 담기 · 빼기 · 순서 · 상태 — 전부 422.
    assert _move(client, login_as, "global_admin", t["ta"].id, set_sprint=True, sprint_id=closed).status_code == 422
    assert _move(client, login_as, "global_admin", t["closed_open"].id, set_sprint=True, sprint_id=None).status_code == 422
    assert _move(client, login_as, "global_admin", t["closed_open"].id, reorder=True, on_board=True).status_code == 422
    assert _move(client, login_as, "global_admin", t["closed_open"].id, to_status="완료").status_code == 422
    res = client.patch(f"/api/tickets/{t['closed_open'].notion_page_id}", json={"status": "완료"}, headers=hdr())
    assert res.status_code == 422, res.text
    # 기간 · 목표 · 재개방 · 삭제 — 안 된다. 이름은 된다.
    assert client.patch(f"/api/work/sprints/{closed}", json={"goal": "새 목표"}, headers=hdr()).status_code == 422
    assert client.patch(f"/api/work/sprints/{closed}", json={"ends_on": "2026-12-31"}, headers=hdr()).status_code == 422
    assert client.post(f"/api/work/sprints/{closed}/state", json={"state": "active"}, headers=hdr()).status_code == 409
    assert client.delete(f"/api/work/sprints/{closed}", headers=hdr()).status_code == 422
    assert client.post(f"/api/work/sprints/{closed}/close", json={"target_sprint_id": None}, headers=hdr()).status_code == 409
    res = client.patch(f"/api/work/sprints/{closed}", json={"name": "9-1(정정)"}, headers=hdr())
    assert res.status_code == 200 and res.json()["name"] == "9-1(정정)", res.text
    # 리뷰와 회의록은 그대로다.
    body = _meeting(client, login_as, "global_admin", closed).json()
    assert {x["title"] for x in body["tickets"]} == {"닫힌 회차에 남은 일", "닫힌 회차의 끝난 일"}
    res = client.post(f"/api/work/sprints/{closed}/decisions", json={"kind": "decision", "body": "회고"}, headers=hdr())
    assert res.status_code == 200, res.text


def test_moving_a_ticket_to_another_teams_project_is_blocked_only_in_open_sprints(client, login_as, world):
    """열린 회차의 티켓은 같은 팀 프로젝트로만 옮긴다. 닫힌 회차의 티켓은 기록이라 막지 않는다."""
    s, t, p = world["sprints"], world["tickets"], world["projects"]
    hdr = _hdr(login_as, "global_admin")
    res = client.patch(f"/api/tickets/{t['ta_in'].notion_page_id}", json={"project_id": p["b"].id}, headers=hdr)
    assert res.status_code == 422, res.text
    res = client.patch(f"/api/tickets/{t['ta_in'].notion_page_id}", json={"project_id": p["a2"].id}, headers=hdr)
    assert res.status_code == 422, res.text
    # 닫힌 회차 — 옮겨지고, 회차 membership 은 그대로 남는다.
    res = client.patch(f"/api/tickets/{t['closed_done'].notion_page_id}", json={"project_id": p["b"].id}, headers=hdr)
    assert res.status_code == 200, res.text
    body = _meeting(client, login_as, "global_admin", s["a_91"].id).json()
    assert "닫힌 회차의 끝난 일" in {x["title"] for x in body["tickets"]}


def test_changing_a_projects_team_is_blocked_by_open_sprint_membership_only(client, login_as, world):
    s, p = world["sprints"], world["projects"]
    hdr = _hdr(login_as, "global_admin")
    # 프로젝트 a 의 티켓이 열린 9-2 에 있다 → B 로 못 옮긴다.
    res = client.patch(f"/api/projects/{p['a'].id}", json={"dept_id": D_B}, headers=hdr)
    assert res.status_code == 422, res.text
    # 프로젝트 a2 의 티켓은 **닫힌** 회차에만 있다 → 옮겨진다. 닫힌 회차의 소유는 그대로다.
    res = client.patch(f"/api/projects/{p['a2'].id}", json={"dept_id": D_B}, headers=hdr)
    assert res.status_code == 200, res.text
    body = _meeting(client, login_as, "global_admin", s["a2_90"].id).json()
    assert body["sprint"]["department_id"] == D_A2
    assert {x["title"] for x in body["tickets"]} == {"A-2 옛 일"}
    integrity = client.get("/api/admin/integrity", headers=hdr).json()
    off = next(f for f in integrity["findings"] if f["key"] == "open_sprint_tickets_off_team")
    assert off["count"] == 0, off


# ── 6 · 닫기와 이월 ─────────────────────────────────────────────────────────


def test_closing_carries_over_within_the_team_or_returns_to_the_backlog(client, login_as, world):
    s, t = world["sprints"], world["tickets"]
    hdr = _hdr(login_as, "global_admin")
    # 다른 팀의 회차로는 못 보낸다.
    res = client.post(f"/api/work/sprints/{s['b_92'].id}/close", json={"target_sprint_id": s["b1_93"].id}, headers=hdr)
    assert res.status_code == 422, res.text
    # 같은 팀의 열린 회차로 보낸다.
    res = client.post(f"/api/work/sprints/{s['a_92'].id}/close", json={"target_sprint_id": s["a_93"].id}, headers=hdr)
    assert res.status_code == 200 and res.json()["carried_over"] == 1, res.text
    board = client.get("/api/work/board", params={"sprint_id": s["a_93"].id}, headers=hdr).json()
    assert {c["title"] for col in board["columns"] for c in col["cards"]} == {"A 진행"}
    # 대상이 없으면(같은 팀에 열린 회차가 없어도) 닫히고, 안 끝난 일은 백로그로 돌아간다.
    res = client.post(f"/api/work/sprints/{s['a1_91'].id}/close", json={"target_sprint_id": None}, headers=hdr)
    assert res.status_code == 200 and res.json()["carried_over"] == 1, res.text
    backlog = client.get("/api/work/backlog", params={"department_id": D_A1}, headers=hdr).json()
    assert {i["title"] for i in backlog["items"]} == {"A-1 백로그", "A-1 진행"}


# ── 7 · 판 · 회의의 팀 문맥 ─────────────────────────────────────────────────


def test_the_board_refuses_a_sprint_from_another_team_context(client, login_as, world):
    s = world["sprints"]
    hdr = _hdr(login_as, "a_admin")
    res = client.get("/api/work/board", params={"department_id": D_A1, "sprint_id": s["a_92"].id}, headers=hdr)
    assert res.status_code == 422, res.text
    res = client.get("/api/work/board", params={"department_id": D_A, "sprint_id": s["a_92"].id}, headers=hdr)
    assert res.status_code == 200 and res.json()["team"]["selected"] == D_A, res.text
    # 회차 없이 팀만 고르면 그 팀 프로젝트의 실행분이다 — 하위 팀·조직 공통은 없다.
    res = client.get("/api/work/board", params={"department_id": D_A}, headers=hdr).json()
    titles = {c["title"] for col in res["columns"] for c in col["cards"]}
    assert "A 백로그" in titles and "A-1 백로그" not in titles and "조직 공통 백로그" not in titles


def test_the_meeting_project_filter_narrows_discussion_only(client, login_as, world):
    s, p = world["sprints"], world["projects"]
    hdr = _hdr(login_as, "a_admin")
    whole = client.get(f"/api/work/sprints/{s['a_92'].id}/meeting", headers=hdr).json()
    narrowed = client.get(
        f"/api/work/sprints/{s['a_92'].id}/meeting", params={"project_id": p["b"].id}, headers=hdr,
    ).json()
    assert whole["discuss_project_id"] is None and narrowed["discuss_project_id"] == p["b"].id
    assert narrowed["summary"] == whole["summary"]
    assert all(b["total"] == 0 for b in narrowed["discuss"].values())
    assert whole["team"]["id"] == D_A and [x["name"] for x in whole["team"]["path"]] == ["A본부"]
    assert whole["neighbours"]["prev"]["name"] == "9-1" and whole["neighbours"]["next"]["name"] == "9-3"
