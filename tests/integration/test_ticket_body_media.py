"""티켓 본문의 이미지가 **실제로 보이는가** (S14 · B2 · D12).

## 왜 이 시험이 따로 있는가

문서 본문의 이미지는 S14 초반에 옮겨졌고 그것을 재는 시험이 이미 있다
(`test_migration_bodies_and_visibility.py`). **티켓만 안 옮겨졌다.** 붙일 자리인
`ticket_attachments.uploaded_by_user_id` 가 NOT NULL 이었고, 이관에는 올린 사람이 없어서
그 222블록이 「못 옮겼다」는 분류된 예외 한 줄로만 남아 있었다.

0014 가 그 칸을 nullable 로 바꿨다(D12). `NULL` 의 뜻은 「이관이 가져왔고 올린 사람이
없다」이고, 그것이 사실이다 — 아무나 골라 적으면 「이 사람이 올렸다」가 거짓 기록으로
남는다. 여기서 재는 것은 그 결정이 실제로 화면까지 닿았는가다.

## `real_db` 인 이유

이관은 단계마다 `commit()` 을 부른다. 되감기 위에서 돌리면 그 커밋이 SAVEPOINT 릴리스가
되어 재실행 검증이 거짓 초록이 된다. Known-Bad 시험은 DDL 도 돌린다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.db import make_engine, make_session_factory
from app.core.uploads import MAX_UPLOAD_BYTES, NS_TICKET, attachment_path
from app.migration import runner
from app.tickets import attachments as ticket_attachments
from app.tickets.models import TicketAttachment

pytestmark = [pytest.mark.integration, pytest.mark.real_db]

ORG = "00000000-0000-0000-0000-000000000001"
USER = "11111111-1111-1111-1111-111111111111"
DEPT = "55555555-5555-5555-5555-555555555555"
PROJECT = "22222222-2222-2222-2222-222222222222"
TICKET_WITH_IMAGE = "33333333-3333-3333-3333-33333333333a"
TICKET_WITH_HUGE = "33333333-3333-3333-3333-33333333333b"
OLD_ATTACHMENT = "66666666-6666-6666-6666-666666666666"

PAGE_PROJECT = "aaaa0000-0000-0000-0000-000000000001"
PAGE_IMAGE = "bbbb0000-0000-0000-0000-0000000000a1"
PAGE_HUGE = "bbbb0000-0000-0000-0000-0000000000a2"

BLOCK_IMAGE = "eeee0000-0000-0000-0000-0000000000f1"
BLOCK_HUGE = "eeee0000-0000-0000-0000-0000000000f2"

# 실측 그대로의 모양이다. 서명 붙은 S3 주소이고 한 시간이면 죽는다 — 본문에 남으면
# 사용자에게는 깨진 그림만 보이고, 깨졌다는 사실은 아무 로그에도 안 남는다.
SIGNED_URL = (
    "https://prod-files-secure.s3.us-west-2.amazonaws.com/2557d037/63e378ab/"
    "screenshot.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600"
)
HUGE_URL = (
    "https://prod-files-secure.s3.us-west-2.amazonaws.com/2557d037/11111111/"
    "capture.png?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Expires=3600"
)

# 매직바이트만 맞으면 `sniff_media_type` 이 PNG 로 읽는다. 바이트 내용은 이 시험의
# 관심사가 아니다 — 관심사는 「그 바이트가 우리 저장소로 갔는가」다.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
# 10MB 상한을 한 바이트 넘긴다. 상한은 제품이 정한 것이고 이관 때문에 넓히지 않는다.
HUGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * MAX_UPLOAD_BYTES


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
        CREATE TABLE ticket_attachments (id TEXT PRIMARY KEY, ticket_uid TEXT,
            uploaded_by_user_id TEXT, filename TEXT, stored_name TEXT,
            media_type TEXT, size_bytes INTEGER, created_at TEXT);
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
    conn.execute(
        "INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (USER, "shim@goodmit.co.kr", "임승환", "user", 1, "x", 0, stamp, stamp,
         ORG, DEPT),
    )
    conn.execute(
        "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?)",
        (PROJECT, "용인 클러스터", None, "active", ORG, PAGE_PROJECT, stamp, stamp,
         None, ""),
    )
    for ticket_id, page_id, title in (
        (TICKET_WITH_IMAGE, PAGE_IMAGE, "화면 캡처가 붙은 티켓"),
        (TICKET_WITH_HUGE, PAGE_HUGE, "너무 큰 파일이 붙은 티켓"),
    ):
        conn.execute(
            "INSERT INTO ticket_cache VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticket_id, page_id, ORG, 100, title, "진행", None, PAGE_PROJECT, "", "",
             None, "notion", stamp, stamp, stamp, None, "unresolved", None, None),
        )
    # 사람이 화면에서 올린 첨부 하나. 이관이 더하는 본문 이미지와 **섞여도 수가 맞는가**를
    # 재려면 소스에 이런 행이 있어야 한다 — 없으면 그 검사가 아무것도 안 세고 통과한다.
    conn.execute(
        "INSERT INTO ticket_attachments VALUES (?,?,?,?,?,?,?,?)",
        (OLD_ATTACHMENT, TICKET_WITH_IMAGE, USER, "명세서.pdf",
         "0123456789abcdef0123456789abcdef.pdf", "application/pdf", 1024, stamp),
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


def _task(page_id: str, title: str) -> dict:
    return {
        "id": page_id, "url": f"https://notion.so/{page_id}",
        "created_time": "2026-01-01T00:00:00.000Z",
        "last_edited_time": "2026-08-20T00:00:00.000Z",
        "properties": {
            "제목": {"type": "title", "title": [_rich(title)]},
            "티켓 ID": {"type": "unique_id",
                        "unique_id": {"prefix": "GIT", "number": 100}},
            "진행상태": {"type": "status", "status": {"name": "진행"}},
            "프로젝트": {"type": "relation", "relation": [{"id": PAGE_PROJECT}]},
            "티켓 담당자": _people("shim@goodmit.co.kr"),
        },
    }


class FakeNotion:
    """조회만 하는 가짜. 실제 응답의 모양을 그대로 흉내 낸다."""

    class Stats:
        def as_dict(self) -> dict:
            return {"api_calls": 0, "fake": True}

    def __init__(self) -> None:
        self.stats = self.Stats()
        self.downloads: list[str] = []

    def discover(self, *, overrides=None) -> dict:
        return {"tasks": "db-tasks", "projects": "db-projects", "documents": "db-docs",
                "doc_types": "db-types", "categories": "db-categories"}

    def query_database(self, database_id: str, *, role: str) -> list[dict]:
        if role == "projects":
            return [{
                "id": PAGE_PROJECT, "last_edited_time": "2026-08-20T00:00:00.000Z",
                "properties": {
                    "프로젝트": {"type": "title", "title": [_rich("용인 클러스터")]},
                    "진행 상태": {"type": "status", "status": {"name": "진행 중"}},
                },
            }]
        if role == "tasks":
            return [
                _task(PAGE_IMAGE, "화면 캡처가 붙은 티켓"),
                _task(PAGE_HUGE, "너무 큰 파일이 붙은 티켓"),
            ]
        return []

    def page_blocks(self, page_id: str, *, last_edited) -> list[dict]:
        if page_id == PAGE_IMAGE:
            # 이미지는 토글 **안**에 둔다. 실측이 그 모양이고, 최상위만 훑는 구현은
            # 여기서 조용히 그림을 잃는다.
            return [
                {"id": f"p-{page_id}", "type": "paragraph",
                 "paragraph": {"rich_text": [_rich("재현 절차는 아래와 같습니다.")]}},
                {"id": "tgl-1", "type": "toggle",
                 "toggle": {"rich_text": [_rich("자세히")]},
                 "_children": [{
                     "id": BLOCK_IMAGE, "type": "image",
                     "image": {"caption": [_rich("오류 화면")], "type": "file",
                               "file": {"url": SIGNED_URL}},
                 }]},
            ]
        if page_id == PAGE_HUGE:
            return [
                {"id": f"p-{page_id}", "type": "paragraph",
                 "paragraph": {"rich_text": [_rich("녹화를 붙였습니다.")]}},
                {"id": BLOCK_HUGE, "type": "image",
                 "image": {"caption": [], "type": "file", "file": {"url": HUGE_URL}}},
            ]
        return []

    def page_comments(self, page_id: str) -> list[dict]:
        return []

    def download(self, url: str) -> bytes:
        self.downloads.append(url)
        return HUGE_BYTES if url == HUGE_URL else PNG_BYTES


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
        yield _run, _reimport, factory, notion, settings
    finally:
        engine.dispose()


def _body(db, page_id: str) -> str:
    return db.execute(sa.text(
        "SELECT coalesce(body_markdown, '') FROM tickets WHERE notion_page_id = :p"
    ), {"p": page_id}).scalar_one()


def _moved(db) -> list[TicketAttachment]:
    """이관이 옮긴 첨부. 올린 사람이 없다는 것이 곧 그 표시다 (D12)."""
    return list(db.execute(
        sa.select(TicketAttachment)
        .where(TicketAttachment.uploaded_by_user_id.is_(None))
    ).scalars())


# ── 옮겨졌는가 ───────────────────────────────────────────────────────────────


def test_a_body_image_lands_as_a_ticket_attachment(migrate):
    """바이트가 우리 저장소에 실제로 있는가. 행만 생기고 파일이 없으면 화면은 404 다."""
    run, _reimport, factory, notion, settings = migrate
    run()
    with factory() as db:
        rows = _moved(db)
    assert len(rows) == 1, f"본문 이미지가 첨부로 안 들어왔다: {len(rows)}건"
    row = rows[0]
    assert row.media_type == "image/png"
    assert row.size_bytes == len(PNG_BYTES)
    path = attachment_path(
        settings.data_dir, row.ticket_uid, row.stored_name, namespace=NS_TICKET
    )
    assert path is not None and path.read_bytes() == PNG_BYTES, "바이트가 디스크에 없다"
    assert SIGNED_URL in notion.downloads, "바이트를 안 받았다"


def test_the_body_points_at_our_endpoint_not_at_notion(migrate):
    """서명 주소는 한 시간이면 죽는다. 본문에 남기면 깨진 그림만 남는다 (D4)."""
    run, _reimport, factory, _notion, _settings = migrate
    run()
    with factory() as db:
        body = _body(db, PAGE_IMAGE)
        attachment_id = _moved(db)[0].id
    assert f"/api/tickets/attachments/{attachment_id}" in body, body
    assert "prod-files-secure" not in body, "본문에 Notion 서명 주소가 남았다"
    assert "![오류 화면]" in body, "캡션이 사라졌다"


def test_the_uploader_is_null_because_the_migration_has_none(migrate):
    """🔴 D12 그 자체. 아무나 골라 적으면 「이 사람이 올렸다」가 거짓 기록이 된다."""
    run, _reimport, factory, _notion, _settings = migrate
    run()
    with factory() as db:
        rows = _moved(db)
        everyone_else = db.execute(sa.text(
            "SELECT count(*) FROM ticket_attachments "
            "WHERE uploaded_by_user_id IS NOT NULL"
        )).scalar_one()
    assert rows and rows[0].uploaded_by_user_id is None
    # 소스에서 온 첨부는 올린 사람을 그대로 갖는다. 이관이 그 값을 지우지 않는다.
    assert everyone_else == 1


def test_the_attachment_list_survives_an_uploader_that_is_null(migrate):
    """🔴 화면이 읽는 목록이 **NULL 올린이에 안 터지는가**.

    칸을 nullable 로 바꾸면 그 값을 읽는 자리가 전부 후보가 된다. 그중 사람이 실제로
    보는 것은 첨부 목록이고, 거기서 터지면 티켓 상세가 통째로 안 열린다. 이름이 빈
    문자열로 나오는 것은 사실 그대로다 — 올린 사람이 없으니 적을 이름도 없다.
    """
    run, _reimport, factory, _notion, _settings = migrate
    run()
    with factory() as db:
        ticket_uid = db.execute(sa.text(
            "SELECT id FROM tickets WHERE notion_page_id = :p"
        ), {"p": PAGE_IMAGE}).scalar_one()
        views = ticket_attachments.attachment_views(db, ticket_uid=ticket_uid)
    moved = [view for view in views if view["uploaded_by_user_id"] is None]
    assert len(moved) == 1, views
    assert moved[0]["uploaded_by_name"] == ""
    assert moved[0]["url"] == f"/api/tickets/attachments/{moved[0]['id']}"
    # 사람이 올린 첨부의 이름은 그대로 나온다.
    mine = [view for view in views if view["uploaded_by_user_id"] == USER]
    assert mine and mine[0]["uploaded_by_name"] == "임승환"


def test_the_old_not_moved_exception_is_gone(migrate):
    """「올린 사람을 몰라 못 옮겼다」는 이제 참이 아니다. 참이 아닌 예외는 걷는다."""
    run, _reimport, _factory, _notion, _settings = migrate
    report = run()
    kinds = [f.kind for f in report.findings]
    assert "ticket_body_media_not_moved" not in kinds, kinds


# ── 규약을 넘지 않는다 ───────────────────────────────────────────────────────


def test_a_file_over_the_limit_stays_an_exception_and_the_body_says_so(migrate):
    """10MB 상한은 제품이 정한 것이라 이관 때문에 넓히지 않는다.

    대신 **두 가지를 남긴다**: 분류된 예외 한 줄과, 본문에 사람이 읽는 문장 하나.
    조용히 사라지면 「그 자리에 그림이 있었다」는 사실까지 없어진다.
    """
    run, _reimport, factory, _notion, _settings = migrate
    report = run()
    rejected = [f for f in report.findings if f.kind == "body_media_rejected"]
    assert len(rejected) == 1, [f.line() for f in report.findings]
    assert rejected[0].severity == "classified"
    with factory() as db:
        body = _body(db, PAGE_HUGE)
        rows = _moved(db)
    assert "원본에만 있는 이미지입니다." in body, body
    assert "prod-files-secure" not in body
    assert len(rows) == 1, "상한을 넘은 파일이 저장됐다"


# ── 두 번 돌려도 같다 ────────────────────────────────────────────────────────


def test_running_twice_does_not_pile_up_attachments(migrate):
    """재실행 멱등. 같은 이미지를 두 번 받지도, 두 줄로 붙이지도 않는다."""
    run, _reimport, factory, notion, _settings = migrate
    run()
    with factory() as db:
        first = (
            db.execute(sa.text("SELECT count(*) FROM ticket_attachments")).scalar_one(),
            _body(db, PAGE_IMAGE),
        )
    run()
    with factory() as db:
        second = (
            db.execute(sa.text("SELECT count(*) FROM ticket_attachments")).scalar_one(),
            _body(db, PAGE_IMAGE),
        )
    assert first == second, f"{first[0]} → {second[0]}"
    assert notion.downloads.count(SIGNED_URL) == 1, "같은 이미지를 다시 받았다"


def test_the_counts_still_line_up_when_the_migration_adds_rows(migrate):
    """수 대조가 「본문 이미지를 옮겼다」는 이유로 빨간불이 되면 안 된다.

    이관이 `ticket_attachments` 에 **행을 더한다.** 소스에서 온 행만 골라 세지 않으면
    성공이 실패로 읽히고, 그 다음에 일어나는 일은 검사를 지우는 것이다.
    """
    run, _reimport, _factory, _notion, _settings = migrate
    report = run()
    assert not report.failed_checks, [c.line() for c in report.failed_checks]


# ── 재이관 경로 (D5) ─────────────────────────────────────────────────────────


def test_reimport_moves_a_body_image_the_first_pass_left_behind(migrate):
    """파일 없이 돌린 회차가 남긴 자리를 **본문만 다시 넣기**가 채운다.

    운영이 지금 그 상태다 — 본문에는 자리 문장이 있고 첨부는 없다. 고치는 길이
    `migrate_cli reimport-bodies` 이고, 그 길이 실제로 이미지를 옮기는지 여기서 잰다.
    """
    run, reimport, factory, _notion, _settings = migrate
    run(with_files=False)
    with factory() as db:
        assert "원본에만 있는 이미지입니다." in _body(db, PAGE_IMAGE)
        assert not _moved(db)
    reimport()
    with factory() as db:
        body = _body(db, PAGE_IMAGE)
        rows = _moved(db)
    assert len(rows) == 1
    assert f"/api/tickets/attachments/{rows[0].id}" in body
    assert "원본에만 있는 이미지입니다." not in body


def test_reimport_dry_run_moves_nothing(migrate):
    """세는 회차가 바이트를 받거나 첨부를 만들면 그것은 세는 것이 아니라 쓰는 것이다."""
    run, reimport, factory, notion, _settings = migrate
    run(with_files=False)
    downloads = len(notion.downloads)
    reimport(dry_run=True)
    with factory() as db:
        assert not _moved(db), "세기만 하는 회차가 첨부를 만들었다"
        assert "원본에만 있는 이미지입니다." in _body(db, PAGE_IMAGE)
    assert len(notion.downloads) == downloads, "세기만 하는 회차가 바이트를 받았다"


# ── Known-Bad ────────────────────────────────────────────────────────────────


def test_the_column_is_nullable_in_the_migrated_database(migrate):
    """모델과 0014 가 같은 것을 말하는가. 모델만 바꾸면 운영은 그대로 NOT NULL 이다."""
    _run, _reimport, factory, _notion, _settings = migrate
    with factory() as db:
        columns = {
            column["name"]: column
            for column in sa.inspect(db.get_bind()).get_columns("ticket_attachments")
        }
    assert columns["uploaded_by_user_id"]["nullable"] is True


def test_a_not_null_uploader_would_actually_stop_the_load(migrate):
    """Known-Bad — nullable 을 되돌리면 적재가 **실제로 멈추는가**.

    이 시험이 없으면 위의 초록이 「고쳐서 통과」인지 「원래부터 통과」인지 모른다.
    제약을 되돌려 놓고 같은 회차를 돌리면 본문 이미지를 넣는 그 자리에서 죽어야 한다.
    """
    run, _reimport, factory, _notion, _settings = migrate
    with factory() as db:
        db.execute(sa.text(
            "ALTER TABLE ticket_attachments "
            "ALTER COLUMN uploaded_by_user_id SET NOT NULL"
        ))
        db.commit()
    with pytest.raises(IntegrityError):
        run()
