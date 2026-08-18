"""문서 목록·상세도 범위를 지킨다 (1순위 유출 #5).

`GET /api/team-docs` 와 상세는 로그인만 하면 **문서 캐시 전량 + 본문 블록**을 내줬다.

## 판정은 **문서 자신의 소속**이다 (0060 에서 바뀐 규칙)

예전에는 **작성자 집합**으로 판정했다. 세 가지가 잘못이었다:

  * 작성자가 부서를 옮기면 그 사람이 3년 전에 쓴 문서가 따라 움직인다.
  * 작성자를 앱 계정으로 해석하지 못하면 **통과시켰다**. Notion 미러라 그런 문서가 흔했고,
    그래서 사실상 열려 있는 문이었다(그 통과가 없으면 문서가 통째로 사라졌기 때문에 뺄 수도
    없었다 — 축 자체가 틀렸던 것이다).
  * '프로젝트 문서' 라는 개념을 표현할 수 없었다.

이제 문서는 자기 소속을 스스로 들고 있다(`owner_kind` + 부서/프로젝트 id, Portal 이 소유).
작성자와 소유는 다른 개념이고, 이 파일이 그 분리를 지킨다.

## 소속을 모르면 **닫는다**

`owner_kind='unset'` 인 문서는 전역 관리자만 본다. 추측해서 열지 않는다 — 추측은 언제나
넓히는 쪽으로 틀리고, 넓게 틀린 것은 아무도 신고하지 않는다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security

NID_MINE, NID_THEIRS = "notion-doc-mine", "notion-doc-theirs"


@pytest.fixture()
def docs(db, make_user, make_document):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

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
    db.commit()

    make_document(page_id="dm", title="우리팀 문서", dept=mine, author_notion_ids=[NID_MINE])
    make_document(page_id="dt", title="남의팀 문서", dept=theirs, author_notion_ids=[NID_THEIRS])
    # 두 팀이 함께 보는 문서는 '작성자가 둘' 이 아니라 **조직 공통 소유**로 표현한다.
    make_document(page_id="db", title="조직 공통 문서", org_wide=True,
                  author_notion_ids=[NID_MINE, NID_THEIRS])
    # 작성자를 앱 계정으로 해석할 수 없는 문서 — 소속만 제대로면 정상적으로 보인다.
    make_document(page_id="dn", title="작성자 미해석 문서", dept=mine, author_notion_ids=[])
    # 소속을 아직 못 정한 문서 — 전역 관리자만 본다.
    make_document(page_id="du", title="소속 미지정 문서")


def _titles(client):
    return {d["title"] for d in client.get("/api/team-docs").json()["items"]}


def test_a_user_sees_their_own_teams_documents(client, login_as, docs):
    login_as("user", email="ds-me@goodmit.co.kr")
    titles = _titles(client)
    assert "우리팀 문서" in titles
    assert "남의팀 문서" not in titles, "다른 팀 문서와 본문 블록이 그대로 나간다"


def test_an_organization_wide_document_is_visible_to_both_teams(client, login_as, docs):
    """조직 공통 문서는 부서와 무관하게 그 조직 사람 전부에게 보인다.

    부서 범위 사용자에게 조직 공통 자원이 안 보이면 '조직 공통' 이라는 개념 자체가 성립하지
    않는다 — 부서 집합에 없다고 막으면 안 되는 이유다.
    """
    login_as("user", email="ds-me@goodmit.co.kr")
    assert "조직 공통 문서" in _titles(client)
    login_as("user", email="ds-other@goodmit.co.kr")
    assert "조직 공통 문서" in _titles(client)


def test_author_mapping_does_not_decide_visibility(client, login_as, docs):
    """작성자를 앱 계정으로 해석하지 못해도 **소속이 있으면 보인다**.

    예전에는 이 경우를 '판정 불가' 로 보고 통과시켰고(그래서 남의 팀에도 보였다), 그 통과를
    빼면 문서가 통째로 사라졌다 — 축이 틀렸다는 신호였다. 이제 소속과 작성자가 분리돼
    같은 문서가 **우리 팀에는 보이고 남의 팀에는 안 보인다.**
    """
    login_as("user", email="ds-me@goodmit.co.kr")
    assert "작성자 미해석 문서" in _titles(client)

    login_as("user", email="ds-other@goodmit.co.kr")
    assert "작성자 미해석 문서" not in _titles(client), (
        "작성자 매핑이 없다는 이유만으로 남의 팀 문서가 보인다 — 예전의 우회 경로가 살아 있다"
    )


def test_a_document_with_no_ownership_is_closed(client, login_as, docs):
    """소속을 모르는 문서는 **아무에게도 안 보인다**(전역 관리자만).

    추측하지 않는다는 것이 이 모델의 핵심이다. 대신 관리자 진단이 이 문서들을 목록으로
    보여 주고, 사람이 Portal 에서 소속을 지정한다.
    """
    login_as("user", email="ds-me@goodmit.co.kr")
    assert "소속 미지정 문서" not in _titles(client)

    login_as("system_admin")
    assert "소속 미지정 문서" in _titles(client), (
        "전역 관리자에게도 안 보이면 그 문서는 누구도 고칠 수 없는 상태가 된다"
    )


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


def test_a_project_document_follows_the_projects_scope(client, login_as, db, make_user, make_project, make_document):
    """프로젝트 문서는 **그 프로젝트의 ACL 을 그대로 물려받는다**.

    문서에 부서를 따로 적지 않는다 — 프로젝트가 옮겨 가면 그 문서도 함께 따라가야 하고,
    두 곳에 적으면 언젠가 한쪽만 고쳐진다.
    """
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="프로젝트팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="다른팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()
    member = make_user("pd-member@goodmit.co.kr", role="user", display_name="참여자")
    outsider = make_user("pd-outsider@goodmit.co.kr", role="user", display_name="외부인")
    member.department_id = mine.id
    outsider.department_id = theirs.id
    db.commit()
    project = make_project(name="인프라 자동화", dept=mine, external_id="px-doc")
    make_document(page_id="pdoc", title="프로젝트 문서", project=project)

    login_as("user", email="pd-member@goodmit.co.kr")
    assert "프로젝트 문서" in _titles(client)
    assert client.get("/api/team-docs/pdoc").status_code == 200

    login_as("user", email="pd-outsider@goodmit.co.kr")
    assert "프로젝트 문서" not in _titles(client)
    assert client.get("/api/team-docs/pdoc").status_code == 404


# RBAC 재감사(2026-08-16)로 발견: 범위 판정이 org 범위(admin_scope="org") 관리자를 global 과
# 똑같이 취급했다 — 위 시험들이 잡는 dept 경계와 달리 이 org 경계는 어떤 시험도 없었다.
# 목록·상세뿐 아니라 휴지통 이동 같은 쓰기도 `get_doc_in_scope` 하나로 모이므로 함께 확인한다.
@pytest.fixture()
def org_docs(db, make_user, make_document):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Organization

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
    db.commit()

    make_document(page_id="odm", title="A조직 문서", org_id=DEFAULT_ORG_ID, org_wide=True,
                  author_notion_ids=["notion-org-mine"])
    make_document(page_id="odt", title="B조직 문서", org_id=other_org.id, org_wide=True,
                  author_notion_ids=["notion-org-theirs"])


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
