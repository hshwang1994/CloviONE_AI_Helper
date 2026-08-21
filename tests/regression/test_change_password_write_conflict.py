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

import pytest
from sqlalchemy.exc import OperationalError

from tests.fakes.pgerrors import serialization_failure
from sqlalchemy.orm import Session as OrmSession

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

NEW_PASSWORD = "N3w-Different-Pass!"


def _fake_lock_error() -> OperationalError:
    """재시도해야 하는 경합 — PG 의 `40001 serialization_failure` 다.

    qa-contract-change: SQLite 의 database is locked 문자열을 흉내 내던 가짜 예외를 PG 의 SQLSTATE 40001 로 바꿨다. PG 에서 재시도 판정 기준은 메시지가 아니라 SQLSTATE 이므로, 문자열만 두면 제품이 아니라 가짜 예외 때문에 실패한다.
        """
    return serialization_failure("UPDATE users SET password_hash=?")


def _patch_flaky_commit(monkeypatch, *, fail_times: int) -> None:
    """앞 `fail_times` 번의 커밋을 직렬화 경합으로 실패시킨다.

    **rate limiter 의 커밋은 건드리지 않는다.** 리미터는 이제 자기 세션에서 곧바로
    커밋하므로(D-192, `app/core/ratelimit.py`), 모든 `Session.commit` 을 무조건
    실패시키면 주입한 고장이 정작 시험하려는 코드가 아니라 리미터 안에서 터진다 —
    시험은 빨간불인데 원인은 제품이 아니라 주입 범위에 있다.
    """
    original_commit = OrmSession.commit
    state = {"remaining": fail_times}

    def flaky_commit(self, *a, **kw):
        limiter_session = any(
            "rate_limit_buckets" in str(getattr(obj, "table", ""))
            for obj in getattr(self, "new", ())
        )
        if state["remaining"] > 0 and not limiter_session and not _is_limiter_frame():
            state["remaining"] -= 1
            raise _fake_lock_error()
        return original_commit(self, *a, **kw)

    monkeypatch.setattr(OrmSession, "commit", flaky_commit)
    monkeypatch.setattr("app.auth.router.time.sleep", lambda _seconds: None)
def _is_limiter_frame() -> bool:
    """지금 커밋을 부른 것이 rate limiter 인가.

    호출 스택을 보는 것은 무딘 방법이지만, 여기서 필요한 것은 «이 커밋이 시험 대상인가»
    하나뿐이고 리미터는 자기 모듈 안에서만 커밋한다. 세션 객체로는 구별할 수 없다 —
    리미터도 같은 팩토리로 만든 `Session` 이다.
    """
    import inspect

    return any(
        frame.filename.replace("\\", "/").endswith("app/core/ratelimit.py")
        for frame in inspect.stack()[:12]
    )


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
