"""Security regressions for external camera source preparation (#84)."""

from __future__ import annotations

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest

from backend.app.services.camera_source import ExternalHttpSource, ExternalRtspSource
from backend.app.services.camera_source_security import (
    _open_connection_any,
    _parse_camera_url,
    _resolve_allowed_address,
    prepare_external_camera_url,
)
from backend.app.services.external_camera import _sanitize_camera_url, _stderr_preview


def _dns_answers(*addresses: str) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    answers = []
    for address in addresses:
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        answers.append((family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 0)))
    return answers


class _CompletedFfmpegProcess:
    returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"\xff\xd8" + (b"x" * 100) + b"\xff\xd9", b""


class _EmptyHttpResponse:
    status = 200
    content_length = 0

    def __init__(self) -> None:
        self.content = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def iter_chunked(self, _size: int):
        async def chunks():
            if False:
                yield b""

        return chunks()


class _EmptyHttpSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def get(self, _url: str, **_kwargs):
        return _EmptyHttpResponse()


@pytest.mark.parametrize(
    "hostname",
    [
        "127.1",
        "127.0.0.2",
        "2130706433",
        "0177.0.0.1",
        "0x7f000001",
        "[::ffff:127.0.0.1]",
    ],
)
def test_alternate_loopback_spellings_are_rejected(hostname: str) -> None:
    """Changing a loopback spelling must not bypass the camera SSRF guard."""
    assert _sanitize_camera_url(f"rtsp://{hostname}/stream", ("rtsp",)) is None


def test_url_sanitization_preserves_raw_credentials_and_ipv6_brackets() -> None:
    """Security reconstruction must not corrupt legitimate encoded credentials or IPv6."""
    url = "rtsps://cam%40user:p%3A%40ss@[fd12:3456::50]:7441/live?profile=main"
    assert _sanitize_camera_url(url, ("rtsp", "rtsps")) == url


def test_rtsps_without_explicit_port_keeps_the_existing_port_322_default() -> None:
    """Changing the historical RTSPS default would break Bambu-style external feeds."""
    parsed = _parse_camera_url("rtsps://camera.example/live", ("rtsp", "rtsps"))
    assert parsed is not None
    assert parsed.port == 322


def test_url_sanitization_preserves_path_parameters() -> None:
    parsed = _parse_camera_url("rtsp://camera.example/stream;track=1?quality=high", ("rtsp",))
    assert parsed is not None
    assert parsed.path_and_query == "/stream;track=1?quality=high"


def test_ffmpeg_stderr_preview_redacts_external_camera_password() -> None:
    """ffmpeg echoes input URLs; diagnostics must never persist camera credentials."""
    stderr = b"Input #0, rtsp, from 'rtsp://camera-user:s3cr3t@127.0.0.1:45000/live':"
    preview = _stderr_preview(stderr, 300)
    assert "s3cr3t" not in preview
    assert "rtsp://camera-user:[REDACTED]@127.0.0.1:45000/live" in preview


@pytest.mark.asyncio
async def test_external_http_source_rejects_dns_answering_loopback() -> None:
    """A hostname resolving to loopback must fail before go2rtc receives a source URL."""
    loop = asyncio.get_running_loop()
    with (
        patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_dns_answers("127.0.0.1"))),
        pytest.raises(ValueError, match="unsafe external camera"),
    ):
        await ExternalHttpSource("http://camera.example/snapshot.jpg").resolve("printer-7")


@pytest.mark.asyncio
async def test_external_http_source_rejects_mixed_safe_and_link_local_dns_answers() -> None:
    """Every DNS answer must be safe; selecting only the first answer is a bypass."""
    loop = asyncio.get_running_loop()
    answers = _dns_answers("192.168.10.20", "169.254.169.254")
    with (
        patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=answers)),
        pytest.raises(ValueError, match="unsafe external camera"),
    ):
        await ExternalHttpSource("http://camera.example/live.mjpeg").resolve("printer-7")


@pytest.mark.asyncio
async def test_dns_resolution_is_bounded() -> None:
    async def never_returns(*_args, **_kwargs):
        await asyncio.sleep(60)

    loop = asyncio.get_running_loop()
    with (
        patch.object(loop, "getaddrinfo", new=never_returns),
        patch("backend.app.services.camera_source_security._DNS_TIMEOUT", 0.01),
    ):
        assert await _resolve_allowed_address("camera.example", 80) is None


