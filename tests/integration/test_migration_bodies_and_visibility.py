"""이관이 **본문을 잃지 않고 문서가 보이는가** (S14).

## 이 시험이 세 가지를 함께 보는 이유

셋 다 「오류가 하나도 안 나면서 조용히 틀리는」 자리다.

1. **본문 이미지와 표.** 우리 스키마에 자리가 없던 시절 이관은 그것을 글자
   (`[원본에서 확인: image]`)로 바꿔 넣었다. 검사도 화면도 아무 말을 안 하고, 표 셀의
   글자는 어디에도 안 남는다.
2. **이미지 주소.** Notion 서명 URL 은 한 시간이면 죽는다. 죽었다는 사실은 사용자가
   문서를 열어 깨진 그림을 볼 때만 드러난다(D4).
3. **공간의 소속.** `owner_kind='unset'` 이면 `_stored_ownership_rules` 의 어느 갈래에도
   안 걸려서 전역 조회 권한이 있는 사람 말고는 아무도 문서를 못 본다(D7).

## `real_db` 인 이유

이관은 단계마다 `commit()` 을 부른다. 되감기 위에서 돌리면 그 커밋이 SAVEPOINT 릴리스가
되어 재실행 검증이 거짓 초록이 된다 — `test_migration_dry_run.py` 와 같은 이유다.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.knowledge import service as knowledge_service
from app.knowledge.models import Document, DocumentVersion, KnowledgeSpace
from app.migration import runner
from app.storage import service as storage_service
from app.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.real_db]

ORG = "00000000-0000-0000-0000-000000000001"
USER = "11111111-1111-1111-1111-111111111111"
DEPT = "55555555-5555-5555-5555-555555555555"
PROJECT = "22222222-2222-2222-2222-222222222222"
TICKET = "33333333-3333-3333-3333-33333333333a"
DOC_OPEN = "44444444-4444-4444-4444-44444444444a"
DOC_SECRET = "44444444-4444-4444-4444-44444444444b"

PAGE_PROJECT = "aaaa0000-0000-0000-0000-000000000001"
PAGE_TICKET = "bbbb0000-0000-0000-0000-0000000000a1"
PAGE_OPEN = "cccc0000-0000-0000-0000-0000000000d1"
PAGE_SECRET = "cccc0000-0000-0000-0000-0000000000d2"

BLOCK_IMAGE = "eeee0000-0000-0000-0000-0000000000f1"
# 실측 그대로의 모양이다. 서명 붙은 S3 주소이고 한 시간이면 죽는다.
SIGNED_URL = (
    "https://prod-files-secure.s3.us-west-2.amazonaws.com/2557d037/63e378ab/"
    "image.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600"
)
# 매직바이트만 맞으면 `sniff_media_type` 이 PNG 로 읽는다. 바이트 내용은 이 시험의
# 관심사가 아니다 — 관심사는 「그 바이트가 우리 저장소로 갔는가」다.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

PROJECT_NAME = "용인 클러스터"

TICKET_ATTACHMENT_URL = "https://prod-files-secure.s3.us-west-2.amazonaws.com/ticket-spec"
TICKET_ATTACHMENT_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _write_source(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE organizations (id TEXT PRIMARY KEY, slug TEXT, name TEXT,
            status TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, display_name TEXT,
            role TEXT, active INTEGER, password_hash TEXT, must_change_password INTEGER,
            created_at TEXT, updated_at TEXT, org_id TEXT, department_id TEXT);
        CREATE TABLE departments (id TEXT PRIMARY KEY, name TEXT, org_id TEXT,
            parent_id TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT, code TEXT, status TEXT,
            org_id TEXT, notion_page_id TEXT, created_at TEXT, updated_at TEXT,
            archived_at TEXT, notion_owner_ids TEXT);
        CREATE TABLE ticket_cache (id TEXT PRIMARY KEY, notion_page_id TEXT,
            org_id TEXT, notion_ticket_number INTEGER, title TEXT, status TEXT,
            due_date TEXT, project_ids TEXT, project_names TEXT,
            assignee_notion_ids TEXT, body_markdown TEXT, source TEXT,
            synced_at TEXT, created_at TEXT, updated_at TEXT, project_uid TEXT,
            project_link TEXT, parent_page_id TEXT, notion_missing_at TEXT);
        CREATE TABLE document_cache (id TEXT PRIMARY KEY, notion_page_id TEXT,
            title TEXT, org_id TEXT, owner_kind TEXT, archived INTEGER,
            restricted INTEGER, document_type TEXT, synced_at TEXT);
        """
    )
    stamp = "2026-01-01 00:00:00"
    conn.execute(
        "INSERT INTO organizations VALUES (?,?,?,?,?,?)",
        (ORG, "clovirassist", "ClovirAssist", "active", stamp, stamp),
    )
    conn.execute(
        "INSERT INTO departments VALUES (?,?,?,?,?,?)",
        (DEPT, "개발팀", ORG, None, stamp, stamp),
    )
    # 부서를 붙여 두는 것이 실측과 같다. 부서가 없는 계정은 **자기 소속 때문에** 아무것도
    # 못 보고(`_membership_scope` 가 `unassigned` 를 추측하지 않는다), 그러면 이 시험이
    # 공간의 소속이 아니라 사용자의 소속을 재게 된다.
    conn.execute(
        "INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (USER, "shim@goodmit.co.kr", "임승환", "user", 1, "x", 0, stamp, stamp,
         ORG, DEPT),
    )
    conn.execute(
        "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?)",
        (PROJECT, PROJECT_NAME, None, "active", ORG, PAGE_PROJECT, stamp, stamp, None, ""),
    )
    conn.execute(
        "INSERT INTO ticket_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (TICKET, PAGE_TICKET, ORG, 100, "첫 티켓", "진행", None, PAGE_PROJECT, "", "",
         None, "notion", stamp, stamp, stamp, None, "unresolved", None, None),
    )
    for doc_id, page_id, title, restricted in (
        (DOC_OPEN, PAGE_OPEN, "설계 문서", 0),
        (DOC_SECRET, PAGE_SECRET, "인사 문서", 1),
    ):
        conn.execute(
            "INSERT INTO document_cache VALUES (?,?,?,?,?,?,?,?,?)",
            (doc_id, page_id, title, ORG, "unset", 0, restricted, "기타", stamp),
        )
    conn.commit()
    conn.close()


