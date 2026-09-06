"""알림 audience 구분 (팀/사용자 알림 vs 관리자 알림).

## 무엇이 문제였나

`Notification` 모델에는 자유 텍스트 `type` 컬럼만 있고, 이벤트가 **누구를 위한 것인지**
(관리자가 처리해야 할 운영 알림인가, 그 사용자 개인의 알림인가)를 저장하는 컬럼이 없었다.
`notify_user`/`notify_admins`/`notify_approvers`/`notify_active_users` 는 수신자를 다르게
고르면서도 그 "채널"을 기록하지 않아, 벨/목록 화면은 한 사람이 관리자이자 사용자일 때
자기 개인 알림(티켓 배정 등)과 관리자용 알림(백업 실패, 러너 장애 등)을 구분할 방법이 없었다.

이 파일은 `audience` 컬럼과 그것을 채우는 발송 함수 쪽 로직을 고정한다.
"""

from __future__ import annotations

import pytest

from tests.fixtures.org_tree import (  # noqa: F401 — fixture 재수출
    org_tree,
    people,
)

pytestmark = pytest.mark.integration


def test_notify_user_defaults_to_user_audience(db, fake_clock):
    from app.notifications.service import notify_user

    row = notify_user(
        db, "u1", type_="ticket_assigned", title="티켓 배정", now=fake_clock.now(),
    )
    db.commit()

    assert row.audience == "user"


def test_notify_admins_tags_admin_audience(client, login_as, make_user, db, fake_clock):
    login_as("admin", email="watcher-audience@goodmit.co.kr")

    from app.notifications.service import notify_admins

    count = notify_admins(
        db, type_="backup_failed", title="예약 백업이 실패했습니다", now=fake_clock.now(),
    )
    db.commit()
    assert count >= 1

    from app.notifications.models import Notification

    rows = db.query(Notification).filter(Notification.type == "backup_failed").all()
    assert rows, "notify_admins가 만든 행을 찾지 못했다"
    assert all(r.audience == "admin" for r in rows), "notify_admins는 audience='admin'을 채워야 한다"


def test_admin_only_event_types_are_always_admin_audience(db, fake_clock):
    """백업 실패·러너 장애처럼 유형 자체가 명백히 관리자용이면, 어느 발송 함수를 거치든
    audience가 'admin'으로 못박혀야 한다 — 실수로 notify_user를 직접 불러도 새지 않는다."""
    from app.notifications.service import notify_user

    row = notify_user(
        db, "u1", type_="backup_failed", title="백업 실패", now=fake_clock.now(),
    )
    db.commit()

    assert row.audience == "admin"


def test_list_notifications_filters_by_audience(client, login_as, db, fake_clock):
    csrf = login_as("user", email="audience-filter@goodmit.co.kr")
    me = client.get("/api/me").json()["user"]

    from app.notifications.service import notify_admins, notify_user

    notify_user(
        db, me["id"], type_="ticket_assigned", title="내 티켓 배정", now=fake_clock.now(),
    )
    notify_admins(
        db, type_="backup_failed", title="예약 백업이 실패했습니다", now=fake_clock.now(),
    )
    db.commit()
    del csrf

    all_items = client.get("/api/notifications").json()["items"]
    assert len(all_items) >= 1  # 이 로그인 사용자가 admin이 아니면 admin 알림은 안 보임(소유권)

    user_only = client.get("/api/notifications?audience=user").json()["items"]
    assert all(it["audience"] == "user" for it in user_only)
    assert any(it["title"] == "내 티켓 배정" for it in user_only)


# ── 숫자와 일괄 처리도 audience 를 따라간다 ──────────────────────────────────
#
# 목록만 audience 로 자르고 「안 읽음 N」과 '모두 읽음' 은 안 잘랐던 동안, 한 화면이 서로
# 반대되는 말을 했다: 관리 알림만 안 읽힌 사람의 「내 업무 > 알림」이 **한 줄도 없는 목록
# 위에 "안 읽음 3"** 을 띄웠고, 그 숫자를 근거로 뜨는 '모두 읽음' 버튼을 누르면 화면에 나온
# 적 없는 백업 실패·계정 잠금 알림까지 읽음이 됐다. 그 뒤 관리자 콘솔 벨은 0 을 띄운다 —
# 조치가 필요한 사건이 아무도 못 본 채 조용히 묻힌다.


