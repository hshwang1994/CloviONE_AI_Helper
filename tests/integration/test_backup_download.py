"""백업 목록이 「이 백업을 받을 수 있는가」를 **정직하게** 말하는가 (ops-03 서버 절반).

화면은 「내려받기」 단추를 `file_state === "present"` 로만 세웠다. 그런데 그 값이 기록하는
것은 「사람이 서버 파일을 지웠는가」뿐이다(D-204) — **실패한 백업에도, 디스크에서 사라진
파일에도 `present` 가 그대로 남는다.** 그래서 받을 것이 없는 행에 단추가 서고, 누르면
브라우저가 그 주소로 이동해 관리자 콘솔이 통째로 날 JSON 오류 페이지로 바뀐다. 사고가 난
날 여는 화면에서 일어나는 일이라, 그 순간 관리자는 무엇이 깨졌는지 볼 근거를 화면에서 잃는다.

그래서 서버가 답한다: 목록의 각 행이 `downloadable` 과 그 이유를 함께 싣는다. 판정은
`GET /api/admin/backups/{id}/download` 가 실제로 하는 판정과 **같은 것**이어야 한다 —
두 곳이 각자 판단하면 화면의 단추와 서버의 답이 다시 갈라진다. 이 파일은 그 둘을 매번
나란히 확인한다(단추 조건은 P10 의 화면 절반이 쓴다).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


def _row(client, backup_id: str) -> dict:
    body = client.get("/api/admin/backups").json()
    return next(r for r in body["items"] if r["id"] == backup_id)


@pytest.fixture()
def created_backup(client, login_as, stub_pg_dump):
    csrf = login_as("system_admin")
    response = client.post("/api/admin/backups", headers=_headers(csrf))
    assert response.status_code == 201, response.text
    return csrf, response.json()["backup"]


def test_a_healthy_backup_says_it_can_be_downloaded_and_it_can(client, created_backup):
    """반례 — 멀쩡한 백업은 받을 수 있다고 말하고, 실제로 받아진다."""
    csrf, backup = created_backup

    assert backup["downloadable"] is True
    assert backup["download_blocked_reason"] is None
    assert _row(client, backup["id"])["downloadable"] is True

    response = client.get(
        f"/api/admin/backups/{backup['id']}/download", headers=_headers(csrf)
    )
    assert response.status_code == 200, response.text


def test_a_failed_backup_is_not_offered_for_download(client, login_as, db, fake_clock):
    """실패한 백업에는 받을 덤프가 없다 — 「받을 수 있다」고 말하면 잘못된 안심을 준다."""
    from app.backups.models import STATUS_FAILED, Backup

    row = Backup(
        backup_type="pg_dump", path="/tmp/clv-failed-set", status=STATUS_FAILED,
        created_at=fake_clock.now(), error_message="디스크가 가득 찼습니다.",
    )
    db.add(row)
    db.commit()
    csrf = login_as("system_admin")

    listed = _row(client, row.id)
    assert listed["file_state"] == "present", (
        "전제가 깨졌다 — file_state 는 사람이 지웠는지만 기록하므로 실패 행에도 present 다"
    )
    assert listed["downloadable"] is False
    assert listed["download_blocked_reason"] == "failed"

    # 서버의 답과 같은 판정인가 — 눌러도 파일은 나오지 않는다.
    response = client.get(f"/api/admin/backups/{row.id}/download", headers=_headers(csrf))
    assert response.status_code == 404, response.text


def test_a_backup_whose_file_vanished_from_disk_says_so(client, db, created_backup):
    """디스크에서 파일이 사라져도 `file_state` 는 그대로 `present` 다 — 서버가 실제로 본다."""
    from app.backups.service import dump_path

    csrf, backup = created_backup
    dump_path(backup["path"]).unlink()

    listed = _row(client, backup["id"])
    assert listed["file_state"] == "present"
    assert listed["downloadable"] is False
    assert listed["download_blocked_reason"] == "missing"

    response = client.get(
        f"/api/admin/backups/{backup['id']}/download", headers=_headers(csrf)
    )
    assert response.status_code == 404, response.text


def test_a_discarded_backup_says_a_person_removed_it(client, created_backup):
    """「사람이 지웠다」와 「파일이 없어졌다」는 다른 사고다 — 이유를 뭉개지 않는다."""
    csrf, backup = created_backup
    client.post(f"/api/admin/backups/{backup['id']}/discard-file", headers=_headers(csrf))

    listed = _row(client, backup["id"])
    assert listed["downloadable"] is False
    assert listed["download_blocked_reason"] == "removed"

    response = client.get(
        f"/api/admin/backups/{backup['id']}/download", headers=_headers(csrf)
    )
    assert response.status_code == 409, response.text


def test_a_running_backup_is_not_offered_either(client, login_as, db, fake_clock):
    """아직 쓰이는 중인 파일을 받으면 반쪽 덤프를 받아 간다(다운로드 라우트와 같은 판정)."""
    from app.backups.models import STATUS_RUNNING, Backup

    row = Backup(backup_type="pg_dump", path="/tmp/clv-running-set-2",
                 status=STATUS_RUNNING, created_at=fake_clock.now())
    db.add(row)
    db.commit()
    csrf = login_as("system_admin")

    listed = _row(client, row.id)
    assert listed["downloadable"] is False
    assert listed["download_blocked_reason"] == "running"

    response = client.get(f"/api/admin/backups/{row.id}/download", headers=_headers(csrf))
    assert response.status_code == 409, response.text


def test_the_single_row_responses_answer_the_same_question(client, created_backup):
    """목록에만 실으면 화면이 만든 직후·검증 직후에 옛 판정을 그대로 그린다."""
    csrf, backup = created_backup

    verified = client.post(
        f"/api/admin/backups/{backup['id']}/verify", headers=_headers(csrf)
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["backup"]["downloadable"] is True

    discarded = client.post(
        f"/api/admin/backups/{backup['id']}/discard-file", headers=_headers(csrf)
    )
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["backup"]["downloadable"] is False
    assert discarded.json()["backup"]["download_blocked_reason"] == "removed"
