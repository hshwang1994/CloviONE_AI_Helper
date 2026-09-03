"""Confluence 한 번 가져오기 (문서 개편 14~20번).

## 이 파일이 지키는 계약 다섯

1. **모든 페이지**가 문서가 된다 — 보관된 것과 깊은 하위까지. 그리고 그 사실을 주장이
   아니라 **원본 수 대조**로 증명한다(14번).
2. 페이지 계층을 폴더로 재현하지 않는다 — 한 페이지 = 한 문서(14번).
3. 🔴 **3MB 이상 첨부 하나가 문서 전체를 실패시키지 않는다**(18번). 본문·댓글·나머지
   첨부가 그대로 들어오고, 건너뛴 사실은 보고서와 본문 양쪽에 남는다.
4. 댓글은 **기존 구조**로 들어온다(19번). 작성자를 못 풀면 실행 계정으로 넣되 원 작성자를
   본문 첫 줄에 적는다 — 내용을 잃지 않으면서 남의 이름을 사칭하지도 않는다.
5. 🔴 문서가 앉는 공간의 `owner_kind` 가 **`organization`** 이다. `unset` 이면 그 문서는
   전역 조회 권한자 말고는 아무에게도 안 보인다 — 목록에서도 AI 검색에서도, 오류 한 줄
   없이. 실측에서 문서 110건이 그렇게 사라진 적이 있다.

## 두 번 돌려도 안 늘어난다

다리는 `legacy_mapping(legacy_source='confluence')` 하나다. 같은 회차를 두 번 돌려
문서·첨부·댓글이 각각 몇 개가 되는지 실제로 센다.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.integration

ME = "cf-admin@goodmit.co.kr"

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _adf(*nodes):
    return {"type": "doc", "content": list(nodes)}


def _para(text):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


class FakeConfluence:
    """`ConfluenceSource` 와 **같은 겉모양**. 바깥으로 나가지 않는다."""

    def __init__(self):
        self.stats = _Stats()
        self.downloads = 0
        self.pages = {
            "1": {
                "id": "1", "title": "CMP 홈", "status": "current", "parentId": None,
                "version": {"number": 1, "createdAt": "2025-03-01T00:00:00.000Z"},
                "createdAt": "2025-01-01T00:00:00.000Z",
            },
            "2": {
                # 🔴 깊은 하위 페이지. 「상위만 가져왔다」를 잡는 자리다.
                "id": "2", "title": "설치 가이드", "status": "current", "parentId": "1",
                "version": {"number": 3, "createdAt": "2026-05-02T00:00:00.000Z"},
                "createdAt": "2025-02-02T00:00:00.000Z",
            },
            "3": {
                # 🔴 보관된 페이지. 기본 필터가 조용히 빼던 갈래다.
                "id": "3", "title": "옛 규약", "status": "archived", "parentId": "2",
                "version": {"number": 1, "createdAt": "2024-01-01T00:00:00.000Z"},
                "createdAt": "2024-01-01T00:00:00.000Z",
            },
        }

    # ── 목록 ─────────────────────────────────────────────────────────────────

    def find_spaces(self, keys):
        return {k: f"space-{k}" for k in keys}

    def list_pages(self, space_id, *, space_key):
        return [dict(p, _space_key=space_key) for p in self.pages.values()]

    def list_blogposts(self, space_id, *, space_key):
        return []

    # ── 내용 ─────────────────────────────────────────────────────────────────

    def page_body(self, page_id, *, version=None):
        page = self.pages[page_id]
        if page_id == "2":
            adf = _adf(
                {"type": "heading", "attrs": {"level": 2},
                 "content": [{"type": "text", "text": "준비물"}]},
                {"type": "bulletList", "content": [
                    {"type": "listItem", "content": [_para("Docker 24 이상")]},
                ]},
                {"type": "table", "content": [
                    {"type": "tableRow", "content": [
                        {"type": "tableHeader", "content": [_para("항목")]},
                        {"type": "tableCell", "content": [_para("값")]},
                    ]},
                ]},
                {"type": "mediaSingle", "content": [
                    {"type": "media", "attrs": {"id": "att-small", "type": "file"}},
                ]},
                {"type": "mediaSingle", "content": [
                    {"type": "media", "attrs": {"id": "att-huge", "type": "file"}},
                ]},
                {"type": "paragraph", "content": [
                    {"type": "inlineCard", "attrs": {"url": "https://example.test/spec"}},
                ]},
            )
        else:
            adf = _adf(_para(f"{page['title']} 의 본문입니다."))
        return {
            "_version": (page.get("version") or {}).get("number"),
            "id": page_id, "title": page["title"], "status": page["status"],
            "parentId": page.get("parentId"), "version": page.get("version") or {},
            "createdAt": page.get("createdAt"), "adf": adf,
        }

    def page_attachments(self, page_id):
        if page_id != "2":
            return []
        return [
            {"id": "att-small", "title": "구성도.png", "fileSize": 1024,
             "mediaType": "image/png", "downloadLink": "/download/small"},
            # 🔴 3MB 이상. 이 하나 때문에 문서가 죽으면 안 된다.
            {"id": "att-huge", "title": "설치본.zip", "fileSize": 9 * 1024 * 1024,
             "mediaType": "application/zip", "downloadLink": "/download/huge"},
        ]

    def page_comments(self, page_id):
        if page_id != "2":
            return []
        return [{
            "id": "c-1", "_kind": "footer-comments",
            "version": {"createdAt": "2026-06-01T00:00:00.000Z",
                        "authorDisplayName": "김동현"},
            "body": {"atlas_doc_format": {
                "value": json.dumps(_adf(_para("이 순서대로 하면 됩니다.")))}},
        }]

    def download(self, link, *, declared_size=None):
        """진짜 소스와 **같은 순서**로 판단한다 — 크기를 먼저 보고, 넘으면 바이트를
        한 번도 안 만진다. 그래서 세는 것은 「불렸는가」가 아니라 **「바이트를 받았는가」**다."""
        if declared_size is not None and declared_size >= 3 * 1024 * 1024:
            self.stats.attachments_too_large += 1
            return None
        self.downloads += 1
        return _PNG


class _Stats:
    attachments_too_large = 0

    def as_dict(self):
        return {"attachments_too_large": self.attachments_too_large}


@pytest.fixture()
def actor(db, make_user):
    user = make_user(ME, role="system_admin", display_name="가져온 사람")
    db.commit()
    return user


def _run(db, actor, source, **kw):
    from app.migration import runner

    return runner.import_confluence(
        db, source=source, actor=actor, space_keys=["CMP"], **kw
    )


# ── 전부 가져왔는가 ──────────────────────────────────────────────────────────


def test_every_page_including_archived_and_deep_children_becomes_a_document(db, actor):
    """인수 조건 12. 그리고 그것을 **수 대조**로 증명한다."""
    from app.knowledge.models import Document
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    source = FakeConfluence()
    report = _run(db, actor, source)

    made = db.query(LegacyMapping).filter(
        LegacyMapping.legacy_source == SRC_CONFLUENCE,
        LegacyMapping.target_type == T_DOCUMENT,
    ).all()
    assert len(made) == 3, "세 페이지가 다 문서가 되지 않았다"

    titles = {db.get(Document, m.target_id).title for m in made}
    assert titles == {"CMP 홈", "설치 가이드", "옛 규약"}

    # 대조 게이트가 통과했다 — 「전부 가져왔다」가 주장이 아니다.
    blocking = [f for f in report.findings if f.severity == "blocking"]
    assert blocking == [], [f.detail for f in blocking]


def test_the_page_tree_is_not_rebuilt_as_folders(db, actor):
    """인수 조건: 계층을 폴더로 만들지 않는다(14번·22번)."""
    from app.knowledge.models import Document, Folder
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    _run(db, actor, FakeConfluence())
    ids = [m.target_id for m in db.query(LegacyMapping).filter(
        LegacyMapping.legacy_source == SRC_CONFLUENCE,
        LegacyMapping.target_type == T_DOCUMENT).all()]
    assert all(db.get(Document, i).folder_id is None for i in ids)
    assert db.query(Folder).count() == 0, "폴더가 생겼다 — 계층을 재현하면 안 된다"


def test_documents_land_in_an_organization_owned_space(db, actor):
    """🔴 이 파일에서 가장 위험한 줄. `unset` 이면 아무에게도 안 보인다."""
    from app.knowledge.models import Document, KnowledgeSpace
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    _run(db, actor, FakeConfluence())
    row = db.query(LegacyMapping).filter(
        LegacyMapping.legacy_source == SRC_CONFLUENCE,
        LegacyMapping.target_type == T_DOCUMENT).first()
    space = db.get(KnowledgeSpace, db.get(Document, row.target_id).space_id)
    assert space.owner_kind == "organization", f"소유가 {space.owner_kind} 다"
    assert space.org_id


# ── 본문과 미리보기 ──────────────────────────────────────────────────────────


def test_the_body_keeps_tables_lists_images_and_link_previews(db, actor):
    """인수 조건 17 — 본문만 가져오고 끝내지 않는다. **미리보기 카드도 내용이다.**"""
    from app.knowledge.models import Document, DocumentVersion
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    _run(db, actor, FakeConfluence())
    doc_id = next(
        m.target_id for m in db.query(LegacyMapping).filter(
            LegacyMapping.legacy_source == SRC_CONFLUENCE,
            LegacyMapping.target_type == T_DOCUMENT).all()
        if db.get(Document, m.target_id).title == "설치 가이드"
    )
    document = db.get(Document, doc_id)
    version = db.get(DocumentVersion, document.current_version_id)
    body = json.dumps(version.body, ensure_ascii=False)

    assert '"table"' in body, "표가 사라졌다"
    assert '"bulletList"' in body, "목록이 사라졌다"
    assert '"image"' in body, "본문 이미지가 사라졌다"
    assert "/api/knowledge/attachments/" in body, "이미지가 우리 주소를 안 가리킨다"
    # 링크 미리보기(inlineCard)의 주소가 남는다 — 버리면 「여기 무언가 있었다」가 사라진다.
    assert "https://example.test/spec" in body

    # 목록의 미리보기(발췌)를 만드는 파생 글자도 함께 만들어졌다.
    assert "준비물" in version.body_text
    assert "원본에서 확인" not in version.body_text


# ── 3MB 규칙 ────────────────────────────────────────────────────────────────


def test_an_oversized_attachment_never_fails_the_document(db, actor):
    """🔴 인수 조건 14·15. 큰 파일 하나 때문에 문서가 통째로 죽으면 안 된다."""
    from app.knowledge.models import Document, DocumentVersion
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    source = FakeConfluence()
    report = _run(db, actor, source)

    doc_id = next(
        m.target_id for m in db.query(LegacyMapping).filter(
            LegacyMapping.legacy_source == SRC_CONFLUENCE,
            LegacyMapping.target_type == T_DOCUMENT).all()
        if db.get(Document, m.target_id).title == "설치 가이드"
    )
    document = db.get(Document, doc_id)
    assert document is not None, "큰 첨부 때문에 문서가 아예 안 생겼다"

    # 3MB 미만은 붙었다.
    from app.knowledge import attachments as doc_attachments

    linked = doc_attachments.of_document(db, doc_id)
    names = {record.filename for _, record in linked}
    assert len(linked) == 1, f"첨부가 {len(linked)}건이다 — 작은 것 하나여야 한다"

    # 건너뛴 사실이 **보고서와 본문 양쪽에** 남는다 — 조용히 사라지지 않는다.
    kinds = {f.kind for f in report.findings}
    assert "confluence_attachment_too_large" in kinds, kinds
    version = db.get(DocumentVersion, document.current_version_id)
    assert "설치본.zip" in version.body_text, "건너뛴 파일이 본문에 안 남았다"

    # 그리고 본문·댓글은 그대로 들어왔다.
    assert "준비물" in version.body_text
    assert names  # 이름을 실제로 읽었다는 증거


# ── 댓글 ─────────────────────────────────────────────────────────────────────


def test_comments_land_in_the_existing_structure_without_faking_authorship(db, actor):
    """인수 조건 13 · 19번. 새 댓글 시스템을 만들지 않는다."""
    from app.knowledge.models import Document, DocumentComment
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    _run(db, actor, FakeConfluence())
    doc_id = next(
        m.target_id for m in db.query(LegacyMapping).filter(
            LegacyMapping.legacy_source == SRC_CONFLUENCE,
            LegacyMapping.target_type == T_DOCUMENT).all()
        if db.get(Document, m.target_id).title == "설치 가이드"
    )
    rows = db.query(DocumentComment).filter(
        DocumentComment.document_id == doc_id).all()
    assert len(rows) == 1
    comment = rows[0]
    assert "이 순서대로 하면 됩니다." in comment.body
    # 작성자를 못 풀었으므로 실행 계정이지만, **원 작성자를 본문이 말한다.**
    assert comment.author_user_id == actor.id
    assert "김동현" in comment.body
    # 원본의 시각을 지킨다.
    assert comment.created_at.year == 2026


# ── 두 번 돌리기 ─────────────────────────────────────────────────────────────


def test_running_twice_does_not_duplicate_anything(db, actor):
    """인수 조건 9 의 Confluence 판 — 다리가 실제로 막는가."""
    from app.knowledge.models import Document, DocumentComment
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    source = FakeConfluence()
    _run(db, actor, source)
    first_docs = db.query(Document).count()
    first_comments = db.query(DocumentComment).count()
    first_downloads = source.downloads

    _run(db, actor, source)
    assert db.query(Document).count() == first_docs, "두 번째 회차가 문서를 늘렸다"
    assert db.query(DocumentComment).count() == first_comments, "댓글이 늘었다"
    assert db.query(LegacyMapping).filter(
        LegacyMapping.legacy_source == SRC_CONFLUENCE,
        LegacyMapping.target_type == T_DOCUMENT).count() == 3
    # 이미 옮긴 첨부의 **바이트를 다시 안 받는다.** 상한을 넘은 것은 애초에 바이트를
    # 안 만지므로(크기를 먼저 본다) 두 번째 회차에도 값이 안 는다.
    assert source.downloads == first_downloads, "같은 첨부의 바이트를 다시 받았다"
    assert first_downloads == 1, f"첫 회차가 바이트를 {first_downloads}번 받았다"


def test_dry_run_writes_nothing(db, actor):
    """세기만 하는 회차가 행을 만들면 그것은 이미 쓰기다."""
    from app.knowledge.models import Document

    before = db.query(Document).count()
    report = _run(db, actor, FakeConfluence(), dry_run=True)
    assert db.query(Document).count() == before
    assert "dry-run" in report.mode


def test_a_page_count_mismatch_is_a_blocking_finding(db, actor):
    """🔴 「전부 가져왔다」를 **증명**으로 만드는 자리.

    한 페이지가 조용히 사라지면 회차가 그것을 말해야 한다 — 침묵이 이 회차가 고치는
    결함의 모양이다.
    """
    source = FakeConfluence()

    def _boom(page_id, *, version=None):
        if page_id == "3":
            raise RuntimeError("본문을 못 읽었다")
        return FakeConfluence.page_body(source, page_id, version=version)

    source.page_body = _boom
    report = _run(db, actor, source)
    kinds = {f.kind for f in report.findings if f.severity == "blocking"}
    assert "confluence_page_failed" in kinds, kinds
    # 실패한 한 건도 **설명된** 것이므로 수는 맞는다 — 사라진 것이 아니다.
    assert "confluence_page_count_mismatch" not in kinds
