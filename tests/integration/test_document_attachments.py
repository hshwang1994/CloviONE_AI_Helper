"""문서 첨부 — 파일이 먼저 서고, 그 다음에 연결이 선다 (S8 · D-199).

## 이 파일이 지키는 것

**「행은 있는데 파일이 없다」가 생기지 않는다.** 그것은 거짓말이다 — 목록에 이름이
보이고, 크기가 보이고, 눌러야 없다는 것을 안다. 반대 순서로 하면 최악이 「가리키는
사람이 없는 파일」이고, 그건 쓰레기이지 거짓말이 아니다.

첨부의 접근권은 **부모 문서가 정한다.** 범위 시험은 `tests/security/test_attachment_scope.py`
가 따로 든다 — 여기서는 기능이 실제로 도는지를 본다.
"""

from __future__ import annotations

import hashlib
import io
import zipfile

import pytest

from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.storage import adapters, service
from app.storage.models import File

pytestmark = pytest.mark.integration

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<xml/>")
    return buf.getvalue()


@pytest.fixture()
def storage(db, settings):
    provider = service.ensure_default_provider(db, settings)
    db.commit()
    return provider


@pytest.fixture()
def document(db, storage):
    space = KnowledgeSpace(
        org_id=DEFAULT_ORG_ID, name="설계 문서", slug="design", owner_kind="organization"
    )
    db.add(space)
    db.flush()
    doc = Document(space_id=space.id, title="회의록")
    db.add(doc)
    db.commit()
    return doc


def _upload(client, csrf, document_id, *, name="그림.png", content=PNG, caption=""):
    return client.post(
        f"/api/knowledge/documents/{document_id}/attachments",
        files={"file": (name, content, "application/octet-stream")},
        data={"caption": caption},
        headers={"X-CSRF-Token": csrf},
    )


# ── 붙이기 ───────────────────────────────────────────────────────────────────


def test_an_uploaded_file_lands_on_disk_and_in_the_table(client, login_as, db, document, storage):
    csrf = login_as("user")
    response = _upload(client, csrf, document.id, caption="1분기 도면")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["filename"] == "그림.png"
    assert body["mime_type"] == "image/png"
    assert body["size_bytes"] == len(PNG)
    assert body["checksum_sha256"] == hashlib.sha256(PNG).hexdigest()
    assert body["caption"] == "1분기 도면"

    record = db.get(File, body["file_id"])
    assert record is not None
    ref = service.ref_of(storage)
    assert adapters.read_object(ref, record.storage_key) == PNG


def test_the_stored_name_comes_from_the_judged_type_not_the_upload(
    client, login_as, db, document
):
    """🔴 사용자 파일명은 표시용이다. 경로가 되면 traversal 이 열린다."""
    csrf = login_as("user")
    body = _upload(client, csrf, document.id, name="../../etc/passwd.png").json()
    record = db.get(File, body["file_id"])
    assert adapters.STORAGE_KEY_RE.match(record.storage_key), record.storage_key
    assert ".." not in record.filename


def test_an_office_document_is_accepted(client, login_as, document):
    """회의록에 붙는 것은 보통 문서와 스프레드시트다."""
    csrf = login_as("user")
    response = _upload(client, csrf, document.id, name="보고서.docx", content=_docx())
    assert response.status_code == 200, response.text
    assert response.json()["mime_type"].endswith("wordprocessingml.document")


def test_a_file_whose_bytes_are_not_a_known_format_is_refused(client, login_as, document):
    csrf = login_as("user")
    response = _upload(
        client, csrf, document.id, name="악성.png", content=b"\x00\x01\x02\xff\xfe"
    )
    assert response.status_code == 422, response.text


def test_an_empty_file_is_refused(client, login_as, document):
    csrf = login_as("user")
    assert _upload(client, csrf, document.id, content=b"").status_code == 422


