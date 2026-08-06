"""잡 큐의 **단건·재시도·취소**도 범위를 지킨다 (§0-A 2순위).

목록(`GET /api/admin/jobs`)은 이미 범위를 걸었는데 `GET /{id}` · `POST /{id}/retry` ·
`POST /{id}/cancel` 은 `db.get(Job, job_id)` 하나로 끝났다. 목록만 가려서는 아무 의미가
없다 — 세 경로 모두 **id 를 직접 받는다.**

새는 것이 조회로 끝나지 않는다:

* **상세**에는 그 잡의 `last_error` 와 연결 식별자가 실린다. 남의 팀 사람이 무엇을
  요청했고 무엇이 왜 실패했는지가 그대로 보인다.
* **재시도**는 더 나쁘다. 실패한 잡을 다시 큐에 올리면 워커가 **n8n·Notion 쓰기를 다시
  실행한다** — 남의 팀 문서가 다시 발행되고 남의 팀 스케줄이 다시 돈다. 읽기 유출이
  아니라 **남의 범위에서의 쓰기 실행**이다.
* **취소**는 남의 팀의 대기 중인 자동 처리를 조용히 죽인다.

## 시스템 잡(`user_id` 없음)은 가리지 않는다

보존 정리·동기화 같은 자동 작업에는 소유자가 없다. 그것까지 없애면 부서 관리자가
**자기 범위의 자동 처리 실패를 볼 수 없다** — 목록이 이미 그렇게 남기고 있고, 단건도
같은 규칙이어야 한다(두 벌이 되면 목록엔 보이는데 상세는 404 가 된다).
"""

from __future__ import annotations

from datetime import datetime

import pytest

pytestmark = pytest.mark.security

