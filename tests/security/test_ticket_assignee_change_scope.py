"""범위 안의 티켓은 담당자가 아니어도 고칠 수 있다.

담당은 「누가 그 일을 하는가」이지 「누가 고칠 수 있는가」가 아니다. 제목·상태·본문·
담당자가 같은 문을 지난다. 바꾼 내용은 감사 이력에 남는다.

막혀 있는 것은 두 가지다.

  · 범위 밖 티켓 → 404. 이 문은 편집 판정 **앞에** 산다
  · 감사자 → 읽기 전용. 「가져가기」 단추로 남의 일을 한 번에 가져오는 것도 별도 문이다

마지막 줄이 이 파일의 절반이다. 편집을 범위 문 앞에 두면 남의 부서 티켓을 id 하나로
고칠 수 있게 되는데, 그 사고는 목록에 아무 흔적을 안 남긴다.
"""

from __future__ import annotations

import pytest

from app.core.errors import ForbiddenError
from app.core.models_base import join_names
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from app.tickets.repository import TicketDTO
from app.tickets.service import ensure_can_edit
from tests.fixtures.org_tree import D_A1, D_B1, org_tree, people  # noqa: F401

pytestmark = pytest.mark.security


def _ticket(*, assignees: list[str]) -> TicketDTO:
    return TicketDTO(page_id="page-1", title="남의 티켓", assignee_ids=tuple(assignees))


ASSIGNEE_ONLY = {"assignee_user_ids": ["someone"]}
WITH_OTHER_FIELD = {"assignee_user_ids": ["someone"], "title": "제목까지 바꾼다"}


def test_a_bystander_can_hand_the_ticket_to_someone(people):  # noqa: F811
    """담당자만 바꾸는 요청도 범위 안이면 통과한다."""
    ticket = _ticket(assignees=["someone-elses-token"])
    ensure_can_edit(ticket, people["a1"], "my-token", changes=ASSIGNEE_ONLY)


def test_a_bystander_can_edit_any_other_field(people):  # noqa: F811
    """🔴 **이 한 줄이 이 파일의 이유다.** 고치기 전에는 여기서 403 이 났다.

    담당은 소유가 아니다. 제목·상태를 함께 보내도 범위 안이면 통과한다.
    """
    ticket = _ticket(assignees=["someone-elses-token"])
    ensure_can_edit(ticket, people["a1"], "my-token", changes=WITH_OTHER_FIELD)


def test_body_and_attachment_paths_are_the_same_gate(people):  # noqa: F811
    """`changes` 를 안 주는 호출부(본문·첨부)도 같은 문이다 — 담당자가 아니어도 통과."""
    ticket = _ticket(assignees=["someone-elses-token"])
    ensure_can_edit(ticket, people["a1"], "my-token")


def test_my_own_and_unassigned_tickets_still_open(people):  # noqa: F811
    """반례 둘 — 예전에 되던 것이 그대로 된다."""
    ensure_can_edit(_ticket(assignees=[]), people["a1"], "my-token", changes=WITH_OTHER_FIELD)
    ensure_can_edit(_ticket(assignees=["my-token"]), people["a1"], "my-token", changes=WITH_OTHER_FIELD)


def test_an_auditor_cannot_edit_even_in_scope(make_user):
    """감사자는 읽기 전용이다. 미할당이어도 고치지 못한다."""
    auditor = make_user(email="ticket-auditor@goodmit.co.kr", role="auditor",
                        display_name="감사")
    with pytest.raises(ForbiddenError):
        ensure_can_edit(_ticket(assignees=[]), auditor, "tok")


@pytest.fixture()
def their_ticket(db, people, make_project):  # noqa: F811
    """남의 부서 프로젝트에 달린 티켓 하나. API 가 부르는 이름을 돌려준다."""
    their_project = make_project(name="남의 프로젝트", dept=D_B1)
    row = TicketCache(
        notion_page_id=None,
        title="남의 부서 티켓",
        status="진행",
        project_uid=their_project.id,
        project_link=PROJECT_LINK_OK,
        assignee_notion_ids=join_names([]),
        source="native",
    )
    db.add(row)
    db.flush()
    db.commit()
    return row.id


def test_the_exception_lives_behind_the_scope_gate(db, people, their_ticket):  # noqa: F811
    """🔴 **범위 밖은 여전히 없는 티켓이다.**

    편집이 범위 문 앞에 서면 남의 부서 티켓을 id 하나로 고칠 수 있게 된다.
    그 사고는 목록에 아무 흔적을 안 남긴다 — 그 티켓은 애초에 이 사람 목록에 없다.
    """
    from app.core.errors import NotFoundError
    from app.tickets import service

    with pytest.raises(NotFoundError):
        service.ensure_in_scope(db, their_ticket, people["a1"])


def test_my_own_project_ticket_is_in_scope(db, people, make_project):  # noqa: F811
    """반례 — 범위 문이 막기만 하면 그것은 보안이 아니라 고장이다."""
    from app.tickets import service

    mine = make_project(name="우리 프로젝트", dept=D_A1)
    row = TicketCache(
        notion_page_id=None, title="우리 티켓", status="진행",
        project_uid=mine.id, project_link=PROJECT_LINK_OK,
        assignee_notion_ids=join_names([]), source="native",
    )
    db.add(row)
    db.flush()
    db.commit()
    service.ensure_in_scope(db, row.id, people["a1"])
