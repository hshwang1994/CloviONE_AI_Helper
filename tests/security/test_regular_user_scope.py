"""일반 사용자는 **기본이 자기 줄기(branch)** 다 (S4 근본 원인 A → 0060 에서 확장).

## 무엇이 없었나

사용자 지시는 분명했다 — "사용자는 기본적으로 **본인 팀 정보만**". 그런데 그걸 구현한 코드가
저장소에 없었다. 범위 계산이 **역할과 무관하게** `admin_scope` 를 읽는데 그 컬럼의 기본값은
`global` 이고 users 전 행에 그렇게 깔려 있었다. 즉 범위를 올바르게 쓰는 여섯 곳조차
**일반 사용자에게는 전부 no-op** 이었다.

## 조회 범위는 아래로만이 아니라 **위아래 양쪽**이다 (0060)

    굿모닝아이텍
    ├ A
    │  ├ A-1     ← 이 사람은 A(상위 공통)와 A-1 을 본다. A-2·B 는 못 본다.
    │  └ A-2
    └ B

예전에는 하위 전개(descendants)만 했다. 그러면 A-1 사람이 상위 A 부서의 공통 업무를 못 보고,
그 업무를 보려면 A 부서에도 넣어 줘야 하는데 그건 소속을 두 번 적는 것이다. 조상까지 포함하는
**줄기(branch)** 로 바꿨다. 형제 가지(A-2)는 여전히 자동 공유하지 않는다.

## 폴백 규칙이 **뒤집혔다** (0060)

예전 규칙: "부서가 없는 일반 사용자는 좁히지 않는다(전역)". 신규 입사자가 빈 화면을 보면
안 된다는 선의였지만, 결과는 **부서를 안 정한 모든 계정이 전 포털을 보는 것**이었다 —
실측으로 25명 중 21명이 그 상태였다. 편의를 위해 열어 둔 문이 사실상의 기본값이 된 것이다.

새 규칙: 부서 미지정과 조직 직속을 **사람이 구분해 준다**(`users.membership_kind`).
지정 전까지는 **아무것도 안 보인다**(fail-closed). 신규 입사자가 빈 화면을 보는 문제는
관리자 진단 화면이 그 계정을 목록으로 보여 주고 한 번에 지정하게 해서 푼다 — 유출로 푸는
것이 아니라.

`admin_scope` 는 그대로 둔다 — 그건 **관리 범위**이고 이건 **조회 범위**다. 둘은 다른
질문이고, 0060 부터 함수도 둘이다(`management_scope` / `visibility_scope`).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


@pytest.fixture()
def depts(db):
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    parent = Department(name="본부", org_id=DEFAULT_ORG_ID)
    db.add(parent)
    db.flush()
    child = Department(name="우리팀", org_id=DEFAULT_ORG_ID, parent_id=parent.id)
    sibling = Department(name="형제팀", org_id=DEFAULT_ORG_ID, parent_id=parent.id)
    other = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([child, sibling, other])
    db.commit()
    return {"parent": parent, "child": child, "sibling": sibling, "other": other}


def _scope(db, user):
    from app.core.scope import visibility_scope

    return visibility_scope(db, user)


def test_a_regular_user_is_narrowed_to_their_own_department(db, make_user, depts):
    u = make_user("teamonly@goodmit.co.kr", role="user")
    u.department_id = depts["child"].id
    db.commit()

    sc = _scope(db, u)
    assert sc.is_dept, f"일반 사용자가 팀으로 좁혀지지 않았다: {sc.kind}"
    assert depts["child"].id in sc.dept_ids
    assert depts["other"].id not in sc.dept_ids, "다른 줄기의 팀이 범위에 들어왔다"


def test_the_parent_department_is_included_not_just_my_own(db, make_user, depts):
    """하위 팀 사람은 **상위 공통 업무**를 본다 — 같은 줄기이기 때문이다.

    안 그러면 상위 부서의 공통 프로젝트를 보려고 그 사람을 두 부서에 넣어야 하는데,
    그건 소속을 두 번 적는 것이고 두 번 적은 것은 언젠가 갈라진다.
    """
    u = make_user("teamonly-up@goodmit.co.kr", role="user")
    u.department_id = depts["child"].id
    db.commit()

    sc = _scope(db, u)
    assert depts["parent"].id in sc.dept_ids, "상위 부서(공통 업무)가 범위에 없다"


def test_a_sibling_department_is_not_shared(db, make_user, depts):
    """형제 가지는 **자동 공유하지 않는다** — 같은 상위를 둔다고 서로의 업무를 볼 이유는 없다."""
    u = make_user("teamonly-sib@goodmit.co.kr", role="user")
    u.department_id = depts["child"].id
    db.commit()

    sc = _scope(db, u)
    assert depts["sibling"].id not in sc.dept_ids, "형제 팀이 범위에 들어왔다"


def test_the_subtree_is_included_not_just_the_one_department(db, make_user, depts):
    """상위 부서 사람은 하위 팀까지 본다 — 조직도가 계층인데 범위가 한 칸이면 뜻이 없다."""
    u = make_user("hq@goodmit.co.kr", role="user")
    u.department_id = depts["parent"].id
    db.commit()

    sc = _scope(db, u)
    assert depts["child"].id in sc.dept_ids, "하위 팀이 범위에 없다"
    assert depts["sibling"].id in sc.dept_ids, "다른 하위 팀이 범위에 없다"


def test_a_user_with_no_membership_sees_nothing(db, make_user):
    """**폴백 규칙이 뒤집혔다** (0060).

    예전에는 부서 없는 사용자를 전역으로 폴백했다 — 그 편의가 사실상의 기본값이 되어
    실측 25명 중 21명이 전 포털을 봤다. 이제 소속을 모르면 조직 데이터를 아무것도 안 준다.
    """
    u = make_user("nodept@goodmit.co.kr", role="user", membership="unassigned")
    db.commit()

    sc = _scope(db, u)
    assert sc.is_none, f"소속 미지정 계정이 여전히 무언가를 본다: {sc.kind}"
    assert not sc.allows_anything


def test_an_organization_direct_member_sees_the_whole_organization(db, make_user, depts):
    """조직 직속은 **명시적으로 지정**해야 하고, 지정하면 그 조직 전체를 본다.

    "부서가 없다" 를 코드가 조직 직속으로 추측하지 않는다는 것이 핵심이다 — 추측은 언제나
    넓히는 쪽으로 틀린다.
    """
    from app.users.models import MEMBERSHIP_ORGANIZATION

    u = make_user("orgdirect@goodmit.co.kr", role="user", membership=MEMBERSHIP_ORGANIZATION)
    db.commit()

    sc = _scope(db, u)
    assert sc.is_org and sc.org_id == u.org_id


def test_an_admin_still_follows_admin_scope_not_their_department(db, make_user, depts):
    """관리자에게는 **관리 범위**가 답이다. 두 질문을 섞으면 전체 관리자가 자기 부서에 갇힌다."""
    a = make_user("boss@goodmit.co.kr", role="admin")
    a.department_id = depts["child"].id     # 부서는 있지만
    db.commit()                              # admin_scope 는 기본값 global 이다

    from app.core.scope import management_scope

    assert management_scope(db, a).is_global, "관리자가 자기 부서로 갇혔다 — 관리 범위가 무시됐다"
    assert _scope(db, a).is_global, "관리 범위가 전역인데 조회가 더 좁다 — 관리할 수 없게 된다"


def test_a_narrowed_admin_is_still_narrowed(db, make_user, depts):
    """관리자를 부서로 좁혀 두면 그대로 좁혀진다(F2 에서 만든 경로와 이어진다)."""
    from app.core.scope import management_scope
    from app.users.models import ADMIN_SCOPE_DEPT

    a = make_user("deptboss@goodmit.co.kr", role="admin", membership="unassigned")
    a.admin_scope = ADMIN_SCOPE_DEPT
    a.scope_dept_id = depts["child"].id
    db.commit()

    mgmt = management_scope(db, a)
    assert mgmt.is_dept and depts["child"].id in mgmt.dept_ids
    assert depts["parent"].id not in mgmt.dept_ids, (
        "부서 관리자가 상위 부서까지 관리하게 됐다 — 그건 위임이 아니라 승격이다"
    )


def test_search_actually_narrows_for_a_regular_user(client, login_as, make_user, db, depts, app):
    """규칙만 맞고 화면이 안 바뀌면 뜻이 없다 — **검색 결과**로 확인한다.

    검색은 `get_principal` 을 지나는 일반 사용자 경로다. 규칙이 실제로 화면 끝까지
    적용되는지를 여기서 본다.
    """
    from app.search.models import OWNER_DEPARTMENT, SearchDocument

    mine = make_user("mine@goodmit.co.kr", role="user", display_name="우리팀사람")
    theirs = make_user("theirs@goodmit.co.kr", role="user", display_name="남의팀사람")
    mine.department_id = depts["child"].id
    theirs.department_id = depts["other"].id
    db.commit()

    # 문서의 소속은 **Portal 이 정한 Ownership** 이다(0060) — 작성자가 아니다. 작성자
    # 축으로 심으면 사람이 부서를 옮길 때 문서가 따라 움직이는, 지금은 없는 성질을
    # 시험하게 된다.
    with app.state.session_factory() as s:
        for dept_id, title in (
            (depts["child"].id, "우리팀 회의록"),
            (depts["other"].id, "남의팀 회의록"),
        ):
            s.add(SearchDocument(
                kind="document", ref_id=f"ref-{dept_id}", title=title, body="회의",
                owner_kind=OWNER_DEPARTMENT, owner_dept_id=dept_id,
                route="/team-docs", sort_key=title,
            ))
        s.commit()

    login_as("user", email="mine@goodmit.co.kr")
    hits = client.get("/api/search?q=회의록").json()
    titles = {h["title"] for group in hits.get("groups", []) for h in group.get("items", [])}

    assert "우리팀 회의록" in titles, f"자기 팀 문서가 안 보인다: {titles}"
    assert "남의팀 회의록" not in titles, f"남의 팀 문서가 보인다: {titles}"
