"""문서 목록·상세도 범위를 지킨다 (1순위 유출 #5).

`GET /api/team-docs` 와 상세는 로그인만 하면 **문서 캐시 전량 + 본문 블록**을 내줬다.

## 판정은 작성자 집합 — 티켓과 같은 규칙

문서 하나를 여러 명이 쓴다. 대표 작성자 하나로 정하면 두 팀이 함께 쓴 문서가 한쪽에서
사라진다(`core/scope.py` 가 티켓에 대해 종결한 그 쟁점과 같다).

## ⚠️ 작성자를 해석할 수 없는 문서는 **보여야 한다**

`author_notion_ids` 는 다음 동기화가 채운다(X2). 지금 비어 있는 행을 숨기면 **모든 문서가
통째로 사라진다** — 계획서가 PLAN5 로 경고한 바로 그 재앙이다. 이 테스트가 그걸 막는다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-doc-mine", "notion-doc-theirs"


@pytest.fixture()
def docs(db, make_user):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.team_docs.models import DocumentCache

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()
    me = make_user("ds-me@goodmit.co.kr", role="user", display_name="나")
    other = make_user("ds-other@goodmit.co.kr", role="user", display_name="남")
    me.department_id = mine.id
    other.department_id = theirs.id
    db.add(UserNotionMapping(user_id=me.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=other.id, notion_user_id=NID_THEIRS, status=STATUS_VERIFIED))
    db.add_all([
        DocumentCache(notion_page_id="dm", title="우리팀 문서", author_notion_ids=NID_MINE),
        DocumentCache(notion_page_id="dt", title="남의팀 문서", author_notion_ids=NID_THEIRS),
        DocumentCache(notion_page_id="db", title="같이 쓴 문서",
                      author_notion_ids=f"{NID_MINE}|{NID_THEIRS}"),
        DocumentCache(notion_page_id="dn", title="작성자 미해석 문서", author_notion_ids=""),
    ])
    db.commit()


def _titles(client):
    return {d["title"] for d in client.get("/api/team-docs").json()["items"]}


def test_a_user_sees_their_own_teams_documents(client, login_as, docs):
    login_as("user", email="ds-me@goodmit.co.kr")
    titles = _titles(client)
    assert "우리팀 문서" in titles
    assert "남의팀 문서" not in titles, "다른 팀 문서와 본문 블록이 그대로 나간다"


def test_a_shared_document_is_visible_to_both_teams(client, login_as, docs):
    login_as("user", email="ds-me@goodmit.co.kr")
    assert "같이 쓴 문서" in _titles(client)
    login_as("user", email="ds-other@goodmit.co.kr")
    assert "같이 쓴 문서" in _titles(client)


def test_documents_without_resolvable_authors_do_not_vanish(client, login_as, docs):
    """**PLAN5 가 경고한 재앙을 막는 검사.** `author_notion_ids` 는 다음 동기화가 채우므로
    지금은 대부분 비어 있다 — 그걸 숨기면 문서가 통째로 사라진다."""
    login_as("user", email="ds-me@goodmit.co.kr")
    assert "작성자 미해석 문서" in _titles(client)


def test_the_total_matches_what_is_shown(client, login_as, docs):
    """"총 104건" 이라 해 놓고 20건만 보여 주면 사용자는 없는 것을 찾아 페이지를 넘긴다."""
    login_as("user", email="ds-me@goodmit.co.kr")
    body = client.get("/api/team-docs").json()
    assert body["total"] == len(body["items"])


def test_the_detail_follows_the_same_rule(client, login_as, docs):
    login_as("user", email="ds-me@goodmit.co.kr")
    assert client.get("/api/team-docs/dm").status_code == 200
    assert client.get("/api/team-docs/dt").status_code == 404, "목록에서 가린 것이 id 로 열린다"


def test_a_global_admin_still_sees_everything(client, login_as, docs):
    login_as("system_admin")
    assert {"우리팀 문서", "남의팀 문서", "작성자 미해석 문서"} <= _titles(client)


# RBAC 재감사(2026-08-16)로 발견: doc_in_scope가 `not scope.is_dept`로 판정해 org 범위
# (admin_scope="org") 관리자를 global과 똑같이 취급했다 — 위 시험들이 잡는 dept 경계와
# 달리 이 org 경계는 어떤 시험도 없었다. 목록·상세뿐 아니라 휴지통 이동 같은 쓰기도
# get_doc_in_scope 하나로 모이므로 여기서 함께 확인한다.
@pytest.fixture()
def org_docs(db, make_user):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Organization
    from app.team_docs.models import DocumentCache

    other_org = Organization(slug="org-scope-tenant", name="다른 회사", status="active")
    db.add(other_org)
    db.flush()

    boss = make_user("orgdoc-boss@goodmit.co.kr", role="admin", display_name="A조직관리자")
    boss.org_id = DEFAULT_ORG_ID
    boss.admin_scope = "org"
    boss.scope_org_id = DEFAULT_ORG_ID
    mine = make_user("orgdoc-mine@goodmit.co.kr", role="user", display_name="A조직원")
    mine.org_id = DEFAULT_ORG_ID
    theirs = make_user("orgdoc-theirs@goodmit.co.kr", role="user", display_name="B조직원")
    theirs.org_id = other_org.id
    db.add(UserNotionMapping(user_id=mine.id, notion_user_id="notion-org-mine", status=STATUS_VERIFIED))
    db.add(UserNotionMapping(user_id=theirs.id, notion_user_id="notion-org-theirs", status=STATUS_VERIFIED))
    db.add_all([
        DocumentCache(notion_page_id="odm", title="A조직 문서", author_notion_ids="notion-org-mine"),
        DocumentCache(notion_page_id="odt", title="B조직 문서", author_notion_ids="notion-org-theirs"),
    ])
    db.commit()


def test_org_scoped_admin_does_not_see_another_organizations_document(client, login_as, org_docs):
    login_as("admin", email="orgdoc-boss@goodmit.co.kr")
    titles = _titles(client)
    assert "A조직 문서" in titles
    assert "B조직 문서" not in titles, "org 범위 관리자에게 다른 조직 문서가 그대로 보인다"


def test_org_scoped_admin_gets_404_for_another_organizations_document_by_id(client, login_as, org_docs):
    login_as("admin", email="orgdoc-boss@goodmit.co.kr")
    assert client.get("/api/team-docs/odm").status_code == 200
    assert client.get("/api/team-docs/odt").status_code == 404, \
        "목록에서 가린 다른 조직 문서가 id 하나로 열린다"


def test_org_scoped_admin_cannot_trash_another_organizations_document(client, login_as, org_docs):
    """읽기뿐 아니라 쓰기(휴지통 이동)도 get_doc_in_scope 하나를 지난다 — 범위가
    뚫리면 다른 조직 문서를 지울 수 있다."""
    token = login_as("admin", email="orgdoc-boss@goodmit.co.kr")
    r = client.post("/api/team-docs/odt/trash", headers={"X-CSRF-Token": token})
    assert r.status_code == 404, f"org 범위 관리자가 다른 조직 문서를 휴지통으로 보낼 수 있다: {r.status_code} {r.text}"
