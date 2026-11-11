"""Offset-bearing CSV values must survive SQLite's naive UTC storage."""

from datetime import datetime

import pytest

from backend.app.services.spool_csv import _parse_datetime


@pytest.mark.parametrize("value", ["2026-11-09T15:00:00+02:00", "2026-11-09T13:00:00Z", "2026-11-09T13:00:00"])
def test_timestamp_is_normalized_to_naive_utc(value):
    assert _parse_datetime(value) == datetime(2026, 11, 9, 13)
