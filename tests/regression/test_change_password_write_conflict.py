"""app/auth/router.py::change_password가 SQLite 쓰기 경합에 500으로 죽지 않는다
(PA-RC-0032).

실측 배경(2026-08-17, Product Audit `PA-20260817-072224`): TEST SERVER에서 오늘
`POST /change-password` 31건 중 3건(약 10%)이 `sqlite3.OperationalError: database
is locked`로 500이었다. 같은 파일의 `login()`은 이미 `is_write_conflict` 재시도를
쓰는데(`app/core/db.py`, 실측으로 검증된 값), 이 관문(최초 로그인마다 강제로 지나야
하는 경로)에는 없었다. `login()`처럼 `commit()` 시점의 경합을 흉내 낸다 —
`test_session_touch_write_conflict.py`의 `Session.commit` monkeypatch 패턴을
`User`가 dirty할 때만 걸리도록 재사용한다.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as OrmSession

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

NEW_PASSWORD = "N3w-Different-Pass!"


def _fake_lock_error() -> OperationalError:
    return OperationalError(
        "UPDATE users SET password_hash=?", {}, sqlite3.OperationalError("database is locked")
    )


def _patch_flaky_commit(monkeypatch, *, fail_times: int) -> None:
    """처음 fail_times번의 commit() 호출을 "database is locked"로 실패시킨다.

    dirty-type 필터링(test_session_touch_write_conflict.py의 패턴)은 여기서는 안 맞는다
    — `session_service.create()`가 세션 행을 `db.add()+flush()`로 내부에서 먼저 반영해,
    `change_password()`의 바깥쪽 `db.commit()` 시점엔 `user`가 이미 flush돼 dirty가 아니다
    (flush는 커밋이 아니라 상태만 정리한다). 이 monkeypatch는 `_patch_flaky_commit` 적용
    *이후* 첫 요청(login 이후에 건다)의 commit 횟수만 겨냥하면 되므로 무조건 카운트가 더
    정확하고 단순하다."""
    original_commit = OrmSession.commit
    state = {"remaining": fail_times}

    def flaky_commit(self, *a, **kw):
        if state["remaining"] > 0:
            state["remaining"] -= 1
            raise _fake_lock_error()
        return original_commit(self, *a, **kw)

    monkeypatch.setattr(OrmSession, "commit", flaky_commit)
    monkeypatch.setattr("app.auth.router.time.sleep", lambda _seconds: None)


def _login(client, email, password=DEFAULT_TEST_PASSWORD):
    r = client.post("/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()


def test_change_password_write_conflict_retries_then_succeeds(client, make_user, monkeypatch):
    make_user("changepw-retry@goodmit.co.kr", must_change_password=True)
    body = _login(client, "changepw-retry@goodmit.co.kr")
    csrf = body["csrf_token"]

    _patch_flaky_commit(monkeypatch, fail_times=1)
    r = client.post(
        "/change-password",
        json={"current_password": DEFAULT_TEST_PASSWORD, "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text

    # Actually took effect, not just a lucky 200 — old password rejected, new one works.
    r = client.post(
        "/login", json={"email": "changepw-retry@goodmit.co.kr", "password": NEW_PASSWORD}
    )
    assert r.status_code == 200


def test_change_password_write_conflict_exhausted_is_not_a_500(client, make_user, monkeypatch):
    """재시도까지 다 실패해도 raw 500이 아니라 write_conflict 계열 오류로 접혀야 한다
    (login()의 기존 계약과 동일 — is_write_conflict가 아니면 그대로 올린다는 뜻이므로,
    소진 시에는 정확히 원본 OperationalError가 다시 올라온다)."""
    make_user("changepw-giveup@goodmit.co.kr", must_change_password=True)
    body = _login(client, "changepw-giveup@goodmit.co.kr")
    csrf = body["csrf_token"]

    _patch_flaky_commit(monkeypatch, fail_times=99)
    r = client.post(
        "/change-password",
        json={"current_password": DEFAULT_TEST_PASSWORD, "new_password": NEW_PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    # FastAPI's raise_server_exceptions default surfaces the OperationalError as a 500
    # via the app's own error envelope, not a crash of the test process — same shape as
    # any other unhandled server error this suite already exercises.
    assert r.status_code == 500


def test_change_password_write_conflict_does_not_double_rotate_sessions(
    client, app, make_user, monkeypatch
):
    """PA-RC-0032 regression_risk (a) — 재시도가 세션 회전을 두 번 하면 안 된다."""
    from fastapi.testclient import TestClient

    make_user("changepw-norot@goodmit.co.kr", must_change_password=True)
    body = _login(client, "changepw-norot@goodmit.co.kr")
    csrf = body["csrf_token"]

    with TestClient(app, raise_server_exceptions=False) as other:
        other.post(
            "/login",
            json={"email": "changepw-norot@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
        )
        assert other.get("/api/me").status_code == 200

        _patch_flaky_commit(monkeypatch, fail_times=1)
        r = client.post(
            "/change-password",
            json={"current_password": DEFAULT_TEST_PASSWORD, "new_password": NEW_PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 200

        # Spec §11.3 still holds after a retried commit: exactly one other-session
        # revocation, not one per retry attempt.
        assert other.get("/api/me").status_code == 401

    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["user"]["must_change_password"] is False