def _rich(text: str) -> dict:
    return {"plain_text": text, "text": {"content": text},
            "annotations": {"bold": False, "italic": False, "strikethrough": False,
                            "code": False}}


def _people(email: str) -> dict:
    return {"type": "people", "people": [
        {"id": "notion-user-1", "name": "임승환",
         "person": {"email": email, "email_verified": True}}]}


def _table_row(*cells: str) -> dict:
    return {"id": f"row-{'-'.join(cells)}", "type": "table_row",
            "table_row": {"cells": [[_rich(cell)] for cell in cells]}}


class FakeNotion:
    """조회만 하는 가짜. 실제 응답의 모양을 그대로 흉내 낸다."""

    class Stats:
        def as_dict(self) -> dict:
            return {"api_calls": 0, "fake": True}

    def __init__(self) -> None:
        self.stats = self.Stats()
        self.downloads: list[str] = []
        # 기본은 꺼져 있다 — 운영 최초 컷오버가 바로 이 모양이었다. 첫 회차가 놓친
        # 속성 첨부를 `reimport-bodies` 가 나중에 채우는지를 보는 시험만 켠다.
        self.include_ticket_attachment = False

    def discover(self, *, overrides=None) -> dict:
        return {"tasks": "db-tasks", "projects": "db-projects", "documents": "db-docs",
                "doc_types": "db-types", "categories": "db-categories"}

    def query_database(self, database_id: str, *, role: str) -> list[dict]:
        if role == "projects":
            return [{
                "id": PAGE_PROJECT, "last_edited_time": "2026-08-20T00:00:00.000Z",
                "properties": {
                    "프로젝트": {"type": "title", "title": [_rich(PROJECT_NAME)]},
                    "진행 상태": {"type": "status", "status": {"name": "진행 중"}},
                },
            }]
        if role == "tasks":
            return [{
                "id": PAGE_TICKET, "url": f"https://notion.so/{PAGE_TICKET}",
                "created_time": "2026-01-01T00:00:00.000Z",
                "last_edited_time": "2026-08-20T00:00:00.000Z",
                "properties": {
                    "제목": {"type": "title", "title": [_rich("첫 티켓")]},
                    "티켓 ID": {"type": "unique_id",
                                "unique_id": {"prefix": "GIT", "number": 100}},
                    "진행상태": {"type": "status", "status": {"name": "진행"}},
                    "프로젝트": {"type": "relation", "relation": [{"id": PAGE_PROJECT}]},
                    "티켓 담당자": _people("shim@goodmit.co.kr"),
                    **({"파일과 미디어": {"type": "files", "files": [
                        {"name": "ticket-spec.png",
                         "file": {"url": TICKET_ATTACHMENT_URL}},
                    ]}} if self.include_ticket_attachment else {}),
                },
            }]
        if role == "documents":
            return [
                {
                    "id": PAGE_OPEN, "url": f"https://notion.so/{PAGE_OPEN}",
                    # 원본이 말하는 생긴 날. 우리 `created_at` 은 이관일이라 이 값을
                    # 안 옮기면 문서가 전부 같은 날이 된다.
                    "created_time": "2025-03-04T05:06:07.000Z",
                    "last_edited_time": "2025-09-15T06:48:00.000Z",
                    "properties": {
                        "이름 ": {"type": "title", "title": [_rich("설계 문서")]},
                        " 카테고리": {"type": "relation", "relation": [{"id": "cat-1"}]},
                        "프로젝트 선택": {"type": "relation",
                                     "relation": [{"id": PAGE_PROJECT}]},
                        "작성자": _people("shim@goodmit.co.kr"),
                    },
                },
                {
                    "id": PAGE_SECRET, "url": f"https://notion.so/{PAGE_SECRET}",
                    "created_time": "2025-03-04T05:06:07.000Z",
                    "last_edited_time": "2025-09-15T06:48:00.000Z",
                    "properties": {
                        "이름 ": {"type": "title", "title": [_rich("인사 문서")]},
                    },
                },
            ]
        if role == "categories":
            return [{"id": "cat-1", "properties": {
                "이름": {"type": "title", "title": [_rich("인프라")]}}}]
        return []

    def page_comments(self, page_id: str, *, refresh: bool = False) -> list[dict]:
        """이 표본에는 댓글이 없다. 댓글 경로는 `test_migration_ticket_comments` 가 본다."""
        return []

    def page_blocks(self, page_id: str, *, last_edited) -> list[dict]:
        if page_id == PAGE_TICKET:
            # 티켓 본문에도 표가 있다(실측 35개/22쪽). 이쪽 정본은 마크다운이다.
            return [
                {"id": f"p-{page_id}", "type": "paragraph",
                 "paragraph": {"rich_text": [_rich("본문")]}},
                {"id": "t-tbl", "type": "table",
                 "table": {"table_width": 2, "has_column_header": True,
                           "has_row_header": False},
                 "_children": [_table_row("단계", "담당"),
                               _table_row("검증", "임승환")]},
            ]
        if page_id != PAGE_OPEN:
            return [{"id": f"p-{page_id}", "type": "paragraph",
                     "paragraph": {"rich_text": [_rich("본문")]}}]
        table = {
            "id": "tbl-1", "type": "table",
            "table": {"table_width": 2, "has_column_header": True,
                      "has_row_header": False},
            "_children": [_table_row("항목", "값"), _table_row("메모리", "16GB")],
        }
        # 이미지는 토글 **안**에 둔다. 실측이 그 모양이고, 최상위만 훑는 구현은 여기서
        # 조용히 그림을 잃는다.
        toggle = {
            "id": "tgl-1", "type": "toggle",
            "toggle": {"rich_text": [_rich("자세히")]},
            "_children": [{
                "id": BLOCK_IMAGE, "type": "image",
                "image": {"caption": [_rich("구성도")], "type": "file",
                          "file": {"url": SIGNED_URL}},
            }],
        }
        return [
            {"id": "h4-1", "type": "heading_4",
             "heading_4": {"rich_text": [_rich("전환 절차")]}},
            table,
            toggle,
        ]

    def download(self, url: str) -> bytes:
        self.downloads.append(url)
        if url == TICKET_ATTACHMENT_URL:
            return TICKET_ATTACHMENT_BYTES
        return PNG_BYTES


