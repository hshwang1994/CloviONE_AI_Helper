"""설정 캐시가 다른 프로세스의 저장을 바로 따라잡는다 (D-532).

웹 워커 넷과 배치 · 대화형 워커 · 스케줄러는 설정 캐시를 프로세스마다 하나씩 든다. 예전에는 30초 나이 규칙만 있어서
저장을 받은 프로세스 밖의 캐시는 30초 동안 옛 값을 보였다(「사용하지 않음」을 누른 뒤 다시 읽으면 「안 됨」). 같은
프로세스에서 하나의 캐시를 나눠 쓰는 시험은 그 어긋남을 못 본다 - 그래서 여기서는 **따로 채운 캐시 둘**로 잰다.

못박는 것:
  * 한 캐시로 저장하면 다른 캐시는 다음 확인에서 새 값을 본다(나이와 무관).
  * 시계를 멈춰도(같은 시각의 두 저장) 판 번호가 내용으로 갈라 따라잡는다.
  * 같은 프로세스 안에서 판 번호는 1초에 한 번만 묻는다 - 그 사이의 호출은 질의가 없다.
  * 저장한 트랜잭션이 되감기면 그 캐시도 다음 확인에서 DB 의 값으로 돌아온다.
  * 워커는 잡을 돌리기 직전에 따라잡는다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from app.settings.service import SettingsCache, apply_setting

pytestmark = pytest.mark.integration

KEY = "conversation_retention_days"


def _save(app, cache, value, *, commit=True):
    with app.state.session_factory() as db:
        apply_setting(db, cache, key=KEY, value=value, updated_by=None, now=app.state.clock.now())
        if commit:
            db.commit()
        else:
            db.rollback()


def _cache(app, **kw) -> SettingsCache:
    cache = SettingsCache(**kw)
    with app.state.session_factory() as db:
        cache.load(db)
    return cache


def _refresh(app, cache):
    with app.state.session_factory() as db:
        cache.refresh_if_stale(db)


def test_another_process_save_is_seen_on_the_next_check(app):
    writer = _cache(app)
    reader = _cache(app, stamp_interval_seconds=0)
    assert reader.current_value(KEY) == 90
    _save(app, writer, 45)
    _refresh(app, reader)
    assert reader.current_value(KEY) == 45, "다른 캐시가 저장한 값을 다음 확인에서 못 봤다"


def test_two_saves_at_the_same_instant_are_still_told_apart(app):
    """시계를 멈춘 채 두 번 저장해도(같은 updated_at) 판 번호는 내용으로 다르다."""
    writer = _cache(app)
    reader = _cache(app, stamp_interval_seconds=0)
    _save(app, writer, 60)
    _refresh(app, reader)
    assert reader.current_value(KEY) == 60
    _save(app, writer, 61)
    _refresh(app, reader)
    assert reader.current_value(KEY) == 61


def test_the_stamp_is_asked_at_most_once_a_second(app):
    reader = _cache(app)  # 기본 1초
    statements: list[str] = []
    engine = app.state.session_factory.kw["bind"]

    def count(conn, cursor, statement, *_a):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        for _ in range(20):
            _refresh(app, reader)
    finally:
        event.remove(engine, "before_cursor_execute", count)
    assert [s for s in statements if "app_settings" in s] == [], "1초 안에 판 번호를 다시 물었다"


def test_a_rolled_back_save_heals_on_the_next_check(app):
    cache = _cache(app, stamp_interval_seconds=0)
    _save(app, cache, 33, commit=False)       # 같은 트랜잭션에서 캐시가 새 값을 들었다가
    _refresh(app, cache)                       # 저장이 되감기면 다음 확인이 DB 값으로 돌린다
    assert cache.current_value(KEY) == 90


def test_the_worker_catches_up_right_before_a_job(app, settings, fake_clock):
    from app.jobs import repository
    from app.jobs.worker import Worker, WorkerContext

    writer = _cache(app)
    worker_cache = _cache(app, stamp_interval_seconds=0)
    seen: list = []

    def handler(db, job, ctx):
        seen.append(ctx.extras["settings_cache"].current_value(KEY))

    ctx = WorkerContext(settings=settings, clock=fake_clock, extras={"settings_cache": worker_cache})
    worker = Worker(app.state.session_factory, fake_clock, {"cache_probe": handler}, ctx)
    _save(app, writer, 12)
    with app.state.session_factory() as db:
        repository.enqueue(db, job_type="cache_probe", payload={}, now=fake_clock.now())
        db.commit()
    assert worker.run_once()
    assert seen == [12], "워커가 옛 설정으로 잡을 돌렸다"
