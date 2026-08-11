"""VIS-107R — 관리자 대시보드의 `failed_open`이 개수만 주고 나이(시간)를 안 줬다.

`failed_24h`는 24시간 창이 있는데 `failed_open`(전체 미해결 실패)만 시간 제약이 없어,
"미해결 실패 4건"이 오늘 생긴 것인지 3주 전부터 방치된 것인지 화면만 봐서는 구분이
안 됐다(실제로 Chrome 실조작에서 21일 넘게 방치된 실패 4건이 발견됐다 — VIS-108R).

가장 오래된 미해결 실패의 `created_at`을 `failed_open_oldest_at`으로 함께 내려보내,
화면이 "미해결 실패 4건, 가장 오래된 것 21일 전"처럼 나이를 보여줄 수 있게 한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.jobs.models import Job

pytestmark = pytest.mark.integration

AT = datetime(2026, 8, 1, 9, 0, 0)
OLD = datetime(2026, 7, 12, 3, 0, 0)   # 가장 오래된 실패
NEW = datetime(2026, 7, 30, 15, 0, 0)  # 더 최근 실패


def _dashboard(client):
    r = client.get("/api/admin/dashboard")
    assert r.status_code == 200, r.text
    return r.json()


def test_failed_open_oldest_at_is_the_earliest_still_failed_job(client, login_as, db):
    login_as("system_admin")
    new_job = Job(job_type="document_generate", status="failed", payload_json="{}",
                  last_error="n8n timeout", available_at=AT)
    old_job = Job(job_type="retention", status="failed", payload_json="{}",
                  last_error="purge failed", available_at=AT)
    db.add_all([new_job, old_job])
    db.commit()
    # created_at은 TimestampMixin의 삽입 시점 기본값을 그대로 쓰므로, 원하는 나이를
    # 만들려면 커밋 후 직접 덮어써야 한다(다른 잡 관련 테스트들과 같은 순서).
    new_job.created_at = NEW
    old_job.created_at = OLD
    db.commit()

    body = _dashboard(client)
    assert body["jobs_24h"]["failed_open"] == 2
    assert body["jobs_24h"]["failed_open_oldest_at"] == OLD.isoformat()


def test_failed_open_oldest_at_is_null_when_nothing_is_open(client, login_as, db):
    login_as("system_admin")
    # 실패가 아예 없는 상태 — 미해결 실패도 0, 나이도 "없음"(0이 아니라 null)이어야 한다.
    body = _dashboard(client)
    assert body["jobs_24h"]["failed_open"] == 0
    assert body["jobs_24h"]["failed_open_oldest_at"] is None


def test_failed_open_oldest_at_ignores_resolved_jobs(client, login_as, db):
    """되돌린(성공/취소) 잡의 created_at은 '미해결' 나이 계산에 섞이면 안 된다."""
    login_as("system_admin")
    resolved_old = Job(job_type="document_generate", status="succeeded", payload_json="{}",
                        available_at=AT, finished_at=AT)
    still_failed = Job(job_type="retention", status="failed", payload_json="{}",
                        last_error="purge failed", available_at=AT)
    db.add_all([resolved_old, still_failed])
    db.commit()
    resolved_old.created_at = OLD
    still_failed.created_at = NEW
    db.commit()

    body = _dashboard(client)
    assert body["jobs_24h"]["failed_open"] == 1
    assert body["jobs_24h"]["failed_open_oldest_at"] == NEW.isoformat()
