"""사용자 셀프서비스 티켓 조회 유닛 테스트.

티켓은 자체 DB 표(`tickets`)에서 읽는다 — S14 에서 정본이 그리로 옮겨 왔고, 이 파일이
지키는 것은 저장소가 어디든 같아야 하는 것들이다: 매핑이 **검증된** 사람만 자기 티켓을
받는다, 내 목록에는 내 담당 건만 온다, 미할당 목록에서 끝난 티켓은 빠진다, 배정 후보는
활성·검증 매핑이 있는 사람뿐이다.

예전에는 이 판정들이 「Notion 에 어떤 필터를 보냈나」로 확인됐다. 지금은 나가는 요청이
없으므로 **돌아온 목록 자체**로 확인한다 — 필터가 무시되면 남의 티켓이 섞여 들어오고,
그것이 곧 시험이 잡아야 할 사고다.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.core.models_base import join_names
from app.notion_mapping.models import STATUS_UNMAPPED, STATUS_VERIFIED, UserNotionMapping
from app.org.constants import DEFAULT_ORG_ID
from app.tickets import service
from app.tickets.models import PROJECT_LINK_OK, TicketCache

pytestmark = pytest.mark.unit


@pytest.fixture()
def project(make_project):
    """티켓의 소속 프로젝트. 소속이 없으면 범위 판정이 티켓을 통째로 감춘다(0060)."""
    return make_project(name="알파", external_id="px-1")


def _ticket(db, project, *, tid, title, status, due, people, est=None, diff=None):
    db.add(TicketCache(
        notion_page_id=f"n{tid}",
        org_id=DEFAULT_ORG_ID,
        notion_ticket_number=tid,
        url=f"https://example.invalid/{tid}",
        title=title,
        status=status,
        due_date=date.fromisoformat(due),
        est_wd=est,
        difficulty=diff,
        project_ids=join_names(["px-1"]),
        project_names=join_names([project.name]),
        project_uid=project.id,
        project_link=PROJECT_LINK_OK,
        assignee_notion_ids=join_names(people),
    ))
    db.commit()


def _map(db, user, notion_id, status=STATUS_VERIFIED):
    db.add(UserNotionMapping(user_id=user.id, notion_user_id=notion_id, status=status))
    db.commit()


def test_my_notion_id_only_verified(db, make_user):
    u = make_user(email="a@goodmit.co.kr", display_name="가나다", role="user")
    assert service.my_notion_id(db, u) is None  # 매핑 없음
    _map(db, u, "notion-a", status=STATUS_UNMAPPED)
    assert service.my_notion_id(db, u) is None  # 미검증은 안 씀
    m = db.query(UserNotionMapping).filter_by(user_id=u.id).one()
    m.status = STATUS_VERIFIED
    db.commit()
    assert service.my_notion_id(db, u) == "notion-a"


def test_list_my_tickets_returns_only_my_own(db, settings, make_user, project):
    me = make_user(email="me@goodmit.co.kr", display_name="나", role="user")
    mate = make_user(email="mate@goodmit.co.kr", display_name="동료", role="user")
    _map(db, me, "notion-me")
    _map(db, mate, "notion-mate")
    _ticket(db, project, tid=1, title="내 완료", status="완료", due="2026-08-01",
            people=["notion-me"])
    _ticket(db, project, tid=2, title="공동", status="진행", due="2026-08-02",
            people=["notion-me", "notion-mate"])
    # 반례: 동료만 담당한 티켓은 내 목록에 오면 안 된다.
    _ticket(db, project, tid=3, title="동료 것", status="진행", due="2026-08-03",
            people=["notion-mate"])

    out = service.list_my_tickets(db, None, settings, me)
    assert [t["tid"] for t in out["tickets"]] == [1, 2]
    assert out["total"] == 2
    # 공동 담당 티켓의 담당자 이름이 해석된다.
    assert set(out["tickets"][1]["assignee_names"]) == {"나", "동료"}
    # 담당자 필터가 무시되면 동료 것이 섞여 들어온다 — 그 사고를 이름으로도 못박는다.
    assert "동료 것" not in {t["title"] for t in out["tickets"]}
    # 소스 user id 는 응답에 실리지 않는다(§12.3) — 이름과 앱 user_id 로 해석한 값만 나간다.
    assert out["tickets"][1]["assignee_user_ids"] == [me.id, mate.id]


def test_list_my_tickets_answers_for_an_account_with_no_legacy_link(
    db, settings, make_user, project
):
    """옛 소스와 짝이 없는 계정도 **자기 목록을 받는다** (S15 · D-285).

    예전에는 이 자리가 「매핑이 없으면 `{mapped: False}` 로 답한다」였다. 그때는 담당자를
    가리키는 값이 옛 소스의 user id 뿐이라 「이 사람 것이 무엇인지 모른다」가 실제 상태였다.
    지금은 사람마다 가리킬 값이 언제나 있으므로(`assignee_token`) 그 상태가 없다 —
    남의 것을 주지 않는다는 성질은 그대로다.
    """
    u = make_user(email="u@goodmit.co.kr", display_name="새 계정", role="user")
    _ticket(db, project, tid=7, title="누군가의 것", status="진행", due="2026-08-05",
            people=["notion-someone"])
    _ticket(db, project, tid=8, title="내 것", status="진행", due="2026-08-06",
            people=[u.id])
    out = service.list_my_tickets(db, None, settings, u)
    assert [t["tid"] for t in out["tickets"]] == [8]
    assert out["total"] == 1
    # 「연결이 없다」는 갈래 자체가 없어졌다 — 언제나 참인 필드를 응답에 남기지 않는다.
    assert "mapped" not in out


def test_list_unassigned_excludes_terminal(db, settings, make_user, project):
    admin = make_user(email="admin@goodmit.co.kr", display_name="관리자", role="admin")
    _ticket(db, project, tid=3, title="계획 미할당", status="계획", due="2026-08-05", people=[])
    _ticket(db, project, tid=4, title="완료 미할당", status="완료", due="2026-08-06", people=[])
    _ticket(db, project, tid=5, title="취소 미할당", status="취소", due="2026-08-07", people=[])
    # 반례: 담당자가 있으면 미할당이 아니다.
    _ticket(db, project, tid=6, title="담당 있음", status="진행", due="2026-08-08",
            people=["notion-someone"])

    tickets = service.list_unassigned_tickets(db, None, settings, viewer=admin)
    assert [t["tid"] for t in tickets] == [3]  # 완료·취소 제외
    assert tickets[0]["assignee_user_ids"] == []  # 미할당의 정의 그대로


def test_list_assignees_is_every_active_account(db, make_user):
    """담당자 후보는 **활성 사용자 전원**이다 (S15 · D-285).

    예전에는 verified 매핑이 있는 사람만 후보였다. 그 짝은 이제 새로 만들 수 없으므로
    (S14 가 Notion 런타임을 걷었다) 그 조건은 **새 계정을 영원히 후보에서 빼는** 조건이
    된다 — 누구도 그 사람에게 일을 줄 수 없다.

    반례는 그대로다: 비활성·보관 계정은 후보가 아니다.
    """
    a = make_user(email="a2@goodmit.co.kr", display_name="에이", role="user")
    b = make_user(email="b2@goodmit.co.kr", display_name="비", role="user")
    make_user(email="c2@goodmit.co.kr", display_name="씨(짝 없음)", role="user")
    off = make_user(email="d2@goodmit.co.kr", display_name="디(비활성)", role="user",
                    active=False)
    _map(db, a, "notion-a2")
    _map(db, b, "notion-b2", status=STATUS_UNMAPPED)  # 미검증 — 그래도 후보다
    names = [x["display_name"] for x in service.list_assignees(db)]
    assert names == ["비", "씨(짝 없음)", "에이"]
    assert off.display_name not in names