@pytest.fixture()
def migrate(tmp_path, db_url):
    source_path = tmp_path / "legacy.sqlite3"
    _write_source(source_path)
    settings = Settings(
        _env_file=None, app_env="test", database_url=db_url,
        session_secret="test", cookie_secure=False,
        config_dir=Path("config"), secrets_dir=tmp_path / "secrets",
        data_dir=tmp_path / "data",
    )
    (tmp_path / "secrets").mkdir(exist_ok=True)
    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    notion = FakeNotion()

    def _run(*, with_files: bool = True):
        options = runner.MigrationOptions(
            sqlite_path=str(source_path), with_files=with_files
        )
        with factory() as session:
            return runner.run(session, options, notion=notion, settings=settings)

    def _reimport(*, dry_run: bool = False):
        options = runner.MigrationOptions(sqlite_path="", mode="reimport-bodies")
        with factory() as session:
            return runner.reimport_bodies(
                session, options, notion=notion, settings=settings, dry_run=dry_run
            )

    try:
        yield _run, _reimport, factory, notion
    finally:
        engine.dispose()


def _body(db, page_id: str) -> dict:
    row = db.execute(
        sa.select(DocumentVersion.body)
        .join(Document, Document.current_version_id == DocumentVersion.id)
        .where(Document.legacy_page_id == page_id)
    ).scalar_one()
    return row


