"""SQL 절과 행 판정이 **같은 답**을 내는가 (S5 · D-194).

## 왜 이것이 핵심 시험인가

가시성은 한 규칙인데 답해야 할 모양이 둘이다 — 목록·검색은 SQL 절, 상세·행 판정은 파이썬
불리언. 두 벌로 적으면 갈라지고, 갈라진 순간 「목록에는 없는데 id 로는 열리는」(유출) 또는
「목록에는 있는데 열면 404」(고장) 상태가 된다. 이 저장소는 그 모양의 결함을 **네 번** 고쳤다
(`scripts/check_scope_gates.py` 가 그 목록을 들고 있다).

`app/authz/visibility.py` 는 규칙마다 두 표현을 한 객체(`_Rule`)에 나란히 두고 두 렌더러가
같은 목록을 접게 만들었다. **그 설계가 실제로 성립하는지는 실행해 봐야 안다** — 여기서
진짜 행으로 전수 대조한다.

## 세계

    굿모닝아이텍(기본 조직)
    ├ A본부 ─ A1팀
    └ B본부

프로젝트 셋(A본부 것 · B본부 것 · 조직 공통), 문서 여섯(부서 둘 · 조직 공통 · 프로젝트 ·
소속 미정 · 열람 제한). 사람 다섯(A1팀 · B본부 · 미지정 · 프로젝트 멤버 · 관리자).

이 조합이라야 갈래마다 **보이는 행과 안 보이는 행이 모두** 있다. 한쪽만 있으면 두 렌더러가
「전부 보인다」로 일치해도 아무것도 증명하지 못한다 — 마지막 시험이 그것을 막는다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import select

from app.authz.visibility import (
    RESOURCE_DOCUMENT,
    RESOURCE_PROJECT,
    RESOURCE_SEARCH,
    annotate_rows,
    context_for_user,
    effective_visibility_clause,
    is_visible,
)
from app.core.ownership import (
    OWNER_DEPARTMENT,
    OWNER_ORGANIZATION,
    OWNER_PROJECT,
    OWNER_UNSET,
)

pytestmark = pytest.mark.security


@dataclass
class World:
    dept_a: object
    dept_a1: object
    dept_b: object
    project_a: object
    project_b: object
    project_common: object
    users: dict[str, object]


@pytest.fixture()
def world(db, make_user, make_project) -> World:
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import OrgUnit
    from app.projects.models import ProjectMember
    from app.search.models import KIND_DOCUMENT, KIND_TICKET, SearchDocument
    from app.team_docs.models import DocumentCache

    dept_a = OrgUnit(name="A본부", org_id=DEFAULT_ORG_ID)
    dept_b = OrgUnit(name="B본부", org_id=DEFAULT_ORG_ID)
    db.add_all([dept_a, dept_b])
    db.flush()
    dept_a1 = OrgUnit(name="A1팀", org_id=DEFAULT_ORG_ID, parent_id=dept_a.id)
    db.add(dept_a1)
    db.flush()

    project_a = make_project(name="A프로젝트", dept=dept_a)
    project_b = make_project(name="B프로젝트", dept=dept_b)
    project_common = make_project(name="공통프로젝트")

    users = {}
    for key, dept in (("a1", dept_a1), ("b", dept_b), ("member", None), ("outsider", None)):
        user = make_user(f"vis-{key}@goodmit.co.kr", role="user", display_name=f"사람{key}")
        if dept is not None:
            user.department_id = dept.id
            user.org_id = DEFAULT_ORG_ID
        else:
            # 소속 미지정 — 조직 데이터가 하나도 안 보이는 상태(fail-closed)에서 출발한다.
            user.department_id = None
            user.membership_kind = "unassigned"
        users[key] = user
    users["admin"] = make_user("vis-admin@goodmit.co.kr", role="admin")
    db.flush()

    # 프로젝트 멤버 — S5 가 새로 더한 갈래. 부서가 없어도 이 프로젝트는 보여야 한다.
    db.add(ProjectMember(project_id=project_b.id, user_id=users["member"].id))

    docs = [
        ("doc-dept-a", OWNER_DEPARTMENT, dept_a.id, None, False),
        ("doc-dept-a1", OWNER_DEPARTMENT, dept_a1.id, None, False),
        ("doc-dept-b", OWNER_DEPARTMENT, dept_b.id, None, False),
        ("doc-org", OWNER_ORGANIZATION, None, None, False),
        ("doc-proj-a", OWNER_PROJECT, None, project_a.id, False),
        ("doc-proj-b", OWNER_PROJECT, None, project_b.id, False),
        ("doc-unset", OWNER_UNSET, None, None, False),
        ("doc-secret", OWNER_DEPARTMENT, dept_a.id, None, True),
    ]
    for page_id, kind, dept_id, project_id, restricted in docs:
        db.add(DocumentCache(
            notion_page_id=page_id, title=page_id, org_id=DEFAULT_ORG_ID,
            owner_kind=kind, owner_dept_id=dept_id, owner_project_id=project_id,
            restricted=restricted,
        ))
        db.add(SearchDocument(
            kind=KIND_DOCUMENT, ref_id=page_id, title=page_id, body="", sort_key=page_id,
            org_id=DEFAULT_ORG_ID, owner_kind=kind, owner_dept_id=dept_id,
            owner_project_id=project_id,
        ))
    # 문서가 아닌 색인 행도 하나 — 제한 절이 **문서 유형에만** 걸리는지 보는 반례다.
    db.add(SearchDocument(
        kind=KIND_TICKET, ref_id="tk-1", title="tk-1", body="", sort_key="tk-1",
        org_id=DEFAULT_ORG_ID, owner_kind=OWNER_DEPARTMENT, owner_dept_id=dept_a.id,
    ))
    db.commit()
    return World(dept_a, dept_a1, dept_b, project_a, project_b, project_common, users)


def _model_for(resource_type: str):
    if resource_type == RESOURCE_PROJECT:
        from app.projects.models import Project

        return Project, "id"
    if resource_type == RESOURCE_DOCUMENT:
        from app.team_docs.models import DocumentCache

        return DocumentCache, "notion_page_id"
    from app.search.models import SearchDocument

    return SearchDocument, "ref_id"


def _sql_ids(db, ctx, resource_type: str) -> set[str]:
    model, key = _model_for(resource_type)
    stmt = select(model)
    clause = effective_visibility_clause(ctx, resource_type)
    if clause is not None:
        stmt = stmt.where(clause)
    return {str(getattr(row, key)) for row in db.execute(stmt).scalars()}


def _row_ids(db, ctx, resource_type: str) -> set[str]:
    model, key = _model_for(resource_type)
    rows = list(db.execute(select(model)).scalars())
    annotate_rows(db, ctx, resource_type, rows)
    return {
        str(getattr(row, key))
        for row in rows
        if is_visible(db, ctx, resource_type, row)
    }


RESOURCES = (RESOURCE_PROJECT, RESOURCE_DOCUMENT, RESOURCE_SEARCH)
WHO = ("a1", "b", "member", "outsider", "admin")


@pytest.mark.parametrize("resource_type", RESOURCES)
@pytest.mark.parametrize("who", WHO)
def test_the_two_renderers_return_the_same_rows(db, world, resource_type, who):
    ctx = context_for_user(db, world.users[who])
    sql = _sql_ids(db, ctx, resource_type)
    rows = _row_ids(db, ctx, resource_type)
    assert sql == rows, (
        f"{who} / {resource_type}: SQL 절과 행 판정이 다른 답을 낸다.\n"
        f"  SQL 에만: {sorted(sql - rows)}\n"
        f"  행 판정에만: {sorted(rows - sql)}\n"
        "두 렌더러가 갈라지면 목록과 상세가 서로 다른 말을 한다."
    )


@pytest.mark.parametrize("resource_type", RESOURCES)
def test_the_comparison_above_is_not_vacuous(db, world, resource_type):
    """**보이는 행과 안 보이는 행이 모두** 있어야 위 대조가 무엇인가를 증명한다.

    한 사람에게 전부 보이거나 전부 안 보이면 두 렌더러는 그냥 같은 상수를 낸 것뿐이다.
    """
    model, key = _model_for(resource_type)
    everything = {
        str(getattr(row, key)) for row in db.execute(select(model)).scalars()
    }
    seen: set[str] = set()
    for who in WHO:
        ctx = context_for_user(db, world.users[who])
        got = _sql_ids(db, ctx, resource_type)
        seen |= got
        if who == "outsider":
            assert not got, f"소속 미지정 사용자에게 {resource_type} 가 보인다 — fail-closed 가 아니다"
    assert seen, f"{resource_type} 가 누구에게도 안 보인다 — 세계가 비었을 수 있다"

    a1 = _sql_ids(db, context_for_user(db, world.users["a1"]), resource_type)
    assert a1, f"A1팀 사용자에게 {resource_type} 가 하나도 안 보인다"
    assert a1 != everything, (
        f"A1팀 사용자에게 {resource_type} 전부가 보인다 — 경계가 없으면 대조가 헛돈다"
    )
