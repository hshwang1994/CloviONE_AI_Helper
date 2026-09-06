"""범위로 거른 관리 알림이 **아무에게도 안 가는** 경우 (R6-01 후속, notify_admins).

사람이 대상인 관리 알림은 그 사람을 관리하는 관리자에게만 간다
(`tests/integration/test_notification_audience.py` 가 그 규칙을 센다). 그 규칙에는 아무도
안 보는 구멍이 하나 있다 — **거르고 나면 0 명이 남을 수 있다.**

부서가 없는 계정(`department_id IS NULL`)은 부서 범위 관리자의 판정에서 언제나 거짓이고,
조직이 다른 관리자도 마찬가지다. 활성 관리자가 전부 그런 사람들이면 계정 잠금 한 건이
어디에도 남지 않고 사라진다: 두 호출부는 반환값을 안 보고, 그때까지 로그도 없었다.
관리자는 화면에서도 로그에서도 그 사고를 볼 수 없다.

이 파일이 세는 것은 둘이다: ① 한 사람도 안 남으면 관리자 전원에게 간다(그리고 그 사실이
경고로 남는다), ② 범위 안 관리자가 있으면 폴백은 **돌지 않는다**(범위를 좁힌 의미가
폴백 때문에 없어지면 안 된다).
"""

from __future__ import annotations

import logging

import pytest

from tests.fixtures.org_tree import (  # noqa: F401 — fixture 재수출
    org_tree,
    people,
)

pytestmark = pytest.mark.integration


def _keep_only_these_admins(db, keep) -> None:
    """이 설치의 활성 관리자를 `keep` 만으로 만든다(씨앗·다른 시험이 만든 계정을 비활성화)."""
    from app.users.models import ROLE_ADMIN, ROLE_SYSTEM_ADMIN, User

    keep_ids = {u.id for u in keep}
    rows = (
        db.query(User)
        .filter(User.role.in_([ROLE_ADMIN, ROLE_SYSTEM_ADMIN]))
        .all()
    )
    for row in rows:
        if row.id not in keep_ids:
            row.active = False
    db.commit()


def _lock_notice(db, target, fake_clock) -> int:
    from app.notifications.service import notify_admins

    sent = notify_admins(
        db,
        type_="account_locked",
        title=f"계정 잠금 발생: {target.email}",
        related=("user", target.id),
        now=fake_clock.now(),
    )
    db.commit()
    return sent


def _titles(db, user) -> list[str]:
    from app.notifications.models import Notification

    return [
        row.title
        for row in db.query(Notification).filter(Notification.user_id == user.id).all()
    ]


def test_a_lock_on_a_user_nobody_manages_still_reaches_an_admin(
    db, people, fake_clock, caplog
):
    """부서 없는 계정 + 부서 범위 관리자뿐 — 예전에는 잠금 알림이 0 건이었다."""
    _keep_only_these_admins(db, [people["a1_admin"]])
    target = people["unassigned"]
    assert target.department_id is None, "전제가 깨졌다 — 부서 없는 계정이어야 한다"

    with caplog.at_level(logging.WARNING, logger="app.notifications"):
        sent = _lock_notice(db, target, fake_clock)

    assert sent >= 1, "아무의 범위도 아닌 계정이 잠겼는데 알림이 한 건도 안 갔다"
    titles = _titles(db, people["a1_admin"])
    assert any(target.email in t for t in titles), (
        f"관리자 전원 폴백이 안 돌았다: {titles}"
    )
    assert any("관리 범위 안 관리자가 없어" in r.message for r in caplog.records), (
        "조용히 폴백했다 — 무슨 일이 있었는지 로그에 남아야 한다"
    )
    assert not any(target.email in r.getMessage() for r in caplog.records), (
        "경고에 대상의 이메일이 실렸다"
    )


def test_the_fallback_does_not_fire_while_someone_in_scope_exists(
    db, people, fake_clock, caplog
):
    """반례 — 범위 안 관리자가 한 명이라도 있으면 범위 밖 관리자는 예전처럼 못 받는다.

    이것이 없으면 위 시험은 「범위를 없앴다」로도 초록이 된다.
    """
    target = people["unassigned"]

    with caplog.at_level(logging.WARNING, logger="app.notifications"):
        sent = _lock_notice(db, target, fake_clock)

    assert sent >= 1
    assert any(target.email in t for t in _titles(db, people["global_admin"])), (
        "전역 관리자가 잠금 알림을 못 받았다"
    )
    assert _titles(db, people["a1_admin"]) == [], (
        "범위 밖 부서 관리자에게 계정 이메일이 새어 나갔다"
    )
    assert not any("관리 범위 안 관리자가 없어" in r.message for r in caplog.records), (
        "폴백이 필요 없는데 돌았다"
    )


def test_an_in_scope_lock_still_goes_only_to_that_branch(db, people, fake_clock):
    """반례 — 부서 안 계정의 잠금은 그 부서 관리자에게 가고, 형제 부서 관리자에게는 안 간다."""
    _keep_only_these_admins(db, [people["a1_admin"], people["a_admin"]])
    target = people["a1"]

    sent = _lock_notice(db, target, fake_clock)

    assert sent == 2, f"A-1 과 그 상위 A 관리자 둘에게 가야 한다: {sent}"
    assert any(target.email in t for t in _titles(db, people["a1_admin"]))
    assert _titles(db, people["b1"]) == []
