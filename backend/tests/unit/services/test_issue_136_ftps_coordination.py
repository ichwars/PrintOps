"""Regression coverage for the coordinated FTPS transfer follow-up (#136)."""

from __future__ import annotations

import asyncio
import gc
import ssl
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import backend.app.services.bambu_ftp as ftp_mod

pytestmark = pytest.mark.unit


class _FakeClient:
    """Small client surface used by the async download wrappers."""

    _mode_cache: dict[str, str] = {}
    A1_MODELS: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def cache_mode(cls, ip_address: str, mode: str) -> None:
        pass

    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass


def test_download_extension_follows_reported_size_and_stays_bounded():
    assert ftp_mod._download_extension(15_150_000, 30.0) > 105.0
    assert ftp_mod._download_extension(None, 30.0) == 0.0
    assert ftp_mod._download_extension(64 * 1024, 30.0) == 0.0
    assert ftp_mod._download_extension(10 * 1024 * 1024 * 1024, 30.0) == ftp_mod._DOWNLOAD_MAX_TIMEOUT - 30.0


@pytest.mark.asyncio
async def test_reported_size_extends_a_slow_but_progressing_download(tmp_path: Path):
    payload = b"complete"

    class Client(_FakeClient):
        def download_to_file(
            self,
            remote_path: str,
            local_path: Path,
            *,
            size_callback=None,
            cancel_event=None,
            **kwargs,
        ) -> bool:
            size_callback(1_000_000)
            for _ in range(15):
                assert cancel_event is None or not cancel_event.is_set()
                time.sleep(0.01)
            local_path.write_bytes(payload)
            return True

    with (
        patch.object(ftp_mod, "BambuFTPClient", Client),
        patch.object(ftp_mod, "_download_extension", lambda size, base: 0.3 if size else 0.0),
    ):
        result = await ftp_mod.download_file_async("10.0.0.1", "code", "/slow.3mf", tmp_path / "slow.3mf", timeout=0.02)

    assert result is True
    assert (tmp_path / "slow.3mf").read_bytes() == payload


@pytest.mark.asyncio
async def test_downloads_for_one_printer_are_serialized_but_other_printers_are_not():
    order: list[str] = []
    first_entered = asyncio.Event()

    async def hold(ip_address: str, tag: str, delay: float) -> None:
        async with ftp_mod._serialized_download(ip_address, tag) as held:
            order.append(f"{tag}:in:{held}")
            if tag == "first":
                first_entered.set()
            await asyncio.sleep(delay)
            order.append(f"{tag}:out")

    first = asyncio.create_task(hold("10.0.0.2", "first", 0.08))
    await first_entered.wait()
    await asyncio.gather(
        hold("10.0.0.2", "second", 0.01),
        hold("10.0.0.3", "other", 0.01),
    )
    await first

    assert order.index("other:in:True") < order.index("first:out")
    assert order.index("second:in:True") > order.index("first:out")


@pytest.mark.asyncio
async def test_timed_out_path_search_stops_worker_before_next_candidate(tmp_path: Path):
    cancelled = threading.Event()
    walked: list[str] = []

    class Client(_FakeClient):
        def download_to_file(self, remote_path: str, local_path: Path, *, cancel_event=None, **kwargs) -> bool:
            walked.append(remote_path)
            for _ in range(80):
                if cancel_event is not None and cancel_event.is_set():
                    cancelled.set()
                    raise ftp_mod.DownloadCancelled(remote_path)
                time.sleep(0.005)
            return False

    with (
        patch.object(ftp_mod, "BambuFTPClient", Client),
        patch.object(ftp_mod, "_DOWNLOAD_UNWIND_SECONDS", 1.0),
    ):
        result = await ftp_mod.download_file_try_paths_async(
            "10.0.0.4",
            "code",
            ["/one.3mf", "/two.3mf"],
            tmp_path / "candidate.3mf",
            timeout=0.03,
        )

    assert result is False
    assert cancelled.is_set()
    assert walked == ["/one.3mf"]