def test_a_file_just_over_the_upload_cap_is_refused_with_a_reason(client, login_as, document):
    """422 다. 요청 봉투 상한(12MB)보다는 작고 업로드 상한(10MB)보다는 큰 파일이라,
    사용자가 받는 답은 「너무 큽니다」여야 한다."""
    from app.core.uploads import MAX_UPLOAD_BYTES

    csrf = login_as("user")
    oversize = PNG + b"\x00" * (MAX_UPLOAD_BYTES - len(PNG) + 1)
    response = _upload(client, csrf, document.id, content=oversize)
    assert response.status_code == 422, response.text
    assert "너무 큽니다" in response.json()["error"]["message"]


def test_a_request_body_beyond_the_envelope_is_cut_before_the_route(client, login_as, document):
    """봉투 상한을 넘으면 413 이다 — 12MB 를 다 버퍼링한 뒤에 거절하지 않는다."""
    from app.core.middleware import UPLOAD_BODY_BYTES

    csrf = login_as("user")
    huge = PNG + b"\x00" * UPLOAD_BODY_BYTES
    assert _upload(client, csrf, document.id, content=huge).status_code == 413


# ── 보기 ─────────────────────────────────────────────────────────────────────


def test_the_document_detail_carries_its_attachments(client, login_as, document):
    """직렬화가 한 곳이라 화면마다 필드 이름이 안 갈린다."""
    csrf = login_as("user")
    _upload(client, csrf, document.id)
    detail = client.get(f"/api/knowledge/documents/{document.id}").json()
    assert len(detail["attachments"]) == 1
    assert detail["attachments"][0]["filename"] == "그림.png"


def test_attachments_come_back_in_the_order_they_were_added(client, login_as, document):
    csrf = login_as("user")
    for name in ("첫째.png", "둘째.png", "셋째.png"):
        _upload(client, csrf, document.id, name=name)
    items = client.get(f"/api/knowledge/documents/{document.id}/attachments").json()["items"]
    assert [i["filename"] for i in items] == ["첫째.png", "둘째.png", "셋째.png"]


def test_serving_returns_the_bytes_with_nosniff(client, login_as, document):
    """서버가 판정·저장한 형식만 신뢰한다. 실행 불가."""
    csrf = login_as("user")
    attachment_id = _upload(client, csrf, document.id).json()["id"]
    response = client.get(f"/api/knowledge/attachments/{attachment_id}/content")
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Type"] == "image/png"
    assert "inline" in response.headers["Content-Disposition"]
    # 한글 파일명은 헤더에 그대로 못 넣는다(HTTP 헤더는 latin-1). RFC 5987 로 함께 보낸다.
    assert "filename*=UTF-8''" in response.headers["Content-Disposition"]


def test_a_document_file_is_served_as_a_download_not_inline(client, login_as, document):
    """「받아서 여는 것」과 「탭 안에서 열리는 것」은 사용자가 느끼는 위험이 다르다."""
    csrf = login_as("user")
    attachment_id = _upload(
        client, csrf, document.id, name="보고서.docx", content=_docx()
    ).json()["id"]
    response = client.get(f"/api/knowledge/attachments/{attachment_id}/content")
    assert response.headers["Content-Disposition"].startswith("attachment")


# ── 떼기 ─────────────────────────────────────────────────────────────────────


