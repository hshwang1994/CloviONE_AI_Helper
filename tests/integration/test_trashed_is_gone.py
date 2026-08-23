"""휴지통에 넣은 티켓은 **없는 것으로 취급된다** (H2).

`_drop_trashed` 가 목록 세 곳에만 걸려 있었다. 그래서 휴지통에 넣은 티켓이:

  * 상세로는 정상적으로 열리고(`GET /api/tickets/{page_id}`),
  * `can_edit` 도 계산돼 **수정·본문 저장·댓글·첨부가 그대로 됐다**,
  * 검색과 ⌘K 에도 보관기간(기본 7일) 내내 계속 나왔다.

사용자에게는 "지웠는데 아직 열리고 고쳐진다" 이고, 그렇게 고친 내용은 보관기간이 끝나면
티켓과 함께 사라진다 — 한 일이 통째로 없어진다.

게시판은 이걸 제대로 한다(`_board_rows` 가 `deleted_at IS NULL` 로 거르고 첨부도 부모가
지워지면 404). 티켓·문서만 빠져 있었다.

**403 이 아니라 404** 다. 403 은 "있지만 당신은 안 된다" 라서 존재를 알려 준다 —
휴지통 항목은 그 사용자에게 없는 것이 맞다(저장소 규칙: 채팅 이미지 서빙,
`get_scoped_user_or_404` 와 같은 관용).
"""

from __future__ import annotations

import pytest

from app.core.models_base import utcnow
from app.org.constants import DEFAULT_ORG_ID
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

PAGE_ID = "page-t900"


@pytest.fixture()
def ticket(db, portal_project) -> TicketCache:
    """지울 티켓 한 건을 **자체 DB 표에 진짜로 넣는다** (S14).

    예전에는 이 자리에 가짜 Notion 서버가 있었다. 소스가 미러이던 동안에는 그 페이크가
    티켓의 유일한 출처였지만, 자체 DB 가 정본이 된 뒤로는 페이크만 두면 티켓이 **처음부터
    없는** 상태가 된다. 그러면 이 파일의 시험 넷이 전부 조용히 통과한다 — 없는 티켓도
    상세·수정·댓글이 404 이고, 없는 티켓은 색인에도 안 들어가기 때문이다. 휴지통이 한 일이
    하나도 없이 초록불이 나는 것이 이 파일에서 가장 나쁜 결과다.

    소속은 조직 공통 프로젝트(`portal_project`)가 든다. 안 주면 `project_link` 가 'missing'
    이라 전역 관리자 말고는 아무에게도 안 보이고, 그러면 「휴지통에 넣어서 안 보인다」와
    「소속이 없어서 안 보인다」를 구별할 수 없다.
    """
    row = TicketCache(
        notion_page_id=PAGE_ID,
        org_id=DEFAULT_ORG_ID,
        notion_ticket_number=900,
        url="https://example.invalid/t900",
        title="지울 티켓",
        status="진행",
        due_date="2026-09-01",
        project_uid=portal_project.id,
        project_link=PROJECT_LINK_OK,
        project_ids="",
        project_names="",
        assignee_notion_ids="",
        synced_at=utcnow(),
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def signed_in(client, ticket, make_user):
    make_user(email="trash@goodmit.co.kr", role="user", display_name="휴지통 확인")
    r = client.post("/login", json={"email": "trash@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["csrf_token"]


def _trash(app, page_id, title="지운 티켓"):
    from datetime import datetime, timezone

    from app.trash.models import TRASH_TICKET, TrashItem
    from app.users.models import User

    with app.state.session_factory() as db:
        uid = db.query(User).first().id
        db.add(TrashItem(
            item_type=TRASH_TICKET, notion_page_id=page_id, title=title,
            url="https://notion/x", deleted_by_user_id=uid, deleted_by_name="테스트",
            deleted_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))
        db.commit()


def test_trashed_ticket_is_not_readable(client, signed_in, app):
    """상세가 열리면 안 된다 — 열리면 `can_edit` 도 계산되고 편집 버튼이 그려진다."""
    assert client.get(f"/api/tickets/{PAGE_ID}").status_code == 200, "넣기 전에는 열려야 한다"

    _trash(app, PAGE_ID)
    r = client.get(f"/api/tickets/{PAGE_ID}")
    assert r.status_code == 404, f"휴지통 티켓이 아직 열린다: {r.status_code} {r.text[:120]}"


def test_trashed_ticket_cannot_be_edited(client, signed_in, app):
    """읽기를 막아도 쓰기가 뚫려 있으면 소용없다 — API 를 직접 부르면 그만이다."""
    _trash(app, PAGE_ID)
    r = client.patch(
        f"/api/tickets/{PAGE_ID}", json={"title": "몰래 수정"},
        headers={"X-CSRF-Token": signed_in},
    )
    assert r.status_code == 404, f"휴지통 티켓이 수정됐다: {r.status_code} {r.text[:120]}"


def test_trashed_ticket_cannot_take_comments(client, signed_in, app):
    _trash(app, PAGE_ID)
    r = client.post(
        f"/api/tickets/{PAGE_ID}/comments", json={"body": "지운 티켓에 댓글"},
        headers={"X-CSRF-Token": signed_in},
    )
    assert r.status_code == 404, f"휴지통 티켓에 댓글이 달렸다: {r.status_code}"


def test_trashed_ticket_disappears_from_the_search_index(client, signed_in, app):
    """색인에서도 빠져야 한다 — 안 그러면 보관기간 내내 검색과 ⌘K 에 계속 나온다."""
    from app.reports.service import load_display_maps
    from app.search import indexer

    _trash(app, PAGE_ID)
    with app.state.session_factory() as db:
        rows, _truncated = indexer._ticket_rows(
            db, app.state.repositories.tickets, load_display_maps(db)
        )
    assert all(r["ref_id"] != PAGE_ID for r in rows), "휴지통 티켓이 색인에 남아 있다"
