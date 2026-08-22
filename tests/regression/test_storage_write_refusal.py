"""쓰기를 거부할 때 **아무것도 안 남고, 503 이 나간다** (S8 · D-199 9번·13번).

## 이 파일이 고정하는 사고 둘

**① 마운트가 안 붙었는데 조용히 쌓인다.** NFS 서버가 안 떠 있어도 마운트포인트는
사라지지 않는다 — 로컬 디스크의 빈 디렉터리로 남고, 앱은 거기에 잘 쓴다. 며칠 뒤
마운트가 붙는 순간 그 파일들이 한꺼번에 안 보이게 된다. 오류는 한 번도 안 난다.

**② 쓰다 죽어 반쪽 파일이 남는다.** 크기도 있고 열리기도 한다. 체크섬을 다시 세어
보기 전에는 아무도 모른다.

## 500 이 아니라 503 인 이유

마운트가 안 붙은 것은 「서버가 깨졌다」가 아니라 「지금은 못 한다」이다. 그 둘은
사용자가 할 수 있는 일이 다르다 — 기다린다 vs 신고한다.
"""

from __future__ import annotations

import os

import pytest

from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.storage import adapters, service
from app.storage.models import File, StorageProvider

pytestmark = pytest.mark.regression

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def document(db):
    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="공간", slug="refusal", owner_kind="organization"
    )
    db.add(space)
    db.flush()
    doc = Document(space_id=space.id, title="문서")
    db.add(doc)
    db.commit()
    return doc


@pytest.fixture()
def unmounted(db, tmp_path):
    """켜진 운영 저장소가 **안 붙은 NFS** 인 상태."""
    mountpoint = tmp_path / "nas"
    mountpoint.mkdir()
    provider = StorageProvider(
        name="안 붙은 NAS", kind="NFS", role="OPERATIONAL",
        base_path=mountpoint.as_posix(), mount_point=mountpoint.as_posix(),
        config_json='{"source": "nas:/export"}',
    )
    db.add(provider)
    db.commit()
    return provider, mountpoint


@pytest.fixture()
def mounted(db, settings):
    provider = service.ensure_default_provider(db, settings)
    db.commit()
    return provider


# ── ① 마운트가 안 붙었다 ────────────────────────────────────────────────────


def test_uploading_to_an_unmounted_store_is_503_not_500(client, login_as, document, unmounted):
    """🔴 500 으로 나가면 사용자는 신고하고, 관리자는 스택트레이스를 찾는다."""
    csrf = login_as("user")
    response = client.post(
        f"/api/knowledge/documents/{document.id}/attachments",
        files={"file": ("그림.png", PNG, "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "storage_unavailable"


def test_a_refused_upload_leaves_no_bytes_and_no_row(client, login_as, db, document, unmounted):
    """🔴 거부는 「실패」가 아니라 「하지 않았다」다."""
    _, mountpoint = unmounted
    csrf = login_as("user")
    client.post(
        f"/api/knowledge/documents/{document.id}/attachments",
        files={"file": ("그림.png", PNG, "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    db.expire_all()
    assert db.query(File).count() == 0, "쓰지도 않은 파일의 행이 생겼다"
    assert list(mountpoint.iterdir()) == [], "안 붙은 마운트포인트에 파일이 쌓였다"


def test_the_error_message_never_leaks_the_path(client, login_as, document, unmounted):
    """원인(OSError 원문·경로)은 서버 로그에만 남는다(OPS-05)."""
    csrf = login_as("user")
    response = client.post(
        f"/api/knowledge/documents/{document.id}/attachments",
        files={"file": ("그림.png", PNG, "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    message = response.json()["error"]["message"]
    assert "/" not in message and "nas" not in message.lower(), message


def test_the_same_upload_succeeds_once_the_store_is_mounted(client, login_as, document, mounted):
    """반대편 — 여기서 실패하면 위 시험들은 「전부 거절하는 구현」도 통과시킨다."""
    csrf = login_as("user")
    response = client.post(
        f"/api/knowledge/documents/{document.id}/attachments",
        files={"file": ("그림.png", PNG, "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text


def test_readyz_says_unready_when_the_store_is_not_writable(client, unmounted):
    """배포 직후 게이트가 이것을 잡는다. 안 잡으면 그 창에 들어온 업로드가 전부 실패한다."""
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["reason"] == "storage_not_writable"


def test_readyz_is_ready_when_the_store_is_writable(client, mounted):
    assert client.get("/readyz").status_code == 200


# ── ② 쓰다 죽었다 ───────────────────────────────────────────────────────────


def test_a_failed_write_creates_neither_a_partial_file_nor_a_row(
    client, login_as, db, document, mounted, monkeypatch
):
    """🔴 최종 이름은 **성공했을 때만** 생긴다."""
    def boom(src, dst):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "replace", boom)
    csrf = login_as("user")
    response = client.post(
        f"/api/knowledge/documents/{document.id}/attachments",
        files={"file": ("그림.png", PNG, "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 503, response.text
    monkeypatch.undo()

    db.expire_all()
    assert db.query(File).count() == 0
    assert list(adapters.iter_keys(service.ref_of(mounted))) == []


def test_bytes_are_rolled_back_when_the_row_cannot_be_written(db, mounted, monkeypatch):
    """🔴 반대 순서의 사고 — 바이트는 남았는데 행이 없다.

    최악이 「가리키는 사람이 없는 파일」이라 거짓말은 아니지만, 되돌릴 수 있으면
    되돌린다. 안 되돌리면 실패한 업로드마다 디스크가 조금씩 샌다.
    """
    ref = service.ref_of(mounted)

    def boom():
        raise RuntimeError("행을 못 썼다")

    monkeypatch.setattr(db, "flush", boom)
    with pytest.raises(RuntimeError):
        service.store_bytes(db, filename="그림.png", content=PNG)
    monkeypatch.undo()

    assert list(adapters.iter_keys(ref)) == [], "행이 없는데 바이트가 남았다"


def test_reading_a_file_whose_store_went_away_is_503_not_404(db, mounted, monkeypatch):
    """🔴 「파일을 찾을 수 없습니다」는 「지워졌다」와 구별되지 않는다.

    저장소가 잠깐 안 붙은 것을 「없다」로 답하면, 사용자는 자기 파일이 사라졌다고
    믿고 다시 올린다.
    """
    from app.core.errors import StorageUnavailableError

    record = service.store_bytes(db, filename="그림.png", content=PNG)
    db.commit()

    # 저장소가 원격이 되고 마운트가 빠진 상태.
    mounted.kind = "NFS"
    mounted.mount_point = mounted.base_path
    db.commit()

    with pytest.raises(StorageUnavailableError):
        service.file_path(db, record)
    with pytest.raises(StorageUnavailableError):
        service.read_bytes(db, record)