@pytest.mark.asyncio
async def test_late_path_search_error_is_consumed_after_timeout(tmp_path: Path):
    loop_errors: list[str] = []
    asyncio.get_running_loop().set_exception_handler(
        lambda _loop, context: loop_errors.append(context.get("message", ""))
    )

    class Client(_FakeClient):
        def download_to_file(self, remote_path: str, local_path: Path, **kwargs) -> bool:
            time.sleep(0.08)
            raise OSError("late transport failure")

    with (
        patch.object(ftp_mod, "BambuFTPClient", Client),
        patch.object(ftp_mod, "_DOWNLOAD_UNWIND_SECONDS", 0.01),
    ):
        result = await ftp_mod.download_file_try_paths_async(
            "10.0.0.5", "code", ["/late.3mf"], tmp_path / "late.3mf", timeout=0.01
        )

    assert result is False
    await asyncio.sleep(0.12)
    gc.collect()
    await asyncio.sleep(0)
    assert loop_errors == []


@pytest.mark.asyncio
async def test_download_timeout_does_not_wait_forever_for_stalled_worker(tmp_path: Path):
    entered = threading.Event()
    release = threading.Event()

    class Client(_FakeClient):
        def download_to_file(self, remote_path: str, local_path: Path, **kwargs) -> bool:
            entered.set()
            release.wait(2.0)
            return False

    with (
        patch.object(ftp_mod, "BambuFTPClient", Client),
        patch.object(ftp_mod, "_download_extension", lambda size, base: 0.0),
    ):
        task = asyncio.create_task(
            ftp_mod.download_file_async(
                "10.0.0.6",
                "code",
                "/stalled.3mf",
                tmp_path / "stalled.3mf",
                timeout=0.01,
                socket_timeout=0.01,
            )
        )
        assert await asyncio.get_running_loop().run_in_executor(None, entered.wait, 1.0)
        await asyncio.sleep(0.75)
        try:
            assert task.done(), "the timeout path waited beyond its bounded unwind grace"
        finally:
            release.set()
            await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.parametrize(
    ("error", "expected_kind"),
    [
        (TimeoutError("transfer timed out"), ftp_mod.FtpFailureKind.TIMEOUT),
        (ssl.SSLError(1, "data-channel TLS failure"), ftp_mod.FtpFailureKind.HANDSHAKE),
    ],
)
def test_upload_classifies_timeout_and_tls_before_generic_os_errors(
    tmp_path: Path,
    error: OSError,
    expected_kind: ftp_mod.FtpFailureKind,
):
    source = tmp_path / "upload.3mf"
    source.write_bytes(b"3mf")
    client = ftp_mod.BambuFTPClient("192.0.2.138", "code")
    client._ftp = MagicMock()
    client._ftp.transfercmd.side_effect = error

    assert client.upload_file(source, "/upload.3mf") is False
    assert client.last_failure is not None
    assert client.last_failure.kind is expected_kind


@pytest.mark.asyncio
async def test_byte_download_shares_the_per_printer_download_gate(tmp_path: Path):
    byte_entered = threading.Event()
    release_byte = threading.Event()
    same_printer_entered = threading.Event()
    other_printer_entered = threading.Event()

    class Client(_FakeClient):
        def __init__(self, ip_address: str, *args, **kwargs):
            self.ip_address = ip_address

        def download_file(self, remote_path: str, **kwargs) -> bytes:
            byte_entered.set()
            release_byte.wait(2.0)
            return b"bytes"

        def download_to_file(self, remote_path: str, local_path: Path, **kwargs) -> bool:
            event = same_printer_entered if self.ip_address == "10.0.0.7" else other_printer_entered
            event.set()
            local_path.write_bytes(b"file")
            return True

    with patch.object(ftp_mod, "BambuFTPClient", Client):
        byte_task = asyncio.create_task(
            ftp_mod.download_file_bytes_async("10.0.0.7", "code", "/bytes.3mf", timeout=1.0)
        )
        assert await asyncio.get_running_loop().run_in_executor(None, byte_entered.wait, 1.0)
        same_task = asyncio.create_task(
            ftp_mod.download_file_async("10.0.0.7", "code", "/same.3mf", tmp_path / "same.3mf", timeout=1.0)
        )
        other_task = asyncio.create_task(
            ftp_mod.download_file_async("10.0.0.8", "code", "/other.3mf", tmp_path / "other.3mf", timeout=1.0)
        )
        try:
            assert await asyncio.get_running_loop().run_in_executor(None, other_printer_entered.wait, 1.0)
            await asyncio.sleep(0.05)
            assert not same_printer_entered.is_set()
        finally:
            release_byte.set()
            await asyncio.gather(byte_task, same_task, other_task)


