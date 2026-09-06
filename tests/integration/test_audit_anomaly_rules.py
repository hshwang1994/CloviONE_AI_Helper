"""이상 징후 규칙이 **실제로 있었던 일만** 말한다 (app/audit/anomalies.py).

## 무엇이 문제였나

두 가지가 같은 화면에서 동시에 거짓이었다.

1. `SENSITIVE_ACTION_PREFIXES` 의 첫 항목이 `user.` 라 로그인·로그아웃까지 「설정, 권한
   관련 동작」으로 분류됐다. 밤에 평범하게 로그인한 사람마다 이름과 함께 「심야에 설정,
   권한을 바꿨습니다」가 떴다 — 30일 창에서는 소견 아홉 건 중 일곱 건이 그 오탐이었다.
2. 「처음 하는 동작」 규칙의 비교 구간이 조회 창에 매여 함께 미끄러졌다. 창을 넓히면
   비교 구간이 데이터가 없는 과거로 밀려나 규칙 자체가 조용히 사라졌고, 그래서 기간을
   넓힌 관리자가 **소견이 줄어드는 것**을 보고 「괜찮아졌다」로 읽었다. 빈 상태 안내가
   「기간을 늘려 다시 보세요」라고 시키기까지 하는 화면에서 그랬다.

## 무엇을 고정하는가

  * 심야의 로그인·로그아웃은 소견을 만들지 않는다. 심야의 **계정 조작**은 그대로 만든다.
  * 비교 구간은 `now` 에 매인다 — 창보다 오래된 과거 기록만 있어도 규칙이 돈다.
  * 비교 구간이 정말 비면 규칙을 조용히 건너뛰지 않고 `skipped_rules` 로 이유를 말한다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.audit.anomalies import RULE_NEW_ACTOR_ACTION, detect
from app.audit.models import AuditLog

pytestmark = pytest.mark.integration

# UTC 15:00 = KST 24:00 — 심야 규칙(22:00~07:00 KST) 한가운데다.
NIGHT = datetime(2026, 7, 13, 15, 0, 0)


@pytest.fixture()
def actor(db, make_user):
    return make_user("anomaly-actor@goodmit.co.kr", role="admin", display_name="이상탐지 대상")


def _log(db, actor, action: str, *, at: datetime, result: str = "success") -> None:
    db.add(AuditLog(
        user_id=actor.id, action=action, object_type="user", object_id=actor.id,
        result=result, created_at=at,
    ))


def _kinds(result: dict, actor, kind: str) -> list[dict]:
    return [
        f for f in result["findings"]
        if f["kind"] == kind and f["actor_id"] == actor.id
    ]


def test_a_night_time_login_is_not_reported_as_a_settings_change(db, actor):
    """로그인은 상태를 바꾸지도 권한에 닿지도 않는다 — 모듈 자신의 규칙이 그렇게 적혀 있다."""
    for minutes in range(3):
        _log(db, actor, "user.login", at=NIGHT + timedelta(minutes=minutes))
    _log(db, actor, "user.logout", at=NIGHT + timedelta(minutes=5))
    _log(db, actor, "user.login_failed", at=NIGHT + timedelta(minutes=6), result="failure")
    db.commit()

    result = detect(db, now=NIGHT + timedelta(minutes=10), actor_ids=None)
    assert _kinds(result, actor, "off_hours") == [], (
        "평범한 로그인이 「심야에 설정, 권한을 바꿨습니다」로 보고됐다"
    )
    assert _kinds(result, actor, "new_actor_action") == [], (
        "평범한 로그인이 「처음 하는 설정, 권한 관련 동작」으로 보고됐다"
    )


def test_a_night_time_account_change_is_still_reported(db, actor):
    """반례 — 심야 규칙 자체는 살아 있다. 계정을 실제로 만진 것은 그대로 잡힌다."""
    _log(db, actor, "user.login", at=NIGHT)
    _log(db, actor, "user.disable", at=NIGHT + timedelta(minutes=1))
    db.commit()

    result = detect(db, now=NIGHT + timedelta(minutes=10), actor_ids=None)
    off_hours = _kinds(result, actor, "off_hours")
    assert off_hours, f"심야 계정 조작이 안 잡혔다: {result['findings']}"
    assert off_hours[0]["count"] == 1, "로그인까지 함께 세고 있다"
    assert all("user.disable" in e for e in off_hours[0]["evidence"])


def test_a_failed_login_burst_is_still_caught_by_the_failure_rule(db, actor):
    """반례 — 로그인을 민감 목록에서 뺐다고 로그인 실패 탐지가 죽지 않는다.
    `failure_burst` 는 action 이 아니라 `result` 로만 판정한다."""
    for minutes in range(6):
        _log(db, actor, "user.login_failed", at=NIGHT + timedelta(minutes=minutes), result="failure")
    db.commit()

    result = detect(db, now=NIGHT + timedelta(minutes=10), actor_ids=None)
    burst = _kinds(result, actor, "failure_burst")
    assert burst, f"로그인 실패 급증이 안 잡혔다: {result['findings']}"
    assert burst[0]["count"] == 6


def test_the_new_actor_rule_runs_even_when_history_is_older_than_the_window(db, actor):
    """비교 구간이 창과 함께 미끄러지지 않는다.

    50일 전의 계정 조작 한 건이 이 계정의 유일한 과거다. 예전에는 비교 구간이
    `창 시작 - 30일 ~ 창 시작` 이라 그 기록이 구간 밖으로 밀려났고, 비교 구간이 비면
    규칙 전체를 건너뛰었으므로 **최근 24시간을 보는 화면에서 이 규칙이 통째로 사라졌다.**
    """
    now = NIGHT
    _log(db, actor, "user.enable", at=now - timedelta(days=50))
    _log(db, actor, "feature_flag.update", at=now - timedelta(hours=1))
    db.commit()

    result = detect(db, now=now, actor_ids=None, window_hours=24)
    fresh = _kinds(result, actor, RULE_NEW_ACTOR_ACTION)
    assert fresh, f"창보다 오래된 과거만 있으면 규칙이 사라진다: {result}"
    assert fresh[0]["evidence"] == ["feature_flag.update"]
    assert result["skipped_rules"] == []


def test_widening_the_window_does_not_drop_the_finding(db, actor):
    """같은 데이터에서 창을 넓혀도 소견이 사라지지 않는다 — 화면의 빈 상태 안내가
    「기간을 늘려 다시 보세요」라고 말하는 이상, 넓힌 결과가 더 조용하면 그 안내가 거짓이다."""
    now = NIGHT
    _log(db, actor, "user.enable", at=now - timedelta(days=50))
    _log(db, actor, "feature_flag.update", at=now - timedelta(hours=1))
    db.commit()

    narrow = detect(db, now=now, actor_ids=None, window_hours=24)
    wide = detect(db, now=now, actor_ids=None, window_hours=24 * 30)
    assert len(wide["findings"]) >= len(narrow["findings"]), (
        f"창을 넓혔더니 소견이 줄었다: {len(narrow['findings'])} -> {len(wide['findings'])}"
    )
    assert _kinds(wide, actor, RULE_NEW_ACTOR_ACTION), "넓은 창에서 규칙이 사라졌다"


def test_an_empty_baseline_is_reported_instead_of_silently_skipped(db, actor):
    """비교할 과거가 정말 없으면 규칙은 못 돈다 — 그때는 그 사실을 응답이 말한다."""
    now = NIGHT
    _log(db, actor, "feature_flag.update", at=now - timedelta(hours=1))
    db.commit()

    result = detect(db, now=now, actor_ids=None, window_hours=24)
    assert _kinds(result, actor, RULE_NEW_ACTOR_ACTION) == []
    assert len(result["skipped_rules"]) == 1, result["skipped_rules"]
    skipped = result["skipped_rules"][0]
    assert skipped["kind"] == RULE_NEW_ACTOR_ACTION
    assert skipped["reason"].endswith("."), f"완결된 문장이 아니다: {skipped['reason']!r}"
