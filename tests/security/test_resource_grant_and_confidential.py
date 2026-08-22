"""직접 부여와 `confidential` — **더하기 하나, 빼기 하나** (S5 · D-193).

유효 가시성 = 소속 ∪ Project Member ∪ **직접 부여**, 그리고 유일한 축소 원시연산은
`confidential` 하나다. 이 파일은 그 두 문장이 실제로 참인지 **음성 위주**로 본다:

  * 부여가 **그 자원만** 여는가 (옆 자원까지 열리면 그건 부여가 아니라 승격이다)
  * 거두면 **닫히는가** (열기만 되고 닫히지 않으면 되돌릴 수 없는 권한이다)
  * `confidential` 이 소속이 맞는 사람에게도 **닫는가**
  * 그 예외가 **정확히 셋**인가 — 소유자(작성자) · 명시 부여자 · `*_ADMIN`
  * **검색은 예외를 하나도 두지 않는가** — 운영자에게도, 명시 부여자에게도

마지막 줄이 특히 중요하다. 색인은 범위가 없는 전역 저장소라 예외를 하나 열면 그것이
인덱스 안 ACL 의 시작이 된다(`app/authz/visibility.py::_search_plan`). 그 결정이 자원
명세의 한 칸이 된 지금, 그 칸이 조용히 뒤집히지 않는지 여기서 지킨다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.authz.models import GRANTEE_USER
from app.authz.service import grant_resource_access, revoke_resource_access
from app.authz.visibility import (
    RESOURCE_DOCUMENT,
    RESOURCE_SEARCH,
    context_for_user,
    effective_visibility_clause,
)
from app.core.models_base import NAMES_SEP
from app.core.ownership import OWNER_DEPARTMENT

pytestmark = pytest.mark.security

SECRET = "doc-secret"
NEIGHBOUR = "doc-neighbour"


@pytest.fixture()
def secret_world(db, make_user):
    """A본부의 문서 둘 — 하나는 열람 제한, 하나는 평범하다. 사람은 넷."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import OrgUnit
    from app.search.models import KIND_DOCUMENT, SearchDocument
    from app.team_docs.models import DocumentCache

    dept_a = OrgUnit(name="A본부", org_id=DEFAULT_ORG_ID)
    dept_b = OrgUnit(name="B본부", org_id=DEFAULT_ORG_ID)
    db.add_all([dept_a, dept_b])
    db.flush()

    author = make_user("grant-author@goodmit.co.kr", role="user", display_name="작성자")
    mate = make_user("grant-mate@goodmit.co.kr", role="user", display_name="같은부서")
    stranger = make_user("grant-stranger@goodmit.co.kr", role="user", display_name="다른부서")
    moderator = make_user("grant-op@goodmit.co.kr", role="operator", display_name="운영자")
    for user in (author, mate, moderator):
        user.department_id = dept_a.id
        user.org_id = DEFAULT_ORG_ID
    stranger.department_id = dept_b.id
    stranger.org_id = DEFAULT_ORG_ID

    for page_id, restricted in ((SECRET, True), (NEIGHBOUR, False)):
        db.add(DocumentCache(
            notion_page_id=page_id, title=page_id, org_id=DEFAULT_ORG_ID,
            owner_kind=OWNER_DEPARTMENT, owner_dept_id=dept_a.id, restricted=restricted,
            # 작성자 판정은 id 가 있으면 id 로, 없으면 이름 폴백이다. 여기서는 폴백 경로를
            # 쓴다 — 매핑 표가 없는 문서가 실제로 흔하고, 그 경로도 같은 규칙이어야 한다.
            author_names=NAMES_SEP + "작성자" + NAMES_SEP,
        ))
        db.add(SearchDocument(
            kind=KIND_DOCUMENT, ref_id=page_id, title=page_id, body="", sort_key=page_id,
            org_id=DEFAULT_ORG_ID, owner_kind=OWNER_DEPARTMENT, owner_dept_id=dept_a.id,
        ))
    db.commit()
    return {
        "author": author, "mate": mate, "stranger": stranger, "moderator": moderator,
        "dept_a": dept_a, "dept_b": dept_b,
    }


def _visible(db, user, resource_type=RESOURCE_DOCUMENT) -> set[str]:
    from app.search.models import SearchDocument
    from app.team_docs.models import DocumentCache

    model, key = (
        (DocumentCache, "notion_page_id") if resource_type == RESOURCE_DOCUMENT
        else (SearchDocument, "ref_id")
    )
    ctx = context_for_user(db, user)
    stmt = select(model)
    clause = effective_visibility_clause(ctx, resource_type)
    if clause is not None:
        stmt = stmt.where(clause)
    return {str(getattr(row, key)) for row in db.execute(stmt).scalars()}


# ── 축소: confidential ───────────────────────────────────────────────────────

def test_confidential_hides_it_from_the_same_department(db, secret_world):
    """소속이 맞아도 안 보인다 — 「같은 팀」이 곧 「봐도 되는 사람」은 아니다."""
    seen = _visible(db, secret_world["mate"])
    assert NEIGHBOUR in seen, "같은 부서의 평범한 문서까지 사라졌다 — 축소가 너무 넓다"
    assert SECRET not in seen, "열람 제한 문서가 같은 부서 동료에게 보인다"