@pytest.mark.asyncio
async def test_connection_falls_back_across_all_validated_dns_answers() -> None:
    reader = asyncio.StreamReader()
    writer = MagicMock()
    with patch(
        "backend.app.services.camera_source_security.asyncio.open_connection",
        new=AsyncMock(side_effect=[OSError("unreachable"), (reader, writer)]),
    ) as connect:
        result = await _open_connection_any(("2001:db8::20", "192.0.2.20"), 8554)

    assert result == (reader, writer)
    assert [call.args[0] for call in connect.await_args_list] == ["2001:db8::20", "192.0.2.20"]


@pytest.mark.asyncio
async def test_external_http_source_pins_allowed_dns_to_a_loopback_relay() -> None:
    """go2rtc must receive a loopback URL, never the attacker-controlled DNS name."""
    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_dns_answers("192.168.10.20"))):
        result = await ExternalHttpSource("http://user:p%40ss@camera.example:8080/live.mjpeg").resolve("printer-7")

    try:
        assert len(result.go2rtc_sources) == 1
        source_url = result.go2rtc_sources[0]
        assert source_url.startswith("http://user:p%40ss@127.0.0.1:")
        assert source_url.endswith("/live.mjpeg")
        assert "camera.example" not in source_url
        assert result.local_server is not None
    finally:
        if result.local_server is not None:
            result.local_server.close()
            await result.local_server.wait_closed()


@pytest.mark.asyncio
async def test_external_rtsp_source_pins_allowed_dns_and_keeps_raw_credentials() -> None:
    """RTSP credentials survive while go2rtc is prevented from resolving the remote host."""
    loop = asyncio.get_running_loop()
    with patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_dns_answers("10.0.0.25"))):
        result = await ExternalRtspSource("rtsp://cam%40user:p%3Ass@camera.example:8554/stream").resolve("printer-9")

    try:
        source_url = result.go2rtc_sources[0]
        assert source_url.startswith("rtsp://cam%40user:p%3Ass@127.0.0.1:")
        assert source_url.endswith("/stream")
        assert "camera.example" not in source_url
        assert result.go2rtc_sources[1] == "ffmpeg:printer-9#video=mjpeg"
        assert result.local_server is not None
    finally:
        if result.local_server is not None:
            result.local_server.close()
            await result.local_server.wait_closed()


@pytest.mark.asyncio
async def test_direct_snapshot_rejects_forbidden_dns_before_aiohttp() -> None:
    """Direct snapshot capture must share the DNS guard used by go2rtc."""
    from backend.app.services import external_camera

    loop = asyncio.get_running_loop()
    session_factory = MagicMock(return_value=_EmptyHttpSession())
    with (
        patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_dns_answers("169.254.169.254"))),
        patch.object(external_camera.aiohttp, "ClientSession", session_factory),
    ):
        result = await external_camera._capture_snapshot("http://camera.example/snapshot.jpg", 5)

    assert result is None
    session_factory.assert_not_called()


@pytest.mark.asyncio
async def test_direct_rtsp_rejects_legacy_loopback_before_ffmpeg() -> None:
    """The one-shot ffmpeg path must not receive an alternate loopback spelling."""
    from backend.app.services import external_camera

    spawn = AsyncMock(return_value=_CompletedFfmpegProcess())
    with (
        patch.object(external_camera, "get_ffmpeg_path", return_value="/usr/bin/ffmpeg"),
        patch.object(external_camera.asyncio, "create_subprocess_exec", spawn),
    ):
        result = await external_camera._capture_rtsp_frame("rtsp://2130706433/live", 5)

    assert result is None
    spawn.assert_not_awaited()


@pytest.mark.asyncio
async def test_direct_rtsp_uses_loopback_relay_and_protocol_allowlist() -> None:
    """ffmpeg may dial only the pinned relay and the RTSP dependency protocols."""
    from backend.app.services import external_camera

    spawn = AsyncMock(return_value=_CompletedFfmpegProcess())
    with (
        patch.object(external_camera, "get_ffmpeg_path", return_value="/usr/bin/ffmpeg"),
        patch.object(external_camera.asyncio, "create_subprocess_exec", spawn),
    ):
        result = await external_camera._capture_rtsp_frame("rtsp://cam:p%40ss@10.0.0.25:8554/live", 5)

    assert result == b"\xff\xd8" + (b"x" * 100) + b"\xff\xd9"
    args = spawn.await_args.args
    whitelist_index = args.index("-protocol_whitelist")
    assert args[whitelist_index + 1] == "rtsp,rtp,udp,tcp,tls,crypto"
    input_url = args[args.index("-i") + 1]
    assert input_url.startswith("rtsp://cam:p%40ss@127.0.0.1:")
    assert "10.0.0.25" not in input_url


