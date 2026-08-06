"""**앱 사용자로 해석되지 않는 담당자**를 가진 티켓은 미할당 트리아지에 남는다.

## 무엇이 어긋나 있었나

`app/core/scope.py` 의 모듈 docstring 이 이 쟁점을 이미 종결해 놓았다:

    담당자가 아무도 없는(**또는 앱 사용자로 해석되지 않는**) 티켓은 어느 부서에도 속하지
    않으므로 포탈 전용 버킷(미할당 트리아지)에 남고 부서 범위에는 안 나온다.

그런데 `repository_notion.list_unassigned()` 는 `assignee_notion_ids == ""` 로만 걸렀다 —
**Notion 담당자가 있지만 앱 사용자로 매핑되지 않은 티켓은 그 버킷에 들어오지 않는다.**

## 왜 이게 위험한가

부서 범위를 켜는 순간 그 티켓들은 **어디에서도 안 보인다**:

  * `any_assignee_visible()` 은 해석된 담당자 집합이 비면 `False` → 부서 화면에서 빠지고,
  * 미할당 버킷은 원시 Notion id 로 판정하므로 → 트리아지에서도 빠진다.

전체 관리자만 볼 수 있게 되는데, 그 사람들은 이 티켓을 찾을 이유가 없다.
**운영 실측: 색인 티켓행 1,058건 중 227건(21.5%)이 담당자 해석에 실패한다.**
다섯 건 중 한 건이 조용히 사라진다는 뜻이다. 사용자가 겪는 일은 X1 과 같다 —
"일이 영원히 사라진다".
"""

from __future__ import annotations

import pytest

from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.integration

MAPPED_NID = "notion-mapped"
GHOST_NID = "notion-ghost"      # Notion 에는 있지만 앱 사용자로 매핑되지 않은 사람


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id="t-none", tid=1, title="담당자 없음", status="계획", people=[]),
            task_row(page_id="t-mapped", tid=2, title="매핑된 담당자", status="진행",
                     people=[MAPPED_NID]),
            task_row(page_id="t-ghost", tid=3, title="매핑 안 된 담당자", status="진행",
                     people=[GHOST_NID]),
        ],
        projects=[project_row(page_id="p1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def signed_in(client, settings, notion, make_user, db):
    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    me = make_user(email="triage@goodmit.co.kr", role="user", display_name="트리아지")
    db.add(UserNotionMapping(user_id=me.id, notion_user_id=MAPPED_NID, status=STATUS_VERIFIED))
    db.commit()
    from tests.conftest import DEFAULT_TEST_PASSWORD

    r = client.post("/login", json={"email": "triage@goodmit.co.kr",
                                    "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return me


def _sync(app, settings):
    from app.tickets.sync import sync_tickets

    with app.state.session_factory() as db:
        sync_tickets(db, outbound=app.state.outbound_client, settings=settings,
                     now=app.state.clock.now())
        db.commit()


def test_a_ticket_whose_assignee_does_not_resolve_stays_in_triage(
    client, app, settings, signed_in, notion
):
    _sync(app, settings)

    ids = {t["id"] for t in client.get("/api/tickets/unassigned").json()["tickets"]}

    assert "t-none" in ids, "담당자가 아예 없는 티켓이 트리아지에 없다 — 전제가 깨졌다"
    assert "t-ghost" in ids, (
        "Notion 담당자가 앱 사용자로 해석되지 않는 티켓이 트리아지에서 빠졌다 — "
        "부서 범위를 켜면 이 티켓은 어디에서도 안 보인다"
    )
    assert "t-mapped" not in ids, "해석되는 담당자가 있는 티켓까지 트리아지에 들어왔다"
