"""사용자 지적 #4 — "티켓 댓글이 정상적으로 표시되지 않는다" 를 **재현**한다 (C2).

## 무엇을 의심하는가

`ticket_comments.ticket_uid` 와 `ticket_attachments.ticket_uid` 는 **`ticket_cache.id`(자체 UUID)**
에 `ondelete="CASCADE"` 로 걸려 있다. 그런데 `sync._upsert` 는 캐시 행이 없으면
`TicketCache(...)` 를 새로 만들고, 그 `id` 는 `uuid4` 다 — 즉 **같은 Notion 페이지인데
재생성될 때마다 내부 id 가 바뀐다**(계획서 C2).

그래서 두 가지를 각각 확인한다. 둘은 **다른 사건**이고 고치는 방법도 다르다:

1. **동기화가 그냥 한 번 더 돌면** 댓글이 살아남는가?
   (`_upsert` 는 기존 행을 찾아 갱신하므로 살아야 한다 — 안 살면 훨씬 큰 문제다)
2. **티켓이 한 라운드 Notion 응답에서 빠졌다가 돌아오면** 어떻게 되는가?
   prune 이 캐시 행을 지우면 **CASCADE 가 댓글·첨부를 함께 지운다.** 그러면 결정적 id 를
   준다 한들 되살아날 것이 남아 있지 않다 — **id 안정화만으로는 부족하다**는 뜻이다.

이 테스트는 고치기 전에 **사실을 기록**하기 위한 것이다. 추정으로 마이그레이션을 쓰지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.tickets.models import TicketAttachment, TicketCache, TicketComment
from tests.fakes.notion import DEFAULT_PROJECTS_DB, FakeNotionTasksDB, project_row, task_row

pytestmark = pytest.mark.regression

TOKEN_REF = "notion_report_token"
KEEP = "page-keep"          # 늘 Notion 응답에 있는 티켓
GHOST = "page-ghost"        # 한 라운드 빠졌다가 돌아오는 티켓


def _rows(include_ghost: bool):
    """비율 가드(`MAX_DROP_RATIO`)에 걸리지 않도록 넉넉히 채운다.

    한두 건만 두면 한 건이 빠져도 낙폭이 50% 를 넘어 prune 이 **거부**된다 —
    그러면 이 테스트가 재현하려는 상황 자체가 일어나지 않는다.
    """
    rows = [task_row(page_id=f"page-f{i:03d}", tid=100 + i, title=f"채움{i}",
                     status="진행", due="2026-09-01", people=[]) for i in range(20)]
    rows.append(task_row(page_id=KEEP, tid=501, title="남는 티켓",
                         status="진행", due="2026-09-01", people=[]))
    if include_ghost:
        rows.append(task_row(page_id=GHOST, tid=502, title="사라졌다 오는 티켓",
                             status="진행", due="2026-09-01", people=[]))
    return rows


@pytest.fixture()
def notion(fake_http) -> FakeNotionTasksDB:
    return FakeNotionTasksDB(
        rows=_rows(include_ghost=True),
        projects=[project_row(page_id="proj-1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)


@pytest.fixture()
def synced(client, settings, notion, db):
    """토큰을 두고 한 번 동기화해 캐시를 채운다."""
    (settings.secrets_dir / TOKEN_REF).write_text("fake-token", encoding="utf-8")
    _sync(client, db)
    return notion


def _sync(client, db):
    from app.tickets.sync import sync_tickets

    state = sync_tickets(
        db,
        outbound=client.app.state.outbound_client,
        settings=client.app.state.settings,
        now=datetime(2026, 8, 6, 9, 0, 0),
    )
    db.commit()
    return state


def _row(db, page_id):
    return db.execute(
        select(TicketCache).where(TicketCache.notion_page_id == page_id)
    ).scalar_one_or_none()


def _attach_user_data(db, page_id, user):
    """그 티켓에 댓글 하나와 첨부 하나를 붙인다(사용자가 만든 데이터)."""
    row = _row(db, page_id)
    assert row is not None, f"{page_id} 가 캐시에 없다 — 동기화가 안 됐다"
    db.add(TicketComment(
        ticket_uid=row.id, author_user_id=user.id, body="이 댓글이 살아남아야 한다",
    ))
    db.add(TicketAttachment(
        ticket_uid=row.id, filename="증거.png", stored_name="abc.png",
        media_type="image/png", size_bytes=10, uploaded_by_user_id=user.id,
        created_at=datetime(2026, 8, 6, 9, 0),
    ))
    db.commit()
    return row.id


def _counts(db, page_id):
    row = _row(db, page_id)
    if row is None:
        return None, 0, 0
    c = len(db.execute(
        select(TicketComment).where(TicketComment.ticket_uid == row.id)
    ).scalars().all())
    a = len(db.execute(
        select(TicketAttachment).where(TicketAttachment.ticket_uid == row.id)
    ).scalars().all())
    return row.id, c, a


def test_a_plain_resync_keeps_comments(client, db, make_user, synced):
    """평범한 재동기화로 댓글이 사라지면 그건 훨씬 큰 문제다 — 먼저 이것부터 확인한다."""
    user = make_user("cmt-a@goodmit.co.kr", role="user", display_name="작성자")
    db.commit()
    uid_before = _attach_user_data(db, KEEP, user)

    _sync(client, db)
    db.expire_all()

    uid_after, comments, attachments = _counts(db, KEEP)
    assert uid_after == uid_before, (
        f"재동기화가 캐시 행의 자체 UUID 를 바꿨다: {uid_before} → {uid_after}"
    )
    assert comments == 1, "평범한 재동기화로 댓글이 사라졌다"
    assert attachments == 1, "평범한 재동기화로 첨부가 사라졌다"


def test_what_happens_when_a_ticket_vanishes_for_one_round(
    client, db, make_user, synced, fake_http
):
    """🔴 **이 테스트가 #4 의 정체를 기록한다.**

    티켓이 Notion 응답에서 한 라운드 빠지면(페이지네이션 흔들림·필터·일시 권한 문제)
    prune 이 캐시 행을 지우고 **CASCADE 가 댓글·첨부를 함께 지운다.**
    그 뒤 티켓이 돌아와도 **되살아날 것이 남아 있지 않다.**

    → 그래서 `ticket_cache.id` 를 결정적으로 만드는 것**만으로는 부족하다.**
      prune 이 사용자 데이터를 파괴하지 않게 하는 것이 먼저다.
    """
    user = make_user("cmt-b@goodmit.co.kr", role="user", display_name="작성자")
    db.commit()
    uid_before = _attach_user_data(db, GHOST, user)

    # 한 라운드 사라진다.
    FakeNotionTasksDB(
        rows=_rows(include_ghost=False),
        projects=[project_row(page_id="proj-1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)
    state = _sync(client, db)
    db.expire_all()

    gone_row = _row(db, GHOST)
    orphan_comments = len(db.execute(
        select(TicketComment).where(TicketComment.ticket_uid == uid_before)
    ).scalars().all())
    orphan_attachments = len(db.execute(
        select(TicketAttachment).where(TicketAttachment.ticket_uid == uid_before)
    ).scalars().all())

    # 돌아온다.
    FakeNotionTasksDB(
        rows=_rows(include_ghost=True),
        projects=[project_row(page_id="proj-1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)
    _sync(client, db)
    db.expire_all()
    uid_after, comments_after, attachments_after = _counts(db, GHOST)

    print(
        "\n=== #4 재현 결과 ==="
        f"\n  sync 상태          : {state.status} / error={state.error!r}"
        f"\n  사라진 라운드 뒤    : 캐시행={'없음' if gone_row is None else '있음'}"
        f" 댓글={orphan_comments} 첨부={orphan_attachments}"
        f"\n  돌아온 뒤 uid      : {uid_before} → {uid_after}"
        f"\n  돌아온 뒤 댓글/첨부 : {comments_after} / {attachments_after}"
    )

    # 이 테스트는 '고쳐졌다' 를 주장하지 않는다 — **지금 무엇이 일어나는지**를 못박는다.
    # 고친 뒤 이 단언을 '살아남는다' 로 뒤집고, 그때 RED 를 확인한다.
    assert comments_after == 1, (
        "티켓이 한 라운드 사라졌다 돌아오니 댓글이 없다 — 사용자 지적 #4 의 정체.\n"
        f"  캐시행 삭제됨={gone_row is None}, 고아 댓글={orphan_comments}, "
        f"uid {uid_before} → {uid_after}"
    )
    assert attachments_after == 1, "같은 이유로 첨부도 사라졌다"


# ---------------------------------------------------------------------------
# 소프트 프룬이 **숨기기까지** 해야 한다 — 안 그러면 지워진 티켓이 화면에 남는다
# ---------------------------------------------------------------------------


def _list_page_ids(client, db):
    """저장소 읽기 깔때기를 그대로 통과시켜 보이는 티켓 page id 를 모은다."""
    from app.tickets.repository_notion import NotionTicketRepository

    repo = NotionTicketRepository(
        outbound=client.app.state.outbound_client, settings=client.app.state.settings
    )
    return {t.page_id for t in repo.list_all(db).tickets}


def test_a_missing_ticket_disappears_from_lists_immediately(
    client, db, make_user, synced, fake_http
):
    """사용자에게는 **삭제와 똑같이 보여야** 한다.

    표시만 하고 목록에서 안 빼면 "Notion 에서 지웠는데 포털엔 그대로" 가 된다 —
    그건 고친 게 아니라 새 결함이다.
    """
    user = make_user("cmt-c@goodmit.co.kr", role="user", display_name="작성자")
    db.commit()
    _attach_user_data(db, GHOST, user)
    assert GHOST in _list_page_ids(client, db), "사라지기 전인데 목록에 없다"

    FakeNotionTasksDB(
        rows=_rows(include_ghost=False),
        projects=[project_row(page_id="proj-1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)
    _sync(client, db)
    db.expire_all()

    assert GHOST not in _list_page_ids(client, db), (
        "Notion 에서 사라진 티켓이 목록에 그대로 남아 있다 — 표시만 하고 숨기지 않았다"
    )
    assert _row(db, GHOST) is not None, "행은 살아 있어야 한다(댓글·첨부가 매달려 있다)"


def test_the_grace_period_eventually_deletes_it(client, db, make_user, synced, fake_http):
    """2주 동안 안 돌아오면 그건 깜빡임이 아니라 삭제다 — 그때는 진짜로 지운다."""
    from app.core.retention import MISSING_TICKET_GRACE_DAYS, purge_missing_tickets

    user = make_user("cmt-d@goodmit.co.kr", role="user", display_name="작성자")
    db.commit()
    uid = _attach_user_data(db, GHOST, user)

    FakeNotionTasksDB(
        rows=_rows(include_ghost=False),
        projects=[project_row(page_id="proj-1", name="알파")],
        projects_db=DEFAULT_PROJECTS_DB,
    ).install(fake_http)
    _sync(client, db)
    db.expire_all()

    # 유예 안에서는 아무 일도 없다.
    same_day = datetime(2026, 8, 6, 9, 0) + timedelta(days=MISSING_TICKET_GRACE_DAYS - 1)
    assert purge_missing_tickets(db, now=same_day) == 0, "유예 안인데 지웠다"
    db.commit()
    assert _row(db, GHOST) is not None

    # 유예를 넘기면 지운다. 그리고 자식도 함께 정리된다(의도된 CASCADE).
    later = datetime(2026, 8, 6, 9, 0) + timedelta(days=MISSING_TICKET_GRACE_DAYS + 1)
    assert purge_missing_tickets(db, now=later) == 1, "유예를 넘겼는데 안 지웠다"
    db.commit()
    db.expire_all()

    assert _row(db, GHOST) is None
    left = db.execute(
        select(TicketComment).where(TicketComment.ticket_uid == uid)
    ).scalars().all()
    assert left == [], "행은 지웠는데 댓글이 고아로 남았다 — CASCADE 가 안 걸렸다"
