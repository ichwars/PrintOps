"""Daily IANA wall-clock occurrences, with explicit DST behavior."""

import re
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def daily_occurrence(day: date, local_time: str, zone: str) -> datetime | None:
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", local_time):
        raise ValueError("Use HH:MM in 24-hour format")
    try:
        tz = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Use an IANA timezone") from exc
    wall = datetime.combine(day, time.fromisoformat(local_time))
    first = wall.replace(tzinfo=tz, fold=0).astimezone(timezone.utc)
    if first.astimezone(tz).replace(tzinfo=None) != wall:
        return None
    return first
