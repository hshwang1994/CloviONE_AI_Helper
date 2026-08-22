"""첨부도 **범위를 지킨다** (S8 · D-193 · D-194).

## 왜 첨부에 이 시험이 따로 필요한가

첨부는 **서빙 라우트가 곧 접근 통제**다(`app/core/uploads.py` 서문이 그 사고를 적어
뒀다: 게시판 네임스페이스를 채팅이 재사용해 1:1 DM 이미지가 전사 공개가 될 뻔했다).
문서 상세를 막아도 첨부 URL 이 열려 있으면 사내 자료 바이트가 그대로 나간다 — 그리고
첨부 id 는 **상세 응답에 실려 나가므로** 쉽게 샌다.

여기서 보는 것 넷:

1. 남의 부서 문서에 **파일을 붙일 수 없다** (404, 403 이 아니다).
2. 남의 부서 문서의 첨부를 **목록에서 못 보고, 내려받을 수 없고, 못 지운다**.
3. 저장소 설정은 `STORAGE_CONFIGURE` 를 가진 사람만 만진다.
4. 저장 키를 손으로 지어내도 뿌리 밖으로 못 나간다.

## 양쪽을 함께 본다

「안 된다」만 확인하면 **전부 막는 구현**도 통과하고, 그 상태에서는 아무도 파일을 못
올린다. 그래서 각 단정에 「우리 것은 된다」를 함께 둔다.
"""

from __future__ import annotations

import pytest

from app.knowledge.models import Document, KnowledgeSpace
from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.storage import service

pytestmark = pytest.mark.security

BOSS = "attach-scope-boss@goodmit.co.kr"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def world(db, make_user, settings):
    """부서 둘 + 각 부서 문서 + **우리 부서만 보는 관리자** + 저장소 하나."""
    service.ensure_default_provider(db, settings)
    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    boss = make_user(BOSS, role="admin", display_name="팀관리자")
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    def _space(name, slug, dept):
        row = KnowledgeSpace(
            org_id=DEFAULT_ORG_ID, name=name, slug=slug,
            owner_kind="department", owner_dept_id=dept.id,
        )
        db.add(row)
        db.flush()
        return row

    ours, others = _space("우리 공간", "ours", mine), _space("남의 공간", "theirs", theirs)
    ours_doc = Document(space_id=ours.id, title="우리 문서")
    theirs_doc = Document(space_id=others.id, title="남의 문서")
    db.add_all([ours_doc, theirs_doc])
    db.commit()
    return {"ours_doc": ours_doc, "theirs_doc": theirs_doc}


@pytest.fixture()
def api(client, login_as, world):
    headers = {"X-CSRF-Token": login_as("admin", email=BOSS)}

    class Api:
        def get(self, path):
            return client.get(path, headers=headers)

        def delete(self, path):
            return client.delete(path, headers=headers)

        def upload(self, document_id, name="그림.png"):
            return client.post(
                f"/api/knowledge/documents/{document_id}/attachments",
                files={"file": (name, PNG, "application/octet-stream")},
                headers=headers,
            )

    return Api()


@pytest.fixture()
def theirs_attachment(world, db):
    """남의 부서 문서에 이미 붙어 있는 첨부.

    HTTP 로 만들지 않는다. 만들려면 다른 사람으로 로그인해야 하고, 그러면 **이 시험의
    세션이 바뀐다** — 그 상태에서 나오는 401 은 「범위를 지켰다」가 아니라 「로그인이
    풀렸다」이고, 둘을 구별하지 못하면 시험이 아무것도 증명하지 않는다.
    """
    from app.knowledge import attachments as attachments_mod

    link, record = attachments_mod.attach(
        db, world["theirs_doc"], filename="남의그림.png", content=PNG
    )
    db.commit()
    return attachments_mod.json_of(link, record)


# ── 붙이기 ───────────────────────────────────────────────────────────────────


