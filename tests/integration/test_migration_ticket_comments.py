"""Notion 댓글이 **한 건도 안 잃고, 안 늘고, 순서대로** 들어가는가 (S14 · D11).

## 이 단계가 조용히 틀리는 자리 넷

1. **작성자.** `author_user_id` 가 NOT NULL 이라 아무나 골라 적고 싶어지는 자리다.
   그렇게 하면 「이 사람이 이렇게 말했다」가 거짓 기록으로 남고, 화면은 정상으로
   보이기 때문에 아무도 신고하지 않는다.
2. **시각.** 안 옮기면 댓글 324건이 전부 이관한 날 같은 시각에 달린 것이 된다.
3. **순서.** `seq` 는 `GENERATED ALWAYS AS IDENTITY` 라 우리가 정할 수 있는 것은 넣는
   순서 하나다. 그것을 안 정하면 답글이 원글보다 먼저 보인다.
4. **재실행.** 다리를 안 놓으면 두 번 돌릴 때마다 같은 대화가 한 벌씩 더 쌓인다.

표본은 지어내지 않았다 — 내려받아 둔 실제 응답을 `tests/unit/test_migration_comments`
에서 그대로 가져온다.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from app.core.models_base import new_uuid
from app.migration import transform
from app.migration.load import Loader
from app.migration.report import SEVERITY_CLASSIFIED, MigrationReport
from app.notion_mapping.models import STATUS_VERIFIED, UserNotionMapping

from tests.unit.test_migration_comments import (
    ATTACHMENT_ONLY_COMMENT,
    BOT_COMMENT,
    CODE_COMMENT,
    PAGE,
    REPLY_COMMENT,
)

pytestmark = [pytest.mark.integration]

AUTHOR_NOTION_ID = CODE_COMMENT["created_by"]["id"]
BOT_NOTION_ID = BOT_COMMENT["created_by"]["id"]
BOT_PAGE = BOT_COMMENT["parent"]["page_id"]
ATTACHMENT_PAGE = ATTACHMENT_ONLY_COMMENT["parent"]["page_id"]


@pytest.fixture()
def world(db, make_user, make_ticket, portal_project):
    """댓글을 받을 티켓 하나와, 이메일로 이어진 작성자 한 명."""
    author = make_user("seo@goodmit.co.kr", display_name="서윤경")
    db.add(UserNotionMapping(
        id=new_uuid(), user_id=author.id, notion_user_id=AUTHOR_NOTION_ID,
        notion_email=author.email, status=STATUS_VERIFIED, source="migration",
    ))
    db.commit()
    ticket = make_ticket(page_id=PAGE, project=portal_project, title="큐브 결재")
    return author, ticket


def _run(db, settings, comments, *, dry_run=False):
    report = MigrationReport()
    loader = Loader(db, report=report, settings=settings)
    stage = loader.load_ticket_comments(comments, dry_run=dry_run)
    loader.flush_mappings()
    return stage, report


def _rows(db):
    return db.execute(sa.text(
        "SELECT body, author_user_id, created_at, seq FROM ticket_comments "
        "ORDER BY seq"
    )).all()


def _kinds(report) -> list[str]:
    return [f.kind for f in report.findings if f.severity == SEVERITY_CLASSIFIED]


def test_a_thread_lands_in_time_order_with_its_original_time(world, db, settings):
    """🔴 늦게 쓰인 답글을 **먼저 주어도** 시간 순으로 들어가야 한다.

    원본을 시간 순으로 주면 이 시험은 정렬이 없어도 통과한다. 그래서 일부러 뒤집어
    준다 — 실제로 Notion 응답이 늘 시간 순이라는 보장은 어디에도 없다.
    """
    author, ticket = world
    comments = transform.comments_of(PAGE, [REPLY_COMMENT, CODE_COMMENT])
    stage, report = _run(db, settings, comments)

    rows = _rows(db)
    assert stage.inserted == 2
    assert [row.body for row in rows] == [
        transform.parse_comment(CODE_COMMENT).body,
        transform.parse_comment(REPLY_COMMENT).body,
    ], "답글이 원글보다 먼저 들어갔다"
    assert rows[0].seq < rows[1].seq
    assert rows[0].created_at.isoformat() == "2025-09-08T04:17:00"
    assert rows[1].created_at.isoformat() == "2025-11-17T01:19:00"
    assert {row.author_user_id for row in rows} == {author.id}
    owners = {
        row[0] for row in db.execute(
            sa.text("SELECT ticket_uid FROM ticket_comments")
        ).all()
    }
    assert owners == {ticket.id}
    assert "comment_author_unresolved" not in _kinds(report)


def test_running_it_twice_does_not_add_the_same_comment_again(world, db, settings):
    comments = transform.comments_of(PAGE, [CODE_COMMENT, REPLY_COMMENT])
    _run(db, settings, comments)
    before = _rows(db)

    stage, _report = _run(db, settings, comments)
    after = _rows(db)
    assert stage.inserted == 0, "두 번째 회차가 댓글을 또 만들었다"
    assert stage.updated == 2, "이미 옮긴 댓글을 셌다는 사실이 안 남았다"
    assert [(row.body, row.seq) for row in after] == [
        (row.body, row.seq) for row in before
    ]


def test_an_author_we_cannot_resolve_is_classified_never_guessed(
    world, db, settings, make_ticket, portal_project
):
    """🔴 봇 댓글 한 건이 여기 걸린다. 아무나 골라 적으면 거짓 기록이 남는다.

    티켓을 먼저 만든다. 안 만들면 「티켓이 없다」에 먼저 걸려서, 이 시험이 보려던
    작성자 판정에는 닿지도 못한 채 초록이 된다.
    """
    make_ticket(page_id=BOT_PAGE, project=portal_project, title="자동화가 댓글을 단 티켓")
    comments = transform.comments_of(BOT_PAGE, [BOT_COMMENT])
    stage, report = _run(db, settings, comments)
    assert stage.inserted == 0
    assert stage.skipped == 1
    assert _rows(db) == []
    unresolved = [f for f in report.findings if f.kind == "comment_author_unresolved"]
    assert len(unresolved) == 1
    assert unresolved[0].ref == BOT_COMMENT["id"]
    # 사유에 「사람이 아니다」가 읽혀야 다음 사람이 결정할 수 있다.
    assert "integration" in unresolved[0].detail


def test_a_comment_whose_ticket_is_not_here_is_skipped_with_a_reason(db, settings):
    """티켓이 우리 쪽에 없으면 넣을 자리가 없다. 조용히 버리지 않는다."""
    comments = transform.comments_of("page-that-is-not-ours", [CODE_COMMENT])
    stage, report = _run(db, settings, comments)
    assert stage.inserted == 0 and stage.skipped == 1
    assert [f.kind for f in report.findings if f.kind == "comment_ticket_missing"]


def test_a_ticket_without_comments_gets_nothing(world, db, settings):
    """**반례** — 원본에 댓글이 없는 티켓에 아무것도 만들지 않는다."""
    stage, report = _run(db, settings, [])
    assert stage.inserted == 0
    assert _rows(db) == []
    assert not report.findings


def test_a_dry_run_counts_and_writes_nothing(world, db, settings):
    comments = transform.comments_of(PAGE, [CODE_COMMENT, REPLY_COMMENT])
    stage, _report = _run(db, settings, comments, dry_run=True)
    assert stage.inserted == 2, "무엇이 들어갈지 안 세면 미리 볼 것이 없다"
    assert _rows(db) == [], "세기만 하는 회차가 행을 만들었다"
    assert db.execute(sa.text(
        "SELECT count(*) FROM legacy_mapping WHERE target_type = 'comment'"
    )).scalar_one() == 0


def test_a_comment_with_only_a_file_still_carries_who_and_when(
    world, db, settings, make_ticket, portal_project
):
    """글이 없다고 안 넣으면 「누가 언제 무엇을 올렸다」가 통째로 사라진다."""
    make_ticket(page_id=ATTACHMENT_PAGE, project=portal_project, title="그림만 달린 티켓")
    comments = transform.comments_of(ATTACHMENT_PAGE, [ATTACHMENT_ONLY_COMMENT])
    stage, report = _run(db, settings, comments)
    rows = _rows(db)
    assert stage.inserted == 1
    assert rows[0].body == transform.COMMENT_ATTACHMENT_ONLY
    # 파일 자체는 못 옮긴다. 그 사실이 수로 남아야 사람이 결정할 수 있다.
    moved = [f for f in report.findings if f.kind == "comment_attachment_not_moved"]
    assert len(moved) == 1 and "1건" in moved[0].detail


def test_the_bridge_remembers_which_notion_comment_became_which_row(world, db, settings):
    """재실행이 안 늘어나는 **근거**를 직접 잰다."""
    comments = transform.comments_of(PAGE, [CODE_COMMENT])
    _run(db, settings, comments)
    row = db.execute(sa.text(
        "SELECT legacy_source, legacy_source_id, target_type, target_id "
        "FROM legacy_mapping WHERE target_type = 'comment'"
    )).one()
    assert row.legacy_source == "notion"
    assert row.legacy_source_id == CODE_COMMENT["id"]
    assert row.target_id == db.execute(
        sa.text("SELECT id FROM ticket_comments")
    ).scalar_one()
