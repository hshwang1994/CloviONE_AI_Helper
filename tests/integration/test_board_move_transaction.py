"""칸반 Drop 은 **다섯을 한 트랜잭션**으로 처리한다 (§5.2 · BACKLOG P-15).

상태 변경 · 활동 · 감사 · `updated_at` · 알림. 하나라도 따로 커밋되면 어긋난다:

  * 상태만 바뀌고 활동이 안 남으면 사람이 "내가 안 옮겼다" 를 증명할 방법이 없다.
  * 알림만 가고 상태가 롤백되면 **없는 변화를 통보**한 것이 된다.

「한 트랜잭션인가」는 각각이 남았는지 세는 것만으로는 증명되지 않는다. 그래서 **실패를
주입해** 다섯이 함께 사라지는지도 본다 — 그쪽이 진짜 단정이다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.audit.models import AuditLog
from app.notifications.models import Notification
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project
from app.tickets.models import PROJECT_LINK_OK, Ticket
from app.work import keys as work_keys
from app.work.models import TicketActivity, TicketWatcher

pytestmark = pytest.mark.integration

BOSS = "board-move@goodmit.co.kr"
WATCHER = "board-watch@goodmit.co.kr"
PAGE = "page-board-1"


class _FakeRepo:
    """소스까지 반영하는 저장소의 대역. **로컬 캐시를 실제로 고친다.**

    상태 변경만은 `app/tickets/service.py::update_ticket` 을 지나고, 그 함수는 저장소
    구현체가 캐시 행까지 고친다고 약속한다. 대역이 그 약속을 안 지키면 이 시험은
    「상태가 안 바뀌었다」로 실패한다 — 대역의 결함이지 제품의 결함이 아니다.
    """

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def _row(self, db, page_id):
        """**요청의 세션**으로 읽는다 — 시험의 세션이 아니다.

        둘은 같은 커넥션을 나눠 쓰므로(공유 계층, D-190) 시험 세션으로 쓰면 요청이 연
        SAVEPOINT 를 밖에서 건드리게 되고, 그 실패는 「savepoint 가 없다」로 나타난다.
        원인이 제품과 무관한 자리라 찾는 데 오래 걸린다.
        """
        return db.execute(
            select(Ticket).where(Ticket.notion_page_id == page_id)
        ).scalar_one()

    def _dto(self, row):
        from app.tickets.repository import TicketDTO

        return TicketDTO(
            page_id=row.notion_page_id, uid=row.id, number=row.notion_ticket_number,
            title=row.title, status=row.status, project_uid=row.project_uid,
        )

    def get_live(self, db, *, page_id):
        return self._dto(self._row(db, page_id))

    def update(self, db, *, page_id, changes, now):
        if self.fail:
            # 소스가 살아서 거절한 경우. `update_ticket` 은 이 예외를 그대로 올린다.
            from app.core.errors import NotionQueryError

            raise NotionQueryError("소스가 거절했다")
        row = self._row(db, page_id)
        if "status" in changes:
            row.status = changes["status"]
        db.flush()
        return self._dto(row)


@pytest.fixture()
def world(db, make_user):
    boss = make_user(BOSS, role="admin", display_name="관리자")
    boss.admin_scope = "global"
    watcher = make_user(WATCHER, role="user", display_name="지켜보는 사람")
    db.commit()

    project = Project(
        name="보드 프로젝트", org_id=DEFAULT_ORG_ID, notion_page_id="proj-board"
    )
    db.add(project)
    db.flush()
    work_keys.claim(db, project_id=project.id, key="BRD")

    ticket = Ticket(
        title="옮길 티켓", notion_page_id=PAGE, project_uid=project.id,
        project_link=PROJECT_LINK_OK, status="계획", org_id=DEFAULT_ORG_ID,
        source="notion", notion_ticket_number=7, legacy_key="GIT-7",
    )
    db.add(ticket)
    db.flush()
    db.add(TicketWatcher(ticket_id=ticket.id, user_id=watcher.id))
    db.commit()
    return {"project": project, "ticket": ticket, "boss": boss, "watcher": watcher}


def _install(monkeypatch, client, repo):
    """`app.state.repositories` 는 frozen dataclass 라 필드를 못 갈아 끼운다 —
    묶음 자체를 바꾼다(`dataclasses.replace`)."""
    import dataclasses

    monkeypatch.setattr(
        client.app.state,
        "repositories",
        dataclasses.replace(client.app.state.repositories, tickets=repo),
    )


def _counts(db, ticket_id, user_id):
    return {
        "activities": db.execute(
            select(func.count()).select_from(TicketActivity).where(
                TicketActivity.ticket_id == ticket_id
            )
        ).scalar_one(),
        "audits": db.execute(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "ticket.board_move"
            )
        ).scalar_one(),
        "notifications": db.execute(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id,
                Notification.type == "ticket_status_changed",
            )
        ).scalar_one(),
    }


def _move(client, login_as, ticket_id, body):
    return client.post(
        f"/api/work/board/{ticket_id}/move",
        json=body,
        headers={"X-CSRF-Token": login_as("admin", email=BOSS)},
    )


def test_one_drop_writes_all_five(client, login_as, db, world, monkeypatch):
    """상태 · 활동 · 감사 · `updated_at` · 알림이 **한 번에** 남는다."""
    ticket = world["ticket"]
    before_updated = ticket.updated_at
    _install(monkeypatch, client, _FakeRepo())

    r = _move(client, login_as, ticket.id, {"to_status": "진행", "base_version": 1})
    assert r.status_code == 200, r.text

    db.commit()
    db.expire_all()
    row = db.get(Ticket, ticket.id)
    assert row.status == "진행", "상태가 안 바뀌었다"
    assert row.version == 2, "낙관적 잠금이 안 올라갔다 — 다음 저장이 충돌을 못 잡는다"
    assert row.updated_at > before_updated, "목록 정렬이 이 값을 쓴다"

    counts = _counts(db, ticket.id, world["watcher"].id)
    assert counts["activities"] >= 1, "「누가 언제 옮겼나」가 안 남았다"
    assert counts["audits"] == 1, "감사에 안 남았다"
    assert counts["notifications"] == 1, "관찰자가 못 받았다"


def test_a_failure_leaves_none_of_the_five(client, login_as, db, world, monkeypatch):
    """**이쪽이 진짜 단정이다** — 소스가 거절하면 다섯이 함께 사라진다.

    각각이 남았는지 세는 것만으로는 「한 트랜잭션」이 증명되지 않는다. 다섯을 따로
    커밋하는 구현도 그 시험은 통과한다.
    """
    ticket = world["ticket"]
    _install(monkeypatch, client, _FakeRepo(fail=True))

    r = _move(client, login_as, ticket.id, {"to_status": "진행", "base_version": 1})
    assert r.status_code >= 400, "소스가 거절했는데 성공으로 답했다"

    db.rollback()
    db.expire_all()
    row = db.get(Ticket, ticket.id)
    assert row.status == "계획", "실패했는데 상태가 바뀌어 있다"
    assert row.version == 1

    counts = _counts(db, ticket.id, world["watcher"].id)
    assert counts == {"activities": 0, "audits": 0, "notifications": 0}, (
        f"실패한 이동의 흔적이 남았다: {counts}"
    )


def test_a_stale_version_is_refused(client, login_as, db, world, monkeypatch):
    """두 사람이 같은 판을 열어 두면 나중 사람이 앞사람의 이동을 덮어쓴다 — **둘 다
    성공한 것처럼 보인다.** 그래서 편집을 시작할 때 받은 판을 돌려보내게 한다."""
    ticket = world["ticket"]
    _install(monkeypatch, client, _FakeRepo())

    first = _move(client, login_as, ticket.id, {"to_status": "진행", "base_version": 1})
    assert first.status_code == 200, first.text
    db.commit()

    stale = _move(client, login_as, ticket.id, {"to_status": "완료", "base_version": 1})
    assert stale.status_code == 409, f"낡은 판으로 덮어썼다: {stale.status_code}"

    db.expire_all()
    assert db.get(Ticket, ticket.id).status == "진행"


def test_an_unknown_status_is_refused(client, login_as, db, world, monkeypatch):
    """어휘 밖 상태는 **앱이** 거절한다.

    예전에는 상태 허용값이 외부 스키마 조회에서 왔다 — 오타 하나가 새 상태로 저장됐고
    그 티켓은 어느 칸반 열에도 안 나타났다.
    """
    _install(monkeypatch, client, _FakeRepo())
    r = _move(
        client, login_as, world["ticket"].id, {"to_status": "진행중", "base_version": 1}
    )
    assert r.status_code == 422, f"모르는 상태를 받아들였다: {r.status_code} {r.text}"


def test_an_empty_move_is_refused(client, login_as, db, world, monkeypatch):
    """아무것도 안 바뀌는 요청이 판을 올리면 **다른 사람의 편집이 헛 충돌**한다."""
    _install(monkeypatch, client, _FakeRepo())
    r = _move(client, login_as, world["ticket"].id, {"base_version": 1})
    assert r.status_code == 422, f"빈 이동을 받아들였다: {r.status_code}"
    db.expire_all()
    assert db.get(Ticket, world["ticket"].id).version == 1


def test_reordering_writes_a_rank_and_an_activity(client, login_as, db, world, monkeypatch):
    """순서만 바꾸는 이동도 활동으로 남는다 — 백로그에서 그것이 유일한 변화다."""
    _install(monkeypatch, client, _FakeRepo())
    r = _move(
        client, login_as, world["ticket"].id, {"reorder": True, "base_version": 1}
    )
    assert r.status_code == 200, r.text
    db.commit()
    db.expire_all()

    row = db.get(Ticket, world["ticket"].id)
    assert row.backlog_rank is not None, "순위가 안 붙었다"
    kinds = [
        a.kind
        for a in db.execute(
            select(TicketActivity).where(TicketActivity.ticket_id == row.id)
        ).scalars()
    ]
    assert "rank" in kinds, f"순서 변경이 활동에 안 남았다: {kinds}"
