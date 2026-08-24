"""담당자 축이 **옛 소스와 짝이 없는 계정에도 닿는다** (S15 · D-285).

## 무엇이 조용히 닫혀 있었나

티켓의 담당자 칸(`tickets.assignee_notion_ids`)은 이관해 온 행에 옛 소스의 user id 를
담고 있다. 그래서 담당자 축 전체 — 「내 티켓」의 기본 범위, 팀 티켓의 담당자 조건, 담당자
후보 목록, 배정 자체 — 가 `user_notion_mappings` 에 verified 행이 있는 사람만 가리킬 수
있었다.

🔴 그 짝은 **새로 만들 수 없다.** S14 가 Notion 런타임을 걷어낸 뒤(D-284) 새 계정에는 그
행이 영원히 안 생긴다. 실측(2026-08-24 운영 DB): 활성 15명 중 **2명**이 이 상태였고 그중
하나는 그날 만든 계정이다 — 앞으로 만드는 계정은 전부 이 상태로 태어난다.

그 사람들이 겪던 것은 오류가 아니라 **침묵**이었다:

  · `/my-tickets` 가 영원히 비어 있고, 화면은 「Notion 사용자와 연결되어 있지 않습니다」
    라고 말한다 — 연결할 상대가 없어졌으므로 그 안내는 수행 불가능한 절차다.
  · 담당자 후보 목록에 그 사람이 없다 → 아무도 그 사람에게 일을 줄 수 없다.
  · 팀 티켓의 담당자 조건으로 그 사람을 고를 수 없다.

## 이 파일이 고정하는 성질

  1. 짝 없는 계정도 **담당자 후보**로 나온다.
  2. 그 사람에게 배정할 수 있고, 배정한 티켓이 **그 사람의 「내 티켓」에 나온다**.
  3. 담당자 조건이 그 사람을 가리킬 수 있고, 결과가 정확하다(오탐 없음).
  4. 옛 짝이 있는 계정은 **한 글자도 안 바뀐다** — 옛 토큰으로 계속 걸린다.
  5. 🔴 브라우저가 **소스 id 를 말할 수는 없다**(§12.3). 그 값으로 거르면 목록이
     열리는 것이 아니라 **닫힌다**.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.regression

LEGACY_NID = "notion-legacy-person"


@pytest.fixture()
def people(db, make_user):
    """옛 짝이 있는 사람과 없는 사람 하나씩. 뒤엣것이 컷오버 뒤에 만든 계정이다."""
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    legacy = make_user(email="legacy@goodmit.co.kr", role="user", display_name="이관 사용자")
    native = make_user(email="native@goodmit.co.kr", role="user", display_name="새 사용자")
    db.add(UserNotionMapping(user_id=legacy.id, notion_user_id=LEGACY_NID,
                             status=STATUS_VERIFIED))
    db.commit()
    return {"legacy": legacy, "native": native}


@pytest.fixture()
def board(db, people, portal_project, make_ticket):
    """세 건 — 옛 담당자 / 새 담당자 / 미할당."""
    return {
        "legacy": make_ticket(page_id="ax-legacy", project=portal_project, tid=1,
                              title="옛 담당자 티켓", assignees=[LEGACY_NID]),
        "native": make_ticket(project=portal_project, tid=2,
                              title="새 담당자 티켓", assignees=[people["native"].id]),
        "none": make_ticket(project=portal_project, tid=3, title="미할당 티켓", assignees=[]),
    }


def _titles(body) -> set[str]:
    return {t["title"] for t in (body.get("items") or body.get("tickets") or [])}


def test_an_account_with_no_legacy_link_is_an_assignee_candidate(
    client, login_as, people, portal_project
):
    login_as("admin", email="ax-admin@goodmit.co.kr")
    body = client.get("/api/tickets/assignees").json()
    ids = {c["user_id"] for c in body["assignees"]}
    assert people["native"].id in ids, "짝이 없다는 이유로 후보에서 빠졌다 — 아무도 이 사람에게 일을 못 준다"
    assert people["legacy"].id in ids


def test_my_tickets_answers_for_that_account(client, board, people):
    from tests.conftest import DEFAULT_TEST_PASSWORD

    r = client.post("/login", json={"email": "native@goodmit.co.kr",
                                    "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200
    body = client.get("/api/tickets/mine").json()
    assert body["ok"] is True
    assert _titles(body) == {"새 담당자 티켓"}
    assert body["total"] == 1
    # 「연결이 필요하다」는 상태 자체가 없어졌다 — 응답에 그 축이 남아 있으면 화면이
    # 없는 실패 갈래를 되살린다.
    assert "mapped" not in body


def test_the_legacy_account_still_gets_its_own_tickets(client, board, people):
    from tests.conftest import DEFAULT_TEST_PASSWORD

    r = client.post("/login", json={"email": "legacy@goodmit.co.kr",
                                    "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200
    body = client.get("/api/tickets/mine").json()
    assert _titles(body) == {"옛 담당자 티켓"}, "옛 토큰으로 걸리던 티켓이 사라졌다"


def test_the_assignee_filter_can_point_at_that_account(client, login_as, board, people):
    login_as("admin", email="ax-admin@goodmit.co.kr")

    native = client.get(
        f"/api/tickets/team?assignee_user_id={people['native'].id}"
    ).json()
    assert _titles(native) == {"새 담당자 티켓"}
    assert native["total"] == 1

    legacy = client.get(
        f"/api/tickets/team?assignee_user_id={people['legacy'].id}"
    ).json()
    assert _titles(legacy) == {"옛 담당자 티켓"}


def test_the_browser_still_cannot_speak_source_ids(client, login_as, board):
    """§12.3 — 소스 id 로 거르면 열리는 것이 아니라 **닫힌다**.

    이 방향이 없으면 「가리킬 수 없으면 닫는다」가 「아무 값이나 통과시킨다」로 미끄러진다.
    """
    login_as("admin", email="ax-admin@goodmit.co.kr")
    body = client.get(f"/api/tickets/team?assignee_user_id={LEGACY_NID}").json()
    assert body["total"] == 0
    assert _titles(body) == set()

    unknown = client.get("/api/tickets/team?assignee_user_id=00000000-0000-0000-0000-000000000000").json()
    assert unknown["total"] == 0


def test_assigning_that_account_actually_sticks(client, login_as, board, people, db):
    """배정 → 그 사람의 목록에 나온다. 「저장은 됐는데 안 보인다」가 이 축의 옛 증상이다."""
    csrf = login_as("admin", email="ax-admin@goodmit.co.kr")
    r = client.patch(
        "/api/tickets/" + board["none"].id,
        json={"assignee_user_ids": [people["native"].id]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    assert people["native"].id in (r.json().get("ticket") or {}).get("assignee_user_ids", []), r.text

    from tests.conftest import DEFAULT_TEST_PASSWORD

    client.post("/login", json={"email": "native@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    body = client.get("/api/tickets/mine").json()
    assert _titles(body) == {"새 담당자 티켓", "미할당 티켓"}
