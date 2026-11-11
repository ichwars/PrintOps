"""Keep portable spool data and the local outcome of a backed-up print."""

from datetime import datetime

import pytest
from sqlalchemy import delete, select

from backend.app.models.archive import PrintArchive
from backend.app.models.spool import Spool
from backend.app.services.github_backup import GitHubBackupService
from backend.app.services.github_restore import GitHubRestoreService, _CategoryTally


async def test_git_backup_round_trips_usage_reset_and_last_use(db_session):
    used_at = datetime(2026, 11, 9, 11, 30)
    db_session.add(Spool(material="PLA", weight_used=500, weight_used_baseline=300, last_used=used_at))
    await db_session.commit()
    files = {}
    await GitHubBackupService()._collect_spools(db_session, files)
    entry = files["spools/inventory.json"]["spools"][0]
    assert entry["weight_used_baseline"] == 300
    assert entry["last_used"] == used_at.isoformat()

    await db_session.execute(delete(Spool))
    await db_session.commit()
    await GitHubRestoreService()._restore_spools(
        db_session, files["spools/inventory.json"], None, False, _CategoryTally(), {}
    )
    await db_session.commit()
    restored = await db_session.scalar(select(Spool))
    assert (restored.weight_used, restored.weight_used_baseline, restored.last_used) == (500, 300, used_at)


@pytest.mark.parametrize("late_fields", [{}, {"weight_used_baseline": -1, "last_used": "invalid"}])
async def test_older_spool_snapshot_preserves_live_late_fields(db_session, late_fields):
    used_at = datetime(2026, 11, 9, 11, 30)
    spool = Spool(material="PLA", tag_uid="ABCD1234", weight_used_baseline=300, last_used=used_at)
    db_session.add(spool)
    await db_session.commit()
    snapshot = {"spools": [{"id": 77, "tag_uid": "ABCD1234", "material": "PLA", **late_fields}]}
    await GitHubRestoreService()._restore_spools(db_session, snapshot, None, True, _CategoryTally(), {})
    await db_session.commit()
    await db_session.refresh(spool)
    assert (spool.weight_used_baseline, spool.last_used) == (300, used_at)


@pytest.mark.parametrize("source_status", ["printing", "paused"])
async def test_imported_archive_snapshot_is_closed_and_existing_outcome_is_retained(db_session, source_status):
    service = GitHubRestoreService()
    snapshot = {
        "archives": [
            {
                "id": 71,
                "filename": "part.3mf",
                "content_hash": "a" * 64,
                "started_at": "2026-11-09T11:00:00",
                "status": source_status,
            }
        ]
    }
    await service._restore_archives(db_session, snapshot, False, _CategoryTally(), {})
    await db_session.commit()
    archive = await db_session.scalar(select(PrintArchive))
    assert (archive.status, archive.failure_reason) == ("aborted", "noStatusUpdate")
    assert archive.completed_at is None

    completed_at = datetime(2026, 11, 9, 12)
    archive.status, archive.failure_reason, archive.completed_at = "failed", "nozzleClog", completed_at
    archive.filament_used_grams = 18
    archive.cost = 0.9
    await db_session.commit()
    await service._restore_archives(db_session, snapshot, True, _CategoryTally(), {})
    await db_session.commit()
    await db_session.refresh(archive)
    assert (archive.status, archive.failure_reason, archive.completed_at) == ("failed", "nozzleClog", completed_at)
    assert (archive.filament_used_grams, archive.cost) == (18, 0.9)
