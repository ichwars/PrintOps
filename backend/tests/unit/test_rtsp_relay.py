import asyncio
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlparse

import pytest

from backend.app.services.camera import create_tls_proxy
from backend.app.services.camera_source_security import prepare_external_camera_url
from backend.app.services.rtsp_relay import forward_rtsp_responses


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blocked",
    [
        b"RTSP/1.0 302 Moved\r\nLocation: rtsp://example.test/live\r\n\r\n",
        b"REDIRECT rtsp://example.test/live RTSP/1.0\r\nCSeq: 4\r\n\r\n",
        b"\r\nRTSP/1.0 302 Moved\r\nLocation: rtsp://example.test/live\r\n\r\n",
        b"RTSP/1.0 200 OK\r\nContent-Length: 0\r\nContent-Length: 1\r\n\r\n",
    ],
)
async def test_rtsp_relay_forwards_framed_data_and_closes_on_unsafe_headers(blocked):
    sdp = b"v=0\r\ns=PrintOps camera\r\n"
    describe = b"RTSP/1.0 200 OK\r\nContent-Length: %d\r\n\r\n" % len(sdp) + sdp
    payload = b"\x80\x60RTSP/1.0 302 Found\r\n\r\n"
    rtp = b"$\x00" + len(payload).to_bytes(2, "big") + payload
    reader = asyncio.StreamReader()
    writer = Mock(drain=AsyncMock())
    forwarding = asyncio.create_task(forward_rtsp_responses(reader, writer))
    for fragment in (describe[:5], describe[5:] + rtp[:3], rtp[3:] + blocked[:11], blocked[11:]):
        reader.feed_data(fragment)
        await asyncio.sleep(0)
    reader.feed_eof()
    await asyncio.wait_for(forwarding, 1)
    assert b"".join(call.args[0] for call in writer.write.call_args_list) == describe + rtp


@pytest.mark.asyncio
@pytest.mark.parametrize("external_camera", [True, False], ids=["external-camera", "printer-camera"])
async def test_camera_proxy_closes_before_a_redirect_reaches_the_client(external_camera, monkeypatch):
    async def camera_reply(reader, writer):
        try:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"RTSP/1.0 302 Found\r\nLoca")
            await writer.drain()
            writer.write(b"tion: rtsp://fixture-user:fixture-password@example.test/camera\r\n\r\n")
            await writer.drain()
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()

    connect = asyncio.open_connection
    async with await asyncio.start_server(camera_reply, "127.0.0.1", 0) as upstream:
        upstream_port = upstream.sockets[0].getsockname()[1]
        if external_camera:
            with patch(
                "backend.app.services.camera_source_security._resolve_allowed_address",
                new=AsyncMock(return_value="127.0.0.1"),
            ):
                prepared = await prepare_external_camera_url(f"rtsp://camera.test:{upstream_port}/stream", ("rtsp",))
            assert prepared is not None
            local_port = urlparse(prepared.url).port
            close_proxy = prepared.close
        else:
            local_port, server = await create_tls_proxy("127.0.0.1", upstream_port)

            async def close_proxy():
                server.close()
                await server.wait_closed()

            async def simulated_tls_peer(host, port, *, ssl=None):
                assert ssl is not None
                return await connect(host, port)

            monkeypatch.setattr(asyncio, "open_connection", simulated_tls_peer)

        try:
            reader, writer = await connect("127.0.0.1", local_port)
            try:
                writer.write(f"DESCRIBE rtsp://127.0.0.1:{local_port}/stream RTSP/1.0\r\nCSeq: 1\r\n\r\n".encode())
                await writer.drain()
                assert await asyncio.wait_for(reader.read(), 1) == b""
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await close_proxy()