# ── 본문 (D3) ────────────────────────────────────────────────────────────────


def test_a_table_arrives_as_a_table_and_keeps_its_cells(migrate):
    """표 셀의 글자가 남는가. 실측에서 이 자리가 31,310자를 통째로 잃던 곳이다."""
    run, _reimport, factory, _notion = migrate
    run()
    with factory() as db:
        body = _body(db, PAGE_OPEN)
    tables = [node for node in body["content"] if node["type"] == "table"]
    assert len(tables) == 1, "표가 표로 안 들어왔다"
    header = tables[0]["content"][0]["content"]
    assert [cell["type"] for cell in header] == ["tableHeader", "tableHeader"]
    text = json.dumps(body, ensure_ascii=False)
    for word in ("항목", "값", "메모리", "16GB"):
        assert word in text, f"«{word}» 가 사라졌다"


def test_an_image_points_at_our_endpoint_not_at_notion(migrate):
    """서명 주소는 한 시간이면 죽는다. 본문에 남기면 깨진 그림만 남는다 (D4)."""
    run, _reimport, factory, notion = migrate
    run()
    with factory() as db:
        body = _body(db, PAGE_OPEN)
        attachments = db.execute(sa.text(
            "SELECT count(*) FROM document_attachments"
        )).scalar_one()
    images = [node for node in body["content"] if node["type"] == "image"]
    assert len(images) == 1, "이미지가 노드로 안 들어왔다"
    src = images[0]["attrs"]["src"]
    assert src.startswith("/api/knowledge/attachments/"), src
    assert "prod-files-secure" not in json.dumps(body, ensure_ascii=False)
    assert images[0]["attrs"]["alt"] == "구성도"
    assert SIGNED_URL in notion.downloads, "바이트를 안 받았다"
    assert attachments == 1


def test_a_heading_four_keeps_its_words(migrate):
    """옛 회차는 `heading_4` 를 통째로 자리표시자로 바꿔 제목 글자를 잃었다."""
    run, _reimport, factory, _notion = migrate
    run()
    with factory() as db:
        body = _body(db, PAGE_OPEN)
    headings = [node for node in body["content"] if node["type"] == "heading"]
    assert [node["attrs"]["level"] for node in headings] == [4]
    assert "전환 절차" in json.dumps(body, ensure_ascii=False)


def test_no_body_carries_the_old_placeholder(migrate):
    """`[원본에서 확인: image]` 는 **정상으로 보이는 손실**이었다."""
    run, _reimport, factory, _notion = migrate
    report = run()
    with factory() as db:
        left = db.execute(sa.text(
            "SELECT count(*) FROM document_versions WHERE body_text LIKE '%원본에서 확인%'"
        )).scalar_one()
    assert left == 0
    assert not report.failed_checks, [c.line() for c in report.failed_checks]


def test_running_twice_does_not_pile_up_versions_or_attachments(migrate):
    """재실행 멱등. 같은 이미지를 두 번 받지 않는다."""
    run, _reimport, factory, notion = migrate
    run()
    with factory() as db:
        first = (
            db.execute(sa.text("SELECT count(*) FROM document_versions")).scalar_one(),
            db.execute(sa.text("SELECT count(*) FROM document_attachments")).scalar_one(),
            db.execute(sa.text("SELECT count(*) FROM files")).scalar_one(),
        )
    downloads = len(notion.downloads)
    run()
    with factory() as db:
        second = (
            db.execute(sa.text("SELECT count(*) FROM document_versions")).scalar_one(),
            db.execute(sa.text("SELECT count(*) FROM document_attachments")).scalar_one(),
            db.execute(sa.text("SELECT count(*) FROM files")).scalar_one(),
        )
    assert first == second, f"{first} → {second}"
    assert len(notion.downloads) == downloads, "같은 이미지를 다시 받았다"


