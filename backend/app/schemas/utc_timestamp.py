"""Preserve UTC meaning when SQLite returns timestamps without an offset."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


def as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


UtcTimestamp = Annotated[datetime, AfterValidator(as_utc)]
