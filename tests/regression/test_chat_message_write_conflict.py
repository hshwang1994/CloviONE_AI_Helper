"""app/chat/router.py::post_message이 SQLite 쓰기 경합에 500으로 죽지 않는다
(PA-RC-0032).

실측 배경(2026-08-17, Product Audit `PA-20260817-072224`): TEST SERVER journal에서
`POST /api/conversations/{id}/messages`가 `sqlite3.OperationalError: database is
locked`로 500이 난 사례가 확인됐다(05:09:23). AI 대화 전송은 이 제품의 핵심
상호작용이라 같은 잠금에서 raw 500이 나면 기능 실패다. `app/core/db.py`의 공용
`is_write_conflict` 재시도 관용이 이 경로엔 없었다.

`test_change_password_write_conflict.py`와 같은 이유로 무조건 카운트 monkeypatch를
쓴다 — `post_user_message`가 `db.flush()`를 내부에서 먼저 호출해 라우터의 바깥쪽
`db.commit()` 시점엔 이미 dirty/new가 비어 있다.
"""

from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as OrmSession

pytestmark = pytest.mark.integration

CLIENT_MSG_ID = "m0123456789abcdef0123456789abcdef"


def _fake_lock_error() -> OperationalError:
    return OperationalError(
        "INSERT INTO jobs", {}, sqlite3.OperationalError("database is locked")
    )


def _patch_flaky_commit(monkeypatch, *, fail_times: int) -> None:
    original_commit = OrmSession.commit
    state = {"remaining": fail_times}

    def flaky_commit(self, *a, **kw):
        if state["remaining"] > 0:
            state["remaining"] -= 1
            raise _fake_lock_error()
        return original_commit(self, *a, **kw)

    monkeypatch.setattr(OrmSession, "commit", flaky_commit)
    monkeypatch.setattr("app.chat.router.time.sleep", lambda _seconds: None)


@pytest.fixture()
def user_csrf(login_as):
    return login_as("user")


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _new_conversation(client, csrf):
    r = client.post("/api/conversations", json={}, headers=_headers(csrf))
    assert r.status_code == 201
    return r.json()["conversation"]


def test_post_message_write_conflict_retries_then_succeeds(client, user_csrf, db, monkeypatch):
    conv = _new_conversation(client, user_csrf)

    _patch_flaky_commit(monkeypatch, fail_times=1)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "내 할당 티켓 보여줘", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    assert r.status_code == 202, r.text
    assert r.json()["job_id"]

    from app.jobs.models import Job

    job = db.get(Job, r.json()["job_id"])
    assert job.idempotency_key == f"chatmsg:{CLIENT_MSG_ID}"


def test_post_message_write_conflict_retry_does_not_duplicate_the_job(
    client, user_csrf, db, monkeypatch
):
    """PA-RC-0032 regression_risk (c) — 재시도가 잡을 중복 적재하면 안 된다."""
    from sqlalchemy import select

    from app.jobs.models import Job

    conv = _new_conversation(client, user_csrf)

    _patch_flaky_commit(monkeypatch, fail_times=2)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "내 할당 티켓 보여줘", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    assert r.status_code == 202

    matching = db.execute(
        select(Job).where(Job.idempotency_key == f"chatmsg:{CLIENT_MSG_ID}")
    ).scalars().all()
    assert len(matching) == 1


def test_post_message_write_conflict_exhausted_is_not_silently_swallowed(
    client, user_csrf, monkeypatch
):
    conv = _new_conversation(client, user_csrf)

    _patch_flaky_commit(monkeypatch, fail_times=99)
    r = client.post(
        f"/api/conversations/{conv['id']}/messages",
        json={"content": "내 할당 티켓 보여줘", "client_message_id": CLIENT_MSG_ID},
        headers=_headers(user_csrf),
    )
    assert r.status_code == 500
