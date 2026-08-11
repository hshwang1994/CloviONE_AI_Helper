"""app/core/sessions.py의 validate() 부수효과 커밋(last_seen_at 스로틀 갱신, idle/절대
만료 revoke)이 SQLite 쓰기 충돌과 겹쳐도 순수 조회 요청을 500으로 끌고 내려가지 않는다.

실측 배경(2026-08-11 23:58:48, QA 하네스 동시 접속): GET /api/notifications/unread-count,
GET /api/team-chat/rooms — 둘 다 자기 자신의 로직과 무관하게, 인증 단계에서 흔히 도는
`UPDATE sessions SET last_seen_at=?`가 다른 동시 요청과 충돌해
`sqlite3.OperationalError: database is locked`로 500이 났다(app/core/deps.py의
get_db, db.commit()). 고치기 전 원본 코드(`record.last_seen_at = now`를 직접 설정하고
get_db의 마지막 커밋에 얹는 방식)로 되돌리면 아래 테스트가 500으로 재현된다 — 확인함
(revert-to-verify).
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as OrmSession

from app.core.sessions import _commit_best_effort
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _fake_lock_error() -> OperationalError:
    return OperationalError(
        "UPDATE sessions SET last_seen_at=?", {}, sqlite3.OperationalError("database is locked")
    )


def _patch_flaky_user_session_commit(monkeypatch, *, fail_times: int) -> None:
    """UserSession 이 dirty 한 커밋만 처음 fail_times 번 "database is locked" 로 실패시킨다.

    로그인 자체의 커밋(신규 세션은 session.new 이지 session.dirty 가 아니다)이나
    get_db 의 최종 커밋(이 시점엔 UserSession 이 dirty 하지 않다)은 건드리지 않는다 —
    정확히 validate() 안의 세 커밋만 겨냥한다.
    """
    original_commit = OrmSession.commit
    state = {"remaining": fail_times}

    def flaky_commit(self, *a, **kw):
        dirty_types = {type(obj).__name__ for obj in self.dirty}
        if state["remaining"] > 0 and "UserSession" in dirty_types:
            state["remaining"] -= 1
            raise _fake_lock_error()
        return original_commit(self, *a, **kw)

    monkeypatch.setattr(OrmSession, "commit", flaky_commit)


def _login(client, email):
    r = client.post("/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200
    return r


def test_last_seen_touch_write_conflict_retries_then_succeeds(
    client, make_user, fake_clock, monkeypatch
):
    make_user("touch-retry@goodmit.co.kr")
    _login(client, "touch-retry@goodmit.co.kr")
    fake_clock.advance(61)  # _LAST_SEEN_WRITE_INTERVAL_SECONDS 를 넘겨 touch 를 유발한다.

    _patch_flaky_user_session_commit(monkeypatch, fail_times=1)
    r = client.get("/api/me")
    assert r.status_code == 200, r.text


def test_last_seen_touch_write_conflict_exhausted_still_not_500(
    client, make_user, fake_clock, monkeypatch
):
    """재시도까지 다 실패해도(요청 하나 안에서 계속 충돌) 순수 조회 요청은 500이 아니다 —
    이 갱신은 있으면 좋고 없어도 기능이 깨지지 않는 best-effort 다."""
    make_user("touch-give-up@goodmit.co.kr")
    _login(client, "touch-give-up@goodmit.co.kr")
    fake_clock.advance(61)

    _patch_flaky_user_session_commit(monkeypatch, fail_times=99)
    r = client.get("/api/me")
    assert r.status_code == 200, r.text


def test_idle_expiry_revoke_write_conflict_is_401_not_500(
    client, make_user, fake_clock, settings, monkeypatch
):
    make_user("revoke-conflict@goodmit.co.kr")
    _login(client, "revoke-conflict@goodmit.co.kr")
    fake_clock.advance(settings.session_idle_timeout_seconds + 1)

    _patch_flaky_user_session_commit(monkeypatch, fail_times=99)
    r = client.get("/api/me")
    assert r.status_code == 401, r.text


def test_commit_best_effort_reraises_unrelated_operational_errors():
    """무관한 OperationalError(디스크 오류 등)까지 조용히 삼키면 안 된다."""

    class _FakeDb:
        def __init__(self):
            self.commits = 0

        def commit(self):
            self.commits += 1
            raise OperationalError("SELECT 1", {}, sqlite3.OperationalError("disk I/O error"))

        def rollback(self):
            pass

    fake_db = _FakeDb()
    with pytest.raises(OperationalError):
        _commit_best_effort(fake_db, lambda: None)
    assert fake_db.commits == 1, "쓰기 충돌이 아니면 재시도하지 말고 바로 올려야 한다"


def test_commit_best_effort_gives_up_silently_after_exhausting_attempts():
    class _FakeDb:
        def __init__(self):
            self.commits = 0

        def commit(self):
            self.commits += 1
            raise _fake_lock_error()

        def rollback(self):
            pass

    fake_db = _FakeDb()
    _commit_best_effort(fake_db, lambda: None)  # 예외를 올리지 않아야 한다.
    assert fake_db.commits == 2, "정확히 _SIDE_EFFECT_COMMIT_ATTEMPTS 번만 시도해야 한다"
