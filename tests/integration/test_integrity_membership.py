"""조직 정합성 — **세는 것과 고치는 것이 같은 정의를 쓰는가**.

이 화면은 「판정할 수 없는 데이터」를 사람에게 보여 주고, 그중 하나는 버튼으로 고쳐 준다.
그 두 축이 서로 다른 정의를 쓰면 화면이 스스로를 배신한다. 실제로 두 자리에서 갈라져
있었고, 여기서 둘 다 못박는다.

  * **일괄 소속 지정**(`POST /api/admin/integrity/membership`)은 대상을 「그 id 의 행이
    있는가」로만 봤다. 그래서 이미 소속이 있는 사람의 부서를 덮어쓰고, 보관된 계정에도
    소속을 붙이고, 없는 id 는 아무 말 없이 지나갔다. 부서 쪽도 존재만 봐서 **비활성 부서**를
    새로 지정할 수 있었는데 같은 제품의 사용자 편집은 그것을 422 로 막는다.

  * **보관·비활성 계정이 담당인 티켓**을 아무도 세지 않았다. 계정을 닫으면 담당자 해석이
    그 사람을 풀지 않아 티켓의 담당자 칸이 비어 보이고, 담당자가 정말 없는 티켓만 담는
    미할당 대기열에도 안 들어간다 — 일이 어느 목록에서도 안 보이는 상태다.

반례를 같은 파일에 둔다: 멀쩡한 대상과 활성 부서의 지정은 그대로 통과하고, 활성 계정이
담당인 티켓은 새 항목에 잡히지 않는다. 둘이 함께 통과해야 「전부 막는다」도 「하나도 안
본다」도 아니라는 뜻이 된다.
"""

from __future__ import annotations

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department
from app.users.models import MEMBERSHIP_UNASSIGNED, User
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


