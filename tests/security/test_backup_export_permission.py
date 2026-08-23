"""백업 파일을 받아 갈 수 있는 사람 (S12 · CLAUDE.md §6 4번).

백업 덤프는 **데이터베이스 전체**다. 권한 모델을 우회하는 가장 짧은 길이 이 파일이라,
「목록을 볼 수 있다」와 「받아 갈 수 있다」를 같은 칸에 두면 안 된다.

`BACKUP_READ` 는 콘솔 읽기 역할 전체가 갖는다(operator 포함). `BACKUP_EXECUTE` 는
`system_admin` 뿐이다. 다운로드와 서버 파일 삭제는 **후자**에 붙는다.

음성 시험을 먼저 둔다 — 「되는가」만 보면 아무나 되는 구현도 통과한다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def a_backup(client, login_as, stub_pg_dump):
    csrf = login_as("system_admin")
    response = client.post("/api/admin/backups", headers=_headers(csrf))
    assert response.status_code == 201, response.text
    return response.json()["backup"]


@pytest.mark.parametrize("role", ["user", "operator", "admin", "auditor"])
def test_only_system_admin_can_download_a_backup(client, login_as, a_backup, role):
    csrf = login_as(role)
    response = client.get(f"/api/admin/backups/{a_backup['id']}/download", headers=_headers(csrf))
    assert response.status_code == 403, (
        f"{role} 가 데이터베이스 전체를 받아 갈 수 있다: {response.status_code}"
    )


@pytest.mark.parametrize("role", ["user", "operator", "admin", "auditor"])
def test_only_system_admin_can_delete_the_server_copy(client, login_as, a_backup, role):
    csrf = login_as(role)
    response = client.post(
        f"/api/admin/backups/{a_backup['id']}/discard-file", headers=_headers(csrf)
    )
    assert response.status_code == 403, f"{role} 가 복원 지점을 지울 수 있다"


def test_system_admin_can(client, login_as, a_backup):
    """반례 — 위 둘이 **무조건 403 을 내는 검사**가 아님을 보인다."""
    csrf = login_as("system_admin")
    assert client.get(
        f"/api/admin/backups/{a_backup['id']}/download", headers=_headers(csrf)
    ).status_code == 200


def test_operator_can_still_read_the_list(client, login_as, a_backup):
    """반례 — 다운로드를 좁힌 것이 목록 조회까지 좁힌 것은 아니다."""
    csrf = login_as("operator")
    assert client.get("/api/admin/backups", headers=_headers(csrf)).status_code == 200


def test_the_download_body_never_leaks_a_path_outside_the_backup_root(client, login_as, db):
    """행의 `path` 를 그대로 열어 주므로, **DB 를 쓸 수 있는 사람**이 그 값을 바꾸면
    임의 파일을 받아 갈 수 있는가를 확인한다.

    답은 「그 사람은 이미 DB 전체를 읽는다」이므로 이것 자체는 권한 상승이 아니다. 다만
    엔드포인트가 **디렉터리를 통째로 내주지는 않아야** 한다 — 세트가 아닌 임의 디렉터리를
    가리키면 덤프 파일이 없으므로 404 여야 하고, 조용히 무언가를 내보내면 안 된다.
    """
    from app.backups.models import STATUS_VERIFIED, Backup

    row = Backup(
        backup_type="pg_dump", path=str(client.app.state.settings.data_dir),
        status=STATUS_VERIFIED, created_at=client.app.state.clock.now(),
    )
    db.add(row)
    db.commit()
    csrf = login_as("system_admin")
    response = client.get(f"/api/admin/backups/{row.id}/download", headers=_headers(csrf))
    assert response.status_code == 404