@pytest.mark.asyncio
async def test_registry_converts_unsafe_source_to_runtime_error() -> None:
    """Camera routes already handle RuntimeError; unsafe sources must use that contract."""
    from backend.app.services import go2rtc_client, go2rtc_registry

    loop = asyncio.get_running_loop()
    with (
        patch.object(loop, "getaddrinfo", new=AsyncMock(return_value=_dns_answers("127.0.0.1"))),
        patch.object(go2rtc_client, "ensure_stream_multi", new=AsyncMock()) as ensure_stream,
        pytest.raises(RuntimeError, match="invalid camera source"),
    ):
        await go2rtc_registry.acquire(84001, ExternalHttpSource("http://camera.example/live"))

    ensure_stream.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_relay_dials_pinned_ip_and_restores_original_host_header() -> None:
    """The relay must own the outbound dial while preserving HTTP virtual hosting."""
    loop = asyncio.get_running_loop()
    received = loop.create_future()

    async def handle_upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_head = await reader.readuntil(b"\r\n\r\n")
        received.set_result(request_head)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        await writer.drain()
        writer.close()

    upstream = await asyncio.start_server(handle_upstream, "127.0.0.1", 0)
    upstream_port = upstream.sockets[0].getsockname()[1]
    with patch(
        "backend.app.services.camera_source_security._resolve_allowed_address",
        new=AsyncMock(return_value="127.0.0.1"),
    ):
        prepared = await prepare_external_camera_url(
            f"http://camera.example:{upstream_port}/live.mjpeg",
            ("http", "https"),
        )

    assert prepared is not None
    try:
        local = urlparse(prepared.url)
        reader, writer = await asyncio.open_connection(local.hostname, local.port)
        writer.write(f"GET /live.mjpeg HTTP/1.1\r\nHost: {local.hostname}:{local.port}\r\n\r\n".encode())
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()

        request_head = await asyncio.wait_for(received, 1)
        assert response.startswith(b"HTTP/1.1 200 OK")
        assert f"Host: camera.example:{upstream_port}\r\n".encode() in request_head
        assert b"Connection: close\r\n" in request_head
    finally:
        await prepared.close()
        upstream.close()
        await upstream.wait_closed()


@pytest.mark.asyncio
async def test_http_relay_blocks_upstream_redirects() -> None:
    async def handle_upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(
            b"HTTP/1.1 302 Found\r\nLocation: http://169.254.169.254/latest/meta-data\r\nContent-Length: 0\r\n\r\n"
        )
        await writer.drain()
        writer.close()

    upstream = await asyncio.start_server(handle_upstream, "127.0.0.1", 0)
    upstream_port = upstream.sockets[0].getsockname()[1]
    with patch(
        "backend.app.services.camera_source_security._resolve_allowed_address",
        new=AsyncMock(return_value="127.0.0.1"),
    ):
        prepared = await prepare_external_camera_url(f"http://camera.example:{upstream_port}/live", ("http",))
    assert prepared is not None
    try:
        local = urlparse(prepared.url)
        reader, writer = await asyncio.open_connection(local.hostname, local.port)
        writer.write(b"GET /live HTTP/1.1\r\nHost: relay\r\n\r\n")
        await writer.drain()
        response = await reader.read()
        assert response.startswith(b"HTTP/1.1 502")
        assert b"169.254.169.254" not in response
        writer.close()
        await writer.wait_closed()
    finally:
        await prepared.close()
        upstream.close()
        await upstream.wait_closed()


@pytest.mark.asyncio
async def test_rtsp_relay_dials_pinned_ip_and_restores_original_authority() -> None:
    """RTSP request lines must be rewritten without letting the client resolve DNS."""
    loop = asyncio.get_running_loop()
    received = loop.create_future()

    async def handle_upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_head = await reader.readuntil(b"\r\n\r\n")
        received.set_result(request_head)
        writer.write(b"RTSP/1.0 200 OK\r\nCSeq: 1\r\n\r\n")
        await writer.drain()
        writer.close()

    upstream = await asyncio.start_server(handle_upstream, "127.0.0.1", 0)
    upstream_port = upstream.sockets[0].getsockname()[1]
    with patch(
        "backend.app.services.camera_source_security._resolve_allowed_address",
        new=AsyncMock(return_value="127.0.0.1"),
    ):
        prepared = await prepare_external_camera_url(
            f"rtsp://camera.example:{upstream_port}/stream",
            ("rtsp", "rtsps"),
        )

    assert prepared is not None
    try:
        local = urlparse(prepared.url)
        reader, writer = await asyncio.open_connection(local.hostname, local.port)
        local_authority = f"rtsp://{local.hostname}:{local.port}"
        request = f"DESCRIBE {local_authority}/stream RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode()
        writer.write(request[:17])
        await writer.drain()
        writer.write(request[17:])
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()

        request_head = await asyncio.wait_for(received, 1)
        expected = f"DESCRIBE rtsp://camera.example:{upstream_port}/stream RTSP/1.0".encode()
        assert response.startswith(b"RTSP/1.0 200 OK")
        assert request_head.startswith(expected)
        assert local_authority.encode() not in request_head
    finally:
        await prepared.close()
        upstream.close()
        await upstream.wait_closed()