@pytest.fixture()
def admin(client, make_user):
    make_user(email="integrity-boss@goodmit.co.kr", role="system_admin", display_name="관리자")
    response = client.post(
        "/login",
        json={"email": "integrity-boss@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


@pytest.fixture()
def depts(db):
    """활성 부서 하나와 비활성 부서 하나."""
    live = Department(name="살아있는팀", org_id=DEFAULT_ORG_ID, active=True)
    dead = Department(name="정리된팀", org_id=DEFAULT_ORG_ID, active=False)
    db.add_all([live, dead])
    db.commit()
    return {"live": live.id, "dead": dead.id}


@pytest.fixture()
def unassigned_user(db, make_user):
    user = make_user(
        email="no-membership@goodmit.co.kr", display_name="소속미지정", role="user",
        membership=MEMBERSHIP_UNASSIGNED,
    )
    db.commit()
    return user.id


def _assign(client, csrf, **body):
    return client.post(
        "/api/admin/integrity/membership", json=body, headers={"X-CSRF-Token": csrf}
    )


# ── 일괄 소속 지정 ────────────────────────────────────────────────────────────

def test_assigning_an_unassigned_user_to_a_live_department_still_works(
    client, admin, db, depts, unassigned_user
):
    """반례 — 이 동작이 원래 하려던 일은 그대로 된다."""
    response = _assign(client, admin, user_ids=[unassigned_user], department_id=depts["live"])

    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 1
    assert response.json()["skipped"] == []
    db.expire_all()
    assert db.get(User, unassigned_user).department_id == depts["live"]


def test_an_inactive_department_cannot_be_assigned_here_either(
    client, admin, db, depts, unassigned_user
):
    """비활성 부서는 **새로 고를 수 없다** — 사용자 편집과 같은 규칙, 같은 문구다.

    한 규칙이 경로마다 다르면 좁은 쪽이 우회로가 된다. 여기로 들어오면 정합성 보고의
    「비활성 부서에 연결된 자원」이 이 API 때문에 스스로 늘어난다.
    """
    response = _assign(client, admin, user_ids=[unassigned_user], department_id=depts["dead"])

    assert response.status_code == 422, response.text
    assert "비활성" in response.json()["error"]["message"]
    db.expire_all()
    assert db.get(User, unassigned_user).department_id is None, "거절했는데 값이 바뀌었다"


def test_a_department_that_does_not_exist_is_refused_not_silently_ignored(
    client, admin, unassigned_user
):
    response = _assign(
        client, admin, user_ids=[unassigned_user],
        department_id="00000000-0000-0000-0000-000000000000",
    )

    assert response.status_code == 422, response.text


def test_a_user_who_already_has_a_department_is_skipped_with_a_reason(
    client, admin, db, depts, make_user
):
    """**멀쩡한 소속을 덮어쓰지 않는다.** 이 동작은 소속 미지정을 고치는 자리다.

    예전에는 200 changed 1 로 부서가 바뀌었고, 보낸 사람은 자기가 무엇을 덮었는지 몰랐다.
    """
    settled = make_user(email="settled@goodmit.co.kr", display_name="소속있음", role="user")
    settled.department_id = depts["live"]
    settled.membership_kind = "department"
    db.commit()
    settled_id = settled.id

    other = Department(name="다른팀", org_id=DEFAULT_ORG_ID, active=True)
    db.add(other)
    db.commit()

    response = _assign(client, admin, user_ids=[settled_id], department_id=other.id)

    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 0
    skipped = response.json()["skipped"]
    assert len(skipped) == 1
    assert skipped[0]["user_id"] == settled_id
    assert "이미 활성 부서에 속한 계정입니다." in skipped[0]["reason"]
    db.expire_all()
    assert db.get(User, settled_id).department_id == depts["live"], "다른 부서로 덮어썼다"


def test_an_archived_account_is_skipped_with_a_reason(client, admin, db, depts, make_user):
    from app.core.models_base import utcnow

    archived = make_user(
        email="gone@goodmit.co.kr", display_name="보관계정", role="user",
        membership=MEMBERSHIP_UNASSIGNED,
    )
    archived.archived_at = utcnow()
    db.commit()
    archived_id = archived.id

    response = _assign(client, admin, user_ids=[archived_id], department_id=depts["live"])

    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 0
    assert response.json()["skipped"][0]["reason"].startswith("보관된 계정입니다.")
    db.expire_all()
    assert db.get(User, archived_id).department_id is None


def test_an_unknown_id_is_reported_not_swallowed(client, admin, depts, unassigned_user):
    """없는 id 를 조용히 넘기면 「200, changed 0」이 성공으로 읽힌다.

    한 요청 안에서 고칠 수 있는 것은 고치고, 못 고친 것은 사유와 함께 돌려준다.
    """
    ghost = "00000000-0000-0000-0000-0000000000ff"
    response = _assign(
        client, admin, user_ids=[unassigned_user, ghost], department_id=depts["live"]
    )

    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 1
    skipped = response.json()["skipped"]
    assert [s["user_id"] for s in skipped] == [ghost]
    assert skipped[0]["reason"] == "이 계정을 찾을 수 없습니다."


def test_organization_direct_follows_the_same_target_rule(client, admin, db, depts, make_user):
    """조직 직속으로 지정하는 갈래도 같은 대상 규칙을 쓴다(한쪽만 고치면 우회로가 남는다)."""
    settled = make_user(email="settled2@goodmit.co.kr", display_name="소속있음2", role="user")
    settled.department_id = depts["live"]
    settled.membership_kind = "department"
    db.commit()
    settled_id = settled.id

    response = _assign(client, admin, user_ids=[settled_id], organization_direct=True)

    assert response.status_code == 200, response.text
    assert response.json()["changed"] == 0
    db.expire_all()
    assert db.get(User, settled_id).department_id == depts["live"]


# ── 보관·비활성 계정이 담당인 티켓 ────────────────────────────────────────────

def _finding(client, key: str) -> dict:
    report = client.get("/api/admin/integrity")
    assert report.status_code == 200, report.text
    found = next((f for f in report.json()["findings"] if f["key"] == key), None)
    assert found is not None, f"{key} 항목이 진단에 아예 없다"
    return found


def test_a_ticket_held_by_an_archived_account_is_counted(
    client, admin, db, make_user, portal_project, make_ticket
):
    """계정을 보관하면 그 사람의 티켓이 모든 대기열에서 사라진다 — 진단이 그것을 센다.

    반례가 같은 실행 안에 있다: 활성 계정이 담당인 티켓은 세지 않는다. 둘이 함께 통과해야
    이 항목이 「전부 센다」도 「하나도 안 센다」도 아니게 된다.
    """
    from app.core.models_base import utcnow

    leaver = make_user(email="leaver-x@goodmit.co.kr", display_name="떠난사람", role="user")
    stayer = make_user(email="stayer-x@goodmit.co.kr", display_name="남은사람", role="user")
    make_ticket(page_id="t-closed", project=portal_project, tid=91,
                title="보관 계정이 담당", assignees=[leaver.id])
    make_ticket(page_id="t-open", project=portal_project, tid=92,
                title="활성 계정이 담당", assignees=[stayer.id])
    leaver.archived_at = utcnow()
    leaver.active = False
    db.commit()

    finding = _finding(client, "tickets_assigned_to_closed_accounts")

    assert finding["count"] == 1, "보관 계정이 담당인 티켓을 못 세고 있다"
    titles = {i["title"] for i in finding["items"]}
    assert "보관 계정이 담당" in titles
    assert "활성 계정이 담당" not in titles, "정상 배정까지 정합성 오류로 세고 있다"
    assert "떠난사람" in finding["items"][0]["reason"]
    # 여기서 고칠 수 있는 항목이 아니다 — 누구에게 넘길지는 사람이 정한다.
    assert finding["fixable_here"] is False
    assert "오프보딩" in finding["remedy"]


def test_a_ticket_held_by_a_deactivated_account_is_counted_too(
    client, admin, db, make_user, portal_project, make_ticket
):
    """비활성도 같은 사건이다 — 담당자 해석은 활성·미보관 계정만 푼다."""
    paused = make_user(email="paused-x@goodmit.co.kr", display_name="휴직자", role="user")
    make_ticket(page_id="t-paused", project=portal_project, tid=93,
                title="비활성 계정이 담당", assignees=[paused.id])
    paused.active = False
    db.commit()

    finding = _finding(client, "tickets_assigned_to_closed_accounts")

    assert finding["count"] == 1
    assert finding["items"][0]["title"] == "비활성 계정이 담당"


def test_the_closed_assignee_finding_does_not_double_count_unmapped_ones(
    client, admin, db, make_user, portal_project, make_ticket
):
    """어느 계정으로도 안 풀리는 담당자는 **다른 항목**이다(둘은 서로 다른 사건이다)."""
    make_ticket(page_id="t-ghost-x", project=portal_project, tid=94,
                title="유령 담당자", assignees=["notion-ghost-x"])

    closed = _finding(client, "tickets_assigned_to_closed_accounts")
    unmapped = _finding(client, "tickets_with_unmapped_assignees")

    assert closed["count"] == 0, "해석 실패를 보관 계정으로 세고 있다"
    assert unmapped["count"] == 1


# ── 이 숫자는 **아직 남은 일**을 뜻해야 한다 ──────────────────────────────────
#
# 퇴사자 한 명이 몇 년 치 완료 티켓을 달고 나간다(오프보딩은 진행 중인 것만 옮기고, 완료
# 이력은 그 사람에게 그대로 붙어 있다). 그것까지 세면 이 소견은 어떤 조치로도 0 이 되지
# 않고, 표본 50건이 끝난 일로 차서 정작 멈춰 있는 진행 중인 일이 묻힌다. 「담당자를 다시
# 지정하세요」라는 처방도 끝난 티켓에는 맞지 않는다 — 넘길 일이 없다.


def test_a_finished_ticket_of_a_departed_account_is_not_reported(
    client, admin, db, make_user, portal_project, make_ticket
):
    """완료·취소된 티켓은 세지 않는다. 같은 사람의 진행 중인 티켓은 그대로 센다(반례)."""
    from app.core.models_base import utcnow

    leaver = make_user(email="leaver-done@goodmit.co.kr", display_name="퇴사자", role="user")
    make_ticket(page_id="t-done", project=portal_project, tid=95,
                title="끝난 일", assignees=[leaver.id], status="완료")
    make_ticket(page_id="t-cancelled", project=portal_project, tid=96,
                title="취소된 일", assignees=[leaver.id], status="취소")
    make_ticket(page_id="t-running", project=portal_project, tid=97,
                title="멈춰 있는 일", assignees=[leaver.id], status="진행")
    leaver.archived_at = utcnow()
    leaver.active = False
    db.commit()

    finding = _finding(client, "tickets_assigned_to_closed_accounts")

    assert finding["count"] == 1, (
        f"끝난 일까지 세면 이 소견은 아무 조치로도 0 이 되지 않는다: {finding['items']}"
    )
    assert {i["title"] for i in finding["items"]} == {"멈춰 있는 일"}


def test_a_ticket_stamped_completed_is_not_reported_either(
    client, admin, db, make_user, portal_project, make_ticket
):
    """상태 문자열이 무엇이든 완료 시각이 찍혔으면 끝난 일이다."""
    from app.core.models_base import utcnow
    from app.tickets.models import TicketCache

    leaver = make_user(email="leaver-stamp@goodmit.co.kr", display_name="퇴사자2", role="user")
    ticket = make_ticket(page_id="t-stamped", project=portal_project, tid=98,
                         title="시각만 찍힌 일", assignees=[leaver.id], status="검증")
    db.get(TicketCache, ticket.id).completed_at = utcnow()
    leaver.active = False
    db.commit()

    assert _finding(client, "tickets_assigned_to_closed_accounts")["count"] == 0


def test_a_ticket_with_no_status_at_all_is_still_reported(
    client, admin, db, make_user, portal_project, make_ticket
):
    """반례 — 상태가 비어 있는 옛 이관 행은 **남은 일 쪽으로** 읽는다.

    모르는 것을 끝난 것으로 치면 진짜 멈춰 있는 일이 조용히 사라진다.
    """
    leaver = make_user(email="leaver-nostatus@goodmit.co.kr", display_name="퇴사자3", role="user")
    make_ticket(page_id="t-nostatus", project=portal_project, tid=99,
                title="상태 없는 일", assignees=[leaver.id], status=None)
    leaver.active = False
    db.commit()

    finding = _finding(client, "tickets_assigned_to_closed_accounts")

    assert finding["count"] == 1
    assert finding["items"][0]["title"] == "상태 없는 일"
