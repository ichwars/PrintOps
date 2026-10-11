"""Bounded printer-file streams use the real FTPS client and async gate."""

import asyncio
import ftplib
import threading
from unittest.mock import patch

import pytest

from backend.app.services import bambu_ftp


class TestPrinterFileStream:
    @pytest.mark.asyncio
    async def test_live_ftps_download_yields_chunks_before_transfer_finishes(self, ftp_server, patch_ftp_port):
        from backend.app.services.printer_file_stream import stream_printer_file

        chunk_size = bambu_ftp.BambuFTPClient.CHUNK_SIZE
        payload = b"video" * (chunk_size * 8)
        ftp_server.add_file("timelapse/video.mp4", payload)
        progress = []
        stream = stream_printer_file(
            "127.0.0.1",
            "12345678",
            "/timelapse/video.mp4",
            total_bytes=len(payload),
            progress_callback=lambda received, total: progress.append((received, total)),
        )
        chunks = []
        try:
            first = await anext(stream)
            assert 0 < len(first) <= chunk_size
            chunks.append(first)
            assert progress[-1][0] < len(payload), "FTP must still be producing when HTTP receives its first chunk"
            async for chunk in stream:
                assert len(chunk) <= chunk_size
                chunks.append(chunk)
        finally:
            await stream.aclose()
        assert b"".join(chunks) == payload
        assert len(chunks) > 8

    @pytest.mark.asyncio
    async def test_missing_file_is_reported_before_any_body(self, ftp_server, patch_ftp_port):
        from backend.app.services.printer_file_stream import stream_printer_file

        stream = stream_printer_file("127.0.0.1", "12345678", "/timelapse/missing.mp4")
        with pytest.raises(bambu_ftp.FileNotOnPrinterError):
            await anext(stream)
        await stream.aclose()

    @pytest.mark.asyncio
    async def test_transient_start_failure_retries_without_replaying_chunks(self, ftp_server, patch_ftp_port):
        from backend.app.services.printer_file_stream import stream_printer_file

        ftp_server.add_file("timelapse/retry.mp4", b"video")
        ftp_server.inject_failure("RETR", 425, "Temporarily unavailable", count=1)
        stream = stream_printer_file("127.0.0.1", "12345678", "/timelapse/retry.mp4", max_retries=1, retry_delay=0)
        assert b"".join([chunk async for chunk in stream]) == b"video"


@pytest.mark.asyncio
async def test_backpressure_bounds_bytes_and_close_releases_same_printer_gate():
    from backend.app.services.printer_file_stream import _STREAM_QUEUE_CHUNKS, stream_printer_file

    produced = 0
    exited = threading.Event()
    chunk_size = bambu_ftp.BambuFTPClient.CHUNK_SIZE

    class Client(bambu_ftp.BambuFTPClient):
        def connect(self):
            return True

        def disconnect(self):
            exited.set()

        def download_to_sink(self, remote_path, sink, *, cancel_event=None, **kwargs):
            nonlocal produced
            while not cancel_event.is_set():
                produced += 1
                sink(b"v" * chunk_size)
            raise bambu_ftp.DownloadCancelled(remote_path)

    with patch("backend.app.services.printer_file_stream.BambuFTPClient", Client):
        stream = stream_printer_file("192.0.2.153", "code", "/video.mp4")
        assert len(await anext(stream)) == chunk_size
        await asyncio.sleep(0.05)
        assert produced <= _STREAM_QUEUE_CHUNKS + 2
        assert not exited.is_set()
        await asyncio.wait_for(stream.aclose(), 1)
        assert exited.is_set()
        async with bambu_ftp._serialized_download("192.0.2.153", "next") as held:
            assert held


@pytest.mark.asyncio
async def test_error_after_first_chunk_never_retries_or_reports_success():
    from backend.app.services.printer_file_stream import stream_printer_file

    attempts = 0

    class Client(bambu_ftp.BambuFTPClient):
        def connect(self):
            return True

        def disconnect(self):
            pass

        def download_to_sink(self, remote_path, sink, **kwargs):
            nonlocal attempts
            attempts += 1
            sink(b"partial")
            raise ftplib.error_temp("426 Connection lost")

    with patch("backend.app.services.printer_file_stream.BambuFTPClient", Client):
        stream = stream_printer_file("192.0.2.154", "code", "/video.mp4", max_retries=3, retry_delay=0)
        assert await anext(stream) == b"partial"
        with pytest.raises(OSError):
            await anext(stream)
        await stream.aclose()
    assert attempts == 1


@pytest.mark.asyncio
async def test_cancellation_closes_real_stalled_data_socket_before_releasing_gate():
    import socket

    from backend.app.services.printer_file_stream import stream_printer_file

    reader, writer = socket.socketpair()
    exited = threading.Event()

    class Transport:
        sock = None

        def voidcmd(self, command):
            pass

        def transfercmd(self, command):
            return reader

        def voidresp(self):
            pass

        def close(self):
            pass

    class Client(bambu_ftp.BambuFTPClient):
        def connect(self):
            self._ftp = Transport()
            return True

        def disconnect(self):
            exited.set()

    try:
        writer.sendall(b"v" * bambu_ftp.BambuFTPClient.CHUNK_SIZE * 2)
        with patch("backend.app.services.printer_file_stream.BambuFTPClient", Client):
            stream = stream_printer_file("192.0.2.155", "code", "/video.mp4")
            assert await asyncio.wait_for(anext(stream), 1)
            await asyncio.wait_for(stream.aclose(), 1)
        assert reader.fileno() == -1
        assert bambu_ftp._download_lock(asyncio.get_running_loop(), "192.0.2.155").locked() is False
    finally:
        reader.close()
        writer.close()


