"""Interpret persisted history retention before deleting old records."""

from datetime import datetime, timedelta


def history_cutoff(now: datetime, stored: str | None, default: int) -> datetime:
    try:
        days = max(1, int(stored)) if stored is not None else default
    except ValueError:
        days = default
    return now - timedelta(days=min(days, (now - datetime.min).days))
