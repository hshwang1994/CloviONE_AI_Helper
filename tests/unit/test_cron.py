from datetime import datetime

import pytest

from app.core.errors import ValidationAppError
from app.schedules import cron

pytestmark = pytest.mark.unit


def test_invalid_cron_rejected():
    with pytest.raises(ValidationAppError):
        cron.validate_cron("99 99 * * *")
    with pytest.raises(ValidationAppError):
        cron.validate_cron("not a cron")


def test_valid_cron_and_presets():
    cron.validate_cron("*/5 * * * *")
    for expr in cron.PRESETS.values():
        cron.validate_cron(expr)


def test_invalid_timezone_rejected():
    with pytest.raises(ValidationAppError):
        cron.validate_timezone("Mars/Olympus")


def test_asia_seoul_9am_is_midnight_utc():
    # 09:00 KST == 00:00 UTC (KST = UTC+9, no DST).
    after = datetime(2026, 7, 14, 10, 0, 0)  # 19:00 KST
    fire = cron.next_after("0 9 * * *", "Asia/Seoul", after)
    assert fire == datetime(2026, 7, 15, 0, 0, 0)


def test_next_after_is_strictly_after():
    # Exactly at the fire time → next occurrence, not the same one.
    at_fire = datetime(2026, 7, 15, 0, 0, 0)
    fire = cron.next_after("0 9 * * *", "Asia/Seoul", at_fire)
    assert fire == datetime(2026, 7, 16, 0, 0, 0)


def test_dst_spring_forward_new_york():
    # US DST 2026: clocks jump 02:00→03:00 on 2026-03-08.
    # A 02:30 daily cron cannot fire at a nonexistent local time — cronsim
    # must produce a valid next occurrence without crashing or looping.
    after = datetime(2026, 3, 8, 5, 0, 0)  # 00:00 EST local
    fire = cron.next_after("30 2 * * *", "America/New_York", after)
    assert fire > after
    # And the following day resolves normally (02:30 EDT == 06:30 UTC).
    next_day = cron.next_after("30 2 * * *", "America/New_York", fire)
    assert next_day.hour == 6 and next_day.minute == 30


def test_dst_fall_back_new_york():
    # 2026-11-01: clocks fall back 02:00→01:00 (01:30 happens twice).
    after = datetime(2026, 11, 1, 4, 0, 0)
    fire = cron.next_after("30 1 * * *", "America/New_York", after)
    assert fire > after
