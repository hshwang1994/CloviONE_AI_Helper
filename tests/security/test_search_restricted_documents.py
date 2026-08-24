"""문서 단위 열람 제한은 **검색에서도** 집행돼야 한다.

열람 제한의 존재 이유가 "같은 팀이 곧 봐도 되는 사람은 아니다" 인데, 검색 한 줄이면 제목과
분류가 그대로 나온다. 상세는 404 라 본문은 못 읽지만, 제목 자체가 민감한 문서(예:
"OO사 이관 계정 목록")에서는 제목만으로도 유출이다.

## S14 에서 축이 옮겨 갔다

옛 미러(`document_cache.restricted`)가 아니라 정본의 `documents.confidential` 이다
(D1 · D-245). 공간의 `confidential` 도 함께 본다 — 비밀 공간에 든 문서는 공간이 이미
닫혀 있는데 색인 행은 그 사실을 안 들고 있어서, 문서 자신만 보면 그 공간이 통째로 샌다.

축을 옮기는 일 자체가 이 시험이 지키는 것이다. 색인이 새 표를 가리키기 시작했는데 질의
쪽 절이 옛 표를 계속 대조하면 그 절은 **어떤 행에도 안 걸리는 항상-참**이 되고, 그러면 이
층이 조용히 사라진다. 없어진 것은 화면에 안 보인다.

이 파일은 그 구멍을 두 층에서 막는다:
  1. **색인** — 제한 문서는 색인에 담기지 않는다(가장 확실한 fail-closed).
  2. **질의** — 색인에 남아 있더라도(제한을 켠 직후, 다음 색인 전) 결과에서 빠진다.

**예외는 없다.** 작성자와 운영자군도 검색으로는 못 찾는다 — 검색 색인은 범위가 없는 전역
저장소라 예외를 하나 열면 그 예외가 인덱스 안 ACL 의 시작이 된다(채팅을 통째로 안 담는
규칙과 같은 판단). 기능은 잃지 않는다: 그 사람들은 문서 목록에서 그대로 보고 열 수 있다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.security

NOW = datetime(2026, 8, 19, tzinfo=timezone.utc).replace(tzinfo=None)

OP = "docsr-op@goodmit.co.kr"          # 우리팀만 관리하는 부서 운영자
AUTHOR = "docsr-author@goodmit.co.kr"  # 제한 문서의 작성자
TEAMMATE = "docsr-mate@goodmit.co.kr"  # 같은 부서 동료(작성자 아님)

SECRET_TITLE = "제한 문서 인수인계 계정"
OPEN_TITLE = "일반 문서 인수인계 절차"
SECRET_SPACE_TITLE = "비밀 공간 인수인계 메모"


@pytest.fixture()
def world(db, make_user, make_space, make_knowledge_document):
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
    db.commit()

    space = make_space(name="우리 공간", slug="ours-sr", dept=mine, created_by=author)
    secret = make_knowledge_document(
        space=space, title=SECRET_TITLE, text="계정 목록",
        confidential=True, created_by=author,
    )
    open_doc = make_knowledge_document(
        space=space, title=OPEN_TITLE, text="인수인계 절차", created_by=author,
    )
    # 문서 자신은 열려 있는데 **공간이 비밀**인 경우.
    secret_space = make_space(
        name="비밀 공간", slug="secret-sr", dept=mine, confidential=True, created_by=author,
    )
    in_secret_space = make_knowledge_document(
        space=secret_space, title=SECRET_SPACE_TITLE, text="인수인계 메모", created_by=author,
    )
    return {
        "dept": mine,
        "secret_id": secret.id,
        "open_id": open_doc.id,
        "in_secret_space_id": in_secret_space.id,
    }


def _reindex(db, app):
    from app.search.indexer import reindex_all

    reindex_all(db, tickets=app.state.repositories.tickets, now=NOW)
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
    for hidden in (SECRET_TITLE, SECRET_SPACE_TITLE):
        leaked = [r.ref_id for r in rows if hidden in (r.title or "") + (r.body or "")]
        assert not leaked, f"열람 제한 문서가 검색 색인에 들어갔다: {hidden} {leaked}"


# ── 2층: 질의 ───────────────────────────────────────────────────────────────


def test_a_teammate_cannot_find_a_restricted_document(client, login_as, db, app, world):
    """목록에서 가린 문서를 검색으로 찾을 수 없다 — 같은 부서 동료 기준."""
    _reindex(db, app)
    login_as("user", email=TEAMMATE)
    titles = _titles(client)
    assert OPEN_TITLE in titles, "같은 부서 일반 문서가 검색에 안 나온다 — 범위를 과하게 좁혔다"
    assert SECRET_TITLE not in titles, "목록에서 가린 제한 문서가 검색 결과에 그대로 나온다"
    assert SECRET_SPACE_TITLE not in titles, "비밀 공간의 문서가 검색 결과에 그대로 나온다"


def _doc_titles(client):
    return {d["title"] for d in client.get("/api/knowledge/documents").json()["items"]}


def test_no_one_finds_a_restricted_document_through_search_but_the_function_is_not_lost(
    client, login_as, db, app, world,
):
    """**작성자도** 검색으로는 못 찾는다. 대신 문서 목록에서는 그대로 본다.

    예외를 하나 열면 그 예외가 인덱스 안 ACL 의 시작이 된다 — 채팅을 통째로 안 담는 규칙과
    같은 판단이다(`test_search_no_chat.py`: "'본인 것이니 괜찮다'로 예외를 하나 열면…").
    그래서 여기서 함께 확인하는 것이 **기능을 잃지 않았다**는 반대쪽 절반이다: 같은 사람이
    문서 목록에서는 그 문서를 그대로 보고 열 수 있다.
    """
    _reindex(db, app)
    secret_id = world["secret_id"]

    login_as("user", email=AUTHOR)
    assert SECRET_TITLE not in _titles(client), "작성자에게도 검색 색인은 열리지 않는다"
    assert SECRET_TITLE in _doc_titles(client), "작성자가 자기 제한 문서를 목록에서도 못 본다"
    assert client.get(f"/api/knowledge/documents/{secret_id}").status_code == 200, (
        "작성자가 자기 제한 문서의 상세를 못 연다"
    )


def test_turning_restriction_on_removes_it_from_search_without_waiting_for_reindex(
    client, login_as, db, app, world,
):
    """제한을 켜면 **다음 색인을 기다리지 않고** 즉시 검색에서 사라진다.

    색인은 주기 작업이라(기본 300초) 그 사이에 창이 열린다. 질의 단계에도 같은 판정이
    있어야 그 창이 닫힌다 — 이것이 두 층으로 막는 이유다.
    """
    from app.knowledge.models import Document

    # 아직 제한이 아닌 문서를 색인해 둔다(검색에 잡히는 상태).
    _reindex(db, app)
    login_as("user", email=TEAMMATE)
    assert OPEN_TITLE in _titles(client)

    # 운영자가 제한을 켠다. 색인은 다시 돌지 않는다.
    db.get(Document, world["open_id"]).confidential = True
    db.commit()

    login_as("user", email=TEAMMATE)
    assert OPEN_TITLE not in _titles(client), (
        "제한을 켰는데 다음 색인 전까지 검색으로 계속 찾힌다 — 질의 단계 판정이 없다"
    )
