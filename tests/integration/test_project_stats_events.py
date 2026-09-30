"""프로젝트 진행률 · Health 는 **바뀐 그 요청이 커밋될 때** 다시 계산된다 (계획 3.1).

예전에는 한 시간 주기 스윕만 캐시를 썼다. 여기서 확인하는 것:
- 새 프로젝트는 만든 순간 "작업 없음" 이다(계산 전이 아니다).
- 티켓 생성 · 상태 변경 · 프로젝트 이동 · 휴지통 · 복원 · 상하위 관계 · 마일스톤 · 프로젝트 상태가
  모두 캐시를 움직인다.
- 한 트랜잭션에서 여러 번 바꿔도 프로젝트당 계산은 한 번이다.
- 계산이 터져도 원래 쓰기는 커밋된다.
- 목록 API 가 값과 상태를 따로 준다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.projects import stats as project_stats
from app.projects.models import Project
from app.tickets.repository import TicketDraft
from app.tickets.repository_native import NativeTicketRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 30, 3, 0, 0)


def _fresh(db, project_id):
    db.expire_all()
    return db.get(Project, project_id)


def _create_ticket(db, project, *, status="진행", title="작업"):
    dto = NativeTicketRepository().create(
        db, draft=TicketDraft(title=title, status=status, project_id=project.id), now=NOW,
    )
    return dto


def test_a_new_project_is_computed_at_once(db, make_user):
    from app.core.scope import principal_from_user
    from app.projects.schemas import ProjectCreate
    from app.projects.service import create_project

    user = make_user("pm@goodmit.co.kr", role="admin")
    project = create_project(db, ProjectCreate(name="새 프로젝트", status="active"),
                             principal_from_user(db, user), now=NOW)
    db.commit()
    row = _fresh(db, project.id)
    assert row.stats_computed_at is not None, "만든 프로젝트가 다음 스윕까지 계산 전으로 남았다"
    view = project_stats.view(row)
    assert view["progress"]["state"] == project_stats.PROGRESS_NO_TASKS
    assert view["progress"]["pct"] is None


def test_creating_and_finishing_tickets_moves_progress(db, make_project):
    project = make_project(name="진행 프로젝트")
    first = _create_ticket(db, project, status="진행")
    _create_ticket(db, project, status="진행")
    db.commit()
    assert _fresh(db, project.id).progress_pct == 0.0

    NativeTicketRepository().update(db, page_id=first.page_id, changes={"status": "완료"}, now=NOW)
    db.commit()
    assert _fresh(db, project.id).progress_pct == 50.0


def test_moving_a_ticket_recomputes_both_projects(db, make_project):
    a = make_project(name="옮기기 전")
    b = make_project(name="옮긴 뒤")
    moving = _create_ticket(db, a, status="완료")
    _create_ticket(db, a, status="진행")
    db.commit()
    assert _fresh(db, a.id).progress_pct == 50.0

    NativeTicketRepository().update(db, page_id=moving.page_id, changes={"project": [b.id]}, now=NOW)
    db.commit()
    assert _fresh(db, a.id).progress_pct == 0.0, "옛 프로젝트가 떠난 티켓을 계속 셌다"
    assert _fresh(db, b.id).progress_pct == 100.0, "새 프로젝트가 옮겨 온 티켓을 안 셌다"


def test_trash_leaves_the_denominator_and_restore_brings_it_back(db, make_project, make_user):
    from app.trash import service as trash_service
    from app.trash.repository import get_by_page
    from app.trash.models import TRASH_TICKET

    user = make_user("owner@goodmit.co.kr", role="admin")
    project = make_project(name="휴지통 프로젝트")
    trashed = _create_ticket(db, project, status="진행", title="버릴 작업")
    _create_ticket(db, project, status="완료")
    db.commit()
    assert _fresh(db, project.id).progress_pct == 50.0

    trash_service.move_to_trash(db, item_type=TRASH_TICKET, notion_page_id=trashed.page_id,
                                title="버릴 작업", url=None, user=user, now=NOW)
    db.commit()
    assert _fresh(db, project.id).progress_pct == 100.0, "휴지통 티켓이 분모에 남았다"

    item = get_by_page(db, TRASH_TICKET, trashed.page_id)
    trash_service.restore(db, item, user)
    db.commit()
    assert _fresh(db, project.id).progress_pct == 50.0


def test_a_subtask_relation_changes_the_leaves(db, make_project):
    from app.work import relations
    from app.work.models import REL_SUBTASK_OF

    project = make_project(name="계층 프로젝트")
    parent = _create_ticket(db, project, status="진행", title="부모")
    child = _create_ticket(db, project, status="완료", title="자식")
    db.commit()
    assert _fresh(db, project.id).progress_pct == 50.0

    relations.add(db, from_ticket_id=child.uid, to_ticket_id=parent.uid, kind=REL_SUBTASK_OF, now=NOW)
    db.commit()
    assert _fresh(db, project.id).progress_pct == 100.0, "부모를 리프로 계속 셌다"


def test_an_overdue_milestone_moves_health(db, make_project):
    from app.projects import milestones
    from app.projects.schemas import MilestoneCreate

    project = make_project(name="마일스톤 프로젝트")
    _create_ticket(db, project, status="진행")
    db.commit()
    before = _fresh(db, project.id).health_score

    milestones.create(db, _fresh(db, project.id),
                      MilestoneCreate(name="지난 기한", due_on="2026-01-01", status="planned"), now=NOW)
    db.commit()
    after = _fresh(db, project.id).health_score
    assert after is not None and before is not None and after < before, (before, after)


def test_many_changes_in_one_transaction_compute_each_project_once(db, make_project, monkeypatch):
    from app.projects import service

    project = make_project(name="한 번만")
    tickets = [_create_ticket(db, project, title=f"작업 {i}") for i in range(3)]
    db.commit()

    calls: list[str] = []
    real = service.recompute_stats

    def _spy(db_, project_, **kw):
        calls.append(project_.id)
        return real(db_, project_, **kw)

    monkeypatch.setattr(service, "recompute_stats", _spy)
    for dto in tickets:
        NativeTicketRepository().update(db, page_id=dto.page_id, changes={"status": "완료"}, now=NOW)
    db.commit()
    assert calls == [project.id], calls
    assert _fresh(db, project.id).progress_pct == 100.0, "계산이 마지막 상태를 안 봤다"


def test_a_failing_recompute_does_not_lose_the_ticket_write(db, make_project, monkeypatch):
    from app.projects import service

    project = make_project(name="터지는 계산")
    dto = _create_ticket(db, project, status="진행")
    db.commit()

    def _boom(*_a, **_kw):
        raise RuntimeError("계산이 터졌다")

    monkeypatch.setattr(service, "recompute_stats", _boom)
    NativeTicketRepository().update(db, page_id=dto.page_id, changes={"status": "완료"}, now=NOW)
    db.commit()
    db.expire_all()
    from app.tickets.models import TicketCache

    assert db.get(TicketCache, dto.uid).status == "완료", "캐시 계산 실패가 사용자의 저장을 되돌렸다"


def test_a_finished_project_is_not_trouble(db, make_project):
    from app.projects.health import trouble_reasons

    assert trouble_reasons(10, "done") == []
    assert trouble_reasons(10, "on_hold") == []
    assert trouble_reasons(10, "active") != []


def test_the_list_api_reports_value_and_state_separately(client, login_as, make_project, db):
    login_as("system_admin")
    never = make_project(name="계산 전 프로젝트")
    db.commit()
    body = client.get("/api/projects").json()
    item = next(i for i in body["items"] if i["id"] == never.id)
    assert item["progress"] == {"pct": None, "state": "pending"}
    assert item["health"]["state"] == "pending"
