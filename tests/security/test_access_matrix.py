"""접근 행렬 — **한 표로** 주체 × 자원 × 경로를 전부 돌린다 (0060 §39/§40).

## 왜 표인가

권한 결함은 대개 "규칙이 틀려서" 가 아니라 **"한 경로만 빼먹어서"** 생긴다. 목록은 막았는데
단건은 안 막았고, 단건은 막았는데 댓글 목록은 안 막았고, 전부 막았는데 검색이 열려 있다.
경로마다 시험을 따로 쓰면 새 경로가 생겼을 때 아무도 그 사실을 모른다.

그래서 여기서는 **경로 목록**(`_PATHS`)과 **기대 행렬**(`_EXPECTED`)을 따로 두고 곱한다.
경로를 하나 추가하면 모든 주체에 대해 자동으로 검사된다 — 빼먹을 자리가 없다.

## 무엇을 기대하는가 (0060)

조회 범위는 **줄기**다: 조상 ∪ 자기 ∪ 후손. 같은 부모를 둔 형제는 서로 안 보인다.

    주체          A프로젝트   A-1프로젝트  A-2프로젝트  B-1프로젝트  조직공통  미지정문서
    org_direct       O           O           O            O          O        X
    a (A소속)        O           O           O            X          O        X
    a1 (A-1소속)     O           O           X            X          O        X
    b1 (B-1소속)     X           X           X            O          O        X
    unassigned       X           X           X            X          X        X
    a_admin          O           O           O            X          O        X
    a1_admin         O           O           X            X          O        X
    org_admin        O           O           O            O          O        X
    global_admin     O           O           O            O          O        **O**

`a1` 이 A(조상)를 보는 것은 의도다 — 상위 부서의 공통 업무는 아래에서도 보여야 한다.
`a` 가 A-1·A-2(후손)를 보는 것도 의도다. `a1` 이 A-2 를 못 보는 것이 **형제 배제**이고,
이 표의 핵심이다.

미지정 문서는 전역 관리자만 본다 — "판정할 수 없으면 닫는다" 를 지키되, 어디서도 못 찾는
상태로 두지는 않는다(그러면 고칠 수가 없다).

## 이 파일이 하지 않는 것

역할 게이트(누가 관리자 화면을 여는가)는 여기서 안 본다 — `test_admin_rbac.py` 의 몫이다.
여기는 **같은 역할이라도 범위 밖은 못 본다**만 본다. 두 축을 한 파일에 섞으면 어느 축이
막았는지 알 수 없어진다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.tickets.models import PROJECT_LINK_OK, SYNC_STATE_ID, TicketCache, TicketSyncState
from tests.fixtures.org_tree import (  # noqa: F401 — fixture 재수출
    org_tree,
    people,
    resources,
)

pytestmark = pytest.mark.security

PASSWORD = "Str0ng-Passw0rd!"
NOW = datetime(2026, 8, 3, 9, 0, 0)

# 자원 키 → 그 자원을 볼 수 있는 주체 키 집합. **여기 없는 주체는 못 본다.**
_EXPECTED: dict[str, frozenset[str]] = {
    "a": frozenset({"org_direct", "a", "a1", "a2", "a_admin", "a1_admin",
                    "org_admin", "global_admin"}),
    "a1": frozenset({"org_direct", "a", "a1", "a_admin", "a1_admin",
                     "org_admin", "global_admin"}),
    "a2": frozenset({"org_direct", "a", "a2", "a_admin", "org_admin", "global_admin"}),
    "b1": frozenset({"org_direct", "b1", "org_admin", "global_admin"}),
    "org": frozenset({"org_direct", "a", "a1", "a2", "b1", "a_admin", "a1_admin",
                      "org_admin", "global_admin"}),
    "unset": frozenset({"global_admin"}),
}

ALL_SUBJECTS = frozenset({
    "org_direct", "a", "a1", "a2", "b1", "unassigned",
    "a_admin", "a1_admin", "org_admin", "global_admin",
})


@pytest.fixture()
def tickets(db, resources):
    """프로젝트마다 티켓 하나. 티켓의 소속은 **프로젝트가 정한다**(0060 §11)."""
    state = db.get(TicketSyncState, SYNC_STATE_ID) or TicketSyncState(id=SYNC_STATE_ID)
    state.status = "ok"
    state.last_run_at = NOW
    state.last_success_at = NOW
    db.add(state)
    made = {}
    for i, (key, project) in enumerate(resources["projects"].items()):
        page = f"am-page-{key}"
        db.add(TicketCache(
            id=f"am-tc-{key}", notion_page_id=page, notion_ticket_number=900 + i,
            title=f"{key} 티켓", status="진행", due_date="2026-08-10",
            # 담당자는 일부러 **비운다** — 담당자가 판정에 끼면 이 표가 무엇을 재는지
            # 흐려진다. 0060 에서 담당자는 소속을 정하지 않는다.
            assignee_notion_ids="",
            project_uid=project.id, project_link=PROJECT_LINK_OK,
            synced_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        made[key] = page
    db.commit()
    return made


def _login(client, people, key):
    response = client.post(
        "/login", json={"email": people[key].email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


# ── 경로 목록 ────────────────────────────────────────────────────────────────
#
# 각 항목은 (이름, 부르는 함수) 다. 함수는 "이 주체가 이 자원을 **볼 수 있었는가**" 를
# bool 로 돌려준다. 새 경로를 여기 한 줄 넣으면 모든 주체 × 모든 자원에 대해 돌아간다.


def _project_list(client, resources, tickets, key) -> bool:
    body = client.get("/api/projects", params={"page_size": 100}).json()
    return any(p["id"] == resources["projects"][key].id for p in body.get("items", []))


def _project_detail(client, resources, tickets, key) -> bool:
    r = client.get(f"/api/projects/{resources['projects'][key].id}")
    assert r.status_code in (200, 404), r.text
    return r.status_code == 200


def _ticket_detail(client, resources, tickets, key) -> bool:
    r = client.get(f"/api/tickets/{tickets[key]}")
    assert r.status_code in (200, 404), r.text
    return r.status_code == 200


def _ticket_team_list(client, resources, tickets, key) -> bool:
    body = client.get("/api/tickets/team", params={"page_size": 100}).json()
    # 목록 항목의 식별자 키는 `id`(= Notion page id)다 — `page_id` 가 아니다.
    return any(t.get("id") == tickets[key] for t in body.get("items", []))


def _document_list(client, resources, tickets, key) -> bool:
    page_id = resources["documents"][key].notion_page_id
    body = client.get("/api/team-docs", params={"page_size": 100}).json()
    return any(d["id"] == page_id for d in body.get("items", []))


def _document_detail(client, resources, tickets, key) -> bool:
    r = client.get(f"/api/team-docs/{resources['documents'][key].notion_page_id}")
    assert r.status_code in (200, 404), r.text
    return r.status_code == 200


# 「문서 댓글」 경로는 여기 없다 (S14 · C2). 댓글 축이 정본 문서로 옮겨 가면서 이 행렬이
# 쓰는 미러 행(`document_cache`)과 다른 자원이 됐다. 「단건을 막고 댓글을 안 막는 실수」는
# 옮겨 간 자리에서 `tests/integration/test_knowledge_comments.py` 가 네 경로(목록·작성·
# 수정·삭제) 전부에 대해 고정한다.


# 프로젝트가 있는 자원 키 / 문서가 있는 자원 키가 다르다("unset" 은 문서만 있다).
_PROJECT_KEYS = ("a", "a1", "a2", "b1", "org")
_DOCUMENT_KEYS = ("a", "a1", "a2", "b1", "org", "unset")

_PATHS = (
    ("프로젝트 목록", _project_list, _PROJECT_KEYS),
    ("프로젝트 단건", _project_detail, _PROJECT_KEYS),
    ("티켓 단건", _ticket_detail, _PROJECT_KEYS),
    ("팀 티켓 목록", _ticket_team_list, _PROJECT_KEYS),
    ("문서 목록", _document_list, _DOCUMENT_KEYS),
    ("문서 단건", _document_detail, _DOCUMENT_KEYS),
)


@pytest.mark.parametrize("subject", sorted(ALL_SUBJECTS))
def test_access_matrix(client, people, resources, tickets, subject):
    """주체 하나가 **모든 경로 × 모든 자원**에서 표와 정확히 일치하는가.

    주체별로 시험을 나눈 이유는 실패 메시지 때문이다 — 한 덩어리로 돌리면 "어딘가 틀렸다"
    만 보이고, 나누면 "a1_admin 이 A-2 를 본다" 가 제목에 뜬다.
    """
    _login(client, people, subject)
    wrong: list[str] = []
    for label, probe, keys in _PATHS:
        for key in keys:
            expected = subject in _EXPECTED[key]
            actual = probe(client, resources, tickets, key)
            if actual != expected:
                wrong.append(
                    f"{label}/{key}: 기대 {'O' if expected else 'X'} "
                    f"실제 {'O' if actual else 'X'}"
                )
    assert not wrong, f"{subject} 의 접근이 표와 다르다:\n  " + "\n  ".join(wrong)


def test_the_matrix_is_not_vacuous(client, people, resources, tickets):
    """표가 **실제로 갈라지는지** 확인한다.

    모든 경로가 늘 404 를 주면 위 시험은 전원 통과한다 — 기대값도 대부분 X 이기 때문이다.
    그 상태는 "완벽히 안전한 고장난 제품" 이고, 보안 시험이 가장 자주 빠지는 함정이다.
    그래서 **같은 자원에 대해 답이 갈리는 두 주체**가 실제로 있는지 못박는다.
    """
    _login(client, people, "a1")
    assert _project_detail(client, resources, tickets, "a1"), "자기 팀 프로젝트도 안 보인다"
    assert not _project_detail(client, resources, tickets, "a2"), "형제 부서가 보인다"

    _login(client, people, "global_admin")
    assert _project_detail(client, resources, tickets, "a2"), "전역 관리자가 못 본다"


def test_an_unassigned_account_sees_nothing_but_is_not_broken(client, people, resources, tickets):
    """소속 미지정은 **조직 데이터가 하나도 안 보인다**. 다만 오류가 아니라 빈 목록이다.

    401/500 이 나면 사용자는 "로그인이 안 된다" 고 신고하고, 200 + 빈 목록이면 관리자가
    진단 화면에서 소속을 지정한다. fail-closed 는 앞의 것이 아니라 뒤의 것이다.
    """
    _login(client, people, "unassigned")
    for path in ("/api/projects", "/api/team-docs", "/api/tickets/team"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} 가 오류를 냈다: {r.text}"
        assert r.json().get("items") == [], f"{path} 에 항목이 남아 있다"
