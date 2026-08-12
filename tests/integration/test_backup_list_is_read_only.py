"""UA-18: `GET /api/admin/backups`가 더는 오래 멈춘 `running` 행을 정리하지 않는다.

예전엔 이 목록을 열 때마다 `reap_stuck_running()`이 함께 돌아 DB에 썼다 — GET은
`require_csrf`의 안전 메서드 예외로 CSRF 보호를 안 받으므로 그 write가 무방비였고,
게다가 **아무도 화면을 안 열면** 죽은 채 멈춘 백업이 영원히 'running'으로 남았다.
정리는 이제 `worker_main.py`의 10분 백업 틱이 맡고, 이 GET은 순수 읽기다.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

pytestmark = pytest.mark.integration


def test_listing_backups_does_not_reap_a_stuck_running_row(client, login_as, db, fake_clock):
    from app.backups.models import STATUS_FAILED, STATUS_RUNNING, Backup

    now = fake_clock.now()
    stuck = Backup(
        path="/var/backups/stuck.sqlite3",
        status=STATUS_RUNNING,
        created_at=now - timedelta(minutes=90),  # STUCK_RUNNING_MINUTES(60)보다 오래됨
    )
    db.add(stuck)
    db.commit()

    login_as("system_admin")
    resp = client.get("/api/admin/backups")
    assert resp.status_code == 200, resp.text

    db.refresh(stuck)
    assert stuck.status == STATUS_RUNNING, "GET이 여전히 멈춘 백업을 조용히 failed로 바꾸고 있다"
    assert stuck.status != STATUS_FAILED
