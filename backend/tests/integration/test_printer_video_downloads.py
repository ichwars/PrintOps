"""Printer videos stay inside the authorized printer-file download boundary."""

import asyncio
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

import pytest
from httpx import AsyncClient

from backend.app.services.bambu_ftp import FileNotOnPrinterError


@pytest.mark.asyncio
async def test_download_is_streaming_and_preserves_size_and_filename(async_client, printer_factory):
    printer = await printer_factory()
    payload = b"video" * 20000

    async def chunks(*args, **kwargs):
        for start in range(0, len(payload), 65536):
            yield payload[start : start + 65536]

    with (
        patch("backend.app.api.routes.printer_files.stream_printer_file", chunks),
        patch("backend.app.api.routes.printer_files.get_file_size_async", AsyncMock(return_value=len(payload))),
    ):
        response = await asyncio.wait_for(
            async_client.get(f"/api/v1/printers/{printer.id}/files/download", params={"path": "/ipcam/video.mp4"}),
            timeout=2,
        )
    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["content-length"] == str(len(payload))
    assert "attachment" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_missing_video_returns_404_instead_of_empty_download(async_client, printer_factory):
    printer = await printer_factory()

    async def missing(*args, **kwargs):
        raise FileNotOnPrinterError("missing")
        yield b""

    with (
        patch("backend.app.api.routes.printer_files.stream_printer_file", missing),
        patch("backend.app.api.routes.printer_files.get_file_size_async", AsyncMock(return_value=None)),
    ):
        response = await async_client.get(
            f"/api/v1/printers/{printer.id}/files/download", params={"path": "/ipcam/missing.mp4"}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/ipcam/../secret.mp4", "/ipcam/video.mp4\r\nDELE /data", "relative.mp4", "/"])
async def test_bad_remote_paths_are_rejected_before_ftp(async_client, printer_factory, path):
    printer = await printer_factory()
    with patch("backend.app.api.routes.printer_files.get_file_size_async", AsyncMock()) as size:
        response = await async_client.get(f"/api/v1/printers/{printer.id}/files/download", params={"path": path})
    assert response.status_code == 400
    size.assert_not_awaited()


@pytest.mark.asyncio
async def test_auth_enabled_video_download_rejects_anonymous_before_ftp(async_client, db_session):
    from backend.app.models.settings import Settings

    db_session.add(Settings(key="auth_enabled", value="true"))
    await db_session.commit()
    with patch("backend.app.api.routes.printer_files.get_file_size_async", AsyncMock()) as size:
        response = await async_client.get("/api/v1/printers/1/files/download", params={"path": "/ipcam/video.mp4"})
    assert response.status_code == 401
    size.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("permissions,expected", [([], 403), (["printers:files"], 200)])
async def test_video_download_checks_file_permission(async_client, db_session, printer_factory, permissions, expected):
    from backend.app.core.auth import create_access_token
    from backend.app.models.group import Group
    from backend.app.models.settings import Settings
    from backend.app.models.user import User

    printer = await printer_factory()
    group = Group(name="Video permissions", permissions=permissions)
    user = User(username="video-reader", password_hash="unused", role="user", groups=[group])
    db_session.add_all([group, user, Settings(key="auth_enabled", value="true")])
    await db_session.commit()

    async def chunks(*args, **kwargs):
        yield b"video"

    headers = {"Authorization": f"Bearer {create_access_token(data={'sub': user.username})}"}
    with (
        patch("backend.app.api.routes.printer_files.stream_printer_file", chunks),
        patch("backend.app.api.routes.printer_files.get_file_size_async", AsyncMock(return_value=5)) as size,
    ):
        response = await async_client.get(
            f"/api/v1/printers/{printer.id}/files/download", params={"path": "/ipcam/video.mp4"}, headers=headers
        )
    assert response.status_code == expected
    if expected == 403:
        size.assert_not_awaited()
    else:
        assert response.content == b"video"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    ("filename", "ascii_fallback"),
    [
        ("龙泡泡石墩子_p2s_ok.gcode.3mf", "p2s_ok.gcode.3mf"),
        ("こんにちは.gcode.3mf", "gcode.3mf"),
        ("résumé.gcode.3mf", "rsum.gcode.3mf"),
        ("مرحبا.gcode.3mf", "gcode.3mf"),
        ("文件.3mf", "3mf"),
        ("hello.3mf", "hello.3mf"),
    ],
)
async def test_download_printer_file_non_ascii_filename(
    async_client: AsyncClient,
    printer_factory,
    filename: str,
    ascii_fallback: str,
    db_session,
):
    """Non-ASCII filenames must not crash header encoding (issue #1245)."""
    printer = await printer_factory()
    file_bytes = b"fake 3mf content"

    async def chunks(*args, **kwargs):
        yield file_bytes

    with (
        patch(
            "backend.app.api.routes.printer_files.stream_printer_file",
            chunks,
        ),
        patch(
            "backend.app.api.routes.printer_files.get_file_size_async",
            new=AsyncMock(return_value=len(file_bytes)),
        ),
    ):
        response = await async_client.get(
            f"/api/v1/printers/{printer.id}/files/download",
            params={"path": f"/cache/{filename}"},
        )

    assert response.status_code == 200
    assert response.content == file_bytes

    content_disposition = response.headers["content-disposition"]
    assert f'filename="{ascii_fallback}"' in content_disposition
    assert "filename*=UTF-8''" in content_disposition
    encoded_name = content_disposition.split("filename*=UTF-8''", 1)[1]
    assert unquote(encoded_name) == filename
