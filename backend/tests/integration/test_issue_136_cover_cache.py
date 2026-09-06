"""Cover retries coordinate with the shared 3MF cache (#136)."""

import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from backend.app.api.routes.printers import _cover_404_cache, _cover_cache
from backend.app.services.bambu_ftp import cache_3mf_download, clear_3mf_cache
from backend.app.services.bambu_mqtt import PrinterState


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cover_retry_reuses_3mf_published_by_archive_flow(
    async_client: AsyncClient, printer_factory, db_session, tmp_path
):
    """A retry must not fetch a 3MF published while attempt one ran."""
    printer = await printer_factory()
    _cover_cache.pop(printer.id, None)
    _cover_404_cache.pop(printer.id, None)
    clear_3mf_cache(printer.id, delete_files=False)

    source = tmp_path / "CacheRace.gcode.3mf"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Metadata/plate_1.png", b"CACHE_RACE_PNG")

    state = PrinterState()
    state.connected = True
    state.state = "RUNNING"
    state.subtask_name = "CacheRace"
    state.gcode_file = "CacheRace.3mf"

    async def publish_after_failed_attempt(*args, **kwargs):
        cache_3mf_download(printer.id, "CacheRace.gcode.3mf", source)
        return False

    ftp_mock = AsyncMock(side_effect=publish_after_failed_attempt)
    with (
        patch("backend.app.api.routes.printers.printer_manager") as printer_manager,
        patch("backend.app.api.routes.printers.download_file_try_paths_async", ftp_mock),
    ):
        printer_manager.get_status = MagicMock(return_value=state)
        printer_manager.is_awaiting_plate_clear = MagicMock(return_value=False)
        response = await async_client.get(f"/api/v1/printers/{printer.id}/cover")

    assert response.status_code == 200
    assert response.content == b"CACHE_RACE_PNG"
    assert ftp_mock.await_count == 1
