"""Bounded FTPS-to-HTTP downloads for the authorized printer file manager."""

import asyncio
import concurrent.futures
import socket
import threading
from collections.abc import AsyncIterator, Callable

import anyio

from backend.app.services.bambu_ftp import (
    BambuFTPClient,
    DownloadCancelled,
    DownloadDeadlineExceeded,
    FileNotOnPrinterError,
    FTPProtocolError,
    FtpsCooldownActive,
    _download_deadline,
    _serialized_download,
    with_ftp_retry,
)
from backend.app.utils.filename import InvalidFilenameError, validate_print_filename

_STREAM_QUEUE_CHUNKS = 8


def validate_printer_file_path(path: str) -> None:
    """Reject FTP command injection and traversal before opening a connection."""
    if not isinstance(path, str) or not path.startswith("/") or len(path.encode("utf-8")) > 1024:
        raise ValueError("Invalid printer file path")
    try:
        for part in path[1:].split("/"):
            validate_print_filename(part)
    except InvalidFilenameError as exc:
        raise ValueError("Invalid printer file path") from exc


class PrinterFileTransferError(OSError):
    """A started response cannot safely retry by replaying its first bytes."""


async def stream_printer_file(
    ip_address: str,
    access_code: str,
    remote_path: str,
    *,
    printer_model: str | None = None,
    total_bytes: int | None = None,
    socket_timeout: float = BambuFTPClient.DEFAULT_TIMEOUT,
    timeout: float | None = None,
    max_retries: int = 0,
    retry_delay: float = 2,
    progress_callback: Callable[[int, int], None] | None = None,
) -> AsyncIterator[bytes]:
    """Stream with backpressure; retain the printer gate until the worker stops.

    Only failures before the first queued byte can retry. Cancellation closes
    the active data/control sockets and unblocks a producer waiting on a full
    queue. The caller must close the iterator if HTTP delivery stops.
    """
    validate_printer_file_path(remote_path)
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue(_STREAM_QUEUE_CHUNKS)
    cancel = threading.Event()
    active: dict[str, object] = {}
    started = threading.Event()

    def close_socket(sock: socket.socket | None) -> None:
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def stop_worker() -> None:
        cancel.set()
        close_socket(active.get("data"))
        client = active.get("client")
        ftp = getattr(client, "_ftp", None)
        close_socket(getattr(ftp, "sock", None))

    def emit(chunk: bytes) -> None:
        if cancel.is_set():
            raise DownloadCancelled(remote_path)
        pending = asyncio.run_coroutine_threadsafe(queue.put(chunk), loop)
        try:
            while True:
                if cancel.is_set():
                    raise DownloadCancelled(remote_path)
                try:
                    pending.result(timeout=0.1)
                    started.set()
                    return
                except concurrent.futures.TimeoutError:
                    continue
        finally:
            if not pending.done():
                pending.cancel()

    def transfer(force_prot_c: bool) -> bool:
        if cancel.is_set():
            raise DownloadCancelled(remote_path)
        client = BambuFTPClient(
            ip_address, access_code, timeout=socket_timeout, printer_model=printer_model, force_prot_c=force_prot_c
        )
        active["client"] = client
        try:
            if not client.connect():
                raise OSError("Could not connect to the printer file service")
            if cancel.is_set():
                raise DownloadCancelled(remote_path)
            client.download_to_sink(
                remote_path,
                emit,
                cancel_event=cancel,
                expected_size=total_bytes,
                progress_callback=progress_callback,
                data_socket_callback=lambda sock: active.__setitem__("data", sock),
            )
            BambuFTPClient.cache_mode(ip_address, "prot_c" if client._should_use_prot_c() else "prot_p")
            return True
        finally:
            active.pop("data", None)
            if cancel.is_set() and getattr(client, "_ftp", None):
                client._ftp.close()
            else:
                client.disconnect()
            active.pop("client", None)

    async def attempt() -> bool:
        async def run(mode: bool) -> bool:
            worker = loop.run_in_executor(None, transfer, mode)
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                stop_worker()
                try:
                    await asyncio.shield(worker)
                except (DownloadCancelled, OSError, FTPProtocolError):
                    pass
                raise

        try:
            try:
                return await run(False)
            except (FileNotOnPrinterError, FtpsCooldownActive, DownloadCancelled):
                raise
            except Exception:
                if not started.is_set() and printer_model in BambuFTPClient.A1_MODELS:
                    return await run(True)
                raise
        except Exception as exc:
            if started.is_set() and not isinstance(exc, DownloadCancelled):
                raise PrinterFileTransferError("Printer file transfer interrupted; download the file again") from exc
            raise

    async def produce() -> None:
        try:
            result = await asyncio.wait_for(
                with_ftp_retry(
                    attempt,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    operation_name="Printer file download",
                    non_retry_exceptions=(FileNotOnPrinterError, DownloadCancelled, PrinterFileTransferError),
                ),
                timeout=timeout if timeout is not None else _download_deadline(total_bytes or 0),
            )
            if result is not True:
                raise OSError("Could not download the printer file after retries")
            await queue.put(None)
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            await queue.put(DownloadDeadlineExceeded(remote_path))
        except Exception as exc:
            await queue.put(exc)

    async with _serialized_download(ip_address, f"stream of {remote_path}"):
        producer = asyncio.create_task(produce())
        try:
            while True:
                item = await queue.get()
                if isinstance(item, BaseException):
                    raise item
                if item is None:
                    break
                yield item
        finally:
            stop_worker()
            with anyio.CancelScope(shield=True):
                producer.cancel()
                try:
                    await asyncio.shield(producer)
                except asyncio.CancelledError:
                    pass
