"""AI 호출 기록 — 한도의 원장 (계획 3.10 · 3.11, D-517).

못박는 성질:
1. 런타임은 호출마다 한 행을 남긴다: 누가(부서 이름 포함), 어떤 기능으로, 어느 제공자와 모델에, 토큰과 지연, 결과.
   생성이 꺼져 있거나 설정이 비어 아무것도 시도하지 않은 호출은 남기지 않는다.
2. 한도는 **성공한** 호출만, **한도에 세는 액션**만 센다. 실패한 호출과 연결 확인은 한도를 줄이지 않는다.
3. 한도를 다 쓴 순간 한 번 알린다(성공한 호출을 적는 자리에서).
4. 퀴즈와 주간 요약도 한도 안이다 - 예전에는 한도 밖이었다. 막힌 요청은 「한도로 막힘」으로 남는다.
5. 기록이 실패해도 예외가 나가지 않는다 - 답은 이미 나갔다.

기록은 제 세션으로 곧바로 커밋한다. 공유 DB 계층의 시험은 세션들이 한 커넥션의 SAVEPOINT 로 겹치므로, 부른 쪽 세션이
롤백하면 안쪽에서 커밋한 기록까지 함께 사라진다(제품에서는 커넥션이 따로라 남는다). 그래서 이 파일은 런타임을 세션
없이 부르고(`generate(None, ...)`), 요청이 실패로 끝나는 시험은 전용 DB 계층(`real_db`)에서 돈다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.ai import usage
from app.ai.models import AiUsageRecord
from app.ai.providers import base
from app.quotas.models import AiQuota
from tests.fakes.ai import ScriptedAdapter, install_runtime, timeout_failure

pytestmark = pytest.mark.integration


def _rows(db) -> list[AiUsageRecord]:
    db.expire_all()
    return list(db.execute(select(AiUsageRecord).order_by(AiUsageRecord.created_at, AiUsageRecord.id)).scalars())


def _cap(db, user_id: str, *, max_calls: int, now) -> None:
    db.add(AiQuota(scope_type="user", user_id=user_id, period="day", max_calls=max_calls, created_at=now,
                   updated_at=now))
    db.commit()


def test_a_successful_call_leaves_one_row_with_who_what_and_how(app, db, two_orgs):
    person, team = two_orgs.user_a, two_orgs.dept_a
    runtime = install_runtime(app, ScriptedAdapter([base.success("답", input_tokens=120, output_tokens=30)]))
    result = runtime.generate(None, action_key="workspace.ask", task="답하라", data="질문과 근거", actor=person,
                              request_id="req-1")
    assert result.ok
    [row] = _rows(db)
    assert (row.action_key, row.status, row.user_id, row.actor_kind) == ("workspace.ask", "ok", person.id, "user")
    assert (row.provider, row.auth_method, row.model) == ("anthropic", "api_key", "test-model")
    assert (row.input_tokens, row.output_tokens, row.request_id) == (120, 30, "req-1")
    assert row.latency_ms is not None and row.latency_ms >= 0
    assert (row.department_id, row.department_name) == (team.id, "A팀"), "부서 이름은 그때의 이름을 남긴다"


def test_failures_are_recorded_and_idle_calls_are_not(app, db):
    runtime = install_runtime(app, ScriptedAdapter([timeout_failure()]))
    assert not runtime.generate(None, action_key="chat.answer", task="t", data="d").ok
    [row] = _rows(db)
    assert (row.status, row.error_code, row.actor_kind) == ("error", "timeout", "system")

    install_runtime(app, ScriptedAdapter(), enabled=False)
    app.state.ai_runtime.generate(None, action_key="chat.answer", task="t", data="d")
    assert len(_rows(db)) == 1, "생성이 꺼져 있어 아무것도 시도하지 않은 호출이 기록됐다"


def test_only_successful_counted_calls_use_up_the_limit(app, db, make_user, fake_clock):
    from app.quotas import service as quotas

    person = make_user("usage-counted@goodmit.co.kr", role="user")
    now = fake_clock.now()
    for status, action in (("ok", "chat.answer"), ("error", "chat.answer"), ("ok", "system.connection_test"),
                           ("blocked_quota", "chat.answer"), ("ok", "game.quiz")):
        usage.record(app.state.session_factory, actor=usage.Actor(kind="user", user_id=person.id),
                     action_key=action, status=status, now=now)
    assert quotas.used(db, user_id=person.id, period="day", now=now) == 2


def test_reaching_the_limit_is_announced_once(app, db, make_user, fake_clock):
    from app.notifications.models import Notification

    person = make_user("usage-limit@goodmit.co.kr", role="user")
    now = fake_clock.now()
    _cap(db, person.id, max_calls=2, now=now)
    for _ in range(3):
        usage.record(app.state.session_factory, actor=usage.Actor(kind="user", user_id=person.id),
                     action_key="chat.answer", status="ok", now=now)
    db.expire_all()
    notes = db.execute(select(Notification).where(Notification.user_id == person.id,
                                                  Notification.type == "ai_quota_exhausted")).scalars().all()
    assert len(notes) == 1 and "한도" in notes[0].title


@pytest.mark.real_db
def test_the_quiz_is_inside_the_limit_and_a_blocked_try_is_recorded(app, client, login_as, db, fake_clock):
    from app.users.service import get_user_by_email

    csrf = login_as("user", email="quiz-cap@goodmit.co.kr")
    person = get_user_by_email(db, "quiz-cap@goodmit.co.kr")
    _cap(db, person.id, max_calls=0, now=fake_clock.now())
    install_runtime(app, ScriptedAdapter(['{"questions": []}']))
    from app.settings.service import apply_setting

    with app.state.session_factory() as s:
        apply_setting(s, app.state.settings_cache, key="game_ai_enabled", value=True, updated_by=None,
                      now=fake_clock.now())
        s.commit()
    reply = client.post("/api/games/quiz/generate", json={"topic": "보안", "count": 3, "num_options": 4},
                        headers={"X-CSRF-Token": csrf})
    assert reply.status_code == 429, reply.text
    assert "한도" in reply.json()["error"]["message"]
    rows = [r for r in _rows(db) if r.user_id == person.id]
    assert [(r.action_key, r.status) for r in rows] == [("game.quiz", "blocked_quota")]


@pytest.mark.real_db
def test_the_weekly_summary_counts_against_the_requester(app, client, login_as, db, fake_clock, make_project):
    from app.users.service import get_user_by_email

    csrf = login_as("system_admin", email="weekly-cap@goodmit.co.kr")
    person = get_user_by_email(db, "weekly-cap@goodmit.co.kr")
    project = make_project(name="한도 주간 요약")
    _cap(db, person.id, max_calls=0, now=fake_clock.now())
    reply = client.post(f"/api/projects/{project.id}/weekly-report/llm-summary", headers={"X-CSRF-Token": csrf})
    assert reply.status_code == 429, reply.text
    db.expire_all()
    from app.jobs.models import Job

    assert db.execute(select(func.count()).select_from(Job).where(Job.job_type == "project_weekly_summary")
                      ).scalar_one() == 0, "한도에 막힌 요청이 큐에 들어갔다"


def test_a_broken_ledger_never_breaks_the_answer():
    def broken_factory():
        raise RuntimeError("DB 가 없다")

    usage.record(broken_factory, actor=usage.SYSTEM, action_key="chat.answer", status="ok",
                 now=datetime(2026, 9, 30))


def test_records_older_than_the_retention_window_are_purged(app, db, fake_clock):
    from datetime import timedelta

    from app.core.retention import run_retention

    now = fake_clock.now()
    for age in (usage.RETENTION_DAYS + 1, usage.RETENTION_DAYS - 1):
        usage.record(app.state.session_factory, actor=usage.SYSTEM, action_key="chat.answer", status="ok",
                     now=now - timedelta(days=age))
    result = run_retention(db, now=now, settings_cache=app.state.settings_cache)
    db.commit()
    assert result["ai_usage_records"] == 1
    assert [row.created_at for row in _rows(db)] == [now - timedelta(days=usage.RETENTION_DAYS - 1)]
