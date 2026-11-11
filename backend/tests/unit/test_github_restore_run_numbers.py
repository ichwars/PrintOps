"""Malformed backup numbers cannot become production or consumption values."""

import pytest
from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.models.spool_usage_history import SpoolUsageHistory
from backend.app.services.github_restore import GitHubRestoreService, _CategoryTally

pytestmark = pytest.mark.asyncio


async def test_restoring_archive_numbers_keeps_zero_quantity_and_omits_invalid_values(db_session):
    payload = {
        "archives": [
            {
                "id": 1,
                "filename": "fixture.gcode.3mf",
                "filament_used_grams": 100_001,
                "print_time_seconds": 2**31,
                "cost": float("inf"),
                "energy_kwh": float("nan"),
                "energy_cost": True,
                "quantity": 0,
                "plate_id": 2,
            }
        ]
    }
    tally = _CategoryTally()
    await GitHubRestoreService()._restore_archives(db_session, payload, False, tally, {})
    archive = await db_session.scalar(select(PrintArchive))
    assert archive.quantity == 0 and archive.plate_id == 2
    assert archive.cost is archive.energy_kwh is archive.energy_cost is None
    assert archive.filament_used_grams is archive.print_time_seconds is None
    assert "archivesNumbersDropped" in {note["code"] for note in tally.notes}


async def test_restore_deduplicates_consumption_after_invalid_values_are_reset(db_session):
    payload = {
        "usage_history": [
            {
                "spool_id": None,
                "print_name": "Fixture",
                "weight_used": float("inf"),
                "percent_used": 1.5,
                "cost": -2,
                "created_at": "2026-11-11T14:00:00Z",
            }
        ]
    }
    service = GitHubRestoreService()
    tally = _CategoryTally()
    await service._restore_spool_usage(db_session, payload, tally, {}, {})
    await db_session.flush()
    await service._restore_spool_usage(db_session, payload, tally, {}, {})
    assert tally.restored == 1 and tally.skipped == 1
    assert [note["code"] for note in tally.notes] == ["usageNumbersDropped"]
    row = (await db_session.scalars(select(SpoolUsageHistory))).one()
    assert (row.weight_used, row.percent_used, row.cost) == (0, 0, None)
