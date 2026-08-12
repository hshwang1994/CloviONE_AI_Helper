"""Proof that concurrent POST /api/admin/ai-quotas for the same
(scope_type, user_id, period) never 500s — whole-product re-audit finding 5.

`create_quota()` is check-then-insert with no locking: two admins (or a
double-submit) creating the same quota row at nearly the same moment could
both see "no existing quota" and both insert — the loser hit
uq_ai_quota_scope's UNIQUE constraint (scope_type, user_id, period) as a
raw, unhandled IntegrityError/OperationalError (500) instead of the clean
409 the sequential-duplicate path already had ready.

A pure N-way timing race does not reliably reproduce this — confirmed by
this codebase's own test_prompt_create_new_version_race.py (login itself
retries with jitter, desyncing the racers' timing). So the "existing
quota?" SELECT is pinned to a threading.Barrier(2), forcing both requests
to see "none" before either is allowed to proceed to INSERT.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

ADMIN_EMAIL = "quota-racer@goodmit.co.kr"


def test_concurrent_create_same_scope_never_500s(app, login_as):
    login_as("admin", email=ADMIN_EMAIL)  # 관리자 계정을 미리 만들어 둔다.
    engine = app.state.engine
    barrier = threading.Barrier(2)
    hits = 0
    hits_lock = threading.Lock()

    def _pause_before_insert_races(conn, cursor, statement, parameters, context, executemany):
        nonlocal hits
        # ai_quotas는 이 시험 안에서 아래 두 POST 말고는 아무도 건드리지 않는 격리된
        # 테스트 DB라 값 마커 없이 테이블명만으로 걸어도 안전하다(period는 "day"/"month"
        # 리터럴만 허용돼 임의 마커 문자열을 못 넣는다 — service.validate 참고).
        if "FROM ai_quotas" not in statement:
            return
        with hits_lock:
            hits += 1
            should_wait = hits <= 2
        if should_wait:
            barrier.wait(timeout=5)

    def attempt(_i: int) -> int:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post(
                "/login", json={"email": ADMIN_EMAIL, "password": DEFAULT_TEST_PASSWORD}
            )
            assert r.status_code == 200, r.text
            token = r.json()["csrf_token"]
            resp = c.post(
                "/api/admin/ai-quotas",
                json={
                    "scope_type": "global",
                    "period": "day",
                    "max_calls": 100,
                },
                headers={"X-CSRF-Token": token},
            )
            return resp.status_code

    event.listen(engine, "before_cursor_execute", _pause_before_insert_races)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(attempt, range(2)))
    finally:
        event.remove(engine, "before_cursor_execute", _pause_before_insert_races)

    assert codes.count(201) == 1, f"정확히 하나만 성공해야 한다: {codes}"
    assert all(c in (201, 409) for c in codes), f"500이 섞였다(처리 안 된 경합): {codes}"

    # 경합 뒤에도 같은 범위로 다시 만들려 하면 평범한 409(순차 경로) — 크래시 안 남는다.
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post(
            "/login", json={"email": ADMIN_EMAIL, "password": DEFAULT_TEST_PASSWORD}
        )
        token = r.json()["csrf_token"]
        again = c.post(
            "/api/admin/ai-quotas",
            json={"scope_type": "global", "period": "day", "max_calls": 200},
            headers={"X-CSRF-Token": token},
        )
        assert again.status_code == 409
