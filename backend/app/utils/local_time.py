"""Local timezone helpers for calendar-day calculations."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone, tzinfo
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
