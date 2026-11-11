"""Size-aware byte transfers with cooperative cancellation and bounded cleanup."""

import asyncio
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

logger = logging.getLogger("backend.app.services.bambu_ftp")


@dataclass(frozen=True)
class ByteDownloadRequest:
    ip_address: str
    access_code: str = field(repr=False)
    remote_path: str
    timeout: float
    socket_timeout: float | None
    printer_model: str | None
    expected_size: int | None
    progress_callback: Callable | None
    raise_on_not_found: bool
    max_total_timeout: float
    unwind_seconds: float
    floor_bytes_per_sec: float


async def download_bytes(client_factory, request, *, extension, cancelled_error, deadline_error, discard_worker):
    loop = asyncio.get_running_loop()
    cancel = threading.Event()
    reported = {}
    known_size = request.expected_size
    sized = type(known_size) is int and known_size > 0
    timeout = max(request.timeout, known_size / request.floor_bytes_per_sec) if sized else request.timeout

    def transfer():
        if cancel.is_set():
            return None
        client = client_factory(
            request.ip_address, request.access_code, timeout=request.socket_timeout, printer_model=request.printer_model
        )
        if not client.connect():
            return None
        try:
            return client.download_file(
                request.remote_path,
                expected_size=known_size,
                progress_callback=request.progress_callback,
                total_bytes=known_size or 0,
                raise_on_not_found=request.raise_on_not_found,
                cancel_event=cancel,
                size_callback=None if sized else lambda size: reported.__setitem__("size", size),
            )
        finally:
            client.disconnect()

    worker = loop.run_in_executor(None, transfer)

    async def stop_worker():
        cancel.set()
        try:
            data = await asyncio.wait_for(asyncio.shield(worker), request.unwind_seconds)
            return True, data
        except TimeoutError:
            discard_worker(worker)
            return False, None
        except Exception:
            return True, None

    allowed = timeout
    try:
        try:
            return await asyncio.wait_for(asyncio.shield(worker), timeout)
        except TimeoutError:
            extra = 0 if sized else extension(reported.get("size"), timeout, request.max_total_timeout)
            if extra <= 0:
                raise
            allowed += extra
            sized = True
            return await asyncio.wait_for(asyncio.shield(worker), extra)
    except asyncio.CancelledError:
        await asyncio.shield(stop_worker())
        raise
    except cancelled_error:
        return None
    except TimeoutError:
        finished, data = await stop_worker()
        if data:
            return data
        logger.warning(
            "FTP download of %s (%s bytes) exceeded its %.0fs cap for %s",
            request.remote_path,
            known_size or reported.get("size") or "unknown",
            allowed,
            request.ip_address,
        )
        # An unfinished thread or an exhausted size-fitted budget must never retry.
        if sized or not finished:
            raise deadline_error(request.remote_path) from None
        return None