def _seed_both_audiences(client, db, fake_clock):
    """내 업무 1건 + 관리 2건. 두 종류를 다 받는 사람(관리자이자 사용자)이 기준이다."""
    from app.notifications.service import notify_admins, notify_user

    me = client.get("/api/me").json()["user"]
    notify_user(db, me["id"], type_="ticket_assigned", title="내 티켓 배정", now=fake_clock.now())
    notify_admins(db, type_="backup_failed", title="예약 백업이 실패했습니다", now=fake_clock.now())
    notify_admins(db, type_="account_locked", title="계정이 잠겼습니다", now=fake_clock.now())
    db.commit()
    return me


def test_list_unread_counts_only_the_listed_audience(client, login_as, db, fake_clock):
    """목록 옆의 「안 읽음 N」은 **그 목록의** 안 읽음이어야 한다."""
    login_as("admin", email="noti-count@goodmit.co.kr")
    _seed_both_audiences(client, db, fake_clock)

    user_list = client.get("/api/notifications?audience=user").json()
    assert user_list["total"] == 1
    assert user_list["unread"] == 1, f"내 업무 화면이 관리 알림까지 세고 있다: {user_list['unread']}"

    admin_list = client.get("/api/notifications?audience=admin").json()
    assert admin_list["total"] == 2
    assert admin_list["unread"] == 2, f"관리 화면 숫자가 목록과 다르다: {admin_list['unread']}"

    # audience 를 안 주면 예전 계약 그대로 전체다(API 를 직접 부르는 쪽).
    assert client.get("/api/notifications").json()["unread"] == 3


