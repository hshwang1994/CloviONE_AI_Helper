"""프로젝트 주간 리포트 AI 요약 (§L 소비처) — 잡이 AI 런타임을 부르는 경로 (D-515).

예전에는 `app/llm/service.py::LlmService` 를 불렀다. 이제 모든 생성이 AI 런타임 하나를 지나고, 이 잡도 액션
`report.weekly_summary` 로 그 문을 지난다. 이 파일은 그 배선을 확인한다.

qa-contract-change: 옛 설정 키 llm_enabled 를 관리 API 로 켜던 준비 단계와 그 응답 단언이 빠졌다. 생성 켜기는 이제 ai_* 설정이고 가짜 제공자를 끼우는 install_runtime 이 함께 채우며, 켜기 API 자체는 test_ai_console 이 잰다.

⚠️ 값이 실제로 달라지는 표본을 쓴다 — 트리거 전/후, 성공/실패 각각 저장본이 실제로
바뀌는지(또는 안 바뀌는지) 본다. 한 번만 부르고 문자열이 있는지만 보면 배선 없이도
통과할 수 있다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.ai.providers import base
from app.org.constants import DEFAULT_ORG_ID
from app.projects.models import REPORT_SOURCE_LLM, REPORT_SOURCE_RULE, Project, ProjectWeeklyReport

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 3, 1, 0, 0)  # KST 2026-08-03(월) 10:00
WEEK = "2026-08-03"
BOSS_EMAIL = "prj-llm-weekly@goodmit.co.kr"


@pytest.fixture()
def fake_clock():
    from tests.fakes.clock import FakeClock

    return FakeClock(NOW)


@pytest.fixture()
def project(db):
    # 프로젝트 코드는 서버가 짓는 대문자 여섯 글자이고 `I`·`L`·`O` 가 없다 (D-282).
    # 이 시험이 확인하는 것은 요약 배선이지 코드 값이 아니므로, 실패 메시지에서 어느
    # 프로젝트인지 바로 읽히도록 이름의 첫 글자를 여섯 번 쓴다.
    row = Project(name="감마", code="GGGGGG", org_id=DEFAULT_ORG_ID)
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def worker(app, fake_clock):
    """§L 잡을 결정적으로 하나 돌리는 워커. 진짜 제공자는 안 부른다 - 런타임에 가짜 제공자를 끼운다."""
    from app.jobs.worker import Worker, WorkerContext
    from app.worker_main import build_handlers
    from tests.fakes.ai import install_runtime

    def _make(adapter=None):
        ctx = WorkerContext(
            settings=app.state.settings,
            clock=fake_clock,
            outbound_client=app.state.outbound_client,
            extras={"ai_runtime": install_runtime(app, adapter)} if adapter is not None else {},
        )
        return Worker(app.state.session_factory, fake_clock, build_handlers(), ctx)

    return _make


class FakeBackend:
    """정해진 결과 하나를 돌려주는 제공자. 받은 프롬프트의 데이터 쪽을 남긴다."""

    def __init__(self, result: base.ProviderResult) -> None:
        self._result = result
        self.calls = 0
        self.last_body = None

    def generate(self, *, system, user, model, max_output_tokens, timeout) -> base.ProviderResult:
        self.calls += 1
        self.last_body = user
        return self._result


def _hdr(login_as):
    # system_admin: 프로젝트 쓰기(CONSOLE_OPS_ROLES)가 이 역할이면 통과한다. AI 설정은 워커를 만들 때
    # 가짜 제공자와 함께 채운다(`tests/fakes/ai.py::install_runtime`).
    return {"X-CSRF-Token": login_as("system_admin", email=BOSS_EMAIL)}


def test_trigger_enqueues_a_job_and_worker_saves_the_llm_summary(
    client, login_as, project, worker, fake_clock
):
    csrf = _hdr(login_as)

    r = client.post(
        f"/api/projects/{project.id}/weekly-report/llm-summary?week={WEEK}",
        headers=csrf,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "queued": True}

    backend = FakeBackend(base.success("이번 주 감마 프로젝트는 순조롭게 진행되었습니다."))
    assert worker(backend).run_once(fake_clock.now()) is True
    assert backend.calls == 1
    # 규칙이 만든 사실(summary_md)을 입력으로 줬다 — 새로 사실을 지어내지 않는다.
    assert "감마" in backend.last_body

    report = client.get(
        f"/api/projects/{project.id}/weekly-report?week={WEEK}", headers=csrf
    ).json()
    assert report["source"] == REPORT_SOURCE_RULE  # GET 은 여전히 LLM 을 안 부른다
    assert report["saved"]["source"] == REPORT_SOURCE_LLM
    assert report["saved"]["summary_md"] == "이번 주 감마 프로젝트는 순조롭게 진행되었습니다."


def test_failed_generation_leaves_the_existing_saved_report_untouched(
    client, login_as, project, worker, fake_clock, db
):
    csrf = _hdr(login_as)

    # 이미 규칙 기반 저장본이 있다 — 실패한 생성 시도가 이걸 지우면 안 된다.
    client.post(f"/api/projects/{project.id}/weekly-report?week={WEEK}", headers=csrf)
    before = db.execute(
        __import__("sqlalchemy").select(ProjectWeeklyReport)
        .where(ProjectWeeklyReport.project_id == project.id)
    ).scalar_one()
    assert before.source == REPORT_SOURCE_RULE
    before_text = before.summary_md

    client.post(f"/api/projects/{project.id}/weekly-report/llm-summary?week={WEEK}", headers=csrf)
    backend = FakeBackend(base.failure(base.ERROR_AUTH, "http_401", http_status=401))
    assert worker(backend).run_once(fake_clock.now()) is True

    db.expire_all()
    after = db.execute(
        __import__("sqlalchemy").select(ProjectWeeklyReport)
        .where(ProjectWeeklyReport.project_id == project.id)
    ).scalar_one()
    assert after.source == REPORT_SOURCE_RULE
    assert after.summary_md == before_text  # 손 안 댔다

    jobs = client.get("/api/admin/jobs?job_type=project_weekly_summary", headers=csrf).json()
    assert jobs["items"][0]["status"] == "failed"


def test_trigger_requires_write_role(client, login_as, project):
    csrf = login_as("user")
    r = client.post(
        f"/api/projects/{project.id}/weekly-report/llm-summary?week={WEEK}",
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403


def test_trigger_is_404_for_a_project_outside_scope(client, login_as, project, db):
    from app.org.models import Organization

    other_org = Organization(name="다른 회사", slug="other-co")
    db.add(other_org)
    db.commit()
    other = Project(name="델타", code="DDDDDD", org_id=other_org.id)
    db.add(other)
    db.commit()

    csrf = login_as("admin", email="scoped-llm-weekly@goodmit.co.kr")
    from app.users.models import User

    user = db.execute(
        __import__("sqlalchemy").select(User).where(User.email == "scoped-llm-weekly@goodmit.co.kr")
    ).scalar_one()
    user.admin_scope = "org"
    user.scope_org_id = DEFAULT_ORG_ID
    db.commit()

    r = client.post(
        f"/api/projects/{other.id}/weekly-report/llm-summary?week={WEEK}",
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 404