def test_attaching_to_someone_elses_document_is_404(api, world):
    """**403 이 아니라 404** 다. 403 은 그 문서가 존재한다는 사실을 알려 준다."""
    response = api.upload(world["theirs_doc"].id)
    assert response.status_code == 404, f"남의 문서에 파일이 붙었다: {response.text}"


def test_attaching_to_our_own_document_works(api, world):
    """반대편 — 여기서 실패하면 위 시험은 「전부 막는 구현」도 통과시킨다."""
    assert api.upload(world["ours_doc"].id).status_code == 200


# ── 보기 ─────────────────────────────────────────────────────────────────────


def test_listing_someone_elses_attachments_is_404(api, world, theirs_attachment):
    response = api.get(f"/api/knowledge/documents/{world['theirs_doc'].id}/attachments")
    assert response.status_code == 404


def test_downloading_someone_elses_attachment_is_404(api, theirs_attachment):
    """🔴 첨부 id 는 상세 응답에 실려 나간다 — 그것만 쥐고도 열리면 안 된다."""
    response = api.get(f"/api/knowledge/attachments/{theirs_attachment['id']}/content")
    assert response.status_code == 404, "남의 부서 첨부 바이트가 그대로 나갔다"


def test_downloading_our_own_attachment_works(api, world):
    body = api.upload(world["ours_doc"].id).json()
    response = api.get(f"/api/knowledge/attachments/{body['id']}/content")
    assert response.status_code == 200
    assert response.content == PNG


def test_deleting_someone_elses_attachment_is_404(api, theirs_attachment):
    response = api.delete(f"/api/knowledge/attachments/{theirs_attachment['id']}")
    assert response.status_code == 404


def test_deleting_our_own_attachment_works(api, world):
    body = api.upload(world["ours_doc"].id).json()
    assert api.delete(f"/api/knowledge/attachments/{body['id']}").status_code == 200


# ── 저장소 설정 ──────────────────────────────────────────────────────────────


def test_a_department_admin_cannot_read_the_storage_settings(api):
    """저장소 목록은 경로·마운트 소스·용량을 담는다. 그것만으로도 서버 구조가 드러난다."""
    assert api.get("/api/storage/providers").status_code == 403
    assert api.get("/api/storage/status").status_code == 403


def test_a_system_admin_can(client, login_as, world):
    login_as("system_admin", email="attach-scope-root2@goodmit.co.kr")
    assert client.get("/api/storage/providers").status_code == 200


# ── 저장 키 ──────────────────────────────────────────────────────────────────


def test_a_hand_made_storage_key_never_escapes_the_root(db, settings, tmp_path):
    """사용자 입력이 저장 키가 되는 경로는 없다. 그래도 모양 자체를 좁혀 둔다 —
    「없다」에 기대는 방어는 새 라우트 하나에서 무너진다."""
    from app.storage import adapters

    provider = service.ensure_default_provider(db, settings)
    ref = service.ref_of(provider)
    for evil in ("../../etc/passwd", "ab/cd/../../../../etc/shadow", "/etc/passwd"):
        with pytest.raises(ValueError):
            adapters.object_path(ref, evil)


def test_the_upload_never_uses_the_client_filename_as_a_path(client, login_as, db, world):
    """저장명은 서버가 만든다. 사용자 파일명은 표시용으로만 남는다."""
    from app.storage.adapters import STORAGE_KEY_RE
    from app.storage.models import File

    csrf = login_as("system_admin", email="attach-scope-root3@goodmit.co.kr")
    response = client.post(
        f"/api/knowledge/documents/{world['ours_doc'].id}/attachments",
        files={"file": ("../../../etc/passwd.png", PNG, "application/octet-stream")},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    record = db.get(File, response.json()["file_id"])
    assert STORAGE_KEY_RE.match(record.storage_key)
    assert ".." not in record.filename and "/" not in record.filename
