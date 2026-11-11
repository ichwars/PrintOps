"""Git metadata restores every print without resuming a backup's live jobs."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select

from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, PrintLogEntry
from backend.app.schemas.github_backup import RestoreCategory
from backend.app.services.github_backup import github_backup_service
from backend.app.services.github_restore import RUNS_PATH, GitHubRestoreService
from backend.app.services.print_log import write_log_entry

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def archived_runs(db_session, printer_factory, archive_factory):
    first = await printer_factory()
    second = await printer_factory()
    started = datetime(2026, 11, 10, 9)
    archive = await archive_factory(
        second.id,
        with_run=False,
        content_hash="a" * 64,
        started_at=started + timedelta(hours=2),
        status="printing",
        plate_id=2,
    )
    run = await write_log_entry(
        db_session,
        status="completed",
        archive_id=archive.id,
        printer_id=first.id,
        printer_name=first.name,
        started_at=started,
        completed_at=started + timedelta(hours=1),
        plate_id=1,
        filament_used_grams=22,
        cost=0.85,
        energy_kwh=0.15,
    )
    run.quantity, run.good_quantity, run.reject_quantity = 2, 1, 1
    run.user_verdict = "mixed"
    run.confirm_requested = True
    run.confirm_token_hash = "f" * 64
    await write_log_entry(
        db_session,
        status="printing",
        archive_id=archive.id,
        printer_id=second.id,
        printer_name=second.name,
        started_at=archive.started_at,
        plate_id=2,
    )
    await db_session.commit()
    return archive, first, second


async def test_git_restore_preserves_history_and_does_not_revive_a_running_print(db_session, archived_runs):
    _, first, second = archived_runs
    files = {}
    await github_backup_service._collect_archives(db_session, files)
    records = files[RUNS_PATH]["runs"]
    assert len(records) == 2 and records[1]["status"] == "printing"
    assert all("confirm_token_hash" not in row and "energy_start_kwh" not in row for row in records)

    await db_session.execute(delete(PrintLogEntry).execution_options(**{INCLUDE_OPEN_RUNS: True}))
    await db_session.execute(delete(PrintArchive))
    await db_session.commit()
    service = GitHubRestoreService()
    result = await service._apply(db_session, files, [RestoreCategory.ARCHIVES], False)
    assert result["archives"].restored == 3
    archive = await db_session.scalar(select(PrintArchive))
    runs = (await db_session.scalars(select(PrintLogEntry).order_by(PrintLogEntry.started_at))).all()
    assert [(r.archive_id, r.printer_id, r.status, r.plate_id) for r in runs] == [
        (archive.id, first.id, "completed", 1),
        (archive.id, second.id, "aborted", 2),
    ]
    assert archive.status == "aborted" and archive.plate_id == 2
    assert (runs[0].good_quantity, runs[0].reject_quantity, runs[0].user_verdict) == (1, 1, "mixed")
    assert (runs[0].cost, runs[0].energy_kwh, runs[0].duration_seconds) == (0.85, 0.15, 3600)
    assert runs[0].confirm_token_hash is None and runs[1].duration_unmeasured is True
    result = await service._apply(db_session, files, [RestoreCategory.ARCHIVES], False)
    assert result["archives"].skipped == 3 and result["archives"].restored == 0


async def test_git_restore_recognises_an_archive_with_newer_local_prints(db_session, archived_runs):
    archive, _, second = archived_runs
    files = {}
    await github_backup_service._collect_archives(db_session, files)
    archive.started_at += timedelta(days=1)
    await write_log_entry(
        db_session,
        status="completed",
        archive_id=archive.id,
        printer_id=second.id,
        printer_name=second.name,
        started_at=archive.started_at,
        plate_id=3,
    )
    await db_session.commit()
    service = GitHubRestoreService()
    result = await service._apply(db_session, files, [RestoreCategory.ARCHIVES], True)
    assert result["archives"].skipped == 2 and result["archives"].restored == 1
    rows = (await db_session.scalars(select(PrintArchive))).all()
    assert [row.id for row in rows] == [archive.id]
    all_runs = (await db_session.scalars(select(PrintLogEntry).execution_options(**{INCLUDE_OPEN_RUNS: True}))).all()
    assert len(all_runs) == 3
