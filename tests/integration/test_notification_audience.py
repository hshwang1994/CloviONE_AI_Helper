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
        db, "u1", type_="runner_unavailable", title="Runner 장애", now=fake_clock.now(),
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