def test_removing_an_attachment_removes_the_bytes_too(
    client, login_as, db, document, storage
):
    csrf = login_as("user")
    body = _upload(client, csrf, document.id).json()
    record = db.get(File, body["file_id"])
    key = record.storage_key

    response = client.delete(
        f"/api/knowledge/attachments/{body['id']}", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200, response.text
    # 이 세션은 위에서 그 행을 읽어 뒀다. 만료시키지 않으면 캐시된 객체를 보고
    # 「아직 있다」고 답한다 — 시험이 DB 가 아니라 자기 기억을 확인하게 된다.
    db.expire_all()
    assert db.get(File, body["file_id"]) is None
    assert not adapters.object_exists(service.ref_of(storage), key)


def test_a_file_shared_by_two_documents_survives_one_detach(
    client, login_as, db, document, storage
):
    """🔴 무조건 지우면 남의 문서의 첨부가 조용히 깨진다."""
    csrf = login_as("user")
    first = _upload(client, csrf, document.id).json()

    other = Document(space_id=document.space_id, title="다른 문서")
    db.add(other)
    db.commit()
    # 같은 파일 행을 두 문서가 가리키게 한다(같은 바이트를 두 번 올리면 행이 둘이 된다).
    from app.knowledge.models import DocumentAttachment

    db.add(DocumentAttachment(
        document_id=other.id, file_id=first["file_id"], sort_order=1024
    ))
    db.commit()

    client.delete(f"/api/knowledge/attachments/{first['id']}", headers={"X-CSRF-Token": csrf})
    record = db.get(File, first["file_id"])
    assert record is not None, "다른 문서가 아직 가리키는 파일을 지웠다"
    assert adapters.object_exists(service.ref_of(storage), record.storage_key)


# ── 청소와 확인 ──────────────────────────────────────────────────────────────


def test_the_sweep_removes_bytes_nobody_points_at(db, storage, settings):
    """행이 정본이다. 저장소에만 있는 바이트는 쓰레기다."""
    ref = service.ref_of(storage)
    orphan = adapters.new_storage_key(extension=".txt")
    adapters.write_object(ref, orphan, b"nobody points at me")
    assert adapters.object_exists(ref, orphan)

    # 나이 제한을 끄고 부른다 — 방금 쓴 파일이라 기본값(1시간)으로는 아직 후보가 아니다.
    assert service.sweep_orphans(db, min_age_seconds=0) >= 1
    assert not adapters.object_exists(ref, orphan)


def test_the_sweep_leaves_a_file_that_was_just_written(db, storage):
    """🔴 업로드는 바이트를 먼저 쓰고 DB 행을 나중에 만든다(D-250).

    그 사이의 파일은 **정상인데도** 가리키는 행이 없다. 나이를 안 보면 청소가 그 창에
    지나갈 때마다 사용자의 파일이 사라지고, 화면에는 성공이라고 적혀 있다.
    """
    ref = service.ref_of(storage)
    in_flight = adapters.new_storage_key(extension=".txt")
    adapters.write_object(ref, in_flight, b"row is about to be written")

    assert service.sweep_orphans(db) == 0
    assert adapters.object_exists(ref, in_flight), "방금 올라온 파일을 청소가 지웠다"


def test_the_sweep_never_touches_a_file_a_row_points_at(client, login_as, db, document, storage):
    csrf = login_as("user")
    body = _upload(client, csrf, document.id).json()
    record = db.get(File, body["file_id"])

    service.sweep_orphans(db)
    assert adapters.object_exists(service.ref_of(storage), record.storage_key)


def test_verify_reports_a_row_whose_bytes_went_missing(client, login_as, db, document, storage):
    """반대 방향(행은 있는데 파일이 없다)은 **치우지 않는다.** 그것은 사고이고,
    조용히 지우면 사고가 있었다는 사실까지 사라진다."""
    csrf = login_as("user")
    body = _upload(client, csrf, document.id).json()
    record = db.get(File, body["file_id"])
    adapters.delete_object(service.ref_of(storage), record.storage_key)

    result = service.verify_files(db)
    assert result["checked"] == 1
    assert result["missing"] == [record.id]


def test_verify_reports_a_file_whose_bytes_changed(client, login_as, db, document, storage):
    csrf = login_as("user")
    body = _upload(client, csrf, document.id).json()
    record = db.get(File, body["file_id"])
    ref = service.ref_of(storage)
    adapters.object_path(ref, record.storage_key).write_bytes(PNG + b"tampered")

    result = service.verify_files(db)
    assert result["corrupt"] == [record.id]