# ── 공간 소유 (D7) ───────────────────────────────────────────────────────────


def test_the_migration_space_is_owned_by_the_organization(migrate):
    run, _reimport, factory, _notion = migrate
    run()
    with factory() as db:
        space = db.execute(sa.select(KnowledgeSpace)).scalars().one()
    assert space.owner_kind == "organization"
    assert space.org_id, "조직 갈래는 owner_kind 와 org_id 를 함께 본다"


def test_an_ordinary_user_can_actually_see_the_migrated_documents(migrate):
    """🔴 실측에서 활성 24명 중 20명이 문서 110건을 하나도 못 봤다 (D7).

    수를 세는 것으로는 못 잡는다 — `documents` 에는 110건이 있었다. 잡히는 자리는
    **그 사람의 눈으로 목록을 부르는 것**뿐이다.
    """
    run, _reimport, factory, _notion = migrate
    run()
    with factory() as db:
        user = db.get(User, USER)
        rows, total = knowledge_service.list_documents(db, user)
    titles = {row.title for row in rows}
    assert total >= 1, "이관한 문서를 아무도 못 본다"
    assert "설계 문서" in titles


def test_a_confidential_document_still_narrows(migrate):
    """가시성을 넓히는 변경이므로 **좁히는 축이 살아 있는지** 함께 못 박는다 (D-193).

    `restricted` 였던 문서는 작성자·명시 부여자·`*_ADMIN` 말고는 못 본다. 이 사용자는
    그 셋 중 아무것도 아니다.
    """
    run, _reimport, factory, _notion = migrate
    run()
    with factory() as db:
        secret = db.execute(
            sa.select(Document).where(Document.legacy_page_id == PAGE_SECRET)
        ).scalars().one()
        assert secret.confidential is True
        user = db.get(User, USER)
        rows, _total = knowledge_service.list_documents(db, user)
    assert PAGE_SECRET not in {row.legacy_page_id for row in rows}


# ── 프로젝트 소속과 원본 날짜 ────────────────────────────────────────────────


def test_the_project_link_survives_as_a_tag(migrate):
    """`document_relations` 는 문서끼리만 잇는다. 34건의 소속을 버리지 않는다."""
    run, _reimport, factory, _notion = migrate
    run()
    with factory() as db:
        names = {
            row[0] for row in db.execute(sa.text(
                "SELECT t.name FROM tags t JOIN document_tags dt ON dt.tag_id = t.id "
                "JOIN documents d ON d.id = dt.document_id "
                "WHERE d.legacy_page_id = :page"
            ), {"page": PAGE_OPEN})
        }
    assert PROJECT_NAME in names
    assert "인프라" in names, "분류 태그가 프로젝트 태그에 밀렸다"


def test_the_original_dates_are_not_replaced_by_the_migration_day(migrate):
    run, _reimport, factory, _notion = migrate
    run()
    with factory() as db:
        row = db.execute(sa.text(
            "SELECT legacy_created_at, legacy_updated_at, created_at "
            "FROM documents WHERE legacy_page_id = :page"
        ), {"page": PAGE_OPEN}).one()
    assert row.legacy_created_at is not None
    assert row.legacy_created_at.year == 2025
    assert row.legacy_updated_at.month == 9
    assert row.legacy_created_at.date() != row.created_at.date()


# ── 본문만 다시 넣기 (D5) ────────────────────────────────────────────────────


def test_reimport_never_touches_the_copied_tables(migrate):
    """🔴 전체 회차를 다시 돌리면 컷오버 뒤에 생긴 행이 3주 전으로 덮인다."""
    run, reimport, factory, _notion = migrate
    run()
    with factory() as db:
        db.add(User(
            id="99999999-9999-9999-9999-999999999999",
            email="after@goodmit.co.kr", display_name="컷오버 뒤 입사",
            role="user", org_id=ORG, password_hash="x",
        ))
        db.commit()
    reimport()
    with factory() as db:
        still = db.execute(sa.text(
            "SELECT count(*) FROM users WHERE email = 'after@goodmit.co.kr'"
        )).scalar_one()
    assert still == 1, "재이관이 컷오버 뒤에 생긴 사용자를 지웠다"


