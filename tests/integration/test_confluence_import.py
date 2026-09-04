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
                "authorId": "acct-1",
                "version": {"number": 3, "createdAt": "2026-05-02T00:00:00.000Z"},
                "createdAt": "2025-02-02T00:00:00.000Z",
            },
            "3": {
                # 🔴 보관된 페이지. 기본 필터가 조용히 빼던 갈래다.
                "id": "3", "title": "옛 규약", "status": "archived", "parentId": "2",
                # 🔴 우리가 이름을 모르는 계정. 그때는 이름을 지어내지 않는다.
                "authorId": "acct-unknown",
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
                # 🔴 이 문단이 없으면 이 페이지의 글자가 18자라 빈 페이지 규칙에 걸린다.
                # 표와 그림이 아무리 많아도 **세는 것은 글자**다.
                _para("이 페이지는 표와 그림을 함께 담고 있어서 변환기의 여러 갈래를 한 번에 지납니다."),
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
            # 🔴 20자를 넘겨야 한다. 빈 페이지 규칙(`EMPTY_BODY_MAX_CHARS`)이 그 아래를
            # 문서로 안 만들기 때문이다 — 짧게 두면 이 대역의 페이지가 조용히 사라진다.
            adf = _adf(_para(
                f"{page['title']} 의 본문입니다. 이 문단은 빈 페이지 규칙에 안 걸리게 충분히 깁니다."
            ))
        return {
            "_version": (page.get("version") or {}).get("number"),
            "authorId": page.get("authorId"),
            "id": page_id, "title": page["title"], "status": page["status"],
            "parentId": page.get("parentId"), "version": page.get("version") or {},
            "createdAt": page.get("createdAt"), "adf": adf,
        }

    def author_name(self, account_id):
        """원본 작성자의 **이름**. 진짜 소스와 같이 이메일은 안 준다.

        🔴 실측이 그렇다: 작성자 8명 중 이메일을 주는 것은 1명뿐이고 그마저 우리 계정에
        없다. 그래서 대역도 이름만 준다 — 대역이 진짜보다 친절하면 시험이 못 잡는다.
        """
        return {"acct-1": "김동균", "acct-2": "민지원"}.get(account_id or "", "")

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

    # 그리고 그 대조가 **검사로도** 남는다. Finding 만 남기면 보고서의 자기 판정이
    # 「검사 0건」이 되어, 아무 문제가 없는 회차에도 마지막 줄이 FAIL 이 된다.
    counted = [c for c in report.checks if c.name == "Confluence 페이지 전수"]
    assert len(counted) == 1 and counted[0].ok
    assert counted[0].expected == 3 and counted[0].actual == 3


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


# ── 🔴 첨부 바이트가 조용히 0이 되던 자리 ────────────────────────────────────
#
# 실측에서 첨부 1,458개가 전부 「빈 파일」로 거절됐는데 회차는 `CONFLUENCE_IMPORT_OK`
# 로 끝났다. 원인은 리다이렉트다: Confluence 의 download 주소는 302 로 미디어 CDN 을
# 가리키는데 `OutboundClient` 는 자동 추적을 안 한다(SSRF 방어라 그렇게 두는 것이 맞다).
# 그래서 우리가 받은 것은 **빈 몸통을 가진 302** 였고, 400 미만이라 오류로도 안 걸렸다.
#
# 「못 가져왔다」가 「원래 없었다」와 같은 모양으로 보고되던 자리다.


class _Resp:
    def __init__(self, status, content=b"", location=None):
        self.status_code = status
        self.content = content
        self.headers = {"Location": location} if location else {}

    def json(self):
        raise ValueError("본문이 아니다")


class _RecordingOutbound:
    """홉마다 어떤 인증으로 어디에 갔는지 적는 대역."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append({"url": url, "auth": kw.get("auth_type"),
                           "allowlist": kw.get("allowlist")})
        return self.script.pop(0)


def _source(outbound, tmp_path):
    from app.migration.source_confluence import ConfluenceSource

    return ConfluenceSource(outbound, secret_ref="confluence_token",
                            cache_dir=str(tmp_path), throttle_seconds=0, sleep=lambda _s: None)


def test_a_redirected_attachment_is_actually_downloaded(tmp_path):
    """302 를 따라가서 **바이트를 실제로 받는다.**"""
    outbound = _RecordingOutbound([
        _Resp(302, b"", "https://api.media.atlassian.com/file/abc/binary?token=t"),
        _Resp(200, _PNG),
    ])
    got = _source(outbound, tmp_path).download("/download/x", declared_size=len(_PNG))
    assert got == _PNG, "리다이렉트를 따라가지 않아 빈 바이트를 받았다"

    # 🔴 홉이 **새 요청**이라 allowlist 를 다시 지난다. 자동 추적을 켜면 그 검사가 사라진다.
    assert [c["allowlist"] for c in outbound.calls] == ["migration", "migration"]
    # 그리고 CDN 홉에는 인증을 안 붙인다 — 그 주소는 서명 토큰을 자기 안에 들고 있고,
    # Basic 을 겹쳐 보내면 Atlassian 이 그 조합을 거절한다.
    assert [c["auth"] for c in outbound.calls] == ["basic", "none"]


def test_an_empty_body_for_a_sized_attachment_is_a_failure_not_an_empty_file(tmp_path):
    """🔴 목록이 크기를 말했는데 0바이트를 받으면 그것은 **실패**다.

    조용히 빈 바이트를 돌려주면 로더가 「빈 파일은 올릴 수 없습니다」로 거절하고, 그
    거절은 분류된 예외라 회차가 초록으로 끝난다 — 첨부 1,458개가 그렇게 사라졌다.
    """
    from app.migration.source_confluence import ConfluenceSourceError

    outbound = _RecordingOutbound([_Resp(200, b"")])
    with pytest.raises(ConfluenceSourceError, match="0바이트"):
        _source(outbound, tmp_path).download("/download/x", declared_size=158101)


def test_a_redirect_loop_stops_instead_of_spinning(tmp_path):
    """홉이 끝없이 이어지면 회차가 안 끝난다. 상한에서 말하고 멈춘다."""
    from app.migration.source_confluence import ConfluenceSourceError

    loop = [_Resp(302, b"", "https://api.media.atlassian.com/a") for _ in range(6)]
    with pytest.raises(ConfluenceSourceError, match="넘게 넘어갑니다"):
        _source(_RecordingOutbound(loop), tmp_path).download("/download/x", declared_size=10)


def test_the_size_limit_still_short_circuits_before_any_request(tmp_path):
    """3MB 이상은 **요청 자체를 안 한다** — 크기를 목록에서 먼저 보기 때문이다."""
    outbound = _RecordingOutbound([])
    assert _source(outbound, tmp_path).download(
        "/download/big", declared_size=9 * 1024 * 1024) is None
    assert outbound.calls == [], "상한을 넘은 첨부인데 바이트를 받으러 갔다"


# ── 못 옮긴 그림에 **왜 없는지**가 적히는가 ──────────────────────────────────
#
# 운영에서 본문 12곳에 「원본에만 있는 이미지입니다」가 남았고 사용자가 그것이 무엇이냐고
# 물었다. 갈라 보니 사유가 셋이었다: 원본에서 이미 지워진 그림 18 · 3MB 초과 · 형식 거절.
# 🔴 그중 첫째에는 그 문장이 **거짓말**이다 — 같은 주소를 지금 눌러도 Atlassian 이 404 를
# 준다. 원본에도 없는 그림을 「원본에만 있다」고 적으면 읽는 사람은 원본을 보러 갔다가
# 거기서도 깨진 그림을 본다.


#: zip 파일의 머리 네 바이트. 소스에 제어문자를 그대로 박지 않는다.
_ZIP_HEAD = b"PK" + bytes([3, 4])


class GoneImageConfluence(FakeConfluence):
    """그림 셋이 서로 **다른 이유로** 못 들어오는 페이지."""

    def page_body(self, page_id, *, version=None):
        body = super().page_body(page_id, version=version)
        if page_id != "2":
            return body
        body["adf"] = _adf(
            _para("앞 문단입니다."),
            {"type": "mediaSingle", "content": [
                {"type": "media", "attrs": {"id": "att-gone", "type": "file"}}]},
            _para("가운데 문단입니다."),
            {"type": "mediaSingle", "content": [
                {"type": "media", "attrs": {"id": "att-huge", "type": "file"}}]},
            _para("뒤 문단입니다."),
            {"type": "mediaSingle", "content": [
                {"type": "media", "attrs": {"id": "att-nowhere", "type": "file"}}]},
        )
        return body

    def page_attachments(self, page_id):
        if page_id != "2":
            return []
        return [
            {"id": "att-gone", "title": "화면-1.png", "fileSize": 2048,
             "mediaType": "image/png", "downloadLink": "/download/gone"},
            {"id": "att-huge", "title": "매뉴얼.pdf", "fileSize": 9 * 1024 * 1024,
             "mediaType": "application/pdf", "downloadLink": "/download/huge"},
            # 본문이 **안 부르는** 첨부. 형식이 막혀 건너뛴다.
            {"id": "att-orphan", "title": "소스.zip", "fileSize": 2048,
             "mediaType": "application/zip", "downloadLink": "/download/orphan"},
        ]

    def download(self, link, *, declared_size=None):
        from app.core.errors import AppError

        if link == "/download/gone":
            raise AppError("첨부 응답 오류: HTTP 404")
        if link == "/download/orphan":
            # 🔴 이름이 아니라 **내용**으로 형식을 가른다(`storage.store_bytes` 는
            # `sniff_media_type` 을 쓴다). PNG 바이트를 「소스.zip」이라 부르면 통과한다 —
            # 처음에 그렇게 적어서 이 시험이 스스로를 속였다. 진짜 zip 머리를 준다.
            return _ZIP_HEAD + bytes(64)
        return super().download(link, declared_size=declared_size)


def _page2_text(db):
    from app.knowledge.models import Document, DocumentVersion
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    doc_id = next(
        m.target_id for m in db.query(LegacyMapping).filter(
            LegacyMapping.legacy_source == SRC_CONFLUENCE,
            LegacyMapping.target_type == T_DOCUMENT).all()
        if db.get(Document, m.target_id).title == "설치 가이드"
    )
    document = db.get(Document, doc_id)
    return db.get(DocumentVersion, document.current_version_id).body_text


def test_a_lost_image_says_why_it_is_missing_and_names_the_file(db, actor):
    """🔴 사유 셋이 서로 다른 문장으로 선다 — 한 문장으로 뭉치면 하나가 거짓말이 된다."""
    _run(db, actor, GoneImageConfluence())
    text = _page2_text(db)

    assert "원본에서 이미 지워진 그림입니다: 화면-1.png" in text, text
    assert "3MB 를 넘어 옮기지 않은 그림입니다: 매뉴얼.pdf" in text, text
    # 사유를 아는 자리에서는 옛 뭉뚱그린 문장을 안 쓴다. 한 번은 남는다 —
    # `att-nowhere` 는 첨부 목록에 아예 없어 우리가 사유를 모른다(아래 시험).
    assert text.count("원본에만 있는 이미지입니다") == 1, text


def test_a_lost_image_stays_where_the_image_was(db, actor):
    """자리를 잃으면 「어디에 있던 그림인지」를 못 알아본다 — 끝줄로 보내지 않는다."""
    _run(db, actor, GoneImageConfluence())
    text = _page2_text(db)

    before = text.index("앞 문단입니다.")
    gone = text.index("원본에서 이미 지워진 그림입니다")
    middle = text.index("가운데 문단입니다.")
    huge = text.index("3MB 를 넘어 옮기지 않은 그림입니다")
    after = text.index("뒤 문단입니다.")
    assert before < gone < middle < huge < after, (
        "못 옮긴 그림이 본문 흐름에서 밀려났다\n" + text
    )


def test_a_skipped_attachment_the_body_never_referenced_still_gets_a_trailing_line(
    db, actor
):
    """본문이 안 부르는 첨부는 적을 자리가 없다 — 그때만 끝줄이다.

    양쪽을 함께 재는 이유는 「전부 끝줄로 보낸다」로 고쳐도 위 시험이 초록이기 때문이다.
    """
    _run(db, actor, GoneImageConfluence())
    text = _page2_text(db)

    assert "원본에만 있는 첨부 파일입니다: 소스.zip" in text, text
    assert text.index("뒤 문단입니다.") < text.index("소스.zip"), (
        "본문이 안 부르는 첨부는 끝에 서야 한다\n" + text
    )


def test_an_image_with_no_attachment_row_at_all_keeps_the_last_resort_wording(db, actor):
    """사유를 **모르는** 자리에는 마지막 수단이 남는다 — 아는 척하지 않는다.

    `att-nowhere` 는 첨부 목록에 아예 없다. 지워졌는지, 다른 페이지 것인지, 외부
    이미지인지 우리가 알 방법이 없으므로 셋 중 하나를 골라 적으면 그것이 추측이다.
    """
    _run(db, actor, GoneImageConfluence())
    text = _page2_text(db)

    assert "원본에만 있는 이미지입니다" in text, text
    # 그리고 그 자리는 마지막 그림 자리다 — 사유를 몰라도 위치는 안다.
    assert text.index("뒤 문단입니다.") < text.index("원본에만 있는 이미지입니다"), text


# ── 「못 가져왔다」가 초록으로 끝나지 않는가 ─────────────────────────────────
#
# 🔴 이 회차에 실제로 일어났다: 524쪽이 전부 들어오고 첨부는 1,458개 중 **0개**가 들어왔는데
# 회차는 `CONFLUENCE_IMPORT_OK` 로 끝났다. 원인 둘(리다이렉트·0바이트)은 각각 막았지만
# **그 사고를 잡아 줄 검사**는 없었다 — 다음에 다른 이유로 같은 일이 나면 또 초록이다.


class NoAttachmentLandsConfluence(FakeConfluence):
    """첨부가 하나도 안 들어오는 회차. 사유는 무엇이든 좋다 — 결과가 같다."""

    def download(self, link, *, declared_size=None):
        from app.core.errors import AppError

        raise AppError("첨부 응답 오류: HTTP 500")


def test_a_round_where_no_attachment_landed_is_a_failure_not_a_pass(db, actor):
    """원본에 첨부가 있는데 하나도 못 옮겼으면 **회차가 실패한다.**"""
    report = _run(db, actor, NoAttachmentLandsConfluence())

    gate = [c for c in report.checks if "첨부" in c.name]
    assert gate, "첨부 대조 검사가 아예 안 돌았다"
    assert not gate[0].ok, "첨부가 0건인데 검사가 통과했다"
    kinds = {f.kind for f in report.findings}
    assert "confluence_no_attachment_landed" in kinds, kinds
    # 그리고 페이지는 정상으로 들어왔다 — 첨부 실패가 문서를 죽이지 않는다(19번).
    assert report.stages[-1].inserted + report.stages[-1].updated > 0


def test_the_attachment_gate_passes_when_attachments_actually_land(db, actor):
    """반례. 정상 회차에서 이 검사가 초록이 아니면 그것은 게이트가 아니라 소음이다."""
    report = _run(db, actor, FakeConfluence())

    gate = [c for c in report.checks if "첨부" in c.name]
    assert gate and gate[0].ok, [(c.name, c.ok) for c in report.checks]
    kinds = {f.kind for f in report.findings}
    assert "confluence_no_attachment_landed" not in kinds, kinds


def test_the_gate_stays_quiet_when_we_chose_not_to_fetch_files(db, actor):
    """「안 받기로 했다」와 「못 받았다」는 다른 사실이다 — `--no-files` 를 실패로 안 읽는다."""
    report = _run(db, actor, FakeConfluence(), with_files=False)

    assert not [c for c in report.checks if "첨부" in c.name], (
        "파일을 안 받기로 한 회차에 첨부 대조가 돌았다"
    )


def test_the_attachment_gate_does_not_fail_the_second_round(db, actor):
    """🔴 반례 중에서도 가장 중요한 것 — **재실행이 정상이다.**

    이미 옮긴 첨부는 다시 안 붙인다(멱등이 설계다). 그때 「이번에 붙인 수」만 세면 두 번째
    회차의 그 수가 0 이라, 게이트가 정상 회차를 「첨부를 하나도 못 옮겼다」로 읽는다.
    게이트를 넣으면서 실제로 그렇게 적었다가 여기서 잡았다.
    """
    _run(db, actor, FakeConfluence())
    second = _run(db, actor, FakeConfluence())

    gate = [c for c in second.checks if "첨부" in c.name]
    assert gate and gate[0].ok, [(c.name, c.ok, c.actual) for c in second.checks]
    kinds = {f.kind for f in second.findings}
    assert "confluence_no_attachment_landed" not in kinds, kinds


# ── 작성자를 지어내지 않는다 ─────────────────────────────────────────────────
#
# 🔴 예전에는 못 푼 작성자를 **가져오기를 돌린 관리자**로 적었다. 그러면 화면이 「이 관리자가
# 524건을 썼다」고 말한다 — 없는 정보가 아니라 **틀린 정보**다. Confluence 는 작성자의
# 이메일을 안 주므로(실측: 8명 중 1명, 그마저 우리 계정에 없다) 우리 계정으로 이을 수 없다.
# 그래서 셋을 나눈다: 우리 사용자가 썼다 · 원본에 이렇게 적혀 있었다 · 모른다.


def _doc_by_title(db, title):
    from app.knowledge.models import Document
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    for m in db.query(LegacyMapping).filter(
        LegacyMapping.legacy_source == SRC_CONFLUENCE,
        LegacyMapping.target_type == T_DOCUMENT,
    ).all():
        doc = db.get(Document, m.target_id)
        if doc is not None and doc.title == title:
            return doc
    return None


def test_the_original_author_name_survives_the_fallback(db, actor):
    """qa-contract-change: 「못 풀면 비운다」에서 「기본 계정으로 앉힌다」로 바뀌었다
    (사용자 지시 2026-09-04). 문서에는 맡는 사람이 있어야 한다는 판단이다.

    🔴 바뀌지 않은 것을 여기서 지킨다: **원본 이름은 절대 안 지워진다.** 계정을 정하는
    일과 원본이 무엇이라 적었는가는 다른 사실이고, 앞엣것 때문에 뒤엣것을 잃으면 안 된다.
    """
    _run(db, actor, FakeConfluence())

    doc = _doc_by_title(db, "설치 가이드")
    assert doc is not None
    assert doc.created_by is not None, "문서에 맡는 사람이 없다"
    assert doc.legacy_author_name == "김동균", "계정을 정하며 원본 이름을 잃었다"


def test_the_original_author_name_is_kept(db, actor):
    """이을 수는 없어도 **이름은 있다.** 그것까지 버리면 원본보다 아는 것이 적어진다."""
    _run(db, actor, FakeConfluence())

    doc = _doc_by_title(db, "설치 가이드")
    assert doc.legacy_author_name == "김동균", doc.legacy_author_name


def test_an_author_we_cannot_name_is_not_invented(db, actor):
    """🔴 반례. 이름을 못 받으면 **이름은** 지어내지 않는다.

    계정은 기본 계정으로 앉지만(맡을 사람이 있어야 한다), 원본이 안 준 이름을 만들어
    적지는 않는다. 그 둘을 함께 재는 이유는, 「기본 계정으로 보낸다」를 「기본 계정의
    이름을 적는다」로 잘못 고쳐도 한쪽만 재면 초록이기 때문이다.
    """
    _run(db, actor, FakeConfluence())

    doc = _doc_by_title(db, "옛 규약")
    assert doc is not None
    assert not doc.legacy_author_name, doc.legacy_author_name
    assert doc.created_by == actor.id, "기본 계정으로 안 갔다"


def test_the_api_carries_the_original_author_name(client, login_as, db, actor):
    """서버가 이름을 안 실으면 화면이 그것을 그릴 수 없다 — 배선까지 잰다."""
    _run(db, actor, FakeConfluence())
    db.commit()

    doc = _doc_by_title(db, "설치 가이드")
    hdr = {"X-CSRF-Token": login_as("system_admin", email=ME)}
    got = client.get(f"/api/knowledge/documents/{doc.id}", headers=hdr)
    assert got.status_code == 200, got.text
    payload = got.json()
    assert payload["legacy_author_name"] == "김동균", payload.get("legacy_author_name")
    # 계정도 함께 실린다 — 화면은 둘을 나란히 그린다(다르면 둘 다 보인다).
    assert payload["author"] is not None, payload["author"]


# ── 빈 페이지는 문서로 안 만든다 ─────────────────────────────────────────────
#
# 🔴 이 규칙이 **가져오기 안에** 있어야 하는 이유를 실측이 가르쳤다. 처음에는 가져온 뒤에
# 치우는 도구로 만들었는데, 회차를 한 번 더 돌리니 치운 문서 106건이 **그대로 되살아났다**.
# 원본 페이지는 여전히 있고 적재기는 그것을 「아직 안 가져온 페이지」로 읽기 때문이다.
# 회차마다 무효가 되는 청소는 청소가 아니다.


class EmptyPageConfluence(FakeConfluence):
    """본문이 제목뿐인 페이지. 목차 페이지의 모양이다."""

    def page_body(self, page_id, *, version=None):
        body = super().page_body(page_id, version=version)
        if page_id == "2":
            body["adf"] = _adf(_para("짧다"))
        return body


def test_an_empty_page_never_becomes_a_document(db, actor):
    """본문이 20자 이하면 문서를 안 만든다. 첨부가 있어도 마찬가지다(사용자가 정했다)."""
    report = _run(db, actor, EmptyPageConfluence())

    assert _doc_by_title(db, "설치 가이드") is None, "빈 페이지가 문서가 됐다"
    kinds = {f.kind for f in report.findings}
    assert "confluence_page_empty" in kinds, kinds
    # 그리고 대조 게이트는 그것을 **설명된 페이지**로 센다 — 조용히 사라진 것이 아니다.
    assert [c for c in report.checks if "전수" in c.name][0].ok


def test_an_existing_document_that_became_empty_is_archived(db, actor):
    """원본이 비워진 것도 사실이다 — 이미 있던 문서는 치운다."""
    from app.knowledge.models import Document

    _run(db, actor, FakeConfluence())
    doc = _doc_by_title(db, "설치 가이드")
    assert doc is not None and not doc.archived

    _run(db, actor, EmptyPageConfluence())
    db.expire_all()
    again = db.get(Document, doc.id)
    assert again.archived is True, "빈 페이지가 된 문서가 그대로 남았다"
    assert again.archived_by == actor.id


def test_a_page_with_real_content_is_not_touched_by_the_empty_rule(db, actor):
    """🔴 반례. 규칙이 문턱이 아니면 「전부 지운다」도 초록이다."""
    _run(db, actor, EmptyPageConfluence())

    # 다른 페이지들은 본문이 충분히 길다 — 그대로 들어온다.
    assert _doc_by_title(db, "CMP 홈") is not None
    assert _doc_by_title(db, "옛 규약") is not None


def test_the_empty_page_count_is_its_own_number(db, actor):
    """「오류로 못 가져왔다」와 「가져올 내용이 없었다」를 같은 칸에 넣지 않는다."""
    _run(db, actor, EmptyPageConfluence())

    # 보고서의 수를 직접 본다 — 건너뜀(skipped)과 섞이면 원장이 거짓말한다.
    from app.migration.load_confluence import ConfluenceLoader  # noqa: F401

    report = _run(db, actor, EmptyPageConfluence())
    stats = report.notion["load"]
    assert stats["documents_empty"] == 1, stats
    assert stats["documents_skipped"] == 0, stats


def test_the_author_is_corrected_on_a_later_round_too(db, actor):
    """🔴 작성자는 **원본이 정본**이다 — 만들 때만 정하면 옛 값이 영영 남는다.

    실측이 그것을 잡았다: 작성자 수정을 넣고 회차를 돌렸는데 524건 중 **418건**이 여전히
    가져오기를 돌린 관리자였다. 새로 만든 106건만 고쳐졌기 때문이다.
    """
    from app.knowledge.models import Document

    _run(db, actor, FakeConfluence())
    doc = _doc_by_title(db, "설치 가이드")
    # 옛 회차가 남긴 상태를 손으로 만든다 — 실행 계정이 작성자로 적힌 문서.
    doc.created_by = actor.id
    doc.legacy_author_name = None
    db.commit()

    _run(db, actor, FakeConfluence())
    db.expire_all()
    again = db.get(Document, doc.id)
    # 이 대역에는 「김동균」 계정이 없으므로 기본 계정(회차를 돌린 사람)으로 앉는다.
    assert again.created_by == actor.id, "다음 회차가 작성자를 안 다시 정했다"
    assert again.legacy_author_name == "김동균", again.legacy_author_name


def test_a_bridge_pointing_at_a_deleted_document_is_repointed(db, actor):
    """🔴 죽은 다리를 그대로 두면 다음 회차가 **아무도 못 찾는 고아**를 만든다.

    운영에서 실제로 101건이 그렇게 생겼다: 사람이 휴지통을 비워 행이 사라지자 다리는
    없는 문서를 가리킨 채 남았고, 회차는 그 페이지를 「아직 안 가져왔다」로 읽어 새 문서를
    만든 뒤 「다리가 이미 있다」며 안 붙였다. 그 문서는 다리가 없어 다음 회차도 못 찾는다.
    """
    from app.knowledge.models import Document
    from app.migration.models import SRC_CONFLUENCE, T_DOCUMENT, LegacyMapping

    _run(db, actor, FakeConfluence())
    doc = _doc_by_title(db, "설치 가이드")
    dead_id = doc.id
    db.delete(doc)          # 사람이 휴지통에서 영구 삭제한 것과 같은 상태
    db.commit()

    _run(db, actor, FakeConfluence())
    db.expire_all()

    again = _doc_by_title(db, "설치 가이드")
    assert again is not None, "다시 만들어지지 않았다"
    assert again.id != dead_id
    bridges = db.query(LegacyMapping).filter(
        LegacyMapping.legacy_source == SRC_CONFLUENCE,
        LegacyMapping.target_type == T_DOCUMENT,
        LegacyMapping.legacy_source_id == "2",
    ).all()
    assert len(bridges) == 1, f"다리가 {len(bridges)}개다 — 하나여야 한다"
    assert bridges[0].target_id == again.id, "다리가 아직 죽은 문서를 가리킨다"
    assert db.get(Document, bridges[0].target_id) is not None


# ── 이름으로 이어 주고, 못 이으면 기본 계정으로 (사용자 지시 2026-09-04) ──────
#
# Confluence 는 이메일을 안 주지만 이름은 준다. 그 이름으로 지금 계정을 찾아 잇고, 못
# 찾으면 정해 둔 계정으로 앉힌다. 🔴 원본 이름은 **그래도 남는다** — 「원본에 누가 썼다고
# 적혀 있었나」와 「지금 이 문서를 누가 맡는가」는 다른 질문이다.


def test_an_author_is_matched_by_display_name(db, actor, make_user):
    """이메일이 없어도 **이름이 같으면** 그 사람에게 이어 준다."""
    writer = make_user("kdg@goodmit.co.kr", role="user", display_name="김동균")
    db.commit()

    _run(db, actor, FakeConfluence())
    doc = _doc_by_title(db, "설치 가이드")
    assert doc.created_by == writer.id, "이름이 같은 계정에 안 이어졌다"
    assert doc.legacy_author_name == "김동균", "원본 이름을 잃었다"


def test_a_seat_label_does_not_block_the_match(db, actor, make_user):
    """🔴 「(Unlicensed)」는 라이선스 상태지 이름의 일부가 아니다.

    안 떼면 실측 23명 중 15명이 영영 안 맞는다.
    """
    from app.migration.load_confluence import _strip_seat_label

    assert _strip_seat_label("김동균 (Unlicensed)") == "김동균"
    assert _strip_seat_label("서윤경") == "서윤경"
    assert _strip_seat_label(None) == ""

    writer = make_user("kdg2@goodmit.co.kr", role="user", display_name="김동균")
    db.commit()

    class SeatLabelled(FakeConfluence):
        def author_name(self, account_id):
            return "김동균 (Unlicensed)" if account_id == "acct-1" else ""

    _run(db, actor, SeatLabelled())
    assert _doc_by_title(db, "설치 가이드").created_by == writer.id


def test_an_author_is_matched_by_the_email_local_part(db, actor, make_user):
    """원본의 표시 이름이 **계정 아이디**인 경우가 있다 (실측: ujmoon 39건)."""
    writer = make_user("ujmoon@goodmit.co.kr", role="user", display_name="문의진")
    db.commit()

    class IdAsName(FakeConfluence):
        def author_name(self, account_id):
            return "ujmoon" if account_id == "acct-1" else ""

    _run(db, actor, IdAsName())
    doc = _doc_by_title(db, "설치 가이드")
    assert doc.created_by == writer.id, "계정 아이디로 못 이었다"
    assert doc.legacy_author_name == "ujmoon", "원본이 적은 그대로를 안 남겼다"


def test_an_unknown_author_lands_on_the_fallback_account(db, actor, make_user):
    """모르는 사람은 정해 둔 계정으로 앉는다 — 그래도 원본 이름은 남는다."""
    keeper = make_user("keeper@goodmit.co.kr", role="admin", display_name="맡는 사람")
    db.commit()

    from app.migration import runner

    runner.import_confluence(
        db, source=FakeConfluence(), actor=actor, space_keys=["CMP"],
        fallback_author=keeper,
    )
    doc = _doc_by_title(db, "설치 가이드")
    assert doc.created_by == keeper.id, "모르는 작성자가 기본 계정으로 안 갔다"
    assert doc.legacy_author_name == "김동균", "기본 계정으로 보내며 원본 이름을 지웠다"


def test_two_people_with_the_same_name_are_not_guessed(db, actor, make_user):
    """🔴 동명이인 중 하나를 찍는 것은 추정이 아니라 동전 던지기다."""
    make_user("kdg-a@goodmit.co.kr", role="user", display_name="김동균")
    make_user("kdg-b@goodmit.co.kr", role="user", display_name="김동균")
    db.commit()

    _run(db, actor, FakeConfluence())
    doc = _doc_by_title(db, "설치 가이드")
    assert doc.created_by == actor.id, "동명이인 중 하나를 찍었다"
    assert doc.legacy_author_name == "김동균"