def test_the_author_still_sees_it(db, secret_world):
    seen = _visible(db, secret_world["author"])
    assert SECRET in seen, "작성자가 자기 제한 문서를 못 본다"


def test_the_admin_permission_holder_still_sees_it(db, secret_world):
    """`DOCUMENT_ADMIN`(= 운영자군)이 예외다. 현행 `restricted` 와 같은 집합이다."""
    seen = _visible(db, secret_world["moderator"])
    assert SECRET in seen, "운영자가 열람 제한 문서를 못 본다 — 옛 규칙과 달라졌다"


def test_a_different_department_sees_neither(db, secret_world):
    seen = _visible(db, secret_world["stranger"])
    assert SECRET not in seen and NEIGHBOUR not in seen, (
        "다른 부서 사람에게 A본부 문서가 보인다"
    )


# ── 더하기: 직접 부여 ────────────────────────────────────────────────────────

def test_an_explicit_grant_opens_the_confidential_document(db, secret_world):
    """D-193 의 「명시 부여자」 항 — 이것이 없으면 `confidential` 은 축소가 아니라 잠금이다."""
    mate = secret_world["mate"]
    assert SECRET not in _visible(db, mate)

    grant_resource_access(
        db, resource_type=RESOURCE_DOCUMENT, resource_id=SECRET,
        grantee_kind=GRANTEE_USER, grantee_id=mate.id,
    )
    db.commit()
    assert SECRET in _visible(db, mate), "명시로 열어 줬는데 안 보인다"


def test_a_grant_opens_exactly_that_one_resource(db, secret_world):
    """옆 자원까지 열리면 그건 부여가 아니라 승격이다."""
    stranger = secret_world["stranger"]
    grant_resource_access(
        db, resource_type=RESOURCE_DOCUMENT, resource_id=NEIGHBOUR,
        grantee_kind=GRANTEE_USER, grantee_id=stranger.id,
    )
    db.commit()
    seen = _visible(db, stranger)
    assert seen == {NEIGHBOUR}, (
        f"부여가 그 자원 하나만 열지 않았다: {sorted(seen)}"
    )


def test_revoking_closes_it_again(db, secret_world):
    """열기만 되고 닫히지 않으면 되돌릴 수 없는 권한이다."""
    stranger = secret_world["stranger"]
    grant_resource_access(
        db, resource_type=RESOURCE_DOCUMENT, resource_id=NEIGHBOUR,
        grantee_kind=GRANTEE_USER, grantee_id=stranger.id,
    )
    db.commit()
    assert NEIGHBOUR in _visible(db, stranger)

    revoke_resource_access(
        db, resource_type=RESOURCE_DOCUMENT, resource_id=NEIGHBOUR,
        grantee_kind=GRANTEE_USER, grantee_id=stranger.id,
    )
    db.commit()
    assert NEIGHBOUR not in _visible(db, stranger), "부여를 거뒀는데 계속 보인다"


def test_a_grant_on_another_resource_type_does_not_leak(db, secret_world):
    """자원 종류가 다르면 같은 id 라도 다른 자원이다."""
    stranger = secret_world["stranger"]
    grant_resource_access(
        db, resource_type="project", resource_id=NEIGHBOUR,
        grantee_kind=GRANTEE_USER, grantee_id=stranger.id,
    )
    db.commit()
    assert NEIGHBOUR not in _visible(db, stranger), (
        "프로젝트에 준 부여가 같은 id 의 문서를 열었다"
    )


# ── 검색은 예외를 두지 않는다 ────────────────────────────────────────────────

@pytest.mark.parametrize("who", ["author", "moderator", "mate"])
def test_the_search_index_never_returns_a_confidential_document(db, secret_world, who):
    """목록·상세에서는 예외가 셋이지만 **색인에는 하나도 없다**.

    색인은 범위가 없는 전역 저장소라, 예외를 하나 열면 그것이 인덱스 안 ACL 의 시작이 된다.
    기능을 잃지도 않는다 — 그 사람들은 문서 목록에서 그대로 보고 연다.
    """
    user = secret_world[who]
    grant_resource_access(
        db, resource_type=RESOURCE_DOCUMENT, resource_id=SECRET,
        grantee_kind=GRANTEE_USER, grantee_id=user.id,
    )
    db.commit()
    seen = _visible(db, user, RESOURCE_SEARCH)
    assert SECRET not in seen, f"{who} 가 열람 제한 문서를 검색으로 찾았다"
    assert NEIGHBOUR in seen, f"{who} 가 평범한 문서까지 검색에서 잃었다 — 축소가 너무 넓다"


# ── API 표면 ─────────────────────────────────────────────────────────────────

