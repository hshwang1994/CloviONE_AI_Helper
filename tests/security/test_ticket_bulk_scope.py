"""티켓 **일괄** 휴지통 경로도 범위를 지킨다.

## 이 결함이 어떻게 살아남았는가

단건(`POST /api/tickets/{page_id}/trash`)은 `ensure_in_scope` 를 지난다. 그런데 **일괄**
(`POST /api/tickets/trash-bulk`)은 루프 안에서 `ensure_can_edit` 만 불렀다.

`ensure_can_edit` 은 **범위 판정이 아니다**:
  * `MODERATOR_ROLES`(운영자 이상)를 **무조건** 통과시킨다 — 다른 부서 운영자가 그대로 지난다
  * 담당자가 없는 티켓은 **누구나** 통과시킨다

즉 부서 범위 운영자가 page_id 목록만 던지면 **범위 밖 티켓을 통째로 휴지통에 넣을 수 있었다.**
휴지통 모듈에서 정확히 같은 것("단건만 막으면 소용없다 — 일괄도 뚫린다")을 겪고 고쳐 놓고도
티켓에서 반복했다.

정적 검사(`scripts/check_scope_gates.py`)가 처음엔 이걸 **놓쳤다** — 두 가지 이유로:
  ① `/{id}` 경로만 봐서 본문으로 id 목록을 받는 일괄 경로를 안 봤다
  ② `ensure_can_edit` 을 범위 게이트로 인정했다(권한과 범위를 섞었다)
둘 다 고쳐서, 이제 이 결함을 되돌리면 검사가 먼저 잡는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

pytestmark = pytest.mark.security


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 팀 티켓 + 우리 팀만 관리하는 **운영자**(가장 뚫기 쉬운 역할)."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department
    from app.tickets.models import TicketCache, join_names

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    mate = make_user("bulk-mate@goodmit.co.kr", role="user", display_name="동료")
    other = make_user("bulk-other@goodmit.co.kr", role="user", display_name="남")
    boss = make_user("bulk-boss@goodmit.co.kr", role="admin", display_name="팀관리자")
    mate.department_id = mine.id
    other.department_id = theirs.id
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

    def _map(user, nid):
        db.add(UserNotionMapping(user_id=user.id, notion_user_id=nid, status=STATUS_VERIFIED))
        return nid

    n_mate = _map(mate, "n-mate")
    n_other = _map(other, "n-other")
    db.add_all([
        TicketCache(notion_page_id="p-ours", title="우리 티켓", org_id=DEFAULT_ORG_ID,
                    assignee_notion_ids=join_names([n_mate])),
        TicketCache(notion_page_id="p-theirs", title="남의 티켓", org_id=DEFAULT_ORG_ID,
                    assignee_notion_ids=join_names([n_other])),
    ])
    db.commit()
    return {"mine": mine, "theirs": theirs}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """🔴 **이 픽스처가 없으면 이 파일의 테스트는 헛것이 된다.**

    일괄 경로는 건별로 `repo.get_live()` 로 소스에서 제목·URL 을 다시 읽는다. 테스트에서는
    그 왕복이 실패하므로, 범위 게이트를 **떼어도** 그 실패가 `failed` 에 들어가 결과가 똑같다 —
    즉 게이트가 없어도 통과한다. 처음에 정확히 그렇게 만들어서 RED 가 안 나왔다.

    소스를 성공시켜 두면 **막을 수 있는 것이 범위 판정 하나뿐**이 되어 검사가 뜻을 갖는다.
    """
    from app.tickets import service as ticket_service
    from app.tickets.repository import TicketDTO

    class _Repo:
        @staticmethod
        def get_live(db, *, page_id):
            return TicketDTO(page_id=page_id, title="티켓", url=None)

    monkeypatch.setattr(ticket_service, "_repo", lambda *a, **k: _Repo())


def _still_untrashed(db, page_id: str) -> bool:
    from app.trash.models import TrashItem

    return db.execute(
        select(TrashItem).where(TrashItem.notion_page_id == page_id)
    ).scalar_one_or_none() is None


def test_bulk_trash_cannot_reach_another_teams_ticket(client, login_as, db, world):
    csrf = login_as("admin", email="bulk-boss@goodmit.co.kr")
    r = client.post(
        "/api/tickets/trash-bulk",
        json={"page_ids": ["p-theirs"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text            # 부분 성공 계약 — 전체가 실패하지 않는다
    body = r.json()
    assert body["trashed"] == [], f"일괄 경로로 범위 밖 티켓이 휴지통에 갔다: {body}"
    db.expire_all()
    assert _still_untrashed(db, "p-theirs"), "응답은 실패인데 실제로는 지워졌다"


def test_the_failure_does_not_reveal_that_the_ticket_exists(client, login_as, db, world):
    """범위 밖은 **404 와 같은 말**이어야 한다 — '권한이 없습니다' 는 존재를 알려 준다."""
    csrf = login_as("admin", email="bulk-boss@goodmit.co.kr")
    r = client.post(
        "/api/tickets/trash-bulk",
        json={"page_ids": ["p-theirs"]},
        headers={"X-CSRF-Token": csrf},
    )
    failed = r.json()["failed"]
    # 먼저 **정말 막혔는지** 확인한다 — 안 막혔으면 failed 가 비어 문구 검사가 공허해진다
    # (실제로 처음엔 그래서 이 테스트가 sabotage 에도 통과했다).
    assert len(failed) == 1, f"막히지 않았다: {r.json()}"
    msg = failed[0].get("error", "")
    assert "권한" not in msg, f"범위 밖 티켓의 존재를 문구가 알려 준다: {msg!r}"


def test_bulk_trash_still_works_for_my_own_team(client, login_as, db, world):
    """오탐 방지 — 좁히느라 자기 팀 일괄 삭제까지 막으면 그건 기능 고장이다."""
    csrf = login_as("admin", email="bulk-boss@goodmit.co.kr")
    r = client.post(
        "/api/tickets/trash-bulk",
        json={"page_ids": ["p-ours"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    assert [t["id"] for t in r.json()["trashed"]] == ["p-ours"], (
        f"자기 팀 티켓을 일괄로 지울 수 없다: {r.json()}"
    )
