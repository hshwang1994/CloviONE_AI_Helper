"""일반 사용자는 **기본이 자기 팀**이다 (S4 근본 원인 A).

## 무엇이 없었나

사용자 지시는 분명했다 — "사용자는 기본적으로 **본인 팀 정보만**". 그런데 그걸 구현한 코드가
저장소에 없었다. `build_scope()` 는 **역할과 무관하게** `admin_scope` 를 읽는데 그 컬럼의
기본값은 `global` 이고 users 전 행에 그렇게 깔려 있다. 그래서:

  * 일반 사용자도 `GLOBAL_SCOPE` 를 받고,
  * `scope_filter` 는 global 이면 조건을 안 건다.

즉 범위를 올바르게 쓰는 여섯 곳조차 **일반 사용자에게는 전부 no-op** 이었다.

## 폴백 규칙 — 부서가 없으면 좁히지 않는다

계획서가 "매핑 실패 시 폴백 규칙을 반드시 정한다" 고 했다. 여기서 정한다:
**부서가 없는 일반 사용자는 좁히지 않는다(전역).**

반대로 하면(부서 없음 → 빈 부서 집합) 부서를 아직 배정하지 않은 신규 입사자가 **아무것도
못 보는 계정**이 된다 — 그리고 증상은 "권한이 없습니다" 가 아니라 "목록이 비어 있음" 이라
원인을 찾기가 어렵다. 사람을 먼저 들여보내고 부서를 나중에 정하는 것이 실제 순서다.

`admin_scope` 는 그대로 둔다 — 그건 **관리자가 관리 화면에서 볼 수 있는 범위**이고
이건 **일반 사용자가 자기 업무 화면에서 볼 수 있는 범위**다. 둘은 다른 질문이다.
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
    other = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([child, other])
    db.commit()
    return {"parent": parent, "child": child, "other": other}


def _scope(db, user):
    from app.core.scope import build_scope

    return build_scope(db, user)


def test_a_regular_user_is_narrowed_to_their_own_department(db, make_user, depts):
    u = make_user("teamonly@goodmit.co.kr", role="user")
    u.department_id = depts["child"].id
    db.commit()

    sc = _scope(db, u)
    assert sc.is_dept, f"일반 사용자가 팀으로 좁혀지지 않았다: {sc.kind}"
    assert depts["child"].id in sc.dept_ids
    assert depts["other"].id not in sc.dept_ids, "남의 팀이 범위에 들어왔다"


def test_the_subtree_is_included_not_just_the_one_department(db, make_user, depts):
    """상위 부서 사람은 하위 팀까지 본다 — 조직도가 계층인데 범위가 한 칸이면 뜻이 없다."""
    u = make_user("hq@goodmit.co.kr", role="user")
    u.department_id = depts["parent"].id
    db.commit()

    sc = _scope(db, u)
    assert depts["child"].id in sc.dept_ids, "하위 팀이 범위에 없다"


def test_a_user_without_a_department_is_not_narrowed(db, make_user):
    """**폴백 규칙.** 반대로 하면 신규 입사자가 아무것도 못 보는 계정이 된다."""
    u = make_user("nodept@goodmit.co.kr", role="user")
    db.commit()

    sc = _scope(db, u)
    assert not sc.is_dept, "부서 없는 사용자가 빈 범위로 떨어졌다 — 화면이 통째로 빈다"


def test_an_admin_still_follows_admin_scope_not_their_department(db, make_user, depts):
    """관리자에게는 **관리 범위**가 답이다. 두 질문을 섞으면 전체 관리자가 자기 부서에 갇힌다."""
    a = make_user("boss@goodmit.co.kr", role="admin")
    a.department_id = depts["child"].id     # 부서는 있지만
    db.commit()                              # admin_scope 는 기본값 global 이다

    sc = _scope(db, a)
    assert not sc.is_dept, "관리자가 자기 부서로 갇혔다 — 관리 범위가 무시됐다"


def test_a_narrowed_admin_is_still_narrowed(db, make_user, depts):
    """관리자를 부서로 좁혀 두면 그대로 좁혀진다(F2 에서 만든 경로와 이어진다)."""
    from app.users.models import ADMIN_SCOPE_DEPT

    a = make_user("deptboss@goodmit.co.kr", role="admin")
    a.admin_scope = ADMIN_SCOPE_DEPT
    a.scope_dept_id = depts["child"].id
    db.commit()

    sc = _scope(db, a)
    assert sc.is_dept and depts["child"].id in sc.dept_ids


def test_search_actually_narrows_for_a_regular_user(client, login_as, make_user, db, depts, app):
    """규칙만 맞고 화면이 안 바뀌면 뜻이 없다 — **검색 결과**로 확인한다.

    검색은 `get_principal` 을 지나는 유일한 일반 사용자 경로다(나머지 다섯은 관리자 화면).
    계획서가 "검색은 코드가 맞다 — (A)만 고치면 저절로 맞아진다" 고 적었는데, 정말 그런지
    끝에서 본다.
    """
    from app.search.models import SearchDocument

    mine = make_user("mine@goodmit.co.kr", role="user", display_name="우리팀사람")
    theirs = make_user("theirs@goodmit.co.kr", role="user", display_name="남의팀사람")
    mine.department_id = depts["child"].id
    theirs.department_id = depts["other"].id
    db.commit()

    with app.state.session_factory() as s:
        for owner, title in ((mine.id, "우리팀 회의록"), (theirs.id, "남의팀 회의록")):
            s.add(SearchDocument(
                kind="document", ref_id=f"ref-{owner}", title=title, body="회의",
                route="/team-docs", owner_user_ids=owner, sort_key=title,
            ))
        s.commit()

    login_as("user", email="mine@goodmit.co.kr")
    hits = client.get("/api/search?q=회의록").json()
    titles = {h["title"] for group in hits.get("groups", []) for h in group.get("items", [])}

    assert "우리팀 회의록" in titles, f"자기 팀 문서가 안 보인다: {titles}"
    assert "남의팀 회의록" not in titles, f"남의 팀 문서가 보인다: {titles}"