def test_reimport_skips_a_document_the_user_edited(migrate):
    """사용자가 고친 문서는 안 덮는다 (D5)."""
    from app.knowledge import versions

    run, reimport, factory, _notion = migrate
    run()
    with factory() as db:
        document = db.execute(
            sa.select(Document).where(Document.legacy_page_id == PAGE_OPEN)
        ).scalars().one()
        versions.snapshot(
            db, document,
            {"type": "doc", "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "내가 쓴 글"}]},
            ]},
            author_id=USER, source="USER", reindex=False,
        )
        db.commit()
        mine = db.get(DocumentVersion, document.current_version_id).body_text

    reimport()
    with factory() as db:
        document = db.execute(
            sa.select(Document).where(Document.legacy_page_id == PAGE_OPEN)
        ).scalars().one()
        now = db.get(DocumentVersion, document.current_version_id).body_text
    assert now == mine == "내가 쓴 글"


def test_reimport_dry_run_writes_nothing(migrate):
    run, reimport, factory, _notion = migrate
    run()
    with factory() as db:
        db.execute(sa.text(
            "UPDATE document_versions SET body_text = 'sabotage', "
            "body = '{\"type\":\"doc\",\"content\":[]}'::jsonb"
        ))
        db.commit()
        before = db.execute(sa.text(
            "SELECT count(*) FROM document_versions"
        )).scalar_one()

    report = reimport(dry_run=True)
    with factory() as db:
        after = db.execute(sa.text("SELECT count(*) FROM document_versions")).scalar_one()
        untouched = db.execute(sa.text(
            "SELECT count(*) FROM document_versions WHERE body_text = 'sabotage'"
        )).scalar_one()
    assert after == before
    assert untouched == before, "세기만 해야 하는 회차가 본문을 고쳤다"
    counted = [stage for stage in report.stages if stage.name == "documents"]
    assert counted and counted[0].updated >= 1, "무엇이 바뀔지 세지도 않았다"


def test_reimport_is_idempotent(migrate):
    run, reimport, factory, _notion = migrate
    run()
    reimport()
    with factory() as db:
        first = (
            db.execute(sa.text("SELECT count(*) FROM document_versions")).scalar_one(),
            db.execute(sa.text("SELECT count(*) FROM document_attachments")).scalar_one(),
        )
    reimport()
    with factory() as db:
        second = (
            db.execute(sa.text("SELECT count(*) FROM document_versions")).scalar_one(),
            db.execute(sa.text("SELECT count(*) FROM document_attachments")).scalar_one(),
        )
    assert first == second, f"{first} → {second}"


def test_reimport_keeps_a_tag_the_user_added(migrate):
    """지금 태그 설정은 집합 치환이다. 그대로 부르면 사용자가 붙인 태그가 사라진다."""
    from app.knowledge import tags

    run, reimport, factory, _notion = migrate
    run()
    with factory() as db:
        document = db.execute(
            sa.select(Document).where(Document.legacy_page_id == PAGE_OPEN)
        ).scalars().one()
        have = [tag.name for tag in tags.of_document(db, document.id)]
        tags.set_for_document(db, document, [*have, "내가 붙인 태그"])
        db.commit()

    reimport()
    with factory() as db:
        document = db.execute(
            sa.select(Document).where(Document.legacy_page_id == PAGE_OPEN)
        ).scalars().one()
        names = {tag.name for tag in tags.of_document(db, document.id)}
    assert "내가 붙인 태그" in names
    assert "인프라" in names


