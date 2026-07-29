"""Cron evaluation with timezone handling (spec §18.3).

Database timestamps are naive UTC; cron expressions are evaluated in the
schedule's timezone (default Asia/Seoul). cronsim handles DST transitions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cronsim import CronSim, CronSimError

from app.core.errors import ValidationAppError

PRESETS = {
    "daily": "0 9 * * *",       # 매일 09:00
    "weekly": "0 9 * * 1",      # 매주 월요일 09:00
    "monthly": "0 9 1 * *",     # 매월 1일 09:00
}


def validate_timezone(tz_name: str) -> None:
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValidationAppError(f"알 수 없는 timezone입니다: {tz_name}") from None


def validate_cron(expression: str) -> None:
    try:
        CronSim(expression, datetime(2026, 1, 1, tzinfo=timezone.utc))
    except CronSimError as exc:
        raise ValidationAppError(f"Cron 표현식이 올바르지 않습니다: {exc}") from None


def next_after(expression: str, tz_name: str, after_utc: datetime) -> datetime:
    """Next fire time strictly after ``after_utc`` (naive UTC in/out)."""
    validate_timezone(tz_name)
    local = after_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name))
    try:
        iterator = CronSim(expression, local)
        fire_local = next(iterator)
    except CronSimError as exc:
        raise ValidationAppError(f"Cron 표현식이 올바르지 않습니다: {exc}") from None
    return fire_local.astimezone(timezone.utc).replace(tzinfo=None)