@pytest.mark.asyncio
async def test_path_search_preserves_success_during_timeout_unwind(tmp_path: Path):
    payload = b"completed during unwind"
    local_path = tmp_path / "late-success.3mf"

    class Client(_FakeClient):
        def download_to_file(self, remote_path: str, destination: Path, **kwargs) -> bool:
            time.sleep(0.05)
            destination.write_bytes(payload)
            return True

    with (
        patch.object(ftp_mod, "BambuFTPClient", Client),
        patch.object(ftp_mod, "_DOWNLOAD_UNWIND_SECONDS", 0.2),
    ):
        result = await ftp_mod.download_file_try_paths_async(
            "10.0.0.9", "code", ["/late-success.3mf"], local_path, timeout=0.01
        )

    assert result is True
    assert local_path.read_bytes() == payload


def test_bounded_client_bypasses_existing_cooldown_without_changing_default():
    ip_address = "192.0.2.136"
    ftp_mod._arm_ftps_cooldown(ip_address)
    transport = MagicMock()
    error = ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] wrong version number")
    error.reason = "WRONG_VERSION_NUMBER"
    transport.connect.side_effect = error

    with (
        patch.object(ftp_mod, "ImplicitFTP_TLS", return_value=transport),
        patch.object(ftp_mod, "_read_cleartext_reply", return_value="421 Too many connections"),
    ):
        with pytest.raises(ftp_mod.FtpsCooldownActive):
            ftp_mod.BambuFTPClient(ip_address, "code").connect()
        assert transport.connect.call_count == 0

        result = ftp_mod.BambuFTPClient(
            ip_address,
            "code",
            respect_handshake_cooldown=False,
        ).connect()

    assert result is False
    assert transport.connect.call_count == 1


@pytest.mark.asyncio
async def test_bounded_upload_retries_reach_printer_during_cooldown(tmp_path: Path):
    ip_address = "192.0.2.137"
    ftp_mod._arm_ftps_cooldown(ip_address)
    transport = MagicMock()
    error = ssl.SSLError(1, "[SSL: WRONG_VERSION_NUMBER] wrong version number")
    error.reason = "WRONG_VERSION_NUMBER"
    transport.connect.side_effect = error
    source = tmp_path / "dispatch.3mf"
    source.write_bytes(b"3mf")
    report = ftp_mod.FtpFailureReport()

    with (
        patch.object(ftp_mod, "ImplicitFTP_TLS", return_value=transport),
        patch.object(ftp_mod, "_read_cleartext_reply", return_value=None),
    ):
        result = await ftp_mod.with_ftp_retry(
            ftp_mod.upload_file_async,
            ip_address,
            "code",
            source,
            "/dispatch.3mf",
            respect_handshake_cooldown=False,
            failure=report,
            max_retries=2,
            retry_delay=0,
        )

    assert result is None
    assert transport.connect.call_count == 3
    assert report.failure is not None
    assert report.failure.kind is ftp_mod.FtpFailureKind.HANDSHAKE


@pytest.mark.parametrize(
    ("kind", "expected", "forbidden"),
    [
        ("storage", "SD card", "network"),
        ("handshake", "TLS", "Check that its SD card"),
        ("network", "network", "Check that its SD card"),
        ("auth", "access code", "Check that its SD card"),
    ],
)
def test_upload_failure_message_uses_recorded_cause(kind: str, expected: str, forbidden: str):
    failure = ftp_mod.FtpFailure(ftp_mod.FtpFailureKind(kind), "detail", "553" if kind == "storage" else None)

    message = ftp_mod.describe_upload_failure(failure)

    assert expected in message
    assert forbidden not in message
