"""A slow listing is distinct from an unavailable printer or an empty folder."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.bambu_ftp import FileListResult


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "available,slow,warnings",
    [
        (False, True, ["listing_timed_out"]),
        (False, False, ["printer_unavailable"]),
        (True, False, []),
    ],
)
async def test_file_list_reports_transport_state(async_client, available, slow, warnings):
    with (
        patch(
            "backend.app.api.routes.printer_files._load_printer_or_404",
            AsyncMock(return_value=SimpleNamespace(ip_address="192.0.2.1", access_code="fixture", model="P1S")),
        ),
        patch(
            "backend.app.api.routes.printer_files.list_files_result_async",
            AsyncMock(return_value=FileListResult([], available, slow)),
        ),
    ):
        response = await async_client.get("/api/v1/printers/1/files?path=/ipcam")
    assert response.status_code == 200
    assert response.json() == {"path": "/ipcam", "files": [], "warnings": warnings}
