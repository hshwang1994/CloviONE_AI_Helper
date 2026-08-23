"""Local Backup 다운로드 UX — **자동으로 지우지 않는다** (S12 · D-204).

D-204 가 정한 흐름: 실행 → 다운로드 → **다운로드 완료 후 「서버에 저장된 백업 파일을
삭제하시겠습니까?」를 명시적으로 묻는다.** 자동 삭제하지 않는다.

여기서 못박는 것:

* 내려받아도 서버 파일은 **그대로 있다.** 서버는 브라우저가 다 받았는지 모른다 —
  받다 만 것과 다 받은 것을 구별할 방법이 없으므로, 「받았으니 지운다」는 서버가 내릴 수
  있는 판단이 아니다.
* 지우기는 **별도 요청**이고, 그 뒤에도 **행은 남는다.** 「그때 백업을 만들어 받아 갔다」는
  사실은 감사 로그와 짝을 이룬다.
* 다운로드는 `BACKUP_EXECUTE` 다. 목록을 볼 수 있는 역할이 데이터베이스 전체를 받아 갈 수
  있으면 「백업 목록 조회」가 사실상 「전체 데이터 반출」이 된다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def created_backup(client, login_as, stub_pg_dump):
    csrf = login_as("system_admin")
    response = client.post("/api/admin/backups", headers=_headers(csrf))
    assert response.status_code == 201, response.text
    return csrf, response.json()["backup"]


def test_a_fresh_backup_reports_its_file_is_on_the_server(created_backup):
    _csrf, backup = created_backup
    assert backup["file_state"] == "present"
    assert backup["downloaded_at"] is None


def test_download_returns_the_dump_and_leaves_the_file_alone(client, db, created_backup):
    from pathlib import Path

    from app.backups.models import Backup
    from app.backups.service import dump_path

    csrf, backup = created_backup
    response = client.get(f"/api/admin/backups/{backup['id']}/download", headers=_headers(csrf))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/octet-stream"
    assert "attachment" in response.headers.get("content-disposition", "")
    assert response.content == dump_path(backup["path"]).read_bytes()

    # 🔴 자동 삭제가 없다는 것을 **디스크에서** 확인한다. 상태값만 보면, 상태는 그대로 두고
    # 파일만 지우는 구현도 통과한다.
    assert Path(dump_path(backup["path"])).is_file()
    db.expire_all()
    row = db.get(Backup, backup["id"])
    assert row.file_state == "present"
    assert row.downloaded_at is not None, "받아 간 사실은 남아야 한다"


def test_the_download_filename_identifies_which_backup_it_is(client, created_backup):
    """받는 사람의 폴더에 `database.dump` 가 여럿 쌓이면 어느 것이 언제 것인지 모른다."""
    csrf, backup = created_backup
    response = client.get(f"/api/admin/backups/{backup['id']}/download", headers=_headers(csrf))
    disposition = response.headers.get("content-disposition", "")
    assert "backup-" in disposition and disposition.endswith('.dump"')


def test_discarding_removes_the_file_but_keeps_the_record(client, db, created_backup):
    from pathlib import Path

    from app.backups.models import Backup

    csrf, backup = created_backup
    response = client.post(
        f"/api/admin/backups/{backup['id']}/discard-file", headers=_headers(csrf)
    )
    assert response.status_code == 200, response.text
    assert response.json()["removed"]["removed_local"] is True
    assert not Path(backup["path"]).exists()

    db.expire_all()
    row = db.get(Backup, backup["id"])
    assert row is not None, "행까지 지우면 그 백업을 만들었다는 사실이 사라진다"
    assert row.file_state == "removed"


def test_discarding_does_not_touch_the_offsite_copy(
    client, db, settings, fake_clock, stub_pg_dump, tmp_path
):
    """🔴 사람이 답한 질문은 「**서버에 저장된** 백업 파일을 지울까요」다.

    백업 저장소의 사본은 **재해 복구용**이라 이 요청과 다른 물건이다. 공간 회수의 부수
    효과로 그것까지 지우면, 정작 필요한 날 물어본 적 없는 삭제로 사라진 것을 알게 된다.
    """
    from pathlib import Path

    from app.backups import destination as destination_mod
    from app.backups.service import discard_file, run_backup
    from app.storage import service as storage_service
    from app.storage.models import StorageProvider

    storage_service.ensure_default_provider(db, settings)
    root = tmp_path / "offsite"
    root.mkdir()
    provider = StorageProvider(
        name="원격 백업", kind="LOCAL", role="BACKUP", base_path=root.as_posix()
    )
    db.add(provider)
    db.commit()

    row = run_backup(db, settings, created_by=None, now=fake_clock.now())
    db.commit()
    remote = Path(provider.base_path) / destination_mod.SET_ROOT / Path(row.path).name
    assert remote.is_dir(), "사본이 애초에 안 갔으면 이 시험은 아무것도 증명하지 못한다"

    result = discard_file(db, row, now=fake_clock.now())
    db.commit()

    assert result["removed_local"] is True
    assert result["removed_remote"] is False
    assert remote.is_dir(), "재해 복구용 사본이 공간 회수의 부수 효과로 사라졌다"


def test_discarding_twice_is_refused_not_silently_repeated(client, created_backup):
    csrf, backup = created_backup
    first = client.post(f"/api/admin/backups/{backup['id']}/discard-file", headers=_headers(csrf))
    assert first.status_code == 200
    second = client.post(f"/api/admin/backups/{backup['id']}/discard-file", headers=_headers(csrf))
    assert second.status_code == 409


def test_downloading_a_discarded_backup_says_so(client, created_backup):
    """「서버에서 지웠다」와 「파일이 없어졌다」는 다른 사고다. 404 로 뭉개지 않는다."""
    csrf, backup = created_backup
    client.post(f"/api/admin/backups/{backup['id']}/discard-file", headers=_headers(csrf))
    response = client.get(f"/api/admin/backups/{backup['id']}/download", headers=_headers(csrf))
    assert response.status_code == 409


def test_verifying_a_discarded_backup_does_not_call_it_corrupt(client, db, created_backup):
    """사람이 지운 백업을 「손상」으로 보고하면, 진짜 손상을 찾을 때 그것이 잡음이 된다."""
    csrf, backup = created_backup
    client.post(f"/api/admin/backups/{backup['id']}/discard-file", headers=_headers(csrf))
    response = client.post(f"/api/admin/backups/{backup['id']}/verify", headers=_headers(csrf))
    assert response.status_code == 200, response.text
    assert response.json()["verify"]["reason"] == "file_removed"


def test_a_running_backup_cannot_be_downloaded(client, login_as, db, fake_clock):
    """아직 쓰이는 중인 파일을 받으면 **반쪽 덤프**를 받아 간다."""
    from app.backups.models import STATUS_RUNNING, Backup

    row = Backup(backup_type="pg_dump", path="/tmp/clv-running-set",
                 status=STATUS_RUNNING, created_at=fake_clock.now())
    db.add(row)
    db.commit()
    csrf = login_as("system_admin")
    response = client.get(f"/api/admin/backups/{row.id}/download", headers=_headers(csrf))
    assert response.status_code == 409
