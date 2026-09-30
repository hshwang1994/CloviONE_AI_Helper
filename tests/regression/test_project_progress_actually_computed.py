"""프로젝트 진행률이 **영원히 계산되지 않던** 사고 (운영에서 눈으로 확인).

qa-contract-change: 예전에는 노션 동기화 회차(sync.py::sync_projects)가 진행률을 다시 계산했고 이 시험은 가짜 노션 서버에 행을 올려 그 회차를 돌렸다. S14 가 그 동기화를 없애면서(D-284) 계산기를 부르는 자리가 주기 스윕(record_health_snapshots) 하나로 옮겨졌고, 시험도 정본 표에 직접 심어 그 스윕을 돌리는 모양으로 다시 썼다.

## 무엇이 보였나

프로젝트 22건 전부 "포털 계산: 아직 계산하지 않았습니다" 였다. 데이터는 있었다 -
티켓 1,069건이 프로젝트에 연결돼 있었다.

## 왜

`app/projects/service.py::recompute_progress` 는 진작에 있었지만 **아무도 부르지
않았다.** 계산기는 옳았는데 배선이 빠져 있었다 - X4 와 같은 모양이다.

## 왜 이 시험이 S14 뒤에 더 중요해졌나

S14 가 그 배선을 **한 번 더 끊을 뻔했다.** 진행률을 부르던 유일한 자리가 노션 동기화
회차였는데 그 회차가 통째로 사라졌기 때문이다. 계산기는 남고 부르는 사람만 사라지는 —
정확히 같은 모양의 사고다. 그래서 이 시험은 이제 「계산기가 옳은가」가 아니라
**「누가 부르는가」**를 본다. 부르는 자리는 둘이다: 티켓을 바꾸는 쓰기 경로(커밋 직전,
`app/projects/stats.py`)와 안전망인 주기 스윕(`record_health_snapshots`).
"""

from __future__ import annotations

from datetime import datetime

import pytest

pytestmark = pytest.mark.regression

NOW = datetime(2026, 8, 24, 3, 0, 0)
TODAY = "2026-08-24"


def _sweep(db):
    """제품이 주기적으로 도는 그 함수. 워커가 시간마다 이것을 부른다(worker_main)."""
    from app.projects.service import record_health_snapshots

    record_health_snapshots(db, today=TODAY, now=NOW)
    db.flush()
    db.expire_all()


def test_the_periodic_sweep_actually_computes_progress(db, make_project, make_ticket):
    """🔴 핵심 - 스윕이 돌고 나면 `progress_pct` 가 **NULL 이 아니어야** 한다."""
    from app.projects.models import Project

    project = make_project(name="진행률 확인용")
    make_ticket(project=project, title="완료 작업", status="완료")
    make_ticket(project=project, title="진행 작업", status="진행")

    row = db.get(Project, project.id)
    assert row.progress_pct is None, (
        "심자마자 값이 차 있다 — 아래 단언이 스윕을 확인하지 못한다"
    )

    _sweep(db)

    row = db.get(Project, project.id)
    assert row.progress_pct is not None, (
        "스윕 뒤에도 진행률이 NULL 이다 - 운영에서 22건 전부 이 상태였다"
    )
    assert row.progress_pct == 50.0, f"완료 1건 / 전체 2건 = 50% 여야 한다: {row.progress_pct}"


def test_a_project_with_no_tasks_stays_none_not_zero(db, make_project):
    """오탐 방지 - 셀 것이 없으면 0% 가 아니라 '못 잰다' 여야 한다(progress.py 규칙)."""
    from app.projects.models import Project

    project = make_project(name="빈 프로젝트")
    _sweep(db)

    row = db.get(Project, project.id)
    assert row.progress_pct is None, f"작업이 없는데 0%가 아닌 값을 냈다: {row.progress_pct}"


def test_a_ticket_change_moves_the_cache_when_it_commits(db, make_project, make_ticket):
    """**배선이 있는지**를 본다. 이 시험이 지키는 것은 계산기가 아니라 부르는 사람이다.

    예전에는 「저장은 스윕만 한다」였다. 그래서 티켓을 끝내도 목록의 진행률이 한 시간 뒤에야
    움직였고, 새 프로젝트는 한 시간 동안 "계산 전" 이었다(계획 3.1). 이제는 티켓을 바꾸는 코드가
    그 프로젝트를 표시하고, 커밋 직전에 한 번 계산한다(`app/projects/stats.py`).
    """
    from app.projects.models import Project
    from app.tickets.repository_native import NativeTicketRepository

    project = make_project(name="상태가 바뀌는 프로젝트")
    done = make_ticket(project=project, title="완료 작업", status="완료")
    make_ticket(project=project, title="진행 작업", status="진행")
    _sweep(db)
    db.commit()
    assert db.get(Project, project.id).progress_pct == 50.0

    NativeTicketRepository().update(db, page_id=done.id, changes={"status": "진행"}, now=NOW)
    db.commit()
    db.expire_all()
    assert db.get(Project, project.id).progress_pct == 0.0, (
        "티켓 상태를 바꿔 커밋했는데 캐시가 그대로다 - 쓰기 경로의 표시가 끊겼다"
    )


def test_a_read_never_writes_the_cache(db, make_project, make_ticket):
    """GET 이 쓰기를 하면 캐시 · 재시도와 어긋나고 목록 정렬(`updated_at DESC`)이 무너진다.

    읽기 함수(`project_progress`)는 바뀐 표본으로 새로 계산해 돌려주지만 행은 건드리지 않는다.
    이 시험의 티켓 변경은 쓰기 경로를 거치지 않으므로(ORM 에 직접) 표시도 없다.
    """
    from app.projects.models import Project
    from app.projects.service import project_progress

    project = make_project(name="읽기만 하는 프로젝트")
    done = make_ticket(project=project, title="완료 작업", status="완료")
    make_ticket(project=project, title="진행 작업", status="진행")
    _sweep(db)
    db.commit()

    done.status = "진행"
    db.flush()
    fresh = project_progress(db, db.get(Project, project.id))
    assert fresh.percent == 0.0
    db.commit()
    db.expire_all()
    assert db.get(Project, project.id).progress_pct == 50.0, "읽기가 캐시를 썼다"