def test_read_all_only_clears_the_requested_audience(client, login_as, db, fake_clock):
    """'모두 읽음'은 그 화면이 보여 준 것만 지운다 — 관리 알림을 몰래 삼키지 않는다."""
    csrf = login_as("admin", email="noti-readall@goodmit.co.kr")
    _seed_both_audiences(client, db, fake_clock)

    r = client.post("/api/notifications/read-all?audience=user", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert r.json()["read_count"] == 1, f"내 업무 '모두 읽음'이 관리 알림까지 지웠다: {r.json()}"

    still = client.get("/api/notifications/unread-count?audience=admin").json()
    assert still["unread"] == 2, f"관리 알림이 조용히 읽음 처리됐다: {still}"
    assert client.get("/api/notifications/unread-count?audience=user").json()["unread"] == 0


def test_read_all_without_audience_still_clears_everything(client, login_as, db, fake_clock):
    """오탐 방지 — audience 를 안 주면 예전과 똑같이 전체를 처리한다(계약 유지)."""
    csrf = login_as("admin", email="noti-readall-all@goodmit.co.kr")
    _seed_both_audiences(client, db, fake_clock)

    r = client.post("/api/notifications/read-all", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200 and r.json()["read_count"] == 3
    assert client.get("/api/notifications/unread-count").json()["unread"] == 0


# ── 모르는 audience 는 «전체» 가 아니라 «거절» 이다 ──────────────────────────
#
# 읽기 경로는 모르는 값을 전체로 폴백한다(목록이 비어 「알림이 없다」로 오독되는 것보다
# 낫다). '모두 읽음' 이 같은 관용을 쓰던 동안 오타 하나(`admn`)가 두 콘솔의 알림을 전부
# 읽음으로 바꿨다 — 위 문단이 막으려던 사고가 오타 한 글자로 되살아났다.


def test_read_all_with_an_unknown_audience_is_refused_and_touches_nothing(
    client, login_as, db, fake_clock
):
    csrf = login_as("admin", email="noti-readall-typo@goodmit.co.kr")
    _seed_both_audiences(client, db, fake_clock)

    r = client.post("/api/notifications/read-all?audience=admn", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 422, f"오타 audience 가 거절되지 않았다: {r.status_code} {r.text}"
    message = r.json()["error"]["message"]
    assert message.endswith("."), f"완결된 문장이 아니다: {message!r}"
    assert "admn" in message

    # 아무것도 읽음이 되지 않았다 — 두 콘솔 모두.
    assert client.get("/api/notifications/unread-count?audience=user").json()["unread"] == 1
    assert client.get("/api/notifications/unread-count?audience=admin").json()["unread"] == 2
    assert client.get("/api/notifications/unread-count").json()["unread"] == 3


def test_read_all_with_admin_audience_leaves_user_notifications_unread(
    client, login_as, db, fake_clock
):
    """반례 — 아는 값(`admin`)은 그 콘솔만 지운다. 위 시험이 «전부 막는 문» 으로 통과하지 못하게 한다."""
    csrf = login_as("admin", email="noti-readall-admin@goodmit.co.kr")
    _seed_both_audiences(client, db, fake_clock)

    r = client.post("/api/notifications/read-all?audience=admin", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    assert r.json()["read_count"] == 2, f"관리 '모두 읽음'이 내 업무 알림까지 지웠다: {r.json()}"

    assert client.get("/api/notifications/unread-count?audience=admin").json()["unread"] == 0
    assert client.get("/api/notifications/unread-count?audience=user").json()["unread"] == 1, (
        "관리 콘솔의 '모두 읽음'이 내 업무 알림을 삼켰다"
    )


# ── 사람이 대상인 관리 알림은 **그 사람을 관리하는 관리자에게만** 간다 ────────
#
# 부서 범위 관리자에게 범위 밖 계정의 잠금 알림이 그대로 갔다. 제목에 그 사람의 이메일이
# 실려 있고, 이어지는 「관련 항목 보기」는 그 관리자에게 존재하지 않는 대상이라 404 다 —
# 알고도 할 수 있는 일이 없다. 같은 사건을 감사 로그 쪽은 이미 같은 범위로 가리고 있었으므로
# (목록·단건·CSV·이상 징후 전부), 한 사건에 두 화면이 서로 다른 범위 규칙을 쓰고 있었다.

def _lock_notice(db, target, fake_clock) -> None:
    from app.notifications.service import notify_admins

    notify_admins(
        db, type_="account_locked",
        title=f"계정 잠금 발생: {target.email}",
        related=("user", target.id), now=fake_clock.now(),
    )
    db.commit()


def _titles(db, user) -> list[str]:
    from app.notifications.models import Notification

    return [
        row.title
        for row in db.query(Notification).filter(Notification.user_id == user.id).all()
    ]


def test_account_locked_notice_skips_an_admin_who_cannot_manage_that_user(
    db, people, fake_clock
):
    """A-1 관리자는 B-1 사람의 잠금을 알 수 없다 — 그 계정은 그 관리자에게 아예 안 보인다."""
    _lock_notice(db, people["b1"], fake_clock)

    assert _titles(db, people["a1_admin"]) == [], (
        "부서 범위 관리자에게 범위 밖 계정의 이메일이 알림으로 새어 나갔다"
    )


def test_a_global_admin_still_gets_every_account_locked_notice(db, people, fake_clock):
    """반례 — 전역 관리자에게는 예전과 똑같이 전부 간다."""
    _lock_notice(db, people["b1"], fake_clock)

    titles = _titles(db, people["global_admin"])
    assert any(people["b1"].email in t for t in titles), (
        f"전역 관리자가 잠금 알림을 못 받았다: {titles}"
    )


def test_a_dept_admin_still_gets_a_lock_inside_the_managed_branch(db, people, fake_clock):
    """반례 — 자기 범위 안의 잠금은 그대로 받는다. 위 시험이 「부서 관리자에게는 아무것도
    안 보낸다」로 통과하면 관리자가 자기 팀 사고를 못 본다."""
    _lock_notice(db, people["a1"], fake_clock)

    titles = _titles(db, people["a1_admin"])
    assert any(people["a1"].email in t for t in titles), (
        f"관리 범위 안 계정의 잠금이 안 갔다: {titles}"
    )


def test_a_notice_that_is_not_about_a_person_still_fans_out_to_everyone(
    db, people, fake_clock
):
    """반례 — 백업 실패처럼 사람이 대상이 아닌 사건은 범위를 따질 수 없다. 예전 그대로
    관리자 전원에게 간다."""
    from app.notifications.service import notify_admins

    sent = notify_admins(
        db, type_="backup_failed", title="예약 백업이 실패했습니다",
        related=("backup", None), now=fake_clock.now(),
    )
    db.commit()

    assert sent >= 2
    assert any("백업" in t for t in _titles(db, people["a1_admin"]))
    assert any("백업" in t for t in _titles(db, people["global_admin"]))


# ── 승인 요청 알림도 **결재할 수 있는 사람에게만** 간다 ──────────────────────
#
# 개인 결재함의 '할 일' 칸과 관리 큐는 둘 다 요청자의 범위로 잘린다
# (`app/approvals/router.py::decision_visible_user_ids`). 그런데 요청 알림 팬아웃만 그 조건
# 없이 관리자 전원에게 갔다 — 부서 범위 관리자는 「승인 요청: 역할 변경」 벨을 받고 들어간
# 결재함에서 「처리할 것이 없습니다」를 봤고, 관리 큐에도 그 줄이 없었다. 알림이 가리키는
# 목적지가 어느 화면에도 없는 상태다. 수신자 규칙과 결재함 규칙은 한 개여야 한다.


@pytest.fixture()
def approval_type():
    """이 파일에서만 쓰는 요청 유형. 실행기가 등록돼 있어야 `create_approval` 이 받는다."""
    from app.approvals.service import APPROVAL_EXECUTORS

    APPROVAL_EXECUTORS["test.audience"] = lambda *a, **k: None
    yield "test.audience"
    APPROVAL_EXECUTORS.pop("test.audience", None)


def _request_approval(db, requester, approval_type, fake_clock):
    from app.approvals.service import create_approval

    row = create_approval(
        db, request_type=approval_type, object_type="user", object_id=requester.id,
        requested_by=requester, payload={"role": "operator"}, now=fake_clock.now(),
    )
    db.commit()
    return row


def test_approval_request_notice_skips_an_admin_who_cannot_decide_it(
    db, people, approval_type, fake_clock
):
    """B-1 사람이 올린 요청은 A-1 부서 관리자의 결재함에 안 뜬다 — 벨도 뜨면 안 된다."""
    _request_approval(db, people["b1"], approval_type, fake_clock)

    assert _titles(db, people["a1_admin"]) == [], (
        "결재함에 뜨지도 않는 승인 요청이 부서 범위 관리자에게 알림으로 갔다"
    )


def test_a_global_admin_still_gets_every_approval_request_notice(
    db, people, approval_type, fake_clock
):
    """반례 — 전역 관리자는 예전과 똑같이 전부 받는다(그 사람의 결재함에는 실제로 뜬다)."""
    _request_approval(db, people["b1"], approval_type, fake_clock)

    assert any("승인 요청" in t for t in _titles(db, people["global_admin"])), (
        f"전역 관리자가 승인 요청 알림을 못 받았다: {_titles(db, people['global_admin'])}"
    )


def test_a_dept_admin_still_gets_a_request_from_inside_the_managed_branch(
    db, people, approval_type, fake_clock
):
    """반례 — 자기 범위 안에서 올라온 요청은 그대로 받는다. 이것이 없으면 위 시험은
    「부서 관리자에게는 아무 승인 알림도 안 보낸다」로도 초록불이다."""
    _request_approval(db, people["a1"], approval_type, fake_clock)

    assert any("승인 요청" in t for t in _titles(db, people["a1_admin"])), (
        f"관리 범위 안에서 올라온 승인 요청이 안 갔다: {_titles(db, people['a1_admin'])}"
    )


def test_an_overdue_notice_goes_to_the_same_people_as_the_request(
    db, people, approval_type, fake_clock
):
    """기한 초과 재촉도 같은 규칙이다 — 결재할 수 없는 사람을 재촉하지 않는다."""
    from datetime import timedelta

    from app.approvals.delegation import notify_overdue

    _request_approval(db, people["b1"], approval_type, fake_clock)
    sent = notify_overdue(db, now=fake_clock.now() + timedelta(hours=25))
    db.commit()

    assert sent >= 1, "기한 초과 알림이 아무에게도 안 갔다"
    assert not [t for t in _titles(db, people["a1_admin"]) if "기한 초과" in t], (
        "결재할 수 없는 관리자에게 기한 초과 재촉이 갔다"
    )
    assert any("기한 초과" in t for t in _titles(db, people["global_admin"]))
