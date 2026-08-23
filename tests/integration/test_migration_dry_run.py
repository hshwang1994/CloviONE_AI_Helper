"""Dry Run 이 실제 PostgreSQL 에서 **끝까지 돌고, 두 번 돌려도 같은가** (S13).

## 왜 `real_db` 인가

이관은 자기 세션에서 `commit()` 을 여러 번 부른다(단계마다). 공유 계층의 트랜잭션
되감기 위에서 돌리면 그 커밋이 SAVEPOINT 릴리스가 되어 **재실행 검증이 거짓 초록**이
된다 — 두 번째 회차가 첫 번째의 커밋을 못 보기 때문이다.

## 소스는 합성이고 Notion 은 가짜다

운영 스냅숏은 이 시험이 들 수 있는 물건이 아니다(개인정보이고 저장소에 못 넣는다).
대신 **모양이 같은** 작은 소스를 만든다 — 실제 회차는 같은 코드로 운영 스냅숏을 지나고,
그 원장은 `docs/platform/EVIDENCE/S13/` 에 있다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.migration import runner
from app.migration.report import SEVERITY_BLOCKING
from app.work import codes

pytestmark = [pytest.mark.integration, pytest.mark.real_db]

ORG = "00000000-0000-0000-0000-000000000001"
USER = "11111111-1111-1111-1111-111111111111"
PROJECT = "22222222-2222-2222-2222-222222222222"
TICKET_A = "33333333-3333-3333-3333-33333333333a"
TICKET_B = "33333333-3333-3333-3333-33333333333b"
TICKET_C = "33333333-3333-3333-3333-33333333333c"
DOC = "44444444-4444-4444-4444-444444444444"

PAGE_PROJECT = "aaaa0000-0000-0000-0000-000000000001"
PAGE_A = "bbbb0000-0000-0000-0000-0000000000a1"
PAGE_B = "bbbb0000-0000-0000-0000-0000000000b1"
PAGE_C = "bbbb0000-0000-0000-0000-0000000000c1"
PAGE_DOC = "cccc0000-0000-0000-0000-0000000000d1"

# 프로젝트 이름. **코드와 아무 상관이 없다** (D-282) — 코드는 이름이 아니라 소스가 주는
# 안 변하는 값(여기서는 `PAGE_PROJECT`)에서 나온다. 앞 판에서는 이 문자열이 확정표의
# 첫 줄과 글자 하나까지 같아야 Key 가 붙었고, 소스가 이름을 바꾼 날 그 결합이 실제로
# 끊어졌다(옛 D-278).
PROJECT_NAME = "SK하이닉스 [용인 클러스터 대비]"


def _write_source(path: Path) -> None:
    """옛 설치 모양의 작은 SQLite. 컬럼 이름은 실측과 같다."""
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE organizations (id TEXT PRIMARY KEY, slug TEXT, name TEXT,
            status TEXT, created_at TEXT, updated_at TEXT);
        CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, display_name TEXT,
            role TEXT, active INTEGER, password_hash TEXT, must_change_password INTEGER,
            created_at TEXT, updated_at TEXT, org_id TEXT);
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
    conn.execute(
        "INSERT INTO organizations VALUES (?,?,?,?,?,?)",
        (ORG, "clovirassist", "ClovirAssist", "active",
         "2026-01-01 00:00:00", "2026-01-01 00:00:00"),
    )
    conn.execute(
        "INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)",
        (USER, "shim@goodmit.co.kr", "임승환", "user", 1, "x", 0,
         "2026-01-01 00:00:00", "2026-01-01 00:00:00", ORG),
    )
    conn.execute(
        "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?)",
        (PROJECT, PROJECT_NAME, None, "active", ORG, PAGE_PROJECT,
         "2026-01-01 00:00:00", "2026-01-01 00:00:00", None, ""),
    )
    rows = [
        # 소속이 하나 — 번호를 받는다.
        (TICKET_A, PAGE_A, 100, "첫 티켓", [PAGE_PROJECT], None),
        # 소속이 둘 — ambiguous 로 분류된다.
        (TICKET_B, PAGE_B, 200, "둘째 티켓", [PAGE_PROJECT, "other-page"], None),
        # 소속이 없다 — missing 으로 분류된다.
        (TICKET_C, PAGE_C, 300, "셋째 티켓", [], None),
    ]
    for ticket_id, page_id, number, title, projects, parent in rows:
        conn.execute(
            "INSERT INTO ticket_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticket_id, page_id, ORG, number, title, "진행", None,
             "\x1f".join(projects), "", "", None, "notion",
             "2026-01-01 00:00:00", "2026-01-01 00:00:00", "2026-01-01 00:00:00",
             None, "unresolved", parent, None),
        )
    conn.execute(
        "INSERT INTO document_cache VALUES (?,?,?,?,?,?,?,?,?)",
        (DOC, PAGE_DOC, "설계 문서", ORG, "unset", 0, 0, "기타",
         "2026-01-01 00:00:00"),
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


class FakeNotion:
    """조회만 하는 가짜. **실제 응답의 모양을 그대로** 흉내 낸다."""

    class Stats:
        def as_dict(self) -> dict:
            return {"api_calls": 0, "fake": True}

    def __init__(self) -> None:
        self.stats = self.Stats()
        self.downloads: list[str] = []

    def discover(self, *, overrides=None) -> dict:
        return {
            "tasks": "db-tasks", "projects": "db-projects", "documents": "db-docs",
            "doc_types": "db-types", "categories": "db-categories",
        }

    def query_database(self, database_id: str, *, role: str) -> list[dict]:
        if role == "projects":
            return [{
                "id": PAGE_PROJECT, "last_edited_time": "2026-08-20T00:00:00.000Z",
                "properties": {
                    "프로젝트명": {"type": "title", "title": [_rich(PROJECT_NAME)]},
                    "진행 상태": {"type": "status", "status": {"name": "진행 중"}},
                },
            }]
        if role == "tasks":
            out = []
            for page_id, number, title, projects in (
                (PAGE_A, 100, "첫 티켓", [PAGE_PROJECT]),
                (PAGE_B, 200, "둘째 티켓", [PAGE_PROJECT, "other-page"]),
                (PAGE_C, 300, "셋째 티켓", []),
            ):
                out.append({
                    "id": page_id, "url": f"https://notion.so/{page_id}",
                    "created_time": "2026-01-01T00:00:00.000Z",
                    "last_edited_time": "2026-08-20T00:00:00.000Z",
                    "properties": {
                        "제목": {"type": "title", "title": [_rich(title)]},
                        "티켓 ID": {"type": "unique_id",
                                    "unique_id": {"prefix": "GIT", "number": number}},
                        "진행상태": {"type": "status", "status": {"name": "진행"}},
                        "마감일": {"type": "date", "date": {"start": "2026-09-01"}},
                        "프로젝트": {"type": "relation",
                                   "relation": [{"id": p} for p in projects]},
                        "티켓 담당자": _people("shim@goodmit.co.kr"),
                    },
                })
            return out
        if role == "documents":
            return [{
                "id": PAGE_DOC, "url": f"https://notion.so/{PAGE_DOC}",
                "created_time": "2026-01-01T00:00:00.000Z",
                "last_edited_time": "2026-08-20T00:00:00.000Z",
                "properties": {
                    "제목": {"type": "title", "title": [_rich("설계 문서")]},
                    "유형": {"type": "relation", "relation": [{"id": "type-1"}]},
                    " 카테고리": {"type": "relation",
                               "relation": [{"id": "cat-1"}, {"id": "cat-2"}]},
                    "작성자": _people("shim@goodmit.co.kr"),
                    "첨부파일 ": {"type": "files", "files": [
                        {"name": "spec.txt", "file": {"url": "https://s3.example/spec"}},
                        {"name": "바깥", "external": {"url": "https://out.example/x"}},
                    ]},
                },
            }]
        if role == "doc_types":
            return [{"id": "type-1", "properties": {
                "이름": {"type": "title", "title": [_rich("설계서")]}}}]
        if role == "categories":
            return [
                {"id": "cat-1", "properties": {
                    "이름": {"type": "title", "title": [_rich("인프라")]}}},
                {"id": "cat-2", "properties": {
                    "이름": {"type": "title", "title": [_rich("보안")]}}},
            ]
        return []

    def page_blocks(self, page_id: str, *, last_edited) -> list[dict]:
        return [
            {"id": "h", "type": "heading_2", "heading_2": {"rich_text": [_rich("배경")]}},
            {"id": "p", "type": "paragraph",
             "paragraph": {"rich_text": [_rich(f"{page_id} 본문")]}},
        ]

    def download(self, url: str) -> bytes:
        self.downloads.append(url)
        return b"spec body\n"


@pytest.fixture()
def dry_run(tmp_path, db_url):
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

    def _run():
        options = runner.MigrationOptions(sqlite_path=str(source_path))
        with factory() as session:
            return runner.run(session, options, notion=FakeNotion(), settings=settings)

    try:
        yield _run, factory
    finally:
        engine.dispose()


def test_a_full_pass_lands_and_every_check_holds(dry_run):
    run, factory = dry_run
    report = run()
    assert not report.blocking, [f.line() for f in report.blocking]
    assert report.checks, "검사를 하나도 안 돌았다"
    assert not report.failed_checks, [c.line() for c in report.failed_checks]
    assert report.passed

    with factory() as db:
        assert db.execute(sa.text("SELECT count(*) FROM tickets")).scalar_one() == 3
        assert db.execute(sa.text("SELECT count(*) FROM documents")).scalar_one() == 1
        assert db.execute(
            sa.text("SELECT count(*) FROM document_versions")
        ).scalar_one() == 1


def test_the_ticket_that_can_be_placed_is_named_after_its_project_code(dry_run):
    """Internal · Canonical 두 층이 함께 선다 (D-282).

    문자열을 여기 적지 않는 이유: 적으면 시험이 **생성기의 답을 미리 아는** 상태가 되고,
    생성기를 고치는 날 시험이 「정책이 깨졌다」가 아니라 「내가 적어 둔 값과 다르다」로
    빨개진다. 봐야 하는 것은 코드가 정책의 모양이고 이름이 그 코드에서 나왔다는 것이다.
    """
    run, factory = dry_run
    run()
    with factory() as db:
        code = db.execute(sa.text(
            "SELECT code FROM projects WHERE id = :id"
        ), {"id": PROJECT}).scalar_one()
        row = db.execute(sa.text(
            "SELECT canonical_key, seq FROM tickets WHERE id = :id"
        ), {"id": TICKET_A}).one()
    assert codes.is_valid(code), f"«{code}» 는 정책의 모양이 아니다"
    assert row.seq == 1
    assert row.canonical_key == f"{code}-1"


def test_the_code_comes_from_the_source_identity_not_from_the_name(dry_run):
    """**Cutover 가 Dry Run 과 같은 코드를 받는 근거**를 직접 잰다 (D-282).

    Dry Run 과 Cutover 는 같은 도구가 서로 다른 DB 에 대고 도는 회차다. 코드가 소스가
    주는 값에서 나오지 않으면 같은 프로젝트가 두 회차에서 다른 이름을 받고, 그때 Dry Run
    이 검증한 티켓 이름 전부가 Cutover 에서 무효가 된다.

    「재실행해도 같다」로는 이것을 못 잡는다 — 재실행은 이미 붙은 코드를 안 건드리기만
    하면 통과하기 때문이다. 그래서 **소스 값에서 직접 다시 계산해** 대조한다.
    """
    run, factory = dry_run
    run()
    with factory() as db:
        code = db.execute(sa.text(
            "SELECT code FROM projects WHERE id = :id"
        ), {"id": PROJECT}).scalar_one()
    assert code == codes.derive(PAGE_PROJECT)


def test_the_old_ticket_name_is_not_carried_over(dry_run):
    """**반례** — 옛 이름(`GIT-100`)이 어디에도 남지 않는다 (D-283).

    이 시험이 없으면 「폐기했다」가 코드 주석으로만 존재하고, 어딘가 한 자리가 계속
    옛 이름을 쓰고 있어도 아무도 모른다.
    """
    from app.work.resolve import resolve

    run, factory = dry_run
    run()
    with factory() as db:
        assert resolve(db, "GIT-100") is None
        columns = db.execute(sa.text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'tickets' AND column_name = 'legacy_key'"
        )).scalar_one()
        tables = db.execute(sa.text(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name IN ('ticket_key_aliases', 'project_key_registry')"
        )).scalar_one()
    assert columns == 0, "`tickets.legacy_key` 가 아직 있다"
    assert tables == 0, "옛 이름 표가 아직 있다"


def test_tickets_that_cannot_be_placed_get_a_reason_not_a_guess(dry_run):
    """U11 — 임의 배정 대신 사유를 남긴다."""
    run, factory = dry_run
    run()
    with factory() as db:
        reasons = dict(db.execute(sa.text(
            "SELECT ticket_id, reason FROM migration_exceptions "
            "WHERE resolved_at IS NULL"
        )).all())
        placed = db.execute(sa.text(
            "SELECT seq, canonical_key, project_uid FROM tickets WHERE id = :id"
        ), {"id": TICKET_B}).one()
    assert reasons == {TICKET_B: "ambiguous", TICKET_C: "missing"}
    assert placed.seq is None and placed.canonical_key is None
    assert placed.project_uid is None


def test_the_counter_is_seeded_so_the_next_ticket_does_not_collide(dry_run):
    run, factory = dry_run
    run()
    with factory() as db:
        last = db.execute(sa.text(
            "SELECT last_seq FROM project_ticket_counters WHERE project_id = :p"
        ), {"p": PROJECT}).scalar_one()
    assert last == 1, "MAX(seq) 와 같아야 한다 — 작으면 다음 티켓이 1번을 또 받는다"


def test_the_document_body_comes_across_as_block_json(dry_run):
    run, factory = dry_run
    run()
    with factory() as db:
        version = db.execute(sa.text(
            "SELECT v.body_text, v.source, d.legacy_page_id "
            "FROM document_versions v JOIN documents d ON d.id = v.document_id"
        )).one()
    assert "배경" in version.body_text
    assert version.source == "MIGRATION"
    assert version.legacy_page_id == PAGE_DOC


def test_the_classification_lands_where_the_schema_has_room_for_it(dry_run):
    """유형은 `documents.doc_type`, 카테고리는 **태그**가 된다.

    `documents` 에 카테고리 칸이 없다. 안 옮기면 소스의 분류가 그냥 사라진다 —
    실측으로 문서 61건이 카테고리를 갖고 있다.
    """
    run, factory = dry_run
    run()
    with factory() as db:
        doc_type = db.execute(sa.text("SELECT doc_type FROM documents")).scalar_one()
        names = sorted(
            row[0] for row in db.execute(sa.text(
                "SELECT t.name FROM tags t JOIN document_tags dt ON dt.tag_id = t.id"
            )).all()
        )
        author = db.execute(sa.text("SELECT created_by FROM documents")).scalar_one()
    assert doc_type == "설계서"
    assert names == ["보안", "인프라"]
    assert author == USER, "작성자가 이메일로 이어져야 한다"


def test_a_hosted_attachment_lands_and_an_external_link_is_classified(dry_run):
    run, factory = dry_run
    report = run()
    with factory() as db:
        files = db.execute(sa.text(
            "SELECT filename, size_bytes, checksum_sha256 FROM files"
        )).all()
        attached = db.execute(
            sa.text("SELECT count(*) FROM document_attachments")
        ).scalar_one()
    assert len(files) == 1 and files[0].filename == "spec.txt"
    assert files[0].size_bytes == 10
    assert len(files[0].checksum_sha256) == 64
    assert attached == 1
    external = [f for f in report.findings if f.kind == "attachment_external_link"]
    assert len(external) == 1, "바깥 링크는 실패가 아니라 분류다"


def test_the_bridge_records_where_every_notion_page_went(dry_run):
    run, factory = dry_run
    run()
    with factory() as db:
        rows = dict(db.execute(sa.text(
            "SELECT legacy_source_id, target_type FROM legacy_mapping "
            "WHERE legacy_source = 'notion'"
        )).all())
    assert rows[PAGE_A] == "ticket"
    assert rows[PAGE_DOC] == "document"
    assert rows[PAGE_PROJECT] == "project"


def test_the_user_mapping_is_made_by_email_never_by_name(dry_run):
    run, factory = dry_run
    run()
    with factory() as db:
        row = db.execute(sa.text(
            "SELECT user_id, notion_user_id, status, source, notion_email "
            "FROM user_notion_mappings"
        )).one()
    assert row.user_id == USER
    assert row.notion_user_id == "notion-user-1"
    assert row.status == "verified"
    assert row.source == "migration"
    assert row.notion_email == "shim@goodmit.co.kr"


def test_a_notion_person_without_a_portal_user_is_classified_not_invented(dry_run):
    """**반례** — 짝이 없으면 주인 없는 행을 지어내지 않고 몇 명인지 남긴다.

    표가 `user_id` NOT NULL 이라 지어내려 해도 못 넣는다. 그때 조용히 넘어가면
    「담당자 미해석 티켓 16%」의 원인이 보고서에서 사라진다.
    """
    run, factory = dry_run
    report = run()
    assert not [f for f in report.findings if f.kind == "user_unmapped"], (
        "이 표본은 전원이 이어진다"
    )
    # 소스를 고친다. PostgreSQL 쪽만 고치면 다음 회차의 표 복사가 되돌려 놓는다.
    conn = sqlite3.connect(Path(report.source_sqlite))
    conn.execute("UPDATE users SET email = ? WHERE id = ?",
                 ("somebody-else@goodmit.co.kr", USER))
    conn.commit()
    conn.close()
    with factory() as db:
        db.execute(sa.text("DELETE FROM user_notion_mappings"))
        db.commit()
    again = run()
    unmapped = [f for f in again.findings if f.kind == "user_unmapped"]
    assert len(unmapped) == 1, "짝이 없어진 사람이 보고서에 안 나온다"
    with factory() as db:
        rows = db.execute(
            sa.text("SELECT count(*) FROM user_notion_mappings")
        ).scalar_one()
    assert rows == 0, "주인 없는 매핑 행을 만들었다"


def test_running_it_twice_changes_nothing(dry_run):
    """**멱등** — 두 번째 회차의 신규가 0 이어야 재실행이 안전하다 (R8)."""
    run, factory = dry_run
    first = run()
    with factory() as db:
        before = db.execute(sa.text(
            "SELECT canonical_key FROM tickets WHERE id = :id"
        ), {"id": TICKET_A}).scalar_one()
        versions_before = db.execute(
            sa.text("SELECT count(*) FROM document_versions")
        ).scalar_one()
        codes_before = dict(db.execute(sa.text(
            "SELECT id, code FROM projects ORDER BY id"
        )).all())

    second = run()
    assert second.passed, [c.line() for c in second.failed_checks] + [
        f.line() for f in second.blocking
    ]
    inserted = sum(stage.inserted for stage in second.stages)
    assert inserted == 0, (
        "두 번째 회차가 행을 새로 만들었다: "
        + str([s.line() for s in second.stages if s.inserted])
    )
    assert second.counts == first.counts

    with factory() as db:
        after = db.execute(sa.text(
            "SELECT canonical_key FROM tickets WHERE id = :id"
        ), {"id": TICKET_A}).scalar_one()
        versions_after = db.execute(
            sa.text("SELECT count(*) FROM document_versions")
        ).scalar_one()
    assert after == before, "재실행이 표시 이름을 움직였다 — 옛 링크가 죽는다"
    assert versions_after == versions_before, "같은 본문에 판이 또 쌓였다 (D-247)"

    # 프로젝트 코드도 함께 본다 (D-282). 위 `canonical_key` 만 보면 **코드가 바뀌고
    # 번호가 반대로 바뀌어** 같은 문자열이 되는 경우를 못 잡는다 — 억지처럼 들리지만,
    # 실제로 S13 이 만난 결함이 정확히 「2회차가 코드를 지운다」였다(D-275).
    with factory() as db:
        codes_after = dict(db.execute(sa.text(
            "SELECT id, code FROM projects ORDER BY id"
        )).all())
    assert codes_before, "코드를 가진 프로젝트가 하나도 없다 — 이 시험이 아무것도 안 봤다"
    assert codes_after == codes_before, "재실행이 프로젝트 코드를 움직였다"


def test_derived_tables_stay_empty_because_the_product_refills_them(dry_run):
    """D-270 — 여기에 행이 있으면 복구 리허설 5단계가 터진다."""
    run, factory = dry_run
    run()
    with factory() as db:
        for table in ("document_chunks", "ai_index_state", "search_documents",
                      "rate_limit_buckets"):
            rows = db.execute(sa.text(f'SELECT count(*) FROM "{table}"')).scalar_one()
            assert rows == 0, f"{table} 에 {rows}행이 들어갔다"


def test_a_run_without_notion_says_so_instead_of_passing_quietly(dry_run, tmp_path,
                                                                 db_url):
    """**반례** — Notion 을 안 읽은 회차가 「통과」로 읽히면 안 된다."""
    source_path = tmp_path / "legacy.sqlite3"
    settings = Settings(
        _env_file=None, app_env="test", database_url=db_url,
        session_secret="test", cookie_secure=False,
        config_dir=Path("config"), secrets_dir=tmp_path / "secrets",
        data_dir=tmp_path / "data",
    )
    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            report = runner.run(
                session,
                runner.MigrationOptions(sqlite_path=str(source_path),
                                        with_notion=False, with_files=False),
                notion=None, settings=settings,
            )
    finally:
        engine.dispose()
    skipped = [f for f in report.findings if f.kind == "notion_skipped"]
    assert skipped, "Notion 을 안 읽었다는 사실이 보고서에 없다"
    # 코드는 Notion 없이도 붙는다 (D-282) — 씨앗이 소스에 있기 때문이다. 그래서 여기서
    # 봐야 하는 것은 「코드를 못 붙였다」가 아니라 **회차가 통과로 읽히지 않는다**이다.
    assert not [f for f in report.findings if f.kind == "project_code_missing"]


def test_a_value_too_long_is_refused_and_counted(tmp_path, db_url):
    """**반례** — 자르지 않고 거절하며, Exit 조건이 그 수를 본다."""
    source_path = tmp_path / "legacy.sqlite3"
    _write_source(source_path)
    conn = sqlite3.connect(source_path)
    conn.execute(
        "UPDATE ticket_cache SET title = ? WHERE id = ?", ("가" * 900, TICKET_A)
    )
    conn.commit()
    conn.close()

    settings = Settings(
        _env_file=None, app_env="test", database_url=db_url,
        session_secret="test", cookie_secure=False,
        config_dir=Path("config"), secrets_dir=tmp_path / "secrets",
        data_dir=tmp_path / "data",
    )
    (tmp_path / "secrets").mkdir(exist_ok=True)
    engine = make_engine(db_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            report = runner.run(
                session, runner.MigrationOptions(sqlite_path=str(source_path)),
                notion=FakeNotion(), settings=settings,
            )
    finally:
        engine.dispose()

    too_long = [f for f in report.findings if f.kind == "too_long"]
    assert too_long, "900자 제목이 그냥 들어갔다"
    assert all(f.severity == SEVERITY_BLOCKING for f in too_long)
    assert not report.passed, "길이 초과가 있는데 통과로 읽혔다"
    failed = {c.name for c in report.failed_checks}
    assert "변환 실패 (길이)" in failed
