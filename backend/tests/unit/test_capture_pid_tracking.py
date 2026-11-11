"""Tests for one-shot camera capture and its process lifetime."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.api.routes.camera import cleanup_orphaned_streams
from backend.app.services.camera import capture_camera_frame_bytes


class TestCaptureLifetime:
    @pytest.mark.asyncio
    async def test_capture_survives_concurrent_stream_cleanup(self):
        fake_process = MagicMock()
        fake_process.pid = 99999
        fake_process.returncode = None

        async def fake_communicate():
            await cleanup_orphaned_streams()
            fake_process.returncode = 0
            return (b"\xff\xd8" + b"\x00" * 200 + b"\xff\xd9", b"")

        fake_process.communicate = fake_communicate

        fake_proxy_server = AsyncMock()
        fake_proxy_server.close = MagicMock()

        with (
            patch("backend.app.services.camera.is_chamber_image_model", return_value=False),
            patch("backend.app.services.camera.get_camera_port", return_value=322),
            patch("backend.app.services.camera.create_tls_proxy", return_value=(12345, fake_proxy_server)),
            patch("backend.app.services.camera.get_ffmpeg_path", return_value="/usr/bin/ffmpeg"),
            patch("asyncio.create_subprocess_exec", return_value=fake_process),
        ):
            result = await capture_camera_frame_bytes("192.168.1.1", "test", "P2S", timeout=10)

        assert result is not None
        fake_process.kill.assert_not_called()
        fake_proxy_server.wait_closed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_capture_nonzero_exit(self):
        """The TLS proxy closes even when FFmpeg returns nonzero."""
        fake_process = MagicMock()
        fake_process.pid = 88888
        fake_process.returncode = 1

        async def fake_communicate():
            return (b"", b"some error")

        fake_process.communicate = fake_communicate

        fake_proxy_server = AsyncMock()
        fake_proxy_server.close = MagicMock()

        with (
            patch("backend.app.services.camera.is_chamber_image_model", return_value=False),
            patch("backend.app.services.camera.get_camera_port", return_value=322),
            patch("backend.app.services.camera.create_tls_proxy", return_value=(12345, fake_proxy_server)),
            patch("backend.app.services.camera.get_ffmpeg_path", return_value="/usr/bin/ffmpeg"),
            patch("asyncio.create_subprocess_exec", return_value=fake_process),
        ):
            result = await capture_camera_frame_bytes("192.168.1.1", "test", "P2S", timeout=10)

        assert result is None
        fake_proxy_server.wait_closed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_capture_timeout_stops_process(self):
        """A timed-out capture stops FFmpeg and closes the TLS proxy."""
        fake_process = MagicMock()
        fake_process.pid = 77777
        fake_process.returncode = None
        fake_process.kill = MagicMock()

        async def fake_communicate():
            await asyncio.sleep(60)  # Will be cancelled by wait_for
            return (b"", b"")

        fake_process.communicate = fake_communicate

        async def fake_wait():
            fake_process.returncode = -9

        fake_process.wait = fake_wait

        fake_proxy_server = AsyncMock()
        fake_proxy_server.close = MagicMock()

        with (
            patch("backend.app.services.camera.is_chamber_image_model", return_value=False),
            patch("backend.app.services.camera.get_camera_port", return_value=322),
            patch("backend.app.services.camera.create_tls_proxy", return_value=(12345, fake_proxy_server)),
            patch("backend.app.services.camera.get_ffmpeg_path", return_value="/usr/bin/ffmpeg"),
            patch("asyncio.create_subprocess_exec", return_value=fake_process),
        ):
            result = await capture_camera_frame_bytes("192.168.1.1", "test", "P2S", timeout=0.01)

        assert result is None
        fake_process.kill.assert_called_once()
        assert fake_process.returncode == -9
        fake_proxy_server.wait_closed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_chamber_image_capture_does_not_spawn_ffmpeg(self):
        with (
            patch("backend.app.services.camera.is_chamber_image_model", return_value=True),
            patch("backend.app.services.camera.read_chamber_image_frame", return_value=b"\xff\xd8test\xff\xd9"),
            patch("asyncio.create_subprocess_exec") as spawn,
        ):
            result = await capture_camera_frame_bytes("192.168.1.1", "test", "A1", timeout=10)

        assert result is not None
        spawn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_proxy_closed_when_spawn_fails(self):
        """A missing FFmpeg executable still closes the TLS proxy."""
        fake_proxy_server = AsyncMock()
        fake_proxy_server.close = MagicMock()

        with (
            patch("backend.app.services.camera.is_chamber_image_model", return_value=False),
            patch("backend.app.services.camera.get_camera_port", return_value=322),
            patch("backend.app.services.camera.create_tls_proxy", return_value=(12345, fake_proxy_server)),
            patch("backend.app.services.camera.get_ffmpeg_path", return_value="/usr/bin/ffmpeg"),
            patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("ffmpeg")),
        ):
            result = await capture_camera_frame_bytes("192.168.1.1", "test", "P2S", timeout=10)

        assert result is None
        fake_proxy_server.wait_closed.assert_awaited_once()
