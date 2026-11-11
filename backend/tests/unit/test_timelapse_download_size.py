"""Timelapse transfers use listing size without occupying a DB connection."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.api.routes import archives
from backend.app.core.auth import OwnershipAccess


@pytest.mark.asyncio
@pytest.mark.parametrize("retry", [False, True])
@pytest.mark.parametrize("manual", [False, True])
async def test_large_timelapse_releases_db_and_passes_size_to_the_transfer(retry, manual):
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = SimpleNamespace(
        ip_address="192.0.2.10", access_code="fixture", model="X1C"
    )
    db.execute.return_value = result
    service = MagicMock()
    service.get_archive = AsyncMock(
        return_value=SimpleNamespace(
            id=1,
            printer_id=1,
            deleted_at=None,
            timelapse_path=None,
            filename="part.3mf",
            print_name="part",
            started_at=None,
            completed_at=None,
            created_at=None,
        )
    )
    service.attach_timelapse = AsyncMock(return_value=True)
    listing = [{"name": "part.avi", "path": "/timelapse/part.avi", "size": 75_647_046, "is_directory": False}]

    async def transfer(*args, **kwargs):
        db.close.assert_awaited_once()
        assert kwargs["total_bytes"] == 75_647_046
        return b"video fixture"

    with (
        patch.object(archives, "ArchiveService", return_value=service),
        patch("backend.app.services.bambu_ftp.list_files_async", AsyncMock(return_value=listing)),
        patch("backend.app.services.bambu_ftp.get_ftp_retry_settings", AsyncMock(return_value=(retry, 0, 0, 30))),
        patch("backend.app.services.bambu_ftp.download_file_bytes_async", AsyncMock(side_effect=transfer)),
    ):
        response = (
            await archives.select_timelapse(1, filename="part.avi", db=db, access=OwnershipAccess(None, True))
            if manual
            else await archives.scan_timelapse(1, db=db, access=OwnershipAccess(None, True))
        )
    assert response["status"] == "attached"
    service.attach_timelapse.assert_awaited_once_with(
        1,
        b"video fixture",
        "part.avi",
        expected_started_at=None,
        **({} if manual else {"replace": False}),
    )