def test_reimport_bodies_attaches_a_ticket_property_file_the_first_pass_missed(migrate):
    """🔴 운영 최초 컷오버가 실제로 이 모양이었다 — 티켓 속성 첨부가 안 붙었다.

    `reimport-bodies` 는 소스 SQLite 를 안 열지만(D5), 속성 첨부는 SQLite 를 안 지나고
    Notion 에서 바로 오므로 이 안전한 재실행 경로로도 채울 수 있어야 한다. 문서용
    `load_files` 호출만 있고 이 경로가 그 함수를 아예 안 부르면, 운영에 있는 실제
    손실은 안 고쳐진다 — 이 시험이 그 배선을 확인한다.
    """
    run, reimport, factory, notion = migrate
    notion.include_ticket_attachment = True
    report = run(with_files=False)
    assert not report.blocking, [f.line() for f in report.blocking]
    with factory() as db:
        before = db.execute(sa.text(
            "SELECT count(*) FROM ticket_attachments"
        )).scalar_one()
    assert before == 0, "첫 회차가 first-files=False 인데도 첨부가 생겼다"

    reimport(dry_run=False)

    with factory() as db:
        rows = db.execute(sa.text(
            "SELECT filename, size_bytes FROM ticket_attachments WHERE ticket_uid = "
            "(SELECT id FROM tickets WHERE notion_page_id = :p)"
        ), {"p": PAGE_TICKET}).all()
        orphan_files = db.execute(sa.text(
            "SELECT count(*) FROM files WHERE filename = 'ticket-spec.png'"
        )).scalar_one()
    assert len(rows) == 1, "reimport-bodies 가 티켓 속성 첨부를 채우지 않았다"
    assert rows[0].filename == "ticket-spec.png"
    assert rows[0].size_bytes == len(TICKET_ATTACHMENT_BYTES)
    assert orphan_files == 0, "문서용 files 표에 잘못 얹혀 고아가 됐다"


def test_reimport_bodies_repairs_a_ticket_attachment_stuck_in_the_old_files_table(migrate):
    """🔴 이 버그가 고쳐지기 전 회차가 실제 운영 DB에 이미 남긴 흔적을 재현한다.

    `legacy_mapping` 이 티켓 소유 첨부를 `file` 로 적어 두면, 그 다리를 「이미
    옮겼다」로만 읽는 재실행은 영영 이 상태를 못 벗어난다. 여기서는 정상 이관 결과를
    지우고 예전 버그가 남긴 그 모양(바이트는 `files` 에, 다리는 `file` 로)을 직접
    만든 뒤 `reimport-bodies` 가 스스로 고치는지 본다.
    """
    run, reimport, factory, notion = migrate
    notion.include_ticket_attachment = True
    report = run()
    assert not report.blocking, [f.line() for f in report.blocking]

    legacy_id = f"{PAGE_TICKET}:0"
    with factory() as db:
        ticket_id = db.execute(sa.text(
            "SELECT id FROM tickets WHERE notion_page_id = :p"
        ), {"p": PAGE_TICKET}).scalar_one()
        db.execute(sa.text(
            "DELETE FROM ticket_attachments WHERE ticket_uid = :t"
        ), {"t": ticket_id})
        db.execute(sa.text(
            "DELETE FROM legacy_mapping WHERE legacy_source_id = :l"
        ), {"l": legacy_id})
        record = storage_service.store_bytes(
            db, filename="ticket-spec.png", content=TICKET_ATTACHMENT_BYTES,
            owner_ref=f"ticket:{ticket_id}",
        )
        db.flush()
        file_id = record.id
        db.execute(sa.text(
            "INSERT INTO legacy_mapping "
            "(id, legacy_source, legacy_source_id, target_type, target_id, migrated_at) "
            "VALUES (gen_random_uuid()::text, 'notion', :l, 'file', :f, now())"
        ), {"l": legacy_id, "f": file_id})
        db.commit()

    reimport(dry_run=False)

    with factory() as db:
        rows = db.execute(sa.text(
            "SELECT filename FROM ticket_attachments WHERE ticket_uid = :t"
        ), {"t": ticket_id}).all()
        remaining_file = db.execute(sa.text(
            "SELECT count(*) FROM files WHERE id = :f"
        ), {"f": file_id}).scalar_one()
        mapping = db.execute(sa.text(
            "SELECT target_type FROM legacy_mapping WHERE legacy_source_id = :l"
        ), {"l": legacy_id}).scalar_one()
    assert len(rows) == 1, "예전 files 표에 갇힌 첨부를 안 고쳤다"
    assert rows[0].filename == "ticket-spec.png"
    assert remaining_file == 0, "고친 뒤에도 고아 files 행이 남았다"
    assert mapping == "ticket_file"


def test_a_ticket_body_table_survives_as_markdown(migrate):
    """티켓 본문의 정본은 마크다운이다. 표가 자리표시자가 되면 셀 글자가 사라진다."""
    run, _reimport, factory, _notion = migrate
    run()
    with factory() as db:
        body = db.execute(sa.text(
            "SELECT body_markdown FROM tickets WHERE notion_page_id = :page"
        ), {"page": PAGE_TICKET}).scalar_one()
    assert "| 단계 | 담당 |" in body
    assert "| 검증 | 임승환 |" in body
    assert "원본에서 확인" not in body
