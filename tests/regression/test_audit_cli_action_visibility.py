"""SEC-22: CLI(app/cli/user_cli.py)로 한 계정 조작이 이상 탐지에서 안 보였다.

`app/audit/anomalies.py` 의 `SENSITIVE_ACTION_PREFIXES` 에는 `"user."` 만 있고
`CRITICAL_ACTIONS` 는 `"user.role_change"`(웹 스펠링) 뿐이었다. CLI 는 같은 조작을
`cli.user.*` 로 적고, 역할 변경은 특히 `cli.user.set_role`(웹의 `user.role_change` 와
다른 동사)로 적는다 - 그 결과 CLI 로 한 역할 변경·계정 조작은 심야 규칙(off_hours),
중대 동작 규칙(critical_action), 신규 행위 규칙(new_actor_action) **어디에도** 걸리지
않았다. 감사 이상 탐지의 존재 이유(비정상적인 권한·계정 조작을 잡아낸다)와 정확히
반대되는 사각지대였다.

`app/health/service.py` 의 "최근 주요 변경" 위젯은 이미 이 매핑
(`cli.user.set_role` ↔ `user.role_change`)을 알고 있었다 - 두 모듈이 같은 사실을
따로 들고 있다가 한쪽만 못 따라간 경우다. 이제 `app/audit/actions.py` 하나를
공유한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.audit.anomalies import detect
from app.audit.models import AuditLog

pytestmark = pytest.mark.regression

# 심야 규칙(22:00~07:00 KST)에 걸리는 시각. UTC 03:00 = KST 12:00 은 낮이라 일부러
# 피한다 - 이 테스트는 심야 판정 자체가 아니라 CLI 액션이 그 판정에 도달하는지를 본다.
# 그래서 낮 시각(KST 정오)을 써서 critical_action 규칙만 단독으로 걸리는지 먼저 본다.
NOON_KST = datetime(2026, 7, 13, 3, 0, 0)  # UTC 03:00 = KST 12:00
MIDNIGHT_KST = datetime(2026, 7, 13, 15, 0, 0)  # UTC 15:00 = KST 24:00


@pytest.fixture()
def actor(db, make_user):
    return make_user("sec22-actor@goodmit.co.kr", role="admin", display_name="SEC22")


def _detect(db, now):
    return detect(db, now=now, actor_ids=None)


def test_cli_role_change_trips_the_critical_action_rule(db, actor):
    """웹의 user.role_change 는 이미 잡혔다 - CLI 의 다른 철자(cli.user.set_role)도
    같은 규칙에 걸려야 한다."""
    db.add(AuditLog(
        user_id=actor.id, action="cli.user.set_role", object_type="user",
        object_id=actor.id, result="success", created_at=NOON_KST,
    ))
    db.commit()

    result = _detect(db, NOON_KST)
    critical = [f for f in result["findings"] if f["kind"] == "critical_action" and f["actor_id"] == actor.id]
    assert critical, (
        f"cli.user.set_role 이 critical_action 규칙에 안 걸렸다: {result['findings']}"
    )
    assert any("cli.user.set_role" in e for e in critical[0]["evidence"])


def test_cli_user_action_at_night_trips_the_off_hours_rule(db, actor):
    """cli.user.enable 같은 평범한 CLI 계정 조작도 심야 규칙의 대상이어야 한다 -
    "user." 접두어만으로는 이 문자열이 안 걸린다."""
    db.add(AuditLog(
        user_id=actor.id, action="cli.user.enable", object_type="user",
        object_id=actor.id, result="success", created_at=MIDNIGHT_KST,
    ))
    db.commit()

    result = _detect(db, MIDNIGHT_KST)
    off_hours = [f for f in result["findings"] if f["kind"] == "off_hours" and f["actor_id"] == actor.id]
    assert off_hours, f"cli.user.enable 이 off_hours 규칙에 안 걸렸다: {result['findings']}"


def test_a_non_sensitive_cli_action_still_does_not_trip_off_hours(db, actor):
    """오탐 방지 - 계정과 무관한 CLI 동작까지 심야 규칙에 걸리면 안 된다."""
    db.add(AuditLog(
        user_id=actor.id, action="cli.department.create", object_type="department",
        object_id="x", result="success", created_at=MIDNIGHT_KST,
    ))
    db.commit()

    result = _detect(db, MIDNIGHT_KST)
    off_hours = [f for f in result["findings"] if f["kind"] == "off_hours" and f["actor_id"] == actor.id]
    assert not off_hours, f"무관한 CLI 동작이 심야 규칙에 걸렸다: {off_hours}"
