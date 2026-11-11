"""Shared listing work and UTC-based FTP LIST timestamps."""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Import the FTP reply type only. The caller supplies the printer transport.
from ftplib import error_perm  # nosec B402

from backend.app.services.ftp_background import clear_stall, record_stall

logger = logging.getLogger("backend.app.services.bambu_ftp")


@dataclass(frozen=True)
class FileListResult:
    files: list[dict]
    available: bool
    timed_out: bool = False
    error: Exception | None = field(default=None, repr=False, compare=False)

    @property
    def missing(self):
        return listing_missing(self.error)


def listing_missing(error):
    """A missing directory differs from an unread one, including wrapped errors."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, error_perm) and str(error).startswith("550"):
            return not any(word in str(error).lower() for word in ("denied", "permission", "access"))
        error = error.__cause__
    return False


# Loop and credentials are part of the identity; never log this key.
_inflight_listings: dict[tuple, tuple[asyncio.Future, threading.Event]] = {}


async def list_files_result(client_factory, ip_address, access_code, path, timeout, socket_timeout, printer_model):
    loop = asyncio.get_running_loop()
    key = (loop, ip_address, access_code, path, socket_timeout, printer_model)
    running = _inflight_listings.get(key)
    if running is None or running[0].done():
        connected = threading.Event()

        def fetch():
            client = client_factory(ip_address, access_code, timeout=socket_timeout, printer_model=printer_model)
            try:
                if not client.connect():
                    return FileListResult([], False)
                connected.set()
                files = client.list_files(path, raise_on_error=True)
                clear_stall(ip_address)
                return FileListResult(files, True)
            except Exception as error:
                cause = error.__cause__ or error
                if isinstance(cause, TimeoutError):
                    record_stall(ip_address, "directory listing timed out")
                return FileListResult([], False, error=error)
            finally:
                if connected.is_set():
                    client.disconnect()

        future = loop.run_in_executor(None, fetch)
        running = (future, connected)
        _inflight_listings[key] = running

        def forget(done):
            current = _inflight_listings.get(key)
            if current is not None and current[0] is done:
                _inflight_listings.pop(key, None)
            if not done.cancelled():
                done.exception()

        future.add_done_callback(forget)
    future, connected = running
    try:
        result = await asyncio.wait_for(asyncio.shield(future), timeout)
    except TimeoutError as error:
        record_stall(ip_address, "directory listing deadline expired")
        logger.warning("FTP list_files timed out after %ss for %s", timeout, path)
        return FileListResult([], False, timed_out=connected.is_set(), error=error)
    return FileListResult([dict(row) for row in result.files], result.available, result.timed_out, result.error)


def _parse_list_mtime(month, day, time_or_year, *, now_utc=None):
    """Return a naive printer timestamp, choosing its year against UTC."""
    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is not None:
        now_utc = now_utc.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        if ":" in time_or_year:
            result = datetime.strptime(f"{month} {day} {now_utc.year} {time_or_year}", "%b %d %Y %H:%M")
            return result.replace(year=now_utc.year - 1) if result > now_utc + timedelta(days=1) else result
        return datetime.strptime(f"{month} {day} {time_or_year}", "%b %d %Y")
    except ValueError:
        return None
