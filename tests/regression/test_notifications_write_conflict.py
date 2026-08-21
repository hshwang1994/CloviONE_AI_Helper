"""app/notifications/service.py의 세 읽음-처리 함수(mark_types_read/mark_read/
mark_all_read)가 SQLite 쓰기 경합에 500으로 죽지 않는다.

실측 배경(2026-08-17, whole-product Chrome E2E 710페이지 스윕): `POST
/api/notifications/read-types`가 화면 진입마다 자동으로 나가는데, 다른 동시 쓰기와
부딪혀 `sqlite3.OperationalError: database is locked`가 그대로 500으로 샜다(서버
journal 확인). 세 함수 다 SAVEPOINT 재시도 없이 `db.execute`/`db.flush`를 직접
불렀다 — `app/core/db.py`의 공용 관용(`team_chat/service.py::_append_message`와
같은 패턴)을 적용한다. 되돌리면 아래 "재시도 후 성공" 테스트가 500으로 재현된다
(revert-to-verify).
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError

from tests.fakes.pgerrors import serialization_failure
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.sql.dml import Update

from app.notifications.service import mark_all_read, mark_read, mark_types_read, notify_user

pytestmark = pytest.mark.integration


def _fake_lock_error() -> OperationalError:
    """재시도해야 하는 경합 — PG 의 `40001 serialization_failure` 다.

    qa-contract-change: SQLite 의 database is locked 문자열을 흉내 내던 가짜 예외를 PG 의 SQLSTATE 40001 로 바꿨다. PG 에서 재시도 판정 기준은 메시지가 아니라 SQLSTATE 이므로, 문자열만 두면 제품이 아니라 가짜 예외 때문에 실패한다.
        """
    return serialization_failure("UPDATE notifications SET read_at=?")


def _patch_flaky_update(monkeypatch, *, fail_times: int) -> None:
    """`Notification` UPDATE만 처음 fail_times번 "database is locked"로 실패시킨다.

    SELECT(소유권 조회 등)는 건드리지 않는다 — 정확히 쓰기 지점만 겨냥한다."""
    original_execute = OrmSession.execute
    state = {"remaining": fail_times}

    def flaky_execute(self, stmt, *a, **kw):
        if state["remaining"] > 0 and isinstance(stmt, Update):
            state["remaining"] -= 1
            raise _fake_lock_error()
        return original_execute(self, stmt, *a, **kw)

    monkeypatch.setattr(OrmSession, "execute", flaky_execute)
    monkeypatch.setattr("app.notifications.service.time.sleep", lambda _seconds: None)


def test_mark_types_read_write_conflict_retries_then_succeeds(db, make_user, fake_clock, monkeypatch):
    user = make_user("noti-types-retry@goodmit.co.kr")
    notify_user(db, user.id, type_="job_failed", title="요청 처리 실패", now=fake_clock.now())
    db.commit()

    _patch_flaky_update(monkeypatch, fail_times=1)
    changed = mark_types_read(db, user.id, ["job_failed"], now=fake_clock.now())
    assert changed == 1


def test_mark_types_read_write_conflict_exhausted_raises_write_unavailable(
    db, make_user, fake_clock, monkeypatch
):
    from app.core.errors import WriteUnavailableError

    user = make_user("noti-types-giveup@goodmit.co.kr")
    notify_user(db, user.id, type_="job_failed", title="요청 처리 실패", now=fake_clock.now())
    db.commit()

    _patch_flaky_update(monkeypatch, fail_times=99)
    with pytest.raises(WriteUnavailableError):
        mark_types_read(db, user.id, ["job_failed"], now=fake_clock.now())


def test_mark_read_write_conflict_retries_then_succeeds(db, make_user, fake_clock, monkeypatch):
    user = make_user("noti-read-retry@goodmit.co.kr")
    row = notify_user(db, user.id, type_="job_failed", title="요청 처리 실패", now=fake_clock.now())
    db.commit()

    _patch_flaky_update(monkeypatch, fail_times=1)
    ok = mark_read(db, user.id, row.id, now=fake_clock.now())
    assert ok is True
    db.refresh(row)
    assert row.read_at is not None


def test_mark_all_read_write_conflict_retries_then_succeeds(db, make_user, fake_clock, monkeypatch):
    user = make_user("noti-all-retry@goodmit.co.kr")
    notify_user(db, user.id, type_="job_failed", title="1", now=fake_clock.now())
    notify_user(db, user.id, type_="system", title="2", now=fake_clock.now())
    db.commit()

    _patch_flaky_update(monkeypatch, fail_times=1)
    count = mark_all_read(db, user.id, now=fake_clock.now())
    assert count == 2
