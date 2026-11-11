"""A printer file that could not be fetched is not reported as missing (TO-C2, TO-C3, TO-C1).

The file browser's previews (G-code, plates, plate thumbnails) and its single
file download answered every failure with 404 "File not found", including a
timeout on a file the browser had just listed. They now answer 404 only when
the printer says the path is not there, 502 when the download failed, and 504
when it ran out of the time its size allows. The timelapse scan answered a
failed download with 500; it now gives 502, and 504 for a deadline.
"""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from backend.app.services.bambu_ftp import DownloadDeadlineExceeded, FileNotOnPrinterError

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PREVIEWS = [
    ("/files/gcode", {"path": "/cache/part.gcode"}),
    ("/files/plates", {"path": "/cache/part.3mf"}),
    ("/files/plate-thumbnail/1", {"path": "/cache/part.3mf"}),
]


@pytest.mark.parametrize(("route", "params"), PREVIEWS)
@pytest.mark.parametrize(
    ("outcome", "status"),
    [
        (FileNotOnPrinterError("/cache/part"), 404),
        (None, 502),
        (DownloadDeadlineExceeded("/cache/part"), 504),
    ],
)
async def test_a_preview_says_what_went_wrong(
    async_client: AsyncClient, printer_factory, route, params, outcome, status
):
    printer = await printer_factory()
    download = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)

    with patch("backend.app.api.routes.printer_files.download_file_bytes_async", download):
        resp = await async_client.get(f"/api/v1/printers/{printer.id}{route}", params=params)

    assert resp.status_code == status, resp.text
    # One FTP session per preview: the plate picker asks once per plate.
    assert download.await_count == 1
    assert download.await_args.kwargs["raise_on_not_found"] is True
    # The file browser's budget: with print start's 300 s ceiling a slow file
    # would get no more than the flat base deadline.
    from backend.app.services.printer_file_preview import MAX_PREVIEW_TRANSFER_SECONDS

    assert download.await_args.kwargs["max_total_timeout"] == MAX_PREVIEW_TRANSFER_SECONDS


@pytest.mark.parametrize(
    ("outcome", "status"),
    [(None, 502), (DownloadDeadlineExceeded("/timelapse/t.mp4"), 504)],
)
async def test_a_timelapse_scan_says_what_went_wrong(
    async_client: AsyncClient, archive_factory, printer_factory, outcome, status
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, filename="t.gcode.3mf")
    listing = [
        {"name": "t.gcode.mp4", "path": "/timelapse/t.gcode.mp4", "is_directory": False, "size": 10, "mtime": None}
    ]
    download = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)

    with (
        patch("backend.app.services.bambu_ftp.list_files_async", AsyncMock(return_value=listing)),
        patch("backend.app.services.bambu_ftp.get_ftp_retry_settings", AsyncMock(return_value=(True, 3, 0.0, 30.0))),
        patch("backend.app.services.bambu_ftp.download_file_bytes_async", download),
    ):
        resp = await async_client.post(f"/api/v1/archives/{archive.id}/timelapse/scan")

    assert resp.status_code == status, resp.text
    if status == 504:
        assert download.await_count == 1  # a size-fitted deadline is not retried
