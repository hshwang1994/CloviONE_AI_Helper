"""「받을 수 있는가」는 **판정이 하나**여야 한다 (R6-05).

목록의 각 행은 `downloadable` 을 싣고, 화면의 「내려받기」 단추는 그 값 하나를 본다.
그 값과 `GET /api/admin/backups/{id}/download` 가 서로 다른 답을 하면, 단추가 없는 행을
API 로는 받을 수 있고(또는 그 반대) 화면과 서버가 갈라진다.

갈라져 있던 자리는 `status == "failed"` 였다. 목록은 「못 받는다」고 답하는데 라우터는
파일이 디스크에 있으면 그대로 내줬다 — `verify_existing` 이 체크섬이 어긋난 세트를
`failed` 로 낮추므로, **정상이던 백업이 검증 한 번으로 그 상태가 된다.** 그때 목록의 답과
API 의 답이 정반대가 된다.

이 파일은 그 한 경우를 판정한다: 덤프 파일이 **디스크에 그대로 있는** 실패 세트.
`tests/integration/test_backup_download.py` 의 실패 세트는 경로 자체가 없어서(파일 없음)
두 판정이 우연히 같은 답을 냈고, 그래서 이 갈라짐을 못 봤다.
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


def test_a_failed_set_whose_dump_is_still_on_disk_is_refused_too(
    client, db, created_backup
):
    """검증에 실패해 `failed` 로 낮아진 세트 — 파일은 있지만 복원에 쓸 수 없다."""
    from app.backups.models import STATUS_FAILED, Backup
    from app.backups.service import dump_path

    csrf, backup = created_backup
    assert dump_path(backup["path"]).is_file(), "전제가 깨졌다 — 덤프가 디스크에 있어야 한다"

    row = db.get(Backup, backup["id"])
    row.status = STATUS_FAILED
    row.error_message = "체크섬이 맞지 않습니다."
    db.commit()

    listed = _row(client, backup["id"])
    assert listed["downloadable"] is False
    assert listed["download_blocked_reason"] == "failed"

    response = client.get(
        f"/api/admin/backups/{backup['id']}/download", headers=_headers(csrf)
    )
    assert response.status_code != 200, (
        "목록은 「못 받는다」고 답하는데 라우터는 파일을 내줬다 — 판정이 둘이다"
    )
    assert response.status_code == 404, response.text
    message = response.json()["error"]["message"]
    assert message.endswith("."), f"완결된 문장이 아니다: {message!r}"
    assert "없습니다" in message


def test_the_same_set_downloads_while_it_is_still_healthy(client, created_backup):
    """반례 — 멀쩡한 세트는 그대로 받아진다. 위 시험이 「전부 막는 문」으로 통과하지 못하게 한다."""
    csrf, backup = created_backup

    assert _row(client, backup["id"])["downloadable"] is True
    response = client.get(
        f"/api/admin/backups/{backup['id']}/download", headers=_headers(csrf)
    )
    assert response.status_code == 200, response.text


def test_every_refusal_reason_the_list_can_report_has_a_sentence(client, created_backup):
    """이유 코드와 문장은 짝이다 — 코드를 하나 늘리고 문장을 잊으면 그 경우가 KeyError 다."""
    from app.backups.router import _DOWNLOAD_REFUSALS, _download_block

    csrf, backup = created_backup
    assert _download_block.__doc__, "판정 함수의 근거가 사라졌다"
    assert set(_DOWNLOAD_REFUSALS) == {"running", "failed", "removed", "missing"}
    for error, message in _DOWNLOAD_REFUSALS.values():
        assert message.endswith("."), message
        assert isinstance(error, type)