@pytest.mark.asyncio
async def test_deadline_closes_stalled_socket_without_retrying():
    import socket

    from backend.app.services.printer_file_stream import stream_printer_file

    reader, writer = socket.socketpair()
    attempts = 0

    class Transport:
        sock = None

        def voidcmd(self, command):
            pass

        def transfercmd(self, command):
            return reader

        def voidresp(self):
            pass

        def close(self):
            pass

    class Client(bambu_ftp.BambuFTPClient):
        def connect(self):
            nonlocal attempts
            attempts += 1
            self._ftp = Transport()
            return True

        def disconnect(self):
            pass

    try:
        with patch("backend.app.services.printer_file_stream.BambuFTPClient", Client):
            stream = stream_printer_file("192.0.2.156", "code", "/video.mp4", timeout=0.03, max_retries=3)
            with pytest.raises(bambu_ftp.DownloadDeadlineExceeded):
                await asyncio.wait_for(anext(stream), 1)
            await stream.aclose()
        assert attempts == 1
        assert reader.fileno() == -1
    finally:
        reader.close()
        writer.close()


@pytest.mark.asyncio
async def test_http_send_failure_closes_source_and_stops_bounded_producer():
    from starlette.requests import ClientDisconnect

    from backend.app.services.printer_file_stream import stream_printer_file
    from backend.app.utils.printer_file_response import PrinterFileStreamingResponse

    exited = threading.Event()

    class Client(bambu_ftp.BambuFTPClient):
        def connect(self):
            return True

        def disconnect(self):
            exited.set()

        def download_to_sink(self, remote_path, sink, *, cancel_event=None, **kwargs):
            while not cancel_event.is_set():
                sink(b"video" * 1000)
            raise bambu_ftp.DownloadCancelled(remote_path)

    async def send(message):
        if message["type"] == "http.response.body":
            raise OSError("HTTP client disconnected")

    async def receive():
        await asyncio.Event().wait()

    with patch("backend.app.services.printer_file_stream.BambuFTPClient", Client):
        stream = stream_printer_file("192.0.2.157", "code", "/video.mp4")
        response = PrinterFileStreamingResponse(stream, await anext(stream))
        with pytest.raises(ClientDisconnect):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    assert exited.is_set()


@pytest.mark.parametrize("path", ["/../video.mp4", "/video.mp4\r\nDELE /cache", "/ipcam//video.mp4", "/ipcam/"])
@pytest.mark.asyncio
async def test_invalid_path_never_connects(path):
    from backend.app.services.printer_file_stream import stream_printer_file

    with patch.object(bambu_ftp.BambuFTPClient, "connect") as connect:
        stream = stream_printer_file("192.0.2.158", "code", path)
        with pytest.raises(ValueError):
            await anext(stream)
    connect.assert_not_called()


def test_incomplete_protocol_completion_withholds_the_final_chunk():
    import socket

    reader, writer = socket.socketpair()
    payload = b"video" * 20000
    received = []

    class Transport:
        def voidcmd(self, command):
            pass

        def transfercmd(self, command):
            return reader

        def voidresp(self):
            raise ftplib.error_temp("426 Transfer failed")

    client = bambu_ftp.BambuFTPClient("192.0.2.159", "code")
    client._ftp = Transport()
    try:
        writer.sendall(payload)
        writer.shutdown(socket.SHUT_WR)
        with pytest.raises(ftplib.error_temp):
            client.download_to_sink("/video.mp4", received.append, expected_size=len(payload))
        assert b"".join(received) == payload[: len(b"".join(received))]
        assert len(b"".join(received)) < len(payload)
    finally:
        reader.close()
        writer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("spec_version", ["2.0", "2.3"])
async def test_asgi_disconnect_cancels_worker_before_returning(spec_version):
    from backend.app.services.printer_file_stream import stream_printer_file
    from backend.app.utils.printer_file_response import PrinterFileStreamingResponse

    disconnected = asyncio.Event()
    exited = threading.Event()

    class Client(bambu_ftp.BambuFTPClient):
        def connect(self):
            return True

        def disconnect(self):
            exited.set()

        def download_to_sink(self, remote_path, sink, *, cancel_event=None, **kwargs):
            while not cancel_event.is_set():
                sink(b"video" * 1000)
            raise bambu_ftp.DownloadCancelled(remote_path)

    async def send(message):
        if message["type"] == "http.response.body":
            disconnected.set()
            await asyncio.sleep(0)

    async def receive():
        await disconnected.wait()
        return {"type": "http.disconnect"}

    with patch("backend.app.services.printer_file_stream.BambuFTPClient", Client):
        stream = stream_printer_file("192.0.2.160", "code", "/video.mp4")
        response = PrinterFileStreamingResponse(stream, await anext(stream))
        await asyncio.wait_for(response({"type": "http", "asgi": {"spec_version": spec_version}}, receive, send), 1)
    assert exited.is_set()
    assert not bambu_ftp._download_lock(asyncio.get_running_loop(), "192.0.2.160").locked()