AT = datetime(2026, 8, 1, 9, 0, 0)


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 팀 사람 + 우리 팀만 관리하는 관리자 + 네 개의 잡."""
    from app.jobs.models import Job
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    mate = make_user("job-mate@goodmit.co.kr", role="user", display_name="동료")
    victim = make_user("job-victim@goodmit.co.kr", role="user", display_name="남")
    boss = make_user("job-boss@goodmit.co.kr", role="admin", display_name="팀관리자")
    mate.department_id = mine.id
    victim.department_id = theirs.id
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    jobs = {
        # 남의 팀 사람이 요청한 문서 생성이 실패해 있다 — 재시도하면 Notion 에 다시 쓴다.
        "theirs_failed": Job(
            job_type="document_generate", user_id=victim.id, status="failed",
            payload_json='{"title": "남의팀 3분기 실적 보고서", "generation_id": "g-theirs"}',
            last_error="notion 401", available_at=AT,
        ),
        "theirs_queued": Job(
            job_type="schedule_run", user_id=victim.id, status="queued",
            payload_json='{"schedule_run_id": "r-theirs"}', available_at=AT,
        ),
        "mine_failed": Job(
            job_type="document_generate", user_id=mate.id, status="failed",
            payload_json='{"title": "우리팀 보고서"}', last_error="n8n timeout",
            available_at=AT,
        ),
        "mine_queued": Job(
            job_type="chat_message", user_id=mate.id, status="queued",
            payload_json="{}", available_at=AT,
        ),
        # 소유자가 없는 자동 작업 — 가리면 자기 범위의 자동 처리 실패를 못 본다.
        "system": Job(
            job_type="retention", user_id=None, status="failed",
            payload_json="{}", last_error="purge failed", available_at=AT,
        ),
    }
    db.add_all(list(jobs.values()))
    db.commit()
    return {key: job.id for key, job in jobs.items()}


def _hdr(login_as):
    return {"X-CSRF-Token": login_as("admin", email="job-boss@goodmit.co.kr")}


def _status(db, job_id):
    from app.jobs.models import Job

    db.expire_all()
    return db.get(Job, job_id).status


def test_a_scoped_admin_cannot_read_another_teams_job(client, login_as, world):
    """상세에는 `last_error` 와 연결 식별자가 실린다 — 목록에서 가린 것이 id 로 열린다."""
    r = client.get(f"/api/admin/jobs/{world['theirs_failed']}", headers=_hdr(login_as))
    assert r.status_code == 404, f"남의 팀 잡 상세가 열린다: {r.status_code} {r.text}"


def test_a_scoped_admin_cannot_rerun_another_teams_job(client, login_as, db, world):
    """재시도는 읽기가 아니라 **쓰기 실행**이다 — 남의 팀 문서가 다시 발행된다."""
    r = client.post(
        f"/api/admin/jobs/{world['theirs_failed']}/retry", headers=_hdr(login_as)
    )
    assert r.status_code == 404, f"남의 팀 잡을 재시도할 수 있다: {r.status_code} {r.text}"
    assert _status(db, world["theirs_failed"]) == "failed", (
        "404 를 돌려주고도 잡이 실제로 재큐잉됐다 — 워커가 곧 집어간다"
    )


def test_a_scoped_admin_cannot_cancel_another_teams_job(client, login_as, db, world):
    r = client.post(
        f"/api/admin/jobs/{world['theirs_queued']}/cancel", headers=_hdr(login_as)
    )
    assert r.status_code == 404, f"남의 팀 잡을 취소할 수 있다: {r.status_code} {r.text}"
    assert _status(db, world["theirs_queued"]) == "queued", (
        "404 를 돌려주고도 남의 팀 자동 처리가 취소됐다"
    )


def test_system_jobs_stay_visible(client, login_as, world):
    """소유자 없는 자동 작업까지 가리면 자기 범위의 자동 처리 실패를 못 본다."""
    hdr = _hdr(login_as)
    rows = client.get("/api/admin/jobs").json()["items"]
    assert world["system"] in {row["id"] for row in rows}, "목록에서 시스템 잡이 사라졌다"

    r = client.get(f"/api/admin/jobs/{world['system']}", headers=hdr)
    assert r.status_code == 200, (
        f"목록엔 보이는데 상세는 404 다 — 판정이 두 벌이다: {r.status_code} {r.text}"
    )
    assert r.json()["job"]["last_error"] == "purge failed"


def test_the_detail_and_the_list_agree_on_my_own_team(client, login_as, world):
    """오탐 방지 — 자기 범위 잡의 상세가 막히면 그건 기능 고장이다."""
    hdr = _hdr(login_as)
    rows = client.get("/api/admin/jobs").json()["items"]
    assert world["mine_failed"] in {row["id"] for row in rows}, "자기 팀 잡이 목록에 없다"

    r = client.get(f"/api/admin/jobs/{world['mine_failed']}", headers=hdr)
    assert r.status_code == 200, f"자기 팀 잡 상세를 못 본다: {r.status_code} {r.text}"


def test_a_scoped_admin_can_still_retry_and_cancel_their_own_team(
    client, login_as, db, world
):
    """오탐 방지 — 자기 범위의 재시도·취소는 그대로 돼야 한다."""
    hdr = _hdr(login_as)

    r = client.post(f"/api/admin/jobs/{world['mine_failed']}/retry", headers=hdr)
    assert r.status_code == 200, f"자기 팀 잡을 재시도할 수 없다: {r.status_code} {r.text}"
    assert _status(db, world["mine_failed"]) == "queued"

    r = client.post(f"/api/admin/jobs/{world['mine_queued']}/cancel", headers=hdr)
    assert r.status_code == 200, f"자기 팀 잡을 취소할 수 없다: {r.status_code} {r.text}"
    assert _status(db, world["mine_queued"]) == "cancelled"


def test_a_global_admin_still_sees_and_operates_everything(client, login_as, db, world):
    """전역 관리자까지 좁히면 운영이 멈춘다."""
    hdr = {"X-CSRF-Token": login_as("system_admin")}
    assert client.get(f"/api/admin/jobs/{world['theirs_failed']}", headers=hdr).status_code == 200
    r = client.post(f"/api/admin/jobs/{world['theirs_failed']}/retry", headers=hdr)
    assert r.status_code == 200, f"전역 관리자가 재시도를 못 한다: {r.status_code} {r.text}"
    assert _status(db, world["theirs_failed"]) == "queued"


def test_an_out_of_scope_job_is_404_before_409(client, login_as, world):
    """상태 충돌(409)이 먼저 나오면 그 id 가 **존재한다는 사실**이 새어 나간다.

    대기 중인 잡에 재시도를 걸면 원래 409 다 — 범위 밖이면 그 전에 404 여야 한다.
    """
    r = client.post(
        f"/api/admin/jobs/{world['theirs_queued']}/retry", headers=_hdr(login_as)
    )
    assert r.status_code == 404, (
        f"409 로 답해 범위 밖 잡의 존재와 상태를 알려 준다: {r.status_code} {r.text}"
    )
