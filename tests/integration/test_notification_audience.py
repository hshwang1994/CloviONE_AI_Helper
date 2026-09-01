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
