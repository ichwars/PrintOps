"""Snapshot and camera tests must leave the live camera's connection alone."""

import time
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, MockTransport, Response

from backend.app.api.routes import camera
from backend.app.services import external_camera, go2rtc_client, go2rtc_registry
from backend.app.services.camera_source import ExternalRtspSource

JPEG = bytes.fromhex("ffd8 ffc0 000b 08 01e0 0280 01 01 11 00 ffd9")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("frame_age", "watched_url"),
    [(0, "/dev/video0"), (None, "/dev/video0"), (60, "/dev/video0"), (0, "/dev/video1")],
)
async def test_snapshot_and_external_test_use_a_recent_live_frame(
    async_client, printer_factory, monkeypatch, frame_age, watched_url
):
    printer = await printer_factory(
        external_camera_enabled=True, external_camera_url="/dev/video0", external_camera_type="usb"
    )
    monkeypatch.setattr(camera, "active_broadcaster_keys", lambda: [f"printer-{printer.id}"])
    monkeypatch.setattr(camera, "active_source_identity", lambda _key: ("usb", watched_url))
    if frame_age is not None:
        monkeypatch.setattr(camera, "_last_frames", {printer.id: JPEG})
        monkeypatch.setattr(camera, "_last_frame_times", {printer.id: time.time() - frame_age})
    capture = AsyncMock()
    monkeypatch.setattr(external_camera, "capture_frame", capture)

    snapshot = await async_client.get(f"/api/v1/printers/{printer.id}/camera/snapshot")
    result = await async_client.post(
        f"/api/v1/printers/{printer.id}/camera/external/test", json={"url": "/dev/video0", "camera_type": "usb"}
    )

    capture.assert_not_awaited()
    assert result.status_code == 200
    assert result.json()["live_view"] is True
    if frame_age == 0 and watched_url == "/dev/video0":
        assert snapshot.status_code == 200
        assert snapshot.content == JPEG
        assert result.json() == {"success": True, "resolution": "640x480", "live_view": True}
    else:
        assert snapshot.status_code == 503
        assert snapshot.headers["Retry-After"] == "2"
        assert result.json()["success"] is False


@pytest.mark.asyncio
async def test_dedicated_snapshot_and_test_of_a_different_camera_still_capture(
    async_client, printer_factory, monkeypatch
):
    printer = await printer_factory(
        external_camera_enabled=True,
        external_camera_url="/dev/video0",
        external_camera_type="usb",
        external_camera_snapshot_url="http://camera.test/snapshot",
    )
    monkeypatch.setattr(camera, "active_broadcaster_keys", lambda: [f"printer-{printer.id}"])
    capture = AsyncMock(return_value=JPEG)
    monkeypatch.setattr(external_camera, "capture_frame", capture)

    response = await async_client.get(f"/api/v1/printers/{printer.id}/camera/snapshot")
    assert response.status_code == 200
    capture.assert_awaited_once_with("/dev/video0", "usb", timeout=15, snapshot_url="http://camera.test/snapshot")
    capture.reset_mock()
    response = await async_client.post(
        f"/api/v1/printers/{printer.id}/camera/external/test", params={"url": "/dev/video1", "camera_type": "usb"}
    )
    assert response.json() == {"success": True, "resolution": "640x480"}
    capture.assert_awaited_once_with("/dev/video1", "usb", timeout=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("external", [False, True])
async def test_snapshot_uses_the_sidecar_when_only_an_mse_viewer_is_watching(
    async_client, printer_factory, monkeypatch, external
):
    printer = await printer_factory(
        external_camera_enabled=external,
        external_camera_url="rtsp://camera.test/live" if external else None,
        external_camera_type="rtsp" if external else None,
    )
    monkeypatch.setattr(go2rtc_registry, "is_registered", lambda printer_id: printer_id == printer.id)
    if external:
        source = ExternalRtspSource(printer.external_camera_url)
        monkeypatch.setattr(go2rtc_registry, "registered_source", lambda _printer_id: source)
    capture = AsyncMock()
    snapshot = AsyncMock(return_value=JPEG)
    monkeypatch.setattr(camera, "capture_camera_frame", capture)
    monkeypatch.setattr(go2rtc_client, "get_snapshot", snapshot)

    response = await async_client.get(f"/api/v1/printers/{printer.id}/camera/snapshot")
    assert response.status_code == 200
    assert response.content == JPEG
    snapshot.assert_awaited_once_with(printer.id)
    capture.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("body, expected", [(JPEG, JPEG), (b"unavailable", None), (JPEG + b"extra", None)])
async def test_sidecar_snapshot_uses_the_registered_stream_name_and_bounds_the_body(monkeypatch, body, expected):
    def handler(request):
        assert request.url.path == "/api/frame.jpeg"
        assert dict(request.url.params) == {"src": "printer-42"}
        return Response(200, content=body)

    def client(**kwargs):
        return AsyncClient(transport=MockTransport(handler), **kwargs)

    monkeypatch.setattr(go2rtc_client.httpx, "AsyncClient", client)
    monkeypatch.setattr(go2rtc_client, "_SNAPSHOT_LIMIT_BYTES", len(JPEG))
    assert await go2rtc_client.get_snapshot(42) == expected
