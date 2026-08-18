"""**앱 사용자로 해석되지 않는 담당자**를 가진 티켓은 어디로 가는가.

## 원래 무엇이 위험했나

운영 실측: 색인 티켓행 1,058건 중 227건(21.5%)이 담당자 해석에 실패한다. 부서 범위를
담당자 축으로 판정하던 시절, 그 티켓들은 **어디에서도 안 보였다** — 해석된 담당자가 0명이라
부서 화면에서 빠지고, 미할당 버킷은 원시 Notion id 로 판정해 트리아지에서도 빠졌다.
다섯 건 중 한 건이 조용히 사라진다는 뜻이었다.

그때의 처방은 "그런 티켓도 미할당 트리아지에 넣는다" 였다. 사라지지는 않게 됐지만 다른
문제가 생겼다: **미할당 화면은 "아무도 안 맡은 일, 집어 가세요" 라는 뜻**인데, 거기에
이미 담당자가 있는 티켓이 섞였다. 남이 집어 가면 원래 담당자는 그 사실을 모른다.

## 0060 의 처방

두 사건을 분리한다(§12).

  * **미할당** = 담당자가 정말 없다 → 미할당 버킷. 사람이 집어 간다.
  * **매핑 실패** = 담당자는 있는데 앱이 그 사람을 못 알아본다 → **정합성 오류**.
    티켓 자체는 프로젝트 ACL 로 정상 노출되고(사라지지 않는다), 관리자 진단 화면
    (`/api/admin/integrity`)이 "사용자 매핑 필요" 목록으로 보여 준다.

원래 위험(티켓이 사라진다)은 그대로 막힌다 — 막는 방법이 바뀌었을 뿐이다. 이 파일은 그
두 가지를 함께 못박는다: **사라지지 않는가**, 그리고 **미할당으로 오분류되지 않는가**.
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
def signed_in(client, settings, notion, make_user, db, portal_project):
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


def test_an_unresolved_assignee_does_not_land_in_the_unassigned_bucket(
    client, app, settings, signed_in, notion
):
    """미할당 버킷은 **담당자가 없는 티켓만** 담는다 (0060 §12).

    "집어 가세요" 화면에 이미 임자가 있는 일이 섞이면, 남이 집어 가는 순간 원래 담당자는
    자기 일이 넘어갔다는 사실을 모른다.
    """
    _sync(app, settings)

    ids = {t["id"] for t in client.get("/api/tickets/unassigned").json()["tickets"]}

    assert "t-none" in ids, "담당자가 아예 없는 티켓이 트리아지에 없다 — 전제가 깨졌다"
    assert "t-ghost" not in ids, (
        "담당자가 있는데 해석만 실패한 티켓이 미할당으로 분류됐다 — 남이 집어 갈 수 있다"
    )
    assert "t-mapped" not in ids, "해석되는 담당자가 있는 티켓까지 트리아지에 들어왔다"


def test_but_it_does_not_disappear_either(client, app, settings, signed_in, notion):
    """**사라지지 않는다** — 원래 이 파일이 막던 그 사고다.

    미할당에서 뺐으니 다른 곳에서는 반드시 보여야 한다. 소속을 정하는 것은 프로젝트이고,
    담당자 해석 실패는 소속과 아무 상관이 없다.
    """
    _sync(app, settings)

    body = client.get("/api/tickets/team?active=false&page_size=100").json()
    ids = {t["id"] for t in body["items"]}
    assert "t-ghost" in ids, (
        "매핑 실패 티켓이 미할당에서도 빠지고 팀 목록에도 없다 — 다시 사라지는 상태다"
    )

    # 단건도 열려야 한다. 목록에만 있고 못 열면 그 티켓은 사실상 없는 것과 같다.
    assert client.get("/api/tickets/t-ghost").status_code == 200


def test_the_diagnostics_screen_lists_it_as_something_to_fix(
    client, app, settings, signed_in, notion, make_user
):
    """정상 노출로 끝내면 아무도 매핑을 안 고친다 — 진단이 **목록으로** 보여 줘야 한다."""
    from tests.conftest import DEFAULT_TEST_PASSWORD

    _sync(app, settings)
    make_user(email="triage-admin@goodmit.co.kr", role="system_admin", display_name="관리자")
    client.post("/login", json={"email": "triage-admin@goodmit.co.kr",
                                "password": DEFAULT_TEST_PASSWORD})

    report = client.get("/api/admin/integrity")
    assert report.status_code == 200, report.text
    finding = next(
        (f for f in report.json()["findings"] if f["key"] == "tickets_with_unmapped_assignees"),
        None,
    )
    assert finding is not None, "매핑 실패 항목이 진단에 아예 없다"
    assert finding["count"] >= 1, "매핑 실패 티켓이 있는데 진단은 0건이라고 말한다"
