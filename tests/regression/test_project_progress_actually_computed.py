"""프로젝트 진행률이 **영원히 계산되지 않던** 사고 (운영에서 눈으로 확인).

## 무엇이 보였나

프로젝트 22건 전부 "포털 계산: 아직 계산하지 않았습니다" 였다. 데이터는 있었다 -
티켓 1,069건이 프로젝트에 연결돼 있었다.

## 왜

`app/projects/service.py::recompute_progress` 는 진작에 있었지만 **아무도 부르지
않았다.** `sync.py::sync_projects` 는 프로젝트 필드(이름·기간·상태)만 갱신하고 끝났다.
계산기는 옳았는데 배선이 빠져 있었다 - X4 와 같은 모양이다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.regression

PROJ = "page-proj-progress"
DONE = "page-task-done"
OPEN = "page-task-open"


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=[
            task_row(page_id=DONE, tid=1, title="완료 작업", status="완료", people=[], project_ids=[PROJ]),
            task_row(page_id=OPEN, tid=2, title="진행 작업", status="진행", people=[], project_ids=[PROJ]),
        ],
        projects=[project_row(page_id=PROJ, name="진행률 확인용")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


def _sync_everything(client, db, settings):
    from app.projects.sync import sync_projects
    from app.tickets.sync import sync_tickets

    now = datetime(2026, 8, 7, 9, 0, 0)
    # 순서가 중요하다 - 진행률은 ticket_cache 를 센다. 티켓이 먼저 들어와야 한다
    # (worker_main.py 가 프로젝트 동기화를 티켓 동기화 뒤에 등록하는 것과 같은 이유).
    sync_tickets(db, outbound=client.app.state.outbound_client, settings=settings, now=now)
    db.commit()
    sync_projects(db, outbound=client.app.state.outbound_client, settings=settings, now=now)
    db.commit()


def test_the_sync_actually_computes_progress(client, settings, notion, db):
    """🔴 핵심 - 동기화가 끝나면 `progress_pct` 가 **NULL 이 아니어야** 한다."""
    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    _sync_everything(client, db, settings)
    db.expire_all()

    from sqlalchemy import select

    from app.projects.models import Project

    row = db.execute(select(Project).where(Project.notion_page_id == PROJ)).scalar_one()
    assert row.progress_pct is not None, (
        "동기화 뒤에도 진행률이 NULL 이다 - 운영에서 22건 전부 이 상태였다"
    )
    assert row.progress_pct == 50.0, f"완료 1건 / 전체 2건 = 50% 여야 한다: {row.progress_pct}"


def test_a_project_with_no_tasks_stays_none_not_zero(client, settings, fake_http, db):
    """오탐 방지 - 셀 것이 없으면 0% 가 아니라 '못 잰다' 여야 한다(progress.py 규칙)."""
    from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row

    world = FakeNotionTasksDB(
        rows=[], projects=[project_row(page_id="page-empty", name="빈 프로젝트")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)
    (settings.secrets_dir / "notion_report_token").write_text("t", encoding="utf-8")
    _sync_everything(client, db, settings)
    db.expire_all()

    from sqlalchemy import select

    from app.projects.models import Project

    row = db.execute(select(Project).where(Project.notion_page_id == "page-empty")).scalar_one()
    assert row.progress_pct is None, f"작업이 없는데 0%가 아닌 값을 냈다: {row.progress_pct}"
