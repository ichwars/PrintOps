"""Git backup regression coverage for selected archive plates (#138)."""

from datetime import datetime

import pytest
from sqlalchemy import select

from backend.app.models.archive import PrintArchive
from backend.app.services.github_backup import github_backup_service
from backend.app.services.github_restore import ARCHIVES_PATH, GitHubRestoreService, _CategoryTally


@pytest.mark.asyncio
async def test_plate_id_survives_collect_then_restore(db_session):
    db_session.add(
        PrintArchive(
            filename="multi.3mf",
            file_path="",
            file_size=1024,
            content_hash="hash-plate-4",
            started_at=datetime(2026, 9, 6, 10, 0, 0),
            plate_id=4,
        )
    )
    await db_session.commit()

    files: dict = {}
    await github_backup_service._collect_archives(db_session, files)
    payload = files[ARCHIVES_PATH]
    assert payload["archives"][0]["plate_id"] == 4

    await db_session.execute(PrintArchive.__table__.delete())
    await db_session.commit()
    await GitHubRestoreService()._restore_archives(db_session, payload, False, _CategoryTally(), {})
    await db_session.commit()

    row = (await db_session.execute(select(PrintArchive))).scalar_one()
    assert row.plate_id == 4
