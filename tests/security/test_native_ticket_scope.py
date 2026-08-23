"""🔴 **자체 DB 에서 만든 티켓도 범위 문을 지난다** (S14).

## 어떻게 열릴 뻔했나

범위 문(`app/tickets/service.py::ensure_in_scope`)은 「행을 못 찾으면 통과」한다. 그 판단은
옳다 — 판정할 근거가 없는 것이지 범위 밖인 것이 아니고, 막 만든 티켓이 자기 눈에 안 보이면
그것도 고장이다.

문제는 **행을 어떻게 찾는가**였다. 그 조회는 `notion_page_id` 하나만 봤고, 자체 DB 에서 만든
티켓은 그 칸이 NULL 이다(API 가 부르는 `page_id` 는 행의 uuid 다). 그래서 조회가 아무 행도
못 찾고 → 「근거 없음」으로 읽혀 → **범위 문을 통째로 지나간다.** 0060 이 담당자 축을 버리고
닫은 바로 그 구멍이, 소스를 바꾸자 새 티켓에서 다시 열린 것이다.

증상이 「어떤 티켓만 아무에게나 보인다」라서 아무도 신고하지 않는다. 그래서 이 파일은
**두 축을 나란히 놓고** 본다 — 이관해 온 티켓(`notion_page_id`)과 자체 DB 티켓(uuid)이
같은 답을 내야 한다. 한 축만 시험하면 그 축만 고쳐 놓고 초록을 볼 수 있다.

## 반례가 절반이다

「남의 티켓이 404 다」만 보면, 그 404 가 범위 문이 낸 것인지 **애초에 티켓이 없어서** 난
것인지 구별되지 않는다. 그래서 같은 뷰어가 자기 프로젝트의 티켓은 **200 으로 연다**는 것을
함께 본다. 그 둘이 같이 있어야 문이 실제로 판정하고 있다는 뜻이 된다.
"""

from __future__ import annotations

import pytest

from app.core.models_base import join_names
from app.tickets.models import PROJECT_LINK_OK, TicketCache
from tests.fixtures.org_tree import D_A1, D_B1, org_tree, people  # noqa: F401

pytestmark = pytest.mark.security


@pytest.fixture()
def world(db, people, make_project):   # noqa: F811 — org_tree 픽스처를 그대로 쓴다
    """부서 둘, 프로젝트 둘, 그리고 각 프로젝트에 **두 모양의 티켓**을 심는다.

    두 모양은 이관해 온 티켓(`notion_page_id` 가 있다)과 자체 DB 에서 만든 티켓
    (`notion_page_id` 가 NULL 이고 API 가 부르는 이름이 행의 uuid 다)이다.

    부서 세계는 `tests/fixtures/org_tree.py` 를 그대로 쓴다 — 범위 판정의 세계를 여기서
    새로 지으면 그 세계가 제품의 실제 계층과 갈라지고, 갈라진 세계 위의 초록은 뜻이 없다.
    """
    viewer = people["a1"]
    our_project = make_project(name="우리 프로젝트", dept=D_A1)
    their_project = make_project(name="남의 프로젝트", dept=D_B1)

    rows = {}
    for label, project, page_id in (
        ("ours_migrated", our_project, "page-ours"),
        ("theirs_migrated", their_project, "page-theirs"),
        ("ours_native", our_project, None),
        ("theirs_native", their_project, None),
    ):
        row = TicketCache(
            notion_page_id=page_id,
            title=f"{label} 티켓",
            status="진행",
            project_uid=project.id,
            project_link=PROJECT_LINK_OK,
            assignee_notion_ids=join_names([]),
            source="notion" if page_id else "native",
        )
        db.add(row)
        db.flush()
        # API 가 부르는 이름. 저장소 구현체의 식별자 규약과 **같은 식**이다.
        rows[label] = row.notion_page_id or row.id
    db.commit()
    return {"viewer": viewer, "ids": rows}


def _visible(db, page_id: str, viewer) -> bool:
    from app.core.errors import NotFoundError
    from app.tickets import service

    try:
        service.ensure_in_scope(db, page_id, viewer)
    except NotFoundError:
        return False
    return True


def test_a_native_ticket_outside_my_scope_is_refused(db, world):
    """**이 한 줄이 이 파일의 이유다.** 고치기 전에는 이 단언이 통과했다(문이 안 걸렸다)."""
    assert not _visible(db, world["ids"]["theirs_native"], world["viewer"])


def test_a_migrated_ticket_outside_my_scope_is_refused(db, world):
    """옛 축도 그대로 막힌다 — 고치면서 반대쪽을 깨지 않았다."""
    assert not _visible(db, world["ids"]["theirs_migrated"], world["viewer"])


def test_both_shapes_of_my_own_ticket_still_open(db, world):
    """**반례.** 이것이 없으면 위 둘은 「전부 막는다」로도 통과한다.

    범위 문이 막기만 하면 그것은 보안이 아니라 고장이다 — 목록에는 보이는데 누르면
    없다고 하는 화면이 된다.
    """
    assert _visible(db, world["ids"]["ours_migrated"], world["viewer"])
    assert _visible(db, world["ids"]["ours_native"], world["viewer"])


def test_an_unknown_id_is_not_judged(db, world):
    """행이 없으면 통과다 — 판정할 근거가 없는 것이지 범위 밖인 것이 아니다.

    이 성질을 함께 못박아 두는 이유: 위 셋을 고치려고 「못 찾으면 막는다」로 바꾸면
    막 만든 티켓이 자기 눈에서 사라지고, 그 증상은 보안 수정으로 위장된다.
    """
    assert _visible(db, "00000000-0000-4000-8000-0000000000ff", world["viewer"])


def test_the_lookup_finds_both_axes(db, world):
    """공용 조회기가 두 축을 다 안다 — 범위 문 말고도 이 함수를 쓰는 자리가 셋 더 있다.

    본문 낙관적 잠금과 댓글 알림과 생성 활동이 같은 조회를 쓴다. 한 축만 알면 그 셋이
    자체 DB 티켓에서 **조용히 아무 일도 안 한다** — 잠금이 안 걸려 두 사람이 서로의 글을
    지우고, 알림이 안 가고, 생성 기록이 안 남는다. 셋 다 오류를 안 낸다.
    """
    from app.tickets import service

    for label in ("ours_migrated", "ours_native", "theirs_migrated", "theirs_native"):
        found = service.ticket_row_for(db, world["ids"][label])
        assert found is not None, f"{label} 을 두 축 어느 쪽으로도 못 찾았다"
    assert service.ticket_row_for(db, "없는-id") is None
    assert service.ticket_row_for(db, None) is None
