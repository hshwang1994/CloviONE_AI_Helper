"""handle_project_weekly_summary — 핸들러 자체의 unit 레벨 실패 케이스.

`tests/integration/test_project_weekly_llm_summary.py` 는 HTTP + Worker.run_once 를 통해
전체 배선(트리거→큐→저장)을 확인하지만, 핸들러 함수 자체의 이른 검증 분기(payload 누락,
프로젝트 없음)는 실제로 그 경로를 타지 않는다 - 라우터가 이미 유효한 project_id/week_of 로
enqueue 하기 때문이다. 이 파일은 핸들러를 직접 불러 그 두 분기를 커버한다
(`pytest --cov=app.jobs.handlers.project_weekly_summary` 로 확인한 미커버 라인: 50, 55).
"""

from __future__ import annotations

import pytest

from app.jobs import repository
from app.jobs.exceptions import PermanentJobError
from app.jobs.handlers.project_weekly_summary import handle_project_weekly_summary
from app.jobs.worker import WorkerContext
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import Project

pytestmark = pytest.mark.unit


def _ctx(settings, fake_clock):
    return WorkerContext(settings=settings, clock=fake_clock, outbound_client=None, extras={})


def _enqueue(db, now, payload):
    job = repository.enqueue(db, job_type="project_weekly_summary", payload=payload, now=now)
    db.commit()
    return job


def test_missing_project_id_raises_permanent_error_without_calling_llm(db, settings, fake_clock):
    now = fake_clock.now()
    job = _enqueue(db, now, {"week_of": "2026-08-03"})  # project_id 없음

    with pytest.raises(PermanentJobError, match="project_id/week_of"):
        handle_project_weekly_summary(db, job, _ctx(settings, fake_clock))


def test_missing_week_of_raises_permanent_error(db, settings, fake_clock):
    now = fake_clock.now()
    row = Project(name="감마", code="GKWUNT", org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.commit()
    job = _enqueue(db, now, {"project_id": row.id})  # week_of 없음

    with pytest.raises(PermanentJobError, match="project_id/week_of"):
        handle_project_weekly_summary(db, job, _ctx(settings, fake_clock))


def test_deleted_project_raises_permanent_error_not_retryable(db, settings, fake_clock):
    """잡을 큐에 넣은 뒤 프로젝트가 지워진 경우 — 드물지만 재시도해도 안 생긴다(핸들러 docstring).

    PermanentJobError 여야 한다는 점이 핵심이다 — 평범한 예외였다면 워커가 백오프 뒤
    재시도를 스케줄하는데, 지워진 프로젝트는 몇 번을 재시도해도 다시 생기지 않는다.
    """
    now = fake_clock.now()
    job = _enqueue(db, now, {"project_id": "no-such-project-id", "week_of": "2026-08-03"})

    with pytest.raises(PermanentJobError, match="프로젝트를 찾을 수 없습니다"):
        handle_project_weekly_summary(db, job, _ctx(settings, fake_clock))
