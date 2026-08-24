"""사용자 지적 #4 — "티켓 댓글이 정상적으로 표시되지 않는다" 를 **재현**한다 (C2).

qa-contract-change: 이 파일은 미러 동기화 회차(sync_tickets)를 돌려 소프트 프룬을 만들었고 S14 가 그 동기화를 없앴다(D-284). 지키는 성질 셋(사라진 티켓의 댓글·첨부가 살아남는다 · 표시된 티켓은 목록에서 즉시 빠진다 · 유예를 넘기면 CASCADE 로 함께 정리된다)은 그대로 살아 있고 표시하는 주체만 이관 도구로 바뀌었으므로, 동기화 대신 그 도구와 같은 방식으로 행에 표시해서 같은 셋을 확인한다.

## 무엇을 의심했는가

`ticket_comments.ticket_uid` 와 `ticket_attachments.ticket_uid` 는 **`tickets.id`(자체 UUID)**
에 `ondelete="CASCADE"` 로 걸려 있다. 티켓 행이 지워지면 사용자가 쓴 댓글과 올린 첨부가
함께 사라지는데, **그 둘은 소스에 없어서 다시 읽어 와도 안 돌아온다.**

0043 의 답이 소프트 프룬이다: 지우지 않고 `notion_missing_at` 에 표시만 하고, 유예
(14일)를 넘겨도 안 돌아오면 그때 진짜로 지운다.

## 표시하는 사람이 바뀌었다 (S14)

예전에는 동기화 회차가 "이번 응답에서 못 봤다"를 표시했다. 그 회차는 없어졌고
(D-284) 지금 표시하는 것은 **이관 도구**다 — 재실행에서 소스 export 에 없는 미러 티켓을
`app/migration/load.py` 가 같은 칸에 같은 방식으로 찍는다. 지우는 쪽은 안 바뀌었다
(`app/core/retention.py::purge_missing_tickets`, 시간마다 도는 retention 틱).

그래서 이 시험은 이제 **표시된 상태에서 무엇이 일어나는가**를 직접 만든다. 만드는 방법이
한 줄이 되니 오히려 정확해졌다 — 지키는 것은 표시의 효과이지 표시한 사람이 아니다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.tickets.models import TicketAttachment, TicketCache, TicketComment

pytestmark = pytest.mark.regression

NOW = datetime(2026, 8, 6, 9, 0)


def _attach_user_data(db, row, user):
    """그 티켓에 댓글 하나와 첨부 하나를 붙인다(사용자가 만든 데이터)."""
    db.add(TicketComment(
        ticket_uid=row.id, author_user_id=user.id, body="이 댓글이 살아남아야 한다",
    ))
    db.add(TicketAttachment(
        ticket_uid=row.id, filename="증거.png", stored_name="abc.png",
        media_type="image/png", size_bytes=10, uploaded_by_user_id=user.id,
        created_at=NOW,
    ))
    db.flush()
    return row.id


def _counts(db, uid):
    c = len(db.execute(
        select(TicketComment).where(TicketComment.ticket_uid == uid)
    ).scalars().all())
    a = len(db.execute(
        select(TicketAttachment).where(TicketAttachment.ticket_uid == uid)
    ).scalars().all())
    return c, a


def _mark_missing(db, row, *, at=NOW):
    """이관 도구가 하는 그대로 — 지우지 않고 표시만 한다(`app/migration/load.py`)."""
    if row.notion_missing_at is None:
        row.notion_missing_at = at
    db.flush()
    db.expire_all()


def _visible_page_ids(client, db):
    """저장소 읽기 깔때기를 그대로 통과시켜 보이는 티켓 page id 를 모은다."""
    from app.tickets.repository_native import NativeTicketRepository

    repo = NativeTicketRepository(
        settings=client.app.state.settings, outbound=client.app.state.outbound_client
    )
    return {t.page_id for t in repo.list_all(db).tickets}


def test_marking_a_ticket_missing_keeps_its_comments_and_files(
    db, make_user, make_ticket, portal_project
):
    """🔴 **이 시험이 #4 의 답을 못박는다** — 표시는 사용자 데이터를 건드리지 않는다.

    지우면 CASCADE 가 댓글과 첨부를 함께 가져간다. 그 둘은 소스에 없으므로 다시 읽어 와도
    안 돌아온다 — 되돌릴 수 없는 삭제를 "이번 회차에 못 봤다"는 추측 하나로 하게 된다.
    """
    user = make_user(email="cmt-a@goodmit.co.kr", display_name="작성자")
    ticket = make_ticket(page_id="page-ghost", project=portal_project, title="사라질 티켓")
    uid = _attach_user_data(db, ticket, user)
    assert _counts(db, uid) == (1, 1), "표본이 안 붙었다 — 아래 단언이 아무것도 안 본다"

    _mark_missing(db, ticket)

    row = db.get(TicketCache, uid)
    assert row is not None, "표시만 해야 하는데 행이 사라졌다"
    assert row.notion_missing_at is not None
    assert _counts(db, uid) == (1, 1), (
        "표시했더니 댓글·첨부가 사라졌다 — 소스에 없는 데이터라 되돌릴 방법이 없다"
    )


def test_a_missing_ticket_disappears_from_lists_immediately(
    client, db, make_user, make_ticket, portal_project
):
    """사용자에게는 **삭제와 똑같이 보여야** 한다.

    표시만 하고 목록에서 안 빼면 "소스에서 지웠는데 포털엔 그대로" 가 된다 — 그건 고친 게
    아니라 새 결함이다.
    """
    user = make_user(email="cmt-c@goodmit.co.kr", display_name="작성자")
    ticket = make_ticket(page_id="page-ghost", project=portal_project, title="사라질 티켓")
    _attach_user_data(db, ticket, user)
    db.commit()
    assert "page-ghost" in _visible_page_ids(client, db), "표시 전인데 목록에 없다"

    _mark_missing(db, ticket)
    db.commit()

    assert "page-ghost" not in _visible_page_ids(client, db), (
        "사라진 티켓이 목록에 그대로 남아 있다 — 표시만 하고 숨기지 않았다"
    )
    assert db.get(TicketCache, ticket.id) is not None, (
        "행은 살아 있어야 한다(댓글·첨부가 매달려 있다)"
    )


def test_the_grace_period_eventually_deletes_it(db, make_user, make_ticket, portal_project):
    """2주 동안 안 돌아오면 그건 깜빡임이 아니라 삭제다 — 그때는 진짜로 지운다.

    지우는 쪽은 시간마다 도는 retention 틱이다(`worker_main::retention_tick` →
    `run_retention` → `purge_missing_tickets`). 표시하는 사람이 바뀌어도 이 경로는 그대로다.
    """
    from app.core.retention import MISSING_TICKET_GRACE_DAYS, purge_missing_tickets

    user = make_user(email="cmt-d@goodmit.co.kr", display_name="작성자")
    ticket = make_ticket(page_id="page-ghost", project=portal_project, title="사라질 티켓")
    uid = _attach_user_data(db, ticket, user)
    _mark_missing(db, ticket)

    # 유예 안에서는 아무 일도 없다.
    same_day = NOW + timedelta(days=MISSING_TICKET_GRACE_DAYS - 1)
    assert purge_missing_tickets(db, now=same_day) == 0, "유예 안인데 지웠다"
    assert db.get(TicketCache, uid) is not None

    # 유예를 넘기면 지운다. 그리고 자식도 함께 정리된다(의도된 CASCADE).
    later = NOW + timedelta(days=MISSING_TICKET_GRACE_DAYS + 1)
    assert purge_missing_tickets(db, now=later) == 1, "유예를 넘겼는데 안 지웠다"
    db.expire_all()

    assert db.get(TicketCache, uid) is None
    assert _counts(db, uid) == (0, 0), (
        "행은 지웠는데 댓글·첨부가 고아로 남았다 — CASCADE 가 안 걸렸다"
    )


def test_a_ticket_that_was_never_marked_is_never_purged(
    db, make_user, make_ticket, portal_project
):
    """오탐 방지 — 표시 안 된 티켓은 몇 년이 지나도 안 지운다.

    이 단언이 없으면 위 시험은 `purge_missing_tickets` 가 **전부** 지우는 세계에서도
    통과한다.
    """
    from app.core.retention import purge_missing_tickets

    user = make_user(email="cmt-e@goodmit.co.kr", display_name="작성자")
    ticket = make_ticket(page_id="page-alive", project=portal_project, title="멀쩡한 티켓")
    uid = _attach_user_data(db, ticket, user)

    assert purge_missing_tickets(db, now=NOW + timedelta(days=3650)) == 0
    assert db.get(TicketCache, uid) is not None
    assert _counts(db, uid) == (1, 1)
