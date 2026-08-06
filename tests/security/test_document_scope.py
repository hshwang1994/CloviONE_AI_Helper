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
