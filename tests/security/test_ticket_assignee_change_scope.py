"""담당자는 **범위 안 누구나** 바꿀 수 있다 — 그리고 그것이 다른 칸을 열지 않는다 (지시 11).

## 무엇이 문제였나

일반 사용자는 「본인 담당이거나 미할당인 티켓」만 편집할 수 있었다. 그래서 「이 일은 제가
할게요」도, 「이건 김OO 씨 일이에요」도 운영자를 불러야 했다 — 팀이 매일 하는 말이 매번
관리 요청이 되면 담당자 칸은 결국 비어 있게 된다.

## 넓힌 것과 안 넓힌 것

넓어진 것은 **누가 바꾸는가** 하나다.

  · 담당자만 바꾸는 요청 → 그 티켓의 프로젝트가 보이면 누구나 할 수 있다
  · 다른 칸이 하나라도 섞이면 → 예전 규칙 그대로다(담당자 또는 미할당만)
  · 범위 밖 티켓 → 예전처럼 404 다. 이 예외는 범위 문 **뒤에** 산다

마지막 줄이 이 파일의 절반이다. 「담당자는 누구나」를 범위 문 앞에 두면 남의 부서 티켓의
담당자를 id 하나로 바꿀 수 있게 되는데, 그 사고는 목록에 아무 흔적을 안 남긴다.
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
    """🔴 **이 한 줄이 이 파일의 이유다.** 고치기 전에는 여기서 403 이 났다."""
    ticket = _ticket(assignees=["someone-elses-token"])
    # 예외가 없다 = 통과다. 담당자도 아니고 미할당도 아닌 티켓인데 담당자만 바꾼다.
    ensure_can_edit(ticket, people["a1"], "my-token", changes=ASSIGNEE_ONLY)


def test_that_exception_does_not_open_any_other_field(people):  # noqa: F811
    """**반례.** 담당자를 함께 보내는 것만으로 아무 칸이나 열리면 안 된다.

    이것이 없으면 위 시험은 「담당자를 실으면 통과」까지만 증명하고, 실제로는 제목·상태·
    마감을 남의 티켓에서 고치는 길이 열린 채로 초록이 뜬다.
    """
    ticket = _ticket(assignees=["someone-elses-token"])
    with pytest.raises(ForbiddenError):
        ensure_can_edit(ticket, people["a1"], "my-token", changes=WITH_OTHER_FIELD)


def test_the_old_rule_is_unchanged_when_nobody_says_what_changes(people):  # noqa: F811
    """`changes` 를 안 주는 호출부(본문·첨부·댓글 경로)는 예전과 똑같다 — 회귀 0."""
    ticket = _ticket(assignees=["someone-elses-token"])
    with pytest.raises(ForbiddenError):
        ensure_can_edit(ticket, people["a1"], "my-token")


def test_my_own_and_unassigned_tickets_still_open(people):  # noqa: F811
    """반례 둘 — 예전에 되던 것이 그대로 된다."""
    ensure_can_edit(_ticket(assignees=[]), people["a1"], "my-token", changes=WITH_OTHER_FIELD)
    ensure_can_edit(_ticket(assignees=["my-token"]), people["a1"], "my-token", changes=WITH_OTHER_FIELD)


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

    담당자 예외가 범위 문 앞에 서면 남의 부서 티켓의 담당자를 id 하나로 바꿀 수 있게 된다.
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
