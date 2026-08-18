"""통합 검색 범위 격리 (0030, PLAN Phase 5).

검색은 **가리기가 가장 쉽게 새는 자리**다. 목록 화면은 부서 필터를 걸어 두고 검색만
전역 인덱스를 그대로 훑으면, 화면에서 안 보이던 남의 부서 티켓·문서가 검색창 한 번에
전부 나온다. 그래서 여기서는 '접근이 막혔다'가 아니라 **'결과에 안 들어 있다'**를 못박는다.

인덱스는 실제 인덱서(`reindex_all`)로 만든다 — 손으로 `SearchDocument` 를 넣으면 인덱서가
소유자를 잘못 해석하는 결함(예: NAMES_SEP 를 콤마로 자르기)을 이 테스트가 못 잡는다.

## 0060 이후 — 무엇이 범위를 정하는가

축이 바뀌었다. 담당자·작성자가 아니라 **자원 자신의 Ownership** 이 정한다:

  * 티켓 → 프로젝트(정확히 하나). 프로젝트의 부서가 곧 티켓의 부서다.
  * 문서 → Portal 이 지정한 Ownership(프로젝트/부서/조직).
  * 게시판 → **조직 전체**. 부서로 나누지 않는다(§19) — 그래서 아래 게시판 시험은
    "안 보인다" 가 아니라 "보인다" 를 못박는다. 정책이 바뀌었고, 바뀐 정책이 실제로
    그렇게 동작하는지가 검사 대상이다.
  * 사용자 → 본인 소속.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.core.models_base import join_names
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.notion_mapping.models import SOURCE_MANUAL, STATUS_VERIFIED, UserNotionMapping
from app.board.models import Post
from app.search.indexer import reindex_all
from app.team_docs.models import DocumentCache
from app.team_docs.models import OWNER_DEPARTMENT
from app.tickets.models import (
    PROJECT_LINK_OK,
    SYNC_STATE_ID,
    TicketCache,
    TicketSyncState,
)

pytestmark = pytest.mark.security

PASSWORD = "Str0ng-Passw0rd!"
NOW = datetime(2026, 8, 3, 9, 0, 0)

D_DEV = "dept-dev-0001"
D_DEV_FE = "dept-dev-fe-01"
D_SALES = "dept-sales-001"


@pytest.fixture()
def org_tree(db):
    for row in (
        Department(id=D_DEV, name="개발팀", org_id=DEFAULT_ORG_ID, parent_id=None),
        Department(id=D_DEV_FE, name="프런트팀", org_id=DEFAULT_ORG_ID, parent_id=D_DEV),
        Department(id=D_SALES, name="영업팀", org_id=DEFAULT_ORG_ID, parent_id=None),
    ):
        db.add(row)
    db.commit()


@pytest.fixture()
def people(db, make_user, org_tree):
    made = {}

    def _mk(key, email, role, *, dept=None, scope="global", scope_dept=None, name=None):
        user = make_user(email=email, role=role, display_name=name or key)
        user.department_id = dept
        user.admin_scope = scope
        user.scope_dept_id = scope_dept
        user.scope_org_id = DEFAULT_ORG_ID if scope != "global" else None
        db.add(user)
        made[key] = user
        return user

    _mk("global_admin", "s-ga@goodmit.co.kr", "admin", dept=D_DEV, name="전역관리자")
    _mk("dept_admin", "s-da@goodmit.co.kr", "admin",
        dept=D_DEV, scope="dept", scope_dept=D_DEV, name="개발부서관리자")
    _mk("plain", "s-plain@goodmit.co.kr", "user", dept=D_DEV, name="일반사용자")
    _mk("target_fe", "s-fe@goodmit.co.kr", "user", dept=D_DEV_FE, name="프런트담당")
    _mk("target_sales", "s-sales@goodmit.co.kr", "user", dept=D_SALES, name="영업담당")
    db.commit()
    return {k: (v.id, v.email, v.display_name) for k, v in made.items()}


@pytest.fixture()
def projects(db, make_project, org_tree):
    """부서마다 프로젝트 하나. **티켓의 소속은 이 프로젝트가 정한다**(0060)."""
    return {
        "fe": make_project(name="프런트 프로젝트", dept=D_DEV_FE).id,
        "sales": make_project(name="영업 프로젝트", dept=D_SALES).id,
    }


@pytest.fixture()
def indexed(db, app, people, projects):
    """티켓·문서·게시판·채팅을 심고 **실제 인덱서**를 돌린다."""
    notion_ids = {}
    for key in ("target_fe", "target_sales"):
        notion_ids[key] = f"notion-search-{key}"
        db.add(UserNotionMapping(
            user_id=people[key][0], notion_user_id=notion_ids[key],
            status=STATUS_VERIFIED, source=SOURCE_MANUAL, last_verified_at=NOW,
        ))

    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status = "ok"
    state.last_run_at = NOW
    state.last_success_at = NOW
    state.ticket_count = 3
    db.add(state)

    # 같은 검색어(회의록)가 걸리는 티켓 3건 — 부서만 다르다.
    for uid, page, number, title, who, project in (
        ("s-tc-1", "s-page-1", 201, "영업팀 스프린트 회의록 정리", ["target_sales"], "sales"),
        ("s-tc-2", "s-page-2", 202, "프런트팀 스프린트 회의록 정리", ["target_fe"], "fe"),
        # 담당자는 두 부서인데 티켓은 **프런트 프로젝트** 것이다. 0060 에서 티켓의 소속을
        # 정하는 것은 담당자가 아니라 프로젝트다 — 담당자가 여럿이어도 소속은 하나다.
        ("s-tc-3", "s-page-3", 203, "공동 담당 회의록", ["target_fe", "target_sales"], "fe"),
    ):
        db.add(TicketCache(
            id=uid, notion_page_id=page, notion_ticket_number=number, title=title,
            status="진행", due_date="2026-08-10",
            assignee_notion_ids=join_names([notion_ids[k] for k in who]),
            project_uid=projects[project], project_link=PROJECT_LINK_OK,
            synced_at=NOW, created_at=NOW, updated_at=NOW,
        ))

    # 문서 2건 — 작성자 표시 이름으로 소유자를 해석한다.
    for page, title, author, dept in (
        ("s-doc-sales", "영업 회의록 초안", people["target_sales"][2], D_SALES),
        ("s-doc-fe", "프런트 회의록 초안", people["target_fe"][2], D_DEV_FE),
    ):
        db.add(DocumentCache(
            notion_page_id=page, title=title, author_names=join_names([author]),
            owner=author, synced_at=NOW, last_edited="2026-08-01",
            # 작성자가 아니라 **Portal 이 지정한 소속**이 판정한다(0060). 작성자가 부서를
            # 옮겨도 문서는 그대로 있어야 한다.
            owner_kind=OWNER_DEPARTMENT, owner_dept_id=dept,
        ))

    # 게시판 2건.
    for pid, title, author_key in (
        ("s-post-sales", "영업 회의록 공지", "target_sales"),
        ("s-post-fe", "프런트 회의록 공지", "target_fe"),
    ):
        db.add(Post(
            id=pid, author_user_id=people[author_key][0], category="notice",
            title=title, body="회의록 본문", created_at=NOW, updated_at=NOW,
        ))
    db.commit()

    result = reindex_all(
        db,
        tickets=app.state.repositories.tickets,
        documents=app.state.repositories.documents,
        now=NOW,
    )
    db.commit()
    assert result.status == "ok", result.error
    return result


def _login(client, email):
    response = client.post("/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def _titles(client, query: str, *, kind: str | None = None) -> set[str]:
    response = client.get("/api/search", params={"q": query})
    assert response.status_code == 200, response.text
    body = response.json()
    return {
        item["title"]
        for group in body["groups"] if kind is None or group["kind"] == kind
        for item in group["items"]
    }


# ── 부서 범위: 남의 부서 것이 결과에 없어야 한다 ──────────────────────────────


def test_dept_admin_does_not_see_another_departments_ticket(client, people, indexed):
    _login(client, people["dept_admin"][1])
    titles = _titles(client, "회의록", kind="ticket")
    assert "프런트팀 스프린트 회의록 정리" in titles, "자기 서브트리 티켓은 보여야 한다"
    assert "영업팀 스프린트 회의록 정리" not in titles, "범위 밖 티켓이 검색으로 새어 나왔다"


def test_dept_admin_does_not_see_another_departments_document(client, people, indexed):
    _login(client, people["dept_admin"][1])
    titles = _titles(client, "회의록", kind="document")
    assert "프런트 회의록 초안" in titles
    assert "영업 회의록 초안" not in titles, "범위 밖 문서가 검색으로 새어 나왔다"


def test_the_board_is_organization_wide_even_for_a_dept_admin(client, people, indexed):
    """자유게시판은 **조직 전체가 읽는다**(0060 §19) — 부서로 나누지 않는다.

    예전에는 작성자의 부서로 검색 결과가 좁혀졌다. 그런데 게시판 화면(`/board`)은 그때도
    조직 전체를 보여 줬다 — **검색만 좁았다.** 그 상태의 증상은 "게시판에서는 읽은 글이
    검색에서는 안 나온다" 이고, 그건 보안이 아니라 고장이다.

    조직 경계는 그대로 지킨다(`org_id`) — 그건 `test_search_org_isolation.py` 가 본다.
    """
    _login(client, people["dept_admin"][1])
    titles = _titles(client, "회의록", kind="board")
    assert {"프런트 회의록 공지", "영업 회의록 공지"} <= titles, (
        "조직 전체가 읽는 게시판이 검색에서만 부서로 좁혀졌다"
    )


def test_a_ticket_with_outside_assignees_still_belongs_to_its_project(
    client, people, indexed
):
    """담당자가 여러 부서여도 티켓의 소속은 **프로젝트 하나**다 (0060 §11).

    예전 규칙은 "담당자 중 한 명이라도 범위 안이면 보인다" 였다. 그 규칙은 티켓 하나를
    담당자 수만큼의 부서에 동시에 열었고, 그래서 남의 팀 사람을 담당자로 넣는 것만으로
    티켓이 그 팀에 노출됐다.

    지금은 프로젝트가 정한다. 여기서 확인하는 두 가지:

      1. 프로젝트를 가진 부서 줄기에서는 **사라지지 않는다** (예전 규칙이 지키던 성질).
      2. 담당자가 있다는 이유만으로 남의 부서에 열리지 **않는다** (예전 규칙의 구멍).

    담당자가 자기 티켓을 못 보는 상태가 되지 않도록, 담당자 후보 자체를 프로젝트에 닿을
    수 있는 사람으로 제한하는 것이 짝이 되는 규칙이다(§14, `list_assignees`).
    """
    _login(client, people["dept_admin"][1])
    assert "공동 담당 회의록" in _titles(client, "회의록", kind="ticket"), (
        "프로젝트를 가진 부서에서 티켓이 사라졌다"
    )

    # 영업팀 사람이 담당자로 들어 있지만, 티켓은 프런트 프로젝트 것이다.
    _login(client, people["target_sales"][1])
    assert "공동 담당 회의록" not in _titles(client, "회의록", kind="ticket"), (
        "담당자로 넣었다는 이유만으로 남의 부서 프로젝트 티켓이 열렸다"
    )


def test_global_admin_sees_every_department(client, people, indexed):
    _login(client, people["global_admin"][1])
    titles = _titles(client, "회의록")
    assert {"영업팀 스프린트 회의록 정리", "프런트팀 스프린트 회의록 정리"} <= titles
    assert {"영업 회의록 초안", "프런트 회의록 초안"} <= titles


# ── 유형별 역할 게이트: 사용자 검색 ──────────────────────────────────────────


def test_plain_user_cannot_search_people(client, people, indexed):
    """`/api/admin/users` 가 admin+ 인데 검색이 그 경계를 우회하면 안 된다."""
    _login(client, people["plain"][1])
    response = client.get("/api/search", params={"q": "영업담당"})
    assert response.status_code == 200
    kinds = {group["kind"] for group in response.json()["groups"]}
    assert "user" not in kinds, "일반 사용자에게 사용자 검색 결과가 나갔다(조직도 열거)"


def test_admin_can_search_people(client, people, indexed):
    _login(client, people["global_admin"][1])
    assert "영업담당" in _titles(client, "영업담당", kind="user")


def test_user_index_never_contains_email(client, people, indexed):
    """이메일이 색인되면 검색창이 '이 주소가 우리 회사에 있는가' 확인 도구가 된다."""
    _login(client, people["global_admin"][1])
    response = client.get("/api/search", params={"q": "s-sales@goodmit.co.kr"})
    assert response.status_code == 200
    assert response.json()["total"] == 0


# ── 인증 ─────────────────────────────────────────────────────────────────────


def test_search_requires_authentication(client):
    assert client.get("/api/search", params={"q": "회의록"}).status_code == 401


# ── 질의 모드 ────────────────────────────────────────────────────────────────


def test_korean_partial_match_through_the_api(client, people, indexed):
    """계획서가 확정한 사례를 **엔드포인트 층에서** 다시 확인한다."""
    _login(client, people["global_admin"][1])
    response = client.get("/api/search", params={"q": "린트 회"})
    body = response.json()
    assert body["mode"] == "fts"
    titles = {i["title"] for g in body["groups"] for i in g["items"]}
    assert "프런트팀 스프린트 회의록 정리" in titles


@pytest.mark.parametrize("query", ["회", "회의"])
def test_short_queries_fall_back_to_like_and_still_return_results(
    client, people, indexed, query
):
    """1~2자는 trigram 이 0건이다 — LIKE 폴백이 없으면 조용히 '없음'이 된다."""
    _login(client, people["global_admin"][1])
    body = client.get("/api/search", params={"q": query}).json()
    assert body["mode"] == "like"
    assert body["total"] > 0, f"{query!r} 가 LIKE 폴백으로도 0건이다"


def test_empty_query_returns_an_empty_envelope(client, people, indexed):
    _login(client, people["global_admin"][1])
    body = client.get("/api/search", params={"q": "   "}).json()
    assert body == {"query": "", "mode": "empty", "total": 0, "truncated": False, "groups": []}
