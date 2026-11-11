"""The real plate routes share one transfer and invalidate changed printer files."""

import asyncio
import io
import zipfile
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.bambu_ftp import DeleteResult

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def archive_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for index in (1, 2):
            z.writestr(f"Metadata/plate_{index}.gcode", "G1 X0")
            z.writestr(f"Metadata/plate_{index}.png", f"png{index}".encode())
    return buffer.getvalue()


async def test_plate_list_and_thumbnails_use_one_ftp_download(async_client, printer_factory):
    printer = await printer_factory()
    download = AsyncMock(return_value=archive_bytes())
    with patch("backend.app.api.routes.printer_files.download_file_bytes_async", download):
        base = f"/api/v1/printers/{printer.id}/files"
        responses = await asyncio.gather(
            async_client.get(base + "/plates", params={"path": "/cache/part.3mf"}),
            async_client.get(base + "/plate-thumbnail/1", params={"path": "/cache/part.3mf"}),
            async_client.get(base + "/plate-thumbnail/2", params={"path": "/cache/part.3mf"}),
        )
    assert [r.status_code for r in responses] == [200, 200, 200]
    assert len(responses[0].json()["plates"]) == 2
    assert responses[1].content == b"png1" and responses[2].content == b"png2"
    download.assert_awaited_once()


@pytest.mark.parametrize("result,status", [(DeleteResult.DELETED, 200), (DeleteResult.NOT_FOUND, 404)])
async def test_file_delete_discards_the_preview_even_if_already_missing(async_client, printer_factory, result, status):
    printer = await printer_factory()
    download = AsyncMock(return_value=archive_bytes())
    path = "/cache/part.3mf"
    base = f"/api/v1/printers/{printer.id}/files"
    with (
        patch("backend.app.api.routes.printer_files.download_file_bytes_async", download),
        patch("backend.app.api.routes.printer_files.delete_file_async", AsyncMock(return_value=result)),
    ):
        assert (await async_client.get(base + "/plates", params={"path": path})).status_code == 200
        assert (await async_client.delete(base, params={"path": path})).status_code == status
        assert (await async_client.get(base + "/plates", params={"path": path})).status_code == 200
    assert download.await_count == 2


async def test_connection_update_discards_the_old_printer_preview(async_client, printer_factory):
    printer = await printer_factory()
    download = AsyncMock(return_value=archive_bytes())
    url = f"/api/v1/printers/{printer.id}/files/plates"
    with patch("backend.app.api.routes.printer_files.download_file_bytes_async", download):
        assert (await async_client.get(url, params={"path": "/part.3mf"})).status_code == 200
        with patch("backend.app.api.routes.printers.printer_manager") as manager:
            manager.connect_printer = AsyncMock()
            response = await async_client.patch(f"/api/v1/printers/{printer.id}", json={"ip_address": "192.0.2.20"})
        assert response.status_code == 200
        assert (await async_client.get(url, params={"path": "/part.3mf"})).status_code == 200
    assert download.await_count == 2