@pytest.mark.asyncio
async def test_registry_closes_relay_when_registration_is_cancelled() -> None:
    from backend.app.services import go2rtc_client, go2rtc_registry
    from backend.app.services.camera_source import CameraSourceResult

    entered = asyncio.Event()
    never = asyncio.Event()
    server = MagicMock()
    server.wait_closed = AsyncMock()
    source = MagicMock()
    source.resolve = AsyncMock(return_value=CameraSourceResult(["http://127.0.0.1:1234/live"], server))

    async def blocked_registration(*_args):
        entered.set()
        await never.wait()

    with patch.object(go2rtc_client, "ensure_stream_multi", new=blocked_registration):
        task = asyncio.create_task(go2rtc_registry.acquire(84002, source))
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    server.close.assert_called_once()
    server.wait_closed.assert_awaited_once()
    assert not go2rtc_registry.is_registered(84002)


@pytest.mark.asyncio
async def test_slow_source_resolution_does_not_hold_global_registry_lock() -> None:
    from backend.app.services import go2rtc_client, go2rtc_registry
    from backend.app.services.camera_source import CameraSourceResult

    entered = asyncio.Event()
    never = asyncio.Event()
    slow_source = MagicMock()

    async def slow_resolve(_name):
        entered.set()
        await never.wait()

    slow_source.resolve = slow_resolve
    fast_source = MagicMock()
    fast_source.resolve = AsyncMock(return_value=CameraSourceResult(["rtsp://10.0.0.2/live"]))

    with patch.object(go2rtc_client, "ensure_stream_multi", new=AsyncMock(return_value=True)):
        slow_task = asyncio.create_task(go2rtc_registry.acquire(84003, slow_source))
        await asyncio.wait_for(entered.wait(), 1)
        assert await asyncio.wait_for(go2rtc_registry.acquire(84004, fast_source), 1) == "printer-84004"
        slow_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await slow_task

    go2rtc_registry._registrations.pop(84004, None)


@pytest.mark.asyncio
async def test_rtsp_relay_buffers_fragmented_request_and_preserves_digest_uri() -> None:
    loop = asyncio.get_running_loop()
    received = loop.create_future()

    async def handle_upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        received.set_result(await reader.readuntil(b"\r\n\r\n"))
        writer.write(b"RTSP/1.0 200 OK\r\nCSeq: 2\r\n\r\n")
        await writer.drain()
        writer.close()

    upstream = await asyncio.start_server(handle_upstream, "127.0.0.1", 0)
    upstream_port = upstream.sockets[0].getsockname()[1]
    with patch(
        "backend.app.services.camera_source_security._resolve_allowed_address",
        new=AsyncMock(return_value="127.0.0.1"),
    ):
        prepared = await prepare_external_camera_url(f"rtsp://camera.example:{upstream_port}/stream", ("rtsp",))
    assert prepared is not None
    try:
        local = urlparse(prepared.url)
        reader, writer = await asyncio.open_connection(local.hostname, local.port)
        local_url = f"rtsp://{local.hostname}:{local.port}/stream"
        request = (
            f"DESCRIBE {local_url} RTSP/1.0\r\nCSeq: 2\r\n"
            f'Authorization: Digest username="cam", uri="{local_url}"\r\n\r\n'
        ).encode()
        writer.write(request[:19])
        await writer.drain()
        writer.write(request[19:])
        await writer.drain()
        assert (await reader.read()).startswith(b"RTSP/1.0 200")
        request_head = await asyncio.wait_for(received, 1)
        assert request_head.startswith(f"DESCRIBE {local_url} RTSP/1.0".encode())
        writer.close()
        await writer.wait_closed()
    finally:
        await prepared.close()
        upstream.close()
        await upstream.wait_closed()
