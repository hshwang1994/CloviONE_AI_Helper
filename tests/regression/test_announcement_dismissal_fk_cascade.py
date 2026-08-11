"""UB-19: 공지를 삭제하면 그 공지의 닫힘 기록도 함께 지워진다(고아로 안 남는다).

`announcement_dismissals.announcement_id`는 FK가 아니었다 - 공지를 삭제해도(하드 삭제,
`app/announcements/router.py::delete_announcement`) 닫힘 기록은 그대로 남아 매 배너
폴링(`service.py::for_user`)이 읽는 "이 사용자의 닫힘 집합"을 무한히 키웠다. `User`와
달리 `Announcement`는 실제로 하드 삭제되는 CRUD 대상이라 이 고아 문제는 진짜 재현된다
(UB-20처럼 전제 자체가 안 맞는 경우가 아니다).

migration 0055가 `ON DELETE CASCADE` FK를 건다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

pytestmark = pytest.mark.regression

NOW = datetime(2026, 8, 11, 9, 0, 0)


@pytest.fixture()
def announcement(db):
    from app.announcements.models import Announcement

    row = Announcement(
        title="공지", body="본문", level="info", audience="all",
        active=True, dismissible=True, created_by=None,
        created_at=NOW, updated_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


def test_deleting_an_announcement_cascades_to_its_dismissals(db, make_user, announcement):
    from sqlalchemy import func, select

    from app.announcements.models import Announcement, AnnouncementDismissal

    user = make_user("dismisser@goodmit.co.kr", role="user", display_name="닫은사람")
    db.add(AnnouncementDismissal(announcement_id=announcement.id, user_id=user.id, dismissed_at=NOW))
    db.commit()

    row = db.get(Announcement, announcement.id)
    db.delete(row)
    db.commit()

    db.expire_all()
    count = db.execute(
        select(func.count()).select_from(AnnouncementDismissal).where(
            AnnouncementDismissal.announcement_id == announcement.id
        )
    ).scalar_one()
    assert count == 0, "공지를 지웠는데 닫힘 기록이 고아로 남았다"


def test_delete_endpoint_cascades_too(client, login_as, db):
    """서비스 함수가 아니라 실제 관리 콘솔 경로(DELETE /api/admin/announcements/{id})로도
    같은 결과를 확인한다 — router.py가 db.delete(row)만 부르고 그 외 정리를 안 해도,
    DB 레벨 CASCADE라 어느 삭제 경로를 타든 고아가 안 생긴다."""
    from sqlalchemy import func, select

    from app.announcements.models import Announcement, AnnouncementDismissal

    csrf = login_as("admin")
    r = client.post(
        "/api/admin/announcements",
        json={"title": "공지", "body": "본문", "level": "info", "audience": "all"},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, r.text
    row_id = r.json()["id"]

    user = login_as("user")
    dismiss_r = client.post(
        f"/api/announcements/{row_id}/dismiss", headers={"X-CSRF-Token": user}
    )
    assert dismiss_r.status_code == 200, dismiss_r.text

    admin_csrf2 = login_as("admin")
    del_r = client.delete(
        f"/api/admin/announcements/{row_id}", headers={"X-CSRF-Token": admin_csrf2}
    )
    assert del_r.status_code == 200, del_r.text

    db.expire_all()
    count = db.execute(
        select(func.count()).select_from(AnnouncementDismissal).where(
            AnnouncementDismissal.announcement_id == row_id
        )
    ).scalar_one()
    assert count == 0
    assert db.get(Announcement, row_id) is None
