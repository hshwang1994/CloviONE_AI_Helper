"""문서 단위 열람 제한(SEC-10)은 **검색에서도** 집행돼야 한다.

`app/team_docs/service.py::doc_in_scope` 는 목록·상세·쓰기가 모두 지나는 단 하나의 문이고,
그 안에 `restricted` 게이트가 있다(같은 부서 동료라도 제한 문서는 못 본다 —
`tests/security/test_document_restricted_scope.py` 가 그 계약을 못박는다).

그런데 통합 검색은 그 문을 지나지 않는다. `app/search/scoping.py` 는 Ownership(조직·부서·
프로젝트) 축만 걸고 `restricted` 를 모른다. 색인기(`app/search/indexer.py::_document_rows`)도
휴지통만 빼고 전 문서를 담는다 — 제목·요약·메모·작성자·태그가 본문 필드로 들어간다.

**결과: 목록에서 가려 둔 문서를 검색으로 찾는다.** 열람 제한의 존재 이유가 "같은 팀이 곧
봐도 되는 사람은 아니다" 인데, 검색 한 줄이면 제목과 분류가 그대로 나온다. 상세는 404 라
본문은 못 읽지만, 제목 자체가 민감한 문서(예: "OO사 이관 계정 목록")에서는 제목만으로도
유출이다.

이 파일은 그 구멍을 두 층에서 막는다:
  1. **색인** — 제한 문서는 색인에 담기지 않는다(가장 확실한 fail-closed).
  2. **질의** — 색인에 남아 있더라도(제한을 켠 직후, 다음 색인 전) 결과에서 빠진다.

**예외는 없다.** 작성자와 운영자군도 검색으로는 못 찾는다 — 검색 색인은 범위가 없는 전역
저장소라 예외를 하나 열면 그 예외가 인덱스 안 ACL 의 시작이 된다(채팅을 통째로 안 담는
규칙과 같은 판단). 기능은 잃지 않는다: 그 사람들은 문서 목록에서 그대로 보고 연다.

fixture 관례는 `test_document_restricted_scope.py` 를 그대로 따른다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.security

NOW = datetime(2026, 8, 19, tzinfo=timezone.utc).replace(tzinfo=None)

NID_MINE = "notion-doc-mine-sr"

OP = "docsr-op@goodmit.co.kr"          # 우리팀만 관리하는 부서 운영자
AUTHOR = "docsr-author@goodmit.co.kr"  # 제한 문서의 작성자
TEAMMATE = "docsr-mate@goodmit.co.kr"  # 같은 부서 동료(작성자 아님)

SECRET_TITLE = "제한 문서 인수인계 계정"
OPEN_TITLE = "일반 문서 인수인계 절차"


@pytest.fixture()
def world(db, make_user, make_document):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    db.add(mine)
    db.flush()

    op = make_user(OP, role="operator", display_name="부서운영자")
    author = make_user(AUTHOR, role="user", display_name="작성자")
    mate = make_user(TEAMMATE, role="user", display_name="동료")
    op.department_id = mine.id
    op.admin_scope = "dept"
    op.scope_dept_id = mine.id
    author.department_id = mine.id
    mate.department_id = mine.id
    db.add(UserNotionMapping(user_id=author.id, notion_user_id=NID_MINE, status=STATUS_VERIFIED))
    db.commit()

    make_document(page_id="dsr", title=SECRET_TITLE, dept=mine,
                  author_notion_ids=[NID_MINE], restricted=True)
    make_document(page_id="dso", title=OPEN_TITLE, dept=mine,
                  author_notion_ids=[NID_MINE], restricted=False)
    return {"dept": mine}


def _reindex(db, app):
    from app.search.indexer import reindex_all

    reindex_all(
        db, tickets=app.state.repositories.tickets,
        documents=app.state.repositories.documents, now=NOW,
    )
    db.commit()


def _titles(client, q="인수인계"):
    body = client.get(f"/api/search?q={q}").json()
    out = []
    for group in body.get("groups", []) or []:
        for hit in group.get("items", []) or []:
            out.append(hit.get("title"))
    # 응답 모양이 그룹이 아니라 평면 목록인 배포에도 견디게 둘 다 훑는다.
    for hit in body.get("items", []) or []:
        out.append(hit.get("title"))
    return out


# ── 1층: 색인 ───────────────────────────────────────────────────────────────


def test_a_restricted_document_is_never_indexed(db, app, world):
    """제한 문서는 검색 색인에 아예 들어가지 않는다.

    색인은 범위가 없는 전역 저장소다 — 거기 남겨 두고 질의에서만 거르면, 새 질의 경로가
    하나 생길 때마다 같은 실수를 다시 할 수 있다. 애초에 안 담는 쪽이 fail-closed 다.
    """
    from app.search.models import SearchDocument

    _reindex(db, app)
    rows = db.execute(select(SearchDocument)).scalars().all()
    titles = [(r.title or "") for r in rows]
    assert OPEN_TITLE in titles, "일반 문서까지 색인에서 빠졌다 — 너무 넓게 막았다"
    leaked = [r.ref_id for r in rows if SECRET_TITLE in (r.title or "") + (r.body or "")]
    assert not leaked, f"열람 제한 문서가 검색 색인에 들어갔다: {leaked}"


# ── 2층: 질의 ───────────────────────────────────────────────────────────────


def test_a_teammate_cannot_find_a_restricted_document(client, login_as, db, app, world):
    """목록에서 가린 문서를 검색으로 찾을 수 없다 — 같은 부서 동료 기준."""
    _reindex(db, app)
    login_as("user", email=TEAMMATE)
    titles = _titles(client)
    assert OPEN_TITLE in titles, "같은 부서 일반 문서가 검색에 안 나온다 — 범위를 과하게 좁혔다"
    assert SECRET_TITLE not in titles, "목록에서 가린 제한 문서가 검색 결과에 그대로 나온다"


def _doc_titles(client):
    return {d["title"] for d in client.get("/api/team-docs").json()["items"]}


def test_no_one_finds_a_restricted_document_through_search_but_the_function_is_not_lost(
    client, login_as, db, app, world,
):
    """**작성자와 운영자도** 검색으로는 못 찾는다. 대신 문서 목록에서는 그대로 본다.

    예외를 하나 열면 그 예외가 인덱스 안 ACL 의 시작이 된다 — 채팅을 통째로 안 담는 규칙과
    같은 판단이다(`test_search_no_chat.py`: "'본인 것이니 괜찮다'로 예외를 하나 열면…").
    그래서 여기서 함께 확인하는 것이 **기능을 잃지 않았다**는 반대쪽 절반이다: 같은 사람이
    문서 목록에서는 그 문서를 그대로 보고 열 수 있다.
    """
    _reindex(db, app)

    login_as("user", email=AUTHOR)
    assert SECRET_TITLE not in _titles(client), "작성자에게도 검색 색인은 열리지 않는다"
    assert SECRET_TITLE in _doc_titles(client), "작성자가 자기 제한 문서를 목록에서도 못 본다"
    assert client.get("/api/team-docs/dsr").status_code == 200, "작성자가 상세를 못 연다"

    login_as("operator", email=OP)
    assert SECRET_TITLE not in _titles(client), "운영자에게도 검색 색인은 열리지 않는다"
    assert SECRET_TITLE in _doc_titles(client), "운영자가 제한 문서를 목록에서 못 본다"
    assert client.get("/api/team-docs/dsr").status_code == 200, "운영자가 상세를 못 연다"


def test_turning_restriction_on_removes_it_from_search_without_waiting_for_reindex(
    client, login_as, db, app, world,
):
    """제한을 켜면 **다음 색인을 기다리지 않고** 즉시 검색에서 사라진다.

    색인은 주기 작업이라(기본 300초) 그 사이에 창이 열린다. 질의 단계에도 같은 판정이
    있어야 그 창이 닫힌다 — 이것이 두 층으로 막는 이유다.
    """
    from app.team_docs.models import DocumentCache

    # 아직 제한이 아닌 문서를 색인해 둔다(검색에 잡히는 상태).
    _reindex(db, app)
    login_as("user", email=TEAMMATE)
    assert OPEN_TITLE in _titles(client)

    # 운영자가 제한을 켠다. 색인은 다시 돌지 않는다.
    doc = db.execute(
        select(DocumentCache).where(DocumentCache.notion_page_id == "dso")
    ).scalar_one()
    doc.restricted = True
    db.commit()

    login_as("user", email=TEAMMATE)
    assert OPEN_TITLE not in _titles(client), (
        "제한을 켰는데 다음 색인 전까지 검색으로 계속 찾힌다 — 질의 단계 판정이 없다"
    )
