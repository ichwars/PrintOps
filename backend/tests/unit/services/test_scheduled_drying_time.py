from datetime import date, datetime, timezone

import pytest

from backend.app.services.drying_schedule_time import daily_occurrence


def test_daily_schedule_has_explicit_timezone():
    assert daily_occurrence(date(2026, 10, 11), "06:30", "Europe/Berlin") == datetime(
        2026, 10, 11, 4, 30, tzinfo=timezone.utc
    )


def test_spring_dst_gap_is_skipped_instead_of_shifted():
    assert daily_occurrence(date(2026, 3, 29), "02:30", "Europe/Berlin") is None


def test_autumn_dst_fold_uses_the_first_occurrence():
    assert daily_occurrence(date(2026, 10, 25), "02:30", "Europe/Berlin") == datetime(
        2026, 10, 25, 0, 30, tzinfo=timezone.utc
    )


@pytest.mark.parametrize("local_time,zone", [("25:00", "UTC"), ("6:30", "UTC"), ("06:30", "Unknown/Zone")])
def test_invalid_wall_time_or_timezone_is_rejected(local_time, zone):
    with pytest.raises(ValueError):
        daily_occurrence(date(2026, 1, 1), local_time, zone)