def test_a_plain_user_cannot_name_the_allowed_users(client, login_as, db, secret_world):
    """제한 문서는 그 사람에게 **애초에 없는 문서**라 404 다.

    403 은 「그 문서는 존재한다」를 알려 준다 — id 를 찍어 보며 403/404 를 세면 어느 문서가
    제한돼 있는지 열거할 수 있고, 그 목록 자체가 「무엇이 민감한가」의 지도다. 범위 판정이
    역할 판정보다 **앞에** 있는 것이 이 저장소의 규약이다.
    """
    mate = secret_world["mate"]
    csrf = login_as("user", email=mate.email)
    r = client.put(
        f"/api/team-docs/{SECRET}/allowed-users",
        json={"user_ids": [mate.id]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, f"일반 사용자가 열람자를 지정했다: {r.status_code} {r.text}"


def test_a_plain_user_is_refused_even_on_a_document_they_can_see(
    client, login_as, db, secret_world
):
    """위 404 가 「그냥 안 보여서」가 아니라는 반례 — **보이는** 문서에서도 막힌다.

    이것이 없으면 위 시험은 역할 게이트가 아예 없어도 통과한다.
    """
    mate = secret_world["mate"]
    csrf = login_as("user", email=mate.email)
    r = client.put(
        f"/api/team-docs/{NEIGHBOUR}/allowed-users",
        json={"user_ids": [mate.id]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403, f"일반 사용자가 열람자를 지정했다: {r.status_code} {r.text}"


def test_a_moderator_can_name_them_and_it_takes_effect(client, login_as, db, secret_world):
    mate = secret_world["mate"]
    csrf = login_as("operator", email=secret_world["moderator"].email)
    r = client.put(
        f"/api/team-docs/{SECRET}/allowed-users",
        json={"user_ids": [mate.id]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    assert r.json()["user_ids"] == [mate.id]
    assert SECRET in _visible(db, mate), "명시 지정이 실제 가시성에 반영되지 않았다"

    listed = client.get(
        f"/api/team-docs/{SECRET}/allowed-users", headers={"X-CSRF-Token": csrf}
    )
    assert listed.status_code == 200
    assert listed.json()["user_ids"] == [mate.id]


def test_naming_a_user_outside_the_management_scope_is_a_404(
    client, login_as, db, secret_world
):
    """범위 밖 계정은 **없는 것과 똑같다** — 「있지만 당신 부서가 아닙니다」로 답하면
    id 를 찍어 보며 남의 부서 명부를 열거할 수 있다."""
    from app.users.models import ADMIN_SCOPE_DEPT

    moderator = secret_world["moderator"]
    moderator.admin_scope = ADMIN_SCOPE_DEPT
    moderator.scope_dept_id = secret_world["dept_a"].id
    db.commit()

    csrf = login_as("operator", email=moderator.email)
    r = client.put(
        f"/api/team-docs/{SECRET}/allowed-users",
        json={"user_ids": [secret_world["stranger"].id]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404, f"범위 밖 계정에 부여가 됐다: {r.status_code} {r.text}"


# ── 역방향 판정도 같은 규칙을 쓴다 ───────────────────────────────────────────

def test_the_reverse_lookup_honours_membership_and_grants(db, secret_world, make_project):
    """「이 프로젝트를 볼 수 있는 사람이 누구인가」는 담당자 후보 목록이 묻는다.

    앞의 정방향 판정과 **같은 규칙 목록**을 접어야 한다 — 갈라지면 「후보로는 떴는데 그
    사람은 그 프로젝트를 못 본다」가 된다. 갈래 셋이 각각 살아 있는지 본다.
    """
    from app.authz.visibility import users_who_can_view_project
    from app.projects.models import ProjectMember

    project = make_project(name="A본부프로젝트", dept=secret_world["dept_a"])
    mate = secret_world["mate"]          # 같은 부서 — 소속 갈래
    stranger = secret_world["stranger"]  # 다른 부서 — 아무 갈래도 안 걸린다
    author = secret_world["author"]      # 같은 부서
    everyone = [mate, stranger, author]

    seen = users_who_can_view_project(db, everyone, project)
    assert {u.id for u in seen} == {mate.id, author.id}, "부서 갈래가 안 걸리거나 남까지 걸린다"

    db.add(ProjectMember(project_id=project.id, user_id=stranger.id))
    db.commit()
    seen = users_who_can_view_project(db, everyone, project)
    assert stranger.id in {u.id for u in seen}, "프로젝트 멤버가 후보에서 빠진다"


def test_the_reverse_lookup_sees_an_explicit_grant(db, secret_world, make_project):
    from app.authz.visibility import RESOURCE_PROJECT, users_who_can_view_project

    project = make_project(name="A본부프로젝트2", dept=secret_world["dept_a"])
    stranger = secret_world["stranger"]
    assert not users_who_can_view_project(db, [stranger], project)

    grant_resource_access(
        db, resource_type=RESOURCE_PROJECT, resource_id=project.id,
        grantee_kind=GRANTEE_USER, grantee_id=stranger.id,
    )
    db.commit()
    seen = users_who_can_view_project(db, [stranger], project)
    assert {u.id for u in seen} == {stranger.id}, "명시 부여를 받은 사람이 후보에서 빠진다"


def test_the_reverse_lookup_is_fail_closed_without_a_project(db, secret_world):
    from app.authz.visibility import users_who_can_view_project

    assert users_who_can_view_project(db, [secret_world["mate"]], None) == []
