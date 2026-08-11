"""방해금지·알림 뮤트의 **순수 규칙** — 서버도 DB도 없이 값으로 고정한다.

이 파일이 지키는 계약 한 줄: **조용히 하는 것과 삼키는 것은 다르다.** 여기서 판정하는
값(`quiet`)은 배지를 끌지 말지만 정하고, 알림 행이 만들어지는지에는 아무 영향이 없다 —
그건 통합 테스트(tests/integration/test_profile_self_service.py)가 실제 API 로 확인한다.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.profiles import prefs

pytestmark = pytest.mark.unit

# 2026-08-03 04:00 UTC = 13:00 KST (낮). 22:00 UTC = 07:00 KST 다음날(조용시간 안).
NOON_KST = datetime(2026, 8, 3, 4, 0, 0)
EARLY_KST = datetime(2026, 8, 3, 22, 0, 0)  # 다음날 07:00 KST


def _evaluate(now=NOON_KST, **kwargs):
    base = dict(
        dnd_enabled=False, dnd_until=None,
        quiet_hours_enabled=False, quiet_start="22:00", quiet_end="08:00",
    )
    base.update(kwargs)
    return prefs.evaluate_quiet(now=now, **base)


def test_default_is_not_quiet():
    assert _evaluate().quiet is False


def test_manual_dnd_without_deadline_stays_on():
    state = _evaluate(dnd_enabled=True)
    assert state.quiet is True
    assert state.reason == "manual"
    assert state.until is None


def test_manual_dnd_expires_and_reports_it():
    past = datetime(2026, 8, 3, 3, 0, 0)
    state = _evaluate(dnd_enabled=True, dnd_until=past)
    assert state.quiet is False
    # 만료를 따로 알려야 서비스가 상태를 정리할 수 있다 — 안 그러면 화면이
    # '켜짐(하지만 조용하지 않음)'이라는 모순된 상태를 계속 그린다.
    assert state.expired is True


def test_manual_dnd_still_on_before_deadline():
    future = datetime(2026, 8, 3, 5, 0, 0)
    state = _evaluate(dnd_enabled=True, dnd_until=future)
    assert state.quiet is True
    assert state.until == future


def test_quiet_hours_wrap_around_midnight():
    # 22:00~08:00 창. 13:00 KST 는 밖, 07:00 KST 는 안.
    assert _evaluate(quiet_hours_enabled=True, now=NOON_KST).quiet is False
    state = _evaluate(quiet_hours_enabled=True, now=EARLY_KST)
    assert state.quiet is True
    assert state.reason == "quiet_hours"


def test_quiet_hours_use_seoul_wall_clock_not_utc():
    """UTC 로 판정했다면 22:00 UTC 는 창 안(22:00)이라 잘못 조용해진다.

    실제로는 07:00 KST 라 조용한 게 맞지만, 이유가 달라진다 — 그래서 UTC 로 보면
    '조용하지 않아야 할 시각'을 골라 확인한다: 13:00 UTC = 22:00 KST.
    """
    utc_1300 = datetime(2026, 8, 3, 13, 0, 0)  # 22:00 KST → 조용해야 한다
    assert _evaluate(quiet_hours_enabled=True, now=utc_1300).quiet is True
    utc_0000 = datetime(2026, 8, 3, 0, 0, 0)  # 09:00 KST → 조용하면 안 된다
    assert _evaluate(quiet_hours_enabled=True, now=utc_0000).quiet is False


def test_manual_dnd_beats_quiet_hours():
    """방금 누른 것이 예약보다 강하다."""
    state = _evaluate(dnd_enabled=True, quiet_hours_enabled=True, now=NOON_KST)
    assert state.quiet is True
    assert state.reason == "manual"


def test_zero_length_quiet_window_is_never_quiet():
    """start == end 를 24시간으로 해석하면 실수 한 번에 영원히 조용해진다."""
    for now in (NOON_KST, EARLY_KST):
        state = _evaluate(
            quiet_hours_enabled=True, quiet_start="09:00", quiet_end="09:00", now=now
        )
        assert state.quiet is False


def test_quiet_window_end_is_exclusive():
    assert prefs.in_quiet_window(8 * 60, 22 * 60, 8 * 60) is False
    assert prefs.in_quiet_window(22 * 60, 22 * 60, 8 * 60) is True


def test_broken_quiet_time_does_not_silence():
    """형식이 깨진 값 때문에 조용해지면 안 된다 — 실패는 '시끄러운 쪽'으로 기운다."""
    assert _evaluate(quiet_hours_enabled=True, quiet_start="25:00", now=EARLY_KST).quiet is False


@pytest.mark.parametrize("value,expected", [
    ("00:00", 0), ("09:30", 570), ("23:59", 1439),
    ("24:00", None), ("9:30", None), ("", None), (None, None), ("09:60", None),
])
def test_parse_hhmm(value, expected):
    assert prefs.parse_hhmm(value) == expected


def test_muted_types_roundtrip_drops_unknown_keys():
    raw = prefs.serialize_muted(["chat_mentioned", "nope", "job_failed", "chat_mentioned"])
    assert prefs.parse_muted(raw) == ["chat_mentioned", "job_failed"]


def test_validate_muted_reports_rejects_instead_of_silently_dropping():
    valid, rejected = prefs.validate_muted(["job_failed", "made_up", "account_locked"])
    assert valid == ["job_failed"]
    # 보안 알림은 애초에 레지스트리에 없으므로 뮤트 대상이 아니다 → 거부된다.
    assert sorted(rejected) == ["account_locked", "made_up"]


def test_security_notifications_can_never_be_muted():
    for key in prefs.UNMUTABLE_TYPES:
        assert key not in prefs.NOTIFICATION_TYPES
        valid, rejected = prefs.validate_muted([key])
        assert valid == []
        assert rejected == [key]


def test_catalog_covers_every_mutable_type():
    catalog = prefs.notification_type_catalog()
    assert {row["key"] for row in catalog} == set(prefs.NOTIFICATION_TYPES)
    assert all(row["label"] and row["help"] for row in catalog)


# NOTI-03: chat_invited가 이 레지스트리(NOTIFICATION_TYPES)에 없는데 프로덕션에는 실제로
# 발생했다는 기록이 있었다 — 재조사하니 chat_invited 자체는 이미 등록돼 있었지만(오래전
# 정정, 이 낡은 기록만 안 갱신됨), 같은 클래스의 결함이 실제로 여섯 건 더 있었다:
# approval_delegated/approval_overdue/board_comment/document_comment/idea_status_changed/
# ticket_comment가 실제로 알림을 만드는데 레지스트리엔 없어 사용자가 절대 끌 수 없었다.
# 한 번 고치고 끝나는 게 아니라 **재발을 막아야** 한다 — 실제 `notify_user`/`notify_admins`/
# `notify_approvers` 호출부의 `type_=`을 전부 스캔해 NOTIFICATION_TYPES(뮤트 가능) ∪
# UNMUTABLE_TYPES(의도적으로 뮤트 불가) 밖에 있는 유형이 있으면 잡는다.
def _all_notify_type_call_sites() -> set[str]:
    """app/ 전체에서 실제로 쓰이는 `type_="literal"` 값을 정적으로 모은다.

    `notifications/service.py` 자신의 `type_=type_`(내부 전달 매개변수)은 새 유형이
    아니므로 제외한다 — 호출부가 넘기는 실제 리터럴만 센다.

    **한계, 정직하게 남긴다**: 정규식이 문자열 리터럴만 잡는다 — `type_=SOME_CONSTANT`처럼
    상수로 넘기는 호출부(현재 chat_invited/chat_mentioned 두 곳, `app/team_chat/service.py`)는
    이 스캔에 안 잡힌다. 지금은 둘 다 이미 등록돼 있어 새는 곳이 없지만, 상수 기반 호출부가
    늘면 이 가드가 그것까지 잡지는 못한다 — 완전한 정적 분석(AST + import 해석)이 필요하면
    그때 넓힌다.
    """
    import re
    from pathlib import Path

    app_dir = Path(prefs.__file__).resolve().parents[1]
    pattern = re.compile(r'type_="([a-z_]+)"')
    found: set[str] = set()
    for path in app_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        found.update(pattern.findall(text))
    return found


def test_every_notify_call_site_type_is_registered_somewhere():
    all_types = _all_notify_type_call_sites()
    assert all_types, "스캔이 아무것도 못 찾았다 — 정규식이나 경로가 깨졌을 수 있다"
    known = set(prefs.NOTIFICATION_TYPES) | prefs.UNMUTABLE_TYPES
    missing = all_types - known
    assert not missing, (
        f"이 유형들은 실제로 알림을 만드는데 NOTIFICATION_TYPES/UNMUTABLE_TYPES 어디에도 "
        f"없다 — 사용자가 절대 끌 수 없다: {missing}"
    )
