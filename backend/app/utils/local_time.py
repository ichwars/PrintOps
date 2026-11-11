"""Local timezone helpers for calendar-day calculations."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def local_zone() -> tzinfo:
    """Resolve the local timezone from TZ, falling back to UTC."""
    tz_name = os.environ.get("TZ", "").strip()
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            logger.warning("Unrecognised TZ env value %r, falling back to UTC", tz_name)
    try:
        return ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        return timezone.utc


def day_zone(name: str | None = None) -> tzinfo:
    """Resolve a caller's IANA zone or use the appliance zone."""
    if name:
        try:
            return ZoneInfo(name)
        except (ValueError, ZoneInfoNotFoundError):
            pass
    return local_zone()


def local_date_start(day: date, zone: tzinfo) -> datetime:
    """Convert local midnight to the naive UTC used by persisted timestamps."""
    if day == date.min:
        return datetime.min
    return datetime.combine(day, time.min, zone).astimezone(timezone.utc).replace(tzinfo=None)


def local_date_end(day: date, zone: tzinfo) -> datetime:
    if day == date.max:
        return datetime.max
    return local_date_start(day + timedelta(days=1), zone) - timedelta(microseconds=1)


def calendar_bounds(
    date_from: date | None, date_to: date | None, tz: str | None = None
) -> tuple[datetime | None, datetime | None]:
    if not (date_from or date_to):
        return None, None
    zone = day_zone(tz)
    return local_date_start(date_from, zone) if date_from else None, local_date_end(date_to, zone) if date_to else None


def parse_calendar_bound(value: str, tz: str | None = None, *, end: bool = False) -> datetime:
    """Date-only filters span local days. Explicit timestamps retain their offset."""
    if len(value) == 10:
        day = date.fromisoformat(value)
        return (local_date_end if end else local_date_start)(day, day_zone(tz))
    return datetime.fromisoformat(value)


def utcnow_naive() -> datetime:
    """Return the current UTC instant without tzinfo for naive DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: datetime | None) -> datetime | None:
    """Normalise an aware or naive datetime to naive UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def local_day_start(now_utc: datetime, *, days_ago: int = 0) -> datetime:
    """Return local midnight days_ago as a UTC instant."""
    tz = local_zone()
    local_now = now_utc.astimezone(tz)
    local_midnight = local_now.replace(hour=0, minute=0, second=0, microsecond=0, fold=0)
    if days_ago:
        local_midnight = (local_midnight - timedelta(days=days_ago)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
            fold=0,
        )
    return local_midnight.astimezone(timezone.utc)


def next_local_hour(now_utc: datetime) -> datetime:
    """Return the next top-of-the-hour local time as a UTC instant."""
    tz = local_zone()
    local_now = now_utc.astimezone(tz)
    local_next = (local_now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0, fold=0)
    return local_next.astimezone(timezone.utc)
