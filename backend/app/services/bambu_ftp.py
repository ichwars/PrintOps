import asyncio
import ftplib  # nosec B402
import logging
import os
import socket
import ssl
import threading
import time
import weakref
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from ftplib import FTP, FTP_TLS  # nosec B402
from io import BytesIO
from pathlib import Path
from typing import TypeVar

from backend.app.services.ftp_background import clear_stall, record_stall, stalled
from backend.app.services.ftp_download_bytes import ByteDownloadRequest, download_bytes
from backend.app.services.ftp_listing import (
    FileListResult,
    _inflight_listings as _inflight_listings,
    _parse_list_mtime,
    list_files_result,
)

FTPProtocolError = ftplib.Error

logger = logging.getLogger(__name__)

T = TypeVar("T")

_UPLOAD_FLOOR_BYTES_PER_SEC = 25 * 1024
_UPLOAD_MIN_TIMEOUT = 600.0
_UPLOAD_CANCEL_GRACE = 60.0

_DOWNLOAD_FLOOR_BYTES_PER_SEC = 25 * 1024
_DOWNLOAD_MAX_TIMEOUT = 300.0
RECOVERY_DOWNLOAD_MAX_TIMEOUT = 900.0
_DOWNLOAD_GATE_WAIT_SECONDS = 30.0
_DOWNLOAD_UNWIND_SECONDS = 30.0


def _download_extension(size_bytes: int | None, base_timeout: float, ceiling: float = _DOWNLOAD_MAX_TIMEOUT) -> float:
    """Return bounded extra time for a download whose size is known (#136)."""
    if not size_bytes or size_bytes <= 0:
        return 0.0
    sized_timeout = min(size_bytes / _DOWNLOAD_FLOOR_BYTES_PER_SEC, ceiling)
    return max(0.0, sized_timeout - base_timeout)


_download_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]] = (
    weakref.WeakKeyDictionary()
)


def _download_lock(loop: asyncio.AbstractEventLoop, ip_address: str) -> asyncio.Lock:
    per_loop = _download_locks.setdefault(loop, {})
    return per_loop.setdefault(ip_address, asyncio.Lock())


@asynccontextmanager
async def _serialized_download(ip_address: str, what: str, *, enabled: bool = True) -> AsyncIterator[bool]:
    """Prefer one heavy download per printer without making the gate fatal."""
    if not enabled:
        yield False
        return

    loop = asyncio.get_event_loop()
    lock = _download_lock(loop, ip_address)
    started = loop.time()
    held = False
    try:
        await asyncio.wait_for(lock.acquire(), timeout=_DOWNLOAD_GATE_WAIT_SECONDS)
        held = True
        waited = loop.time() - started
        if waited > 1.0:
            logger.info("Waited %.1fs for printer %s before %s", waited, ip_address, what)
    except TimeoutError:
        logger.warning(
            "Printer %s is still busy after %ss; starting %s concurrently",
            ip_address,
            _DOWNLOAD_GATE_WAIT_SECONDS,
            what,
        )
    try:
        yield held
    finally:
        if held:
            lock.release()


def _discard_worker_outcome(worker: asyncio.Future) -> None:
    """Consume a shielded worker's eventual error after its caller gives up."""

    def _read(future: asyncio.Future) -> None:
        if future.cancelled():
            return
        try:
            future.exception()
        except BaseException:
            pass

    if worker.done():
        _read(worker)
    else:
        worker.add_done_callback(_read)


# How long to stop attempting FTPS to a printer after its TLS handshake
# fails (#88). A handshake failure — TCP connects but the TLS layer errors
# out — means the printer's file service is broken, not that this specific
# path/retry was unlucky; every candidate-path fan-out (cover thumbnails,
# timelapse matching, archive metadata capture) would otherwise repeat the
# same doomed handshake dozens of times per print, flooding the logs.
FTPS_COOLDOWN_SECONDS = 300.0
_CLEARTEXT_PROBE_TIMEOUT = 2.0

# ip_address -> time.monotonic() deadline until which FTPS attempts to that
# printer are skipped. Keyed by IP (not printer id) so it applies uniformly
# across every call site, including the pre-save Add-Printer diagnostic
# which has no printer id yet.
_ftps_cooldown_until: dict[str, float] = {}
_ftps_session_exhausted: set[str] = set()


def _read_cleartext_reply(ip_address: str, port: int) -> str | None:
    """Ask a non-TLS service on the FTPS port what it actually returned."""
    sock: socket.socket | None = None
    deadline = time.monotonic() + _CLEARTEXT_PROBE_TIMEOUT
    try:
        sock = socket.create_connection((ip_address, port), _CLEARTEXT_PROBE_TIMEOUT)
        sock.settimeout(max(0.05, deadline - time.monotonic()))
        raw = sock.recv(256)
    except OSError as exc:
        logger.debug("Cleartext probe of %s:%s failed: %s", ip_address, port, exc)
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
    if not raw:
        return None
    return "".join(char for char in raw.decode("latin-1").strip() if char.isprintable()) or None


def _ftp_reply_code(error: BaseException) -> str | None:
    message = str(error)
    return message[:3] if len(message) >= 3 and message[:3].isdigit() else None


def ftps_cooldown_remaining(ip_address: str) -> float | None:
    """Seconds left in the FTPS cooldown for this IP, or None if not cooling down."""
    deadline = _ftps_cooldown_until.get(ip_address)
    if deadline is None:
        return None
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        _ftps_cooldown_until.pop(ip_address, None)
        _ftps_session_exhausted.discard(ip_address)
        return None
    return remaining


def clear_ftps_cooldown(ip_address: str) -> None:
    """Drop any active cooldown — called on a successful FTPS connect."""
    _ftps_cooldown_until.pop(ip_address, None)
    _ftps_session_exhausted.discard(ip_address)


def ftps_background_blocked(ip_address: str) -> bool:
    return ftps_cooldown_remaining(ip_address) is not None or stalled(ip_address)


def _is_too_many_connections(reply: str) -> bool:
    return reply.startswith("421") and "too many" in reply.lower()


def _arm_ftps_cooldown(ip_address: str) -> None:
    _ftps_cooldown_until[ip_address] = time.monotonic() + FTPS_COOLDOWN_SECONDS


class FtpsCooldownActive(Exception):
    """Raised instead of attempting a doomed FTPS handshake during cooldown.

    Its message is written to be surfaced directly to users (HTTPException
    detail, diagnostic text) — it names the file-transfer service and
    suggests a printer restart per #88's acceptance criteria.
    """

    def __init__(self, ip_address: str, remaining: float):
        self.ip_address = ip_address
        self.remaining = remaining
        if ip_address in _ftps_session_exhausted:
            super().__init__(
                f"Printer {ip_address} has no file-transfer sessions left (421 too many connections). "
                "If this does not clear within a few minutes, restart the printer."
            )
            return
        super().__init__(
            f"File-transfer service on {ip_address} failed its TLS handshake; "
            f"pausing FTPS attempts to this printer for {remaining:.0f}s more. "
            f"If this persists, try restarting the printer."
        )


class FtpFailureKind(Enum):
    STORAGE = "storage"
    HANDSHAKE = "handshake"
    SESSIONS = "sessions"
    COOLOFF = "cooloff"
    AUTH = "auth"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    NETWORK = "network"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FtpFailure:
    kind: FtpFailureKind
    detail: str
    code: str | None = None


@dataclass
class FtpFailureReport:
    """Per-operation failure holder safe from unrelated concurrent transfers."""

    failure: FtpFailure | None = None


class UploadCancelled(Exception):
    """Raised inside an upload worker to abort an in-flight transfer."""


class DownloadCancelled(Exception):
    """Raised inside a download worker after cooperative cancellation."""


class DownloadDeadlineExceeded(Exception):
    """A progressing download exhausted its size-derived total budget."""


class DeleteResult(Enum):
    """Outcome of an FTP delete attempt.

    Distinguishes "file isn't on the printer" (550, recovery impossible by
    retrying) from "delete failed for some other reason" (network, auth,
    transient FTP error — worth retrying). The post-print SD-card cleanup in
    main.py used to flatten both into ``False`` and log a "may linger" WARNING
    on every successful print where the printer self-cleaned its SD card
    before our cleanup ran (#1721 reporter's A1).
    """

    DELETED = "deleted"
    NOT_FOUND = "not_found"
    FAILED = "failed"


class FileNotOnPrinterError(Exception):
    """Raised when a remote FTP path returns 550 (file not found).

    550 means the file does not exist at that path — retrying the same path
    will never succeed. Callers use this sentinel with with_ftp_retry's
    non_retry_exceptions to immediately move on to the next candidate path
    instead of burning the full retry budget (up to 11 × 30s per path) on
    a lookup that cannot recover.
    """


class FileListingError(Exception):
    """Raised when callers need to distinguish a failed listing from an empty directory."""


class ImplicitFTP_TLS(FTP_TLS):
    """FTP_TLS subclass for implicit FTPS (port 990) with model-specific SSL handling.

    X1C/P1S printers (vsFTPd) require SSL with session reuse on the data channel.
    A1/A1 Mini printers have issues with SSL on the data channel entirely and
    timeout waiting for transfer completion. Set skip_session_reuse=True for A1
    printers to skip SSL on the data channel (control channel remains encrypted).

    Optionally caps the SSL context's maximum TLS version to v1.2 (P2S firmware
    01.02.00.00 needs this — see :mod:`ftp_profiles` and #1401).
    """

    def __init__(self, *args, skip_session_reuse: bool = False, cap_tls_v1_2: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None
        self.skip_session_reuse = skip_session_reuse
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
        if cap_tls_v1_2:
            self.ssl_context.maximum_version = ssl.TLSVersion.TLSv1_2

    def connect(self, host="", port=990, timeout=-999, source_address=None):
        """Connect to host, wrapping socket in TLS immediately (implicit FTPS)."""
        if host:
            self.host = host
        if port > 0:
            self.port = port
        if timeout != -999:
            self.timeout = timeout
        if source_address:
            self.source_address = source_address

        # Create and wrap socket immediately (implicit TLS)
        self.sock = socket.create_connection((self.host, self.port), self.timeout, source_address=self.source_address)
        self.sock = self.ssl_context.wrap_socket(self.sock, server_hostname=self.host)
        self.af = self.sock.family
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd, rest=None):
        """Override to wrap data connection in SSL for X1C/P1S only.

        X1C/P1S printers (vsFTPd) require SSL session reuse on the data channel.
        A1/A1 Mini printers have issues with SSL on the data channel entirely -
        they timeout waiting for the transfer completion response. For A1, we
        skip SSL wrapping on the data channel (control channel remains encrypted).
        """
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p and not self.skip_session_reuse:
            # X1C/P1S: Wrap data channel with SSL session reuse (required by vsFTPd)
            conn = self.ssl_context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,
            )
        # A1/A1 Mini (skip_session_reuse=True): Don't wrap data channel in SSL
        # The control channel remains encrypted via implicit FTPS
        return conn, size


class BambuFTPClient:
    """FTP client for retrieving files from Bambu Lab printers."""

    FTP_PORT = 990
    # Default timeout in seconds (increased for A1 printers)
    DEFAULT_TIMEOUT = 30
    # Models that may need SSL mode fallback (try prot_p first, fall back to prot_c)
    # These models have varying FTP SSL behavior depending on firmware version
    A1_MODELS = ("A1", "A1 Mini")
    # Chunk size for manual upload transfer (64KB)
    # Smaller chunks provide smoother progress reporting — at typical printer FTP
    # speeds (~50-100KB/s) this gives a progress update roughly every second.
    CHUNK_SIZE = 64 * 1024

    # Cache for working FTP modes per printer IP
    # Maps IP -> "prot_p" or "prot_c"
    _mode_cache: dict[str, str] = {}

    def __init__(
        self,
        ip_address: str,
        access_code: str,
        timeout: float | None = None,
        printer_model: str | None = None,
        force_prot_c: bool = False,
        respect_handshake_cooldown: bool = True,
        record_handshake_cooldown: bool = True,
    ):
        self.ip_address = ip_address
        self.access_code = access_code
        self.timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        self.printer_model = printer_model
        self.force_prot_c = force_prot_c
        self.respect_handshake_cooldown = respect_handshake_cooldown
        self.record_handshake_cooldown = record_handshake_cooldown
        self.last_failure: FtpFailure | None = None
        self._ftp: ImplicitFTP_TLS | None = None

    def _is_a1_model(self) -> bool:
        """Check if this is an A1 series printer."""
        if not self.printer_model:
            return False
        return self.printer_model in self.A1_MODELS

    def _get_cached_mode(self) -> str | None:
        """Get cached FTP mode for this printer."""
        return self._mode_cache.get(self.ip_address)

    @classmethod
    def cache_mode(cls, ip_address: str, mode: str):
        """Cache the working FTP mode for a printer."""
        cls._mode_cache[ip_address] = mode
        logger.info("FTP mode cached for %s: %s", ip_address, mode)

    def _should_use_prot_c(self) -> bool:
        """Determine if we should use prot_c (clear) mode."""
        # If explicitly forced, use prot_c
        if self.force_prot_c:
            return True
        # Check cache first
        cached = self._get_cached_mode()
        if cached:
            return cached == "prot_c"
        # Default: try prot_p first (will fall back if needed)
        return False

    def connect(self) -> bool:
        """Connect to the printer FTP server (implicit FTPS on port 990).

        Raises FtpsCooldownActive without touching the network if this IP's
        TLS handshake recently failed and the cooldown window (#88) is still
        active, and again if the handshake fails here — see
        ftps_cooldown_remaining / FTPS_COOLDOWN_SECONDS.
        """
        remaining = ftps_cooldown_remaining(self.ip_address)
        if remaining is not None and self.respect_handshake_cooldown:
            self.last_failure = FtpFailure(
                FtpFailureKind.SESSIONS if self.ip_address in _ftps_session_exhausted else FtpFailureKind.COOLOFF,
                f"FTPS handshake cooldown has {remaining:.0f}s remaining",
            )
            raise FtpsCooldownActive(self.ip_address, remaining)

        use_prot_c = self._should_use_prot_c()
        from backend.app.services.ftp_profiles import get_ftp_profile

        profile = get_ftp_profile(self.printer_model)
        logger.debug(
            f"FTP connecting to {self.ip_address}:{self.FTP_PORT} "
            f"(timeout={self.timeout}s, model={self.printer_model}, prot_c={use_prot_c}, "
            f"cap_tls_v1_2={profile.cap_tls_v1_2})"
        )
        self._ftp = ImplicitFTP_TLS(
            skip_session_reuse=use_prot_c,
            cap_tls_v1_2=profile.cap_tls_v1_2,
        )

        # Isolate the TCP-connect + TLS-handshake step: an ssl.SSLError here
        # means the port answered but the TLS layer itself is broken (the
        # printer's file service is wedged, per #88) — distinct from a
        # closed port (OSError below, still just a transient/unreachable
        # case worth retrying normally).
        try:
            self._ftp.connect(self.ip_address, self.FTP_PORT, timeout=self.timeout)
        except ssl.SSLError as e:
            failed_ftp = self._ftp
            self._ftp = None
            try:
                failed_ftp.close()
            except (OSError, ftplib.Error, EOFError):
                pass
            detail = str(e)
            if (
                self.record_handshake_cooldown
                and getattr(e, "reason", None) == "WRONG_VERSION_NUMBER"
                and remaining is None
            ):
                reply = _read_cleartext_reply(self.ip_address, self.FTP_PORT)
                if reply:
                    if _is_too_many_connections(reply):
                        _ftps_session_exhausted.add(self.ip_address)
                    detail = f"{e} (printer answered in cleartext: {reply})"
                    logger.warning(
                        "Printer %s answered FTPS port %s in cleartext with: %s",
                        self.ip_address,
                        self.FTP_PORT,
                        reply,
                    )
                else:
                    logger.warning(
                        "Printer %s sent no readable cleartext response on FTPS port %s",
                        self.ip_address,
                        self.FTP_PORT,
                    )
            logger.warning("FTP TLS handshake failed for %s: %s", self.ip_address, e)
            if self.record_handshake_cooldown:
                _arm_ftps_cooldown(self.ip_address)
                logger.warning("Pausing FTPS attempts to %s for %.0fs", self.ip_address, FTPS_COOLDOWN_SECONDS)
            kind = FtpFailureKind.SESSIONS if self.ip_address in _ftps_session_exhausted else FtpFailureKind.HANDSHAKE
            self.last_failure = FtpFailure(kind, detail, "421" if kind is FtpFailureKind.SESSIONS else None)
            if self.respect_handshake_cooldown:
                raise FtpsCooldownActive(self.ip_address, FTPS_COOLDOWN_SECONDS) from e
            return False
        except TimeoutError as e:
            logger.warning("FTP connection timed out to %s: %s", self.ip_address, e)
            self.last_failure = FtpFailure(FtpFailureKind.TIMEOUT, str(e))
            if self.respect_handshake_cooldown:
                record_stall(self.ip_address, "connect timed out")
            self._ftp = None
            return False
        except (OSError, ftplib.Error) as e:
            logger.warning("FTP connection failed to %s: %s (type: %s)", self.ip_address, e, type(e).__name__)
            kind = FtpFailureKind.SESSIONS if _is_too_many_connections(str(e)) else FtpFailureKind.NETWORK
            self.last_failure = FtpFailure(kind, str(e), _ftp_reply_code(e))
            if kind is FtpFailureKind.SESSIONS and self.respect_handshake_cooldown:
                record_stall(self.ip_address, "FTP session limit")
            self._ftp = None
            return False

        try:
            logger.debug("FTP connected, logging in as bblp")
            self._ftp.login("bblp", self.access_code)
            if use_prot_c:
                # Use clear (unencrypted) data channel
                logger.debug("FTP logged in, setting prot_c (clear) and passive mode")
                self._ftp.prot_c()
            else:
                # Use protected (encrypted) data channel with session reuse
                logger.debug("FTP logged in, setting prot_p (protected) and passive mode")
                self._ftp.prot_p()
            self._ftp.set_pasv(True)
            # Log welcome message for debugging
            if hasattr(self._ftp, "welcome") and self._ftp.welcome:
                logger.debug("FTP server welcome: %s", self._ftp.welcome)
            logger.info(
                f"FTP connected successfully to {self.ip_address} (model={self.printer_model}, prot_c={use_prot_c})"
            )
            if self.record_handshake_cooldown:
                clear_ftps_cooldown(self.ip_address)
            return True
        except ftplib.error_perm as e:
            logger.warning("FTP connection permission error to %s: %s", self.ip_address, e)
            self.last_failure = FtpFailure(FtpFailureKind.AUTH, str(e), _ftp_reply_code(e))
            self._ftp = None
            return False
        except TimeoutError as e:
            logger.warning("FTP connection timed out to %s: %s", self.ip_address, e)
            self.last_failure = FtpFailure(FtpFailureKind.TIMEOUT, str(e))
            if self.respect_handshake_cooldown:
                record_stall(self.ip_address, "connect timed out")
            self._ftp = None
            return False
        except ssl.SSLError as e:
            logger.warning("FTP SSL error connecting to %s: %s", self.ip_address, e)
            self.last_failure = FtpFailure(FtpFailureKind.HANDSHAKE, str(e))
            self._ftp = None
            return False
        except (OSError, ftplib.Error) as e:
            logger.warning("FTP connection failed to %s: %s (type: %s)", self.ip_address, e, type(e).__name__)
            kind = FtpFailureKind.SESSIONS if _is_too_many_connections(str(e)) else FtpFailureKind.NETWORK
            self.last_failure = FtpFailure(kind, str(e), _ftp_reply_code(e))
            if kind is FtpFailureKind.SESSIONS and self.respect_handshake_cooldown:
                record_stall(self.ip_address, "FTP session limit")
            self._ftp = None
            return False

    def disconnect(self):
        """Disconnect from the FTP server."""
        if self._ftp:
            try:
                self._ftp.quit()
            except (OSError, ftplib.Error, EOFError):
                pass  # Best-effort FTP cleanup; connection may already be closed
            self._ftp = None

    def list_files(self, path: str = "/", *, raise_on_error: bool = False) -> list[dict]:
        """List files in a directory.

        ``raise_on_error`` preserves the historic best-effort default while
        allowing safety-sensitive callers to reject an incomplete snapshot.
        """
        if not self._ftp:
            if raise_on_error:
                raise FileListingError("FTP client is not connected")
            return []

        files = []
        try:
            self._ftp.cwd(path)
            items = []
            self._ftp.retrlines("LIST", items.append)

            for item in items:
                parts = item.split()
                if len(parts) >= 9:
                    name = " ".join(parts[8:])
                    is_dir = item.startswith("d")
                    size = int(parts[4]) if not is_dir else 0

                    # Parse modification time from FTP listing
                    # Format: "Nov 30 10:15" or "Nov 30  2024"
                    mtime = _parse_list_mtime(parts[5], parts[6], parts[7])

                    file_entry = {
                        "name": name,
                        "is_directory": is_dir,
                        "size": size,
                        "path": f"{path.rstrip('/')}/{name}",
                    }
                    if mtime:
                        file_entry["mtime"] = mtime
                    files.append(file_entry)
            logger.debug("Listed %s files in %s", len(files), path)
            clear_stall(self.ip_address)
        except (OSError, ftplib.Error) as e:
            logger.info("FTP list_files failed for %s: %s", path, e)
            if isinstance(e, TimeoutError) and self.respect_handshake_cooldown:
                record_stall(self.ip_address, "listing timed out")
            if raise_on_error:
                raise FileListingError(f"FTP listing failed for {path}") from e

        return files

    def download_file(
        self,
        remote_path: str,
        progress_callback: Callable[[int, int], None] | None = None,
        total_bytes: int = 0,
        raise_on_not_found: bool = False,
        expected_size: int | None = None,
        cancel_event: threading.Event | None = None,
        size_callback: Callable[[int], None] | None = None,
    ) -> bytes | None:
        """Read one complete file, checking size and cancellation before buffering."""
        if not self._ftp:
            return None
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelled(remote_path)
        if size_callback is not None:
            try:
                server_size = self._ftp.size(remote_path)
            except (OSError, ftplib.Error):
                server_size = None
            if type(server_size) is int and server_size > 0:
                size_callback(server_size)
                if expected_size is None:
                    expected_size = server_size
        buffer = BytesIO()
        transferred = 0

        def write(chunk):
            nonlocal transferred
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadCancelled(remote_path)
            if expected_size is not None and transferred + len(chunk) > expected_size:
                raise OSError("Printer file changed size during download")
            buffer.write(chunk)
            transferred += len(chunk)
            if progress_callback is not None:
                progress_callback(transferred, total_bytes or expected_size or 0)

        try:
            self._ftp.retrbinary(f"RETR {remote_path}", write)
            if not transferred or (expected_size is not None and transferred != expected_size):
                logger.info("FTP download of %s is incomplete: %s of %s bytes", remote_path, transferred, expected_size)
                return None
            return buffer.getvalue()
        except ftplib.error_perm as error:
            if raise_on_not_found and str(error).startswith("550"):
                raise FileNotOnPrinterError(f"{remote_path}: {error}") from error
            return None
        except (OSError, ftplib.Error) as error:
            logger.info("FTP download failed for %s: %s", remote_path, error)
            return None

    def download_to_sink(
        self,
        remote_path: str,
        sink: Callable[[bytes], None],
        *,
        expected_size: int | None = None,
        cancel_event: threading.Event | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        data_socket_callback: Callable[[socket.socket], None] | None = None,
    ) -> None:
        """Forward bounded chunks, validating completion without buffering."""
        if not self._ftp:
            raise OSError("Printer file service is not connected")
        transferred = 0
        pending = None
        try:
            self._ftp.voidcmd("TYPE I")
            with self._ftp.transfercmd(f"RETR {remote_path}") as conn:
                if data_socket_callback is not None:
                    data_socket_callback(conn)
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled(remote_path)
                    chunk = conn.recv(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    if expected_size is not None and transferred + len(chunk) > expected_size:
                        raise OSError("Printer file changed size during download")
                    if pending is not None:
                        sink(pending)
                    pending = chunk
                    transferred += len(chunk)
                    if progress_callback is not None:
                        progress_callback(transferred, expected_size or 0)
                if isinstance(conn, ssl.SSLSocket):
                    conn.unwrap()
            self._ftp.voidresp()
            if expected_size is not None and transferred != expected_size:
                raise OSError("Printer file download is incomplete")
            if pending is not None:
                sink(pending)
        except ftplib.error_perm as exc:
            if str(exc).startswith("550"):
                raise FileNotOnPrinterError(remote_path) from exc
            raise

    def download_to_file(
        self,
        remote_path: str,
        local_path: Path,
        *,
        expected_size: int | None = None,
        cancel_event: threading.Event | None = None,
        size_callback: Callable[[int], None] | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> bool:
        """Download to disk with reported-size progress and cancellation."""
        if not self._ftp:
            logger.warning("download_to_file called but FTP not connected")
            return False

        try:
            local_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._ftp.voidcmd("TYPE I")
                server_size = self._ftp.size(remote_path)
            except (OSError, ftplib.Error):
                server_size = None
            authoritative_size = server_size if server_size is not None and server_size >= 0 else expected_size
            if size_callback is not None and authoritative_size and authoritative_size > 0:
                size_callback(authoritative_size)

            with open(local_path, "wb") as f:
                written = 0

                def _write(chunk: bytes) -> None:
                    nonlocal written
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled(remote_path)
                    f.write(chunk)
                    written += len(chunk)
                    if progress_callback is not None:
                        progress_callback(written, authoritative_size or 0)

                self._ftp.retrbinary(f"RETR {remote_path}", _write)
                f.flush()
                os.fsync(f.fileno())
            file_size = local_path.stat().st_size if local_path.exists() else 0
            if file_size == 0:
                logger.warning("FTP download returned 0 bytes for %s", remote_path)
                if local_path.exists():
                    local_path.unlink()
                return False
            if authoritative_size is not None and file_size != authoritative_size:
                logger.warning(
                    "FTP download of %s was incomplete: got %s of %s bytes",
                    remote_path,
                    file_size,
                    authoritative_size,
                )
                local_path.unlink(missing_ok=True)
                return False
            logger.info("Successfully downloaded %s to %s (%s bytes)", remote_path, local_path, file_size)
            return True
        except (OSError, ftplib.Error, DownloadCancelled) as e:
            # Clean up partial file if it exists
            if local_path.exists():
                try:
                    local_path.unlink()
                except OSError:
                    pass  # Best-effort partial file cleanup; not critical if removal fails
            if isinstance(e, DownloadCancelled):
                raise
            # 550 means the file is not at this path. Surface as a sentinel so
            # with_ftp_retry can abandon this path immediately and the caller
            # can advance to the next candidate instead of retrying 11× at
            # 30s intervals (the pattern that cost #972's reporter ~48min).
            if isinstance(e, ftplib.error_perm) and str(e).startswith("550"):
                logger.info("FTP download failed for %s: %s (not on printer)", remote_path, e)
                raise FileNotOnPrinterError(f"{remote_path}: {e}") from e
            # Log at INFO level so we can see failures in normal logs
            logger.info("FTP download failed for %s: %s", remote_path, e)
            return False

    def diagnose_storage(self) -> dict:
        """Run storage diagnostics and return results. For debugging upload issues."""
        results = {
            "connected": self._ftp is not None,
            "can_list_root": False,
            "root_files": [],
            "can_list_cache": False,
            "storage_info": None,
            "pwd": None,
            "errors": [],
        }

        if not self._ftp:
            results["errors"].append("FTP not connected")
            return results

        # Try to get current directory
        try:
            results["pwd"] = self._ftp.pwd()
            logger.debug("FTP current directory: %s", results["pwd"])
        except (OSError, ftplib.Error) as e:
            results["errors"].append(f"PWD failed: {e}")
            logger.debug("FTP PWD failed: %s", e)

        # Try to list root directory
        try:
            self._ftp.cwd("/")
            items = []
            self._ftp.retrlines("LIST", items.append)
            results["can_list_root"] = True
            results["root_files"] = items[:10]  # First 10 entries
            logger.debug("FTP root listing (%s items): %s", len(items), items[:5])
        except (OSError, ftplib.Error) as e:
            results["errors"].append(f"LIST / failed: {e}")
            logger.debug("FTP LIST / failed: %s", e)

        # Try to list /cache (should exist on all printers)
        try:
            self._ftp.cwd("/cache")
            items = []
            self._ftp.retrlines("LIST", items.append)
            results["can_list_cache"] = True
            logger.debug("FTP /cache listing: %s items", len(items))
        except (OSError, ftplib.Error) as e:
            results["errors"].append(f"LIST /cache failed: {e}")
            logger.debug("FTP LIST /cache failed: %s", e)

        # Try to get storage info
        try:
            results["storage_info"] = self.get_storage_info()
            logger.debug("FTP storage info: %s", results["storage_info"])
        except (OSError, ftplib.Error) as e:
            results["errors"].append(f"Storage info failed: {e}")

        return results

    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> bool:
        """Upload a file to the printer with optional progress callback."""
        if not self._ftp:
            logger.warning("upload_file: FTP not connected")
            self.last_failure = FtpFailure(FtpFailureKind.UNKNOWN, "FTP client is not connected")
            return False

        try:
            file_size = local_path.stat().st_size if local_path.exists() else 0
            logger.info("FTP uploading %s (%s bytes) to %s", local_path, file_size, remote_path)

            uploaded = 0
            callback_exception: Exception | None = None

            # Use manual transfer instead of storbinary() for A1 compatibility
            # A1 printers have issues with storbinary's voidresp() hanging after transfer
            with open(local_path, "rb") as f:
                logger.debug("FTP STOR command starting for %s", remote_path)
                t0 = time.monotonic()
                conn = self._ftp.transfercmd(f"STOR {remote_path}")
                logger.info(
                    "FTP data channel ready in %.1fs (PASV + TLS handshake)",
                    time.monotonic() - t0,
                )

                # Set explicit socket options for reliable transfer
                conn.setblocking(True)
                conn.settimeout(self.timeout)

                try:
                    while True:
                        chunk = f.read(self.CHUNK_SIZE)
                        if not chunk:
                            logger.debug("FTP upload: final chunk reached")
                            break

                        conn.sendall(chunk)
                        uploaded += len(chunk)
                        logger.debug("FTP upload progress: %s/%s bytes", uploaded, file_size)

                        if progress_callback:
                            try:
                                progress_callback(uploaded, file_size)
                            except Exception as e:
                                callback_exception = e
                                logger.info(
                                    "FTP upload callback requested stop for %s at %s/%s bytes: %s",
                                    remote_path,
                                    uploaded,
                                    file_size,
                                    e,
                                )
                                break

                except OSError as e:
                    logger.error("FTP connection lost during upload: %s", e)
                    raise
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass

            self._confirm_upload(remote_path, file_size, cancelled=callback_exception is not None)

            if callback_exception is not None:
                cleanup_result: DeleteResult = DeleteResult.FAILED
                try:
                    cleanup_result = self.delete_file(remote_path)
                except Exception as cleanup_error:
                    logger.warning("FTP cancel cleanup failed for %s: %s", remote_path, cleanup_error)

                # NOT_FOUND is success here — the partial file is gone (printer
                # may have already swept on cancel), which is the goal.
                if cleanup_result in (DeleteResult.DELETED, DeleteResult.NOT_FOUND):
                    logger.info("FTP cancel cleanup succeeded for %s (%s)", remote_path, cleanup_result.value)
                    raise callback_exception

                raise RuntimeError(
                    f"Upload cancelled but failed to remove partial file {remote_path} from printer"
                ) from callback_exception

            elapsed = time.monotonic() - t0
            speed_kbs = (file_size / 1024) / elapsed if elapsed > 0 else 0
            logger.info(
                "FTP upload complete: %s (%s bytes in %.1fs, %.0f KB/s)",
                remote_path,
                file_size,
                elapsed,
                speed_kbs,
            )
            return True
        except ftplib.Error as e:
            # FTP reply codes distinguish storage/path failures from transport.
            error_code = _ftp_reply_code(e) or "unknown"
            if error_code in {"452", "552", "553"}:
                kind = FtpFailureKind.STORAGE
            elif error_code == "550":
                kind = FtpFailureKind.NOT_FOUND
            elif isinstance(e, ftplib.error_temp):
                kind = FtpFailureKind.NETWORK
            else:
                kind = FtpFailureKind.UNKNOWN
            self.last_failure = FtpFailure(kind, str(e), None if error_code == "unknown" else error_code)
            logger.error("FTP upload failed for %s: %s (error code: %s)", remote_path, e, error_code)
            if error_code == "553":
                logger.error(
                    "FTP 553 error - Could not create file. Possible causes: "
                    "1) No SD card inserted, 2) SD card full, 3) SD card not formatted correctly (needs FAT32/exFAT), "
                    "4) Printer busy/not ready, 5) File path issue"
                )
            elif error_code == "550":
                logger.error("FTP 550 error - File/directory not found or permission denied")
            elif error_code == "552":
                logger.error("FTP 552 error - Storage quota exceeded (SD card full?)")
            return False
        except TimeoutError as e:
            self.last_failure = FtpFailure(FtpFailureKind.TIMEOUT, str(e), _ftp_reply_code(e))
            logger.error("FTP upload timed out for %s: %s", remote_path, e)
            return False
        except ssl.SSLError as e:
            self.last_failure = FtpFailure(FtpFailureKind.HANDSHAKE, str(e), _ftp_reply_code(e))
            logger.error("FTP upload TLS failure for %s: %s", remote_path, e)
            return False
        except OSError as e:
            self.last_failure = FtpFailure(FtpFailureKind.NETWORK, str(e), _ftp_reply_code(e))
            logger.error("FTP upload failed for %s: %s (type: %s)", remote_path, e, type(e).__name__)
            return False

    def upload_bytes(self, data: bytes, remote_path: str) -> bool:
        """Upload bytes to the printer."""
        if not self._ftp:
            return False

        try:
            # Use manual transfer instead of storbinary() for A1 compatibility
            conn = self._ftp.transfercmd(f"STOR {remote_path}")
            conn.setblocking(True)
            conn.settimeout(self.timeout)

            try:
                # Send data in chunks
                offset = 0
                while offset < len(data):
                    chunk = data[offset : offset + self.CHUNK_SIZE]
                    conn.sendall(chunk)
                    offset += len(chunk)
            except OSError as e:
                logger.error("FTP connection lost during upload_bytes: %s", e)
                raise
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
            self._confirm_upload(remote_path, len(data))
            return True
        except (OSError, ftplib.Error):
            return False

    def _confirm_upload(self, remote_path: str, expected_size: int, *, cancelled: bool = False) -> None:
        """Wait for the printer to flush the data channel to the SD card."""
        assert self._ftp is not None
        try:
            old_timeout = self._ftp.sock.gettimeout()
            self._ftp.sock.settimeout(max(self.timeout, 60))
            try:
                reply = self._ftp.voidresp()
                logger.info("FTP STOR confirmed for %s: %s", remote_path, reply.strip())
            finally:
                self._ftp.sock.settimeout(old_timeout)
        except ftplib.Error as exc:
            if cancelled:
                return  # The caller will remove the partial file.
            # Some P2S firmware sends 426 even though the whole file landed.
            actual = self.get_file_size(remote_path)
            if actual != expected_size:
                logger.error(
                    "FTP STOR rejected for %s: %s; size=%s expected=%s", remote_path, exc, actual, expected_size
                )
                raise
            logger.warning("FTP STOR returned %s for %s, but all %s bytes arrived", exc, remote_path, actual)
        except Exception as exc:
            # A timeout can leave a late 226 waiting on this control channel.
            logger.warning("FTP STOR confirmation not received for %s (proceeding): %s", remote_path, exc)
            if not cancelled:
                self._check_unconfirmed_upload(remote_path, expected_size)

    def _check_unconfirmed_upload(self, remote_path: str, expected_size: int) -> None:
        actual = _size_on_new_connection(self, remote_path)
        if actual is None:
            logger.warning("Could not verify the unconfirmed FTP upload of %s", remote_path)
        elif actual != expected_size:
            logger.error(
                "Unconfirmed FTP upload of %s has %s bytes on the printer, expected %s",
                remote_path,
                actual,
                expected_size,
            )
        else:
            logger.info("Unconfirmed FTP upload of %s verified on a fresh connection (%s bytes)", remote_path, actual)

    def delete_file(self, remote_path: str) -> DeleteResult:
        """Delete a file from the printer.

        Returns :class:`DeleteResult` distinguishing the file-not-found case
        (550) from network / auth / transient FTP failure. Callers that just
        want "did it work" should check ``result == DeleteResult.DELETED``.
        """
        if not self._ftp:
            return DeleteResult.FAILED

        try:
            self._ftp.delete(remote_path)
            return DeleteResult.DELETED
        except ftplib.error_perm as e:
            if str(e).startswith("550"):
                logger.debug("FTP delete: %s not on printer (550)", remote_path)
                return DeleteResult.NOT_FOUND
            logger.warning("Failed to delete %s: %s", remote_path, e)
            return DeleteResult.FAILED
        except (OSError, ftplib.Error) as e:
            logger.warning("Failed to delete %s: %s", remote_path, e)
            return DeleteResult.FAILED

    def get_file_size(self, remote_path: str) -> int | None:
        """Get the size of a file."""
        if not self._ftp:
            return None

        try:
            return self._ftp.size(remote_path)
        except (OSError, ftplib.Error):
            return None

    def get_storage_info(self) -> dict | None:
        """Get storage information from the printer."""
        if not self._ftp:
            return None

        result = {}

        # Try AVBL command (available space) - some FTP servers support this
        try:
            response = self._ftp.sendcmd("AVBL")
            logger.debug("AVBL response: %s", response)
            # Response format: "213 <bytes available>"
            if response.startswith("213"):
                parts = response.split()
                if len(parts) >= 2:
                    result["free_bytes"] = int(parts[1])
        except (OSError, ftplib.Error) as e:
            logger.debug("AVBL command not supported: %s", e)
            # Try STAT command as fallback
            try:
                response = self._ftp.sendcmd("STAT")
                logger.debug("STAT response: %s", response)
            except (OSError, ftplib.Error):
                pass  # Both AVBL and STAT unsupported; storage info will rely on directory scan

        # Calculate used space by listing root directories
        try:
            total_used = 0
            dirs_to_scan = ["/cache", "/timelapse", "/model", "/data", "/data/Metadata", "/"]

            for dir_path in dirs_to_scan:
                try:
                    self._ftp.cwd(dir_path)
                    items = []
                    self._ftp.retrlines("LIST", items.append)

                    for item in items:
                        parts = item.split()
                        if len(parts) >= 5 and not item.startswith("d"):
                            try:
                                total_used += int(parts[4])
                            except ValueError:
                                pass  # Skip entries with non-numeric size fields
                except (OSError, ftplib.Error):
                    pass  # Directory may not exist on this printer model; skip it

            result["used_bytes"] = total_used
        except (OSError, ftplib.Error):
            pass  # Storage scan failed; return whatever info was collected above

        return result if result else None


def _size_on_new_connection(client: BambuFTPClient, remote_path: str) -> int | None:
    """Read back an upload without disturbing the original control channel."""
    probe = BambuFTPClient(
        client.ip_address,
        client.access_code,
        timeout=min(client.timeout, 5.0),
        printer_model=client.printer_model,
        force_prot_c=client.force_prot_c,
        respect_handshake_cooldown=False,
        record_handshake_cooldown=False,
    )
    probe.FTP_PORT = client.FTP_PORT
    try:
        if not probe.connect() or probe._ftp is None:
            return None
        probe._ftp.voidcmd("TYPE I")
        return probe.get_file_size(remote_path)
    except (OSError, ftplib.Error, EOFError):
        return None
    finally:
        probe.disconnect()


def describe_upload_failure(failure: FtpFailure | None) -> str:
    """Build the operator message from the failure the FTP client recorded."""
    if failure is None:
        return "Could not upload the file to the printer. See the server log for the exact reason."
    if failure.kind is FtpFailureKind.STORAGE:
        return (
            f"The printer refused to store the file ({failure.code or 'storage error'}). "
            "Check that its SD card is inserted, has free space, and is formatted FAT32 or exFAT."
        )
    if failure.kind is FtpFailureKind.SESSIONS:
        return (
            "The printer has no file-transfer sessions left (421 too many connections). "
            "If this does not clear within a few minutes, restart the printer."
        )
    if failure.kind is FtpFailureKind.HANDSHAKE:
        return (
            "The printer's file service answered, but not with TLS, so no file was sent. "
            "The SD card is not involved; see the server log for the printer's response."
        )
    if failure.kind is FtpFailureKind.COOLOFF:
        return "The printer's file service is cooling down after a failed TLS handshake; try again in a few minutes."
    if failure.kind is FtpFailureKind.AUTH:
        return "The printer rejected the access code. Update it on the Printers page and retry."
    if failure.kind is FtpFailureKind.TIMEOUT:
        return "The printer's file service did not respond in time. Check its network connection."
    if failure.kind is FtpFailureKind.NETWORK:
        return "The printer's file service could not be reached over the network. Check the printer connection."
    if failure.kind is FtpFailureKind.NOT_FOUND:
        return "The printer rejected the upload path. See the server log; the SD card is not the likely cause."
    return "Could not upload the file to the printer. See the server log for the exact reason."


# Shared 3MF download cache (#972).
#
# Both the cover thumbnail endpoint (api/routes/printers.py) and the archive
# metadata flow (main.py) fetch the same 3MF file over FTP during a print.
# On slow / contended links (A1 Wi-Fi, large files) the duplicate transfers
# compete for the printer's single FTP socket and trigger 425 "can't open
# data channel" errors, feeding back into cause-2's retry storm.
#
# This cache stores the local path of a successfully-downloaded 3MF keyed
# by (printer_id, normalized_name). Whichever flow downloads first populates
# the cache; the other flow reuses the file read-only. Evicted on print
# completion so a later print with the same name re-downloads fresh bytes.
_threemf_path_cache: dict[tuple[int, str], Path] = {}


def normalize_3mf_name(name: str) -> str:
    """Collapse various 3MF filename variants to a cache key.

    Bambu tooling produces names as bare subtask ("Part"), with .3mf, with
    .gcode.3mf, or (Studio-normalized) with spaces → underscores. All of
    these refer to the same print job on the same printer, so they must
    hash to the same cache key.
    """
    # Lowercase first so .3MF / .GCODE.3MF variants strip cleanly — a
    # real-world case since Windows-side tooling sometimes uppercases
    # extensions.
    cleaned = name.strip().lower().replace(".gcode.3mf", "").replace(".gcode", "").replace(".3mf", "")
    return cleaned.replace(" ", "_")


def cache_3mf_download(printer_id: int, name: str, local_path: Path) -> None:
    """Record a successfully-downloaded 3MF so a sibling flow can reuse it."""
    _threemf_path_cache[(printer_id, normalize_3mf_name(name))] = local_path


def get_cached_3mf(printer_id: int, name: str) -> Path | None:
    """Return a cached 3MF path for this printer/name if the file still exists."""
    key = (printer_id, normalize_3mf_name(name))
    cached = _threemf_path_cache.get(key)
    if cached and cached.exists() and cached.stat().st_size > 0:
        return cached
    # Evict dead entry — the file was cleaned up (temp dir clean, manual
    # deletion, restart) so the cache value is no longer usable.
    if cached:
        _threemf_path_cache.pop(key, None)
    return None


def clear_3mf_cache(printer_id: int | None = None, delete_files: bool = True) -> None:
    """Drop cache entries for one printer (or all with None).

    When ``delete_files`` is True (default) the on-disk 3MF is removed as well
    — called from on_print_complete so temp files don't accumulate across
    prints. Tests that want to inspect the cache contents disable this.

    Only paths inside ``archive_dir/temp`` are unlinked. The dispatch sites
    added in #1166 also cache the live archive copy and library file bytes
    so /cover can skip FTP — those are *user data*, never the cache's to
    delete. Pre-fix this branch silently removed archive 3mfs on every print
    completion (#1212 + private reports of "file disappeared overnight").
    """
    from backend.app.core.config import settings as _config_settings

    temp_root = _config_settings.archive_dir / "temp"

    def _is_temp_path(path: Path) -> bool:
        try:
            return path.is_relative_to(temp_root)
        except (OSError, ValueError):
            return False

    def _maybe_unlink(path: Path) -> None:
        if not delete_files or not path.exists():
            return
        if not _is_temp_path(path):
            return
        try:
            path.unlink()
        except OSError as exc:
            logger.debug("3MF cache cleanup skipped %s: %s", path, exc)

    if printer_id is None:
        for path in list(_threemf_path_cache.values()):
            _maybe_unlink(path)
        _threemf_path_cache.clear()
        return
    for key in [k for k in _threemf_path_cache if k[0] == printer_id]:
        _maybe_unlink(_threemf_path_cache[key])
        _threemf_path_cache.pop(key, None)


async def download_file_async(
    ip_address: str,
    access_code: str,
    remote_path: str,
    local_path: Path,
    timeout: float = 60.0,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
    expected_size: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
    serialize: bool = True,
) -> bool:
    """Download with separate socket-inactivity and bounded total budgets."""
    loop = asyncio.get_event_loop()
    is_a1 = printer_model in BambuFTPClient.A1_MODELS if printer_model else False

    class _CombinedCancelEvent:
        def __init__(self, attempt_event: threading.Event):
            self.attempt_event = attempt_event

        def is_set(self) -> bool:
            return self.attempt_event.is_set() or (cancel_event is not None and cancel_event.is_set())

    def _download(
        force_prot_c: bool,
        completion: dict,
        done: threading.Event,
        attempt_cancel: threading.Event,
    ) -> bool:
        mode_str = "prot_c" if force_prot_c else "prot_p"
        try:
            combined_cancel = _CombinedCancelEvent(attempt_cancel)
            if combined_cancel.is_set():
                raise DownloadCancelled(remote_path)
            client = BambuFTPClient(
                ip_address,
                access_code,
                timeout=socket_timeout,
                printer_model=printer_model,
                force_prot_c=force_prot_c,
            )
            if client.connect():
                try:
                    result = client.download_to_file(
                        remote_path,
                        local_path,
                        expected_size=expected_size,
                        cancel_event=combined_cancel,
                        size_callback=lambda size: completion.__setitem__("size", size),
                        progress_callback=progress_callback,
                    )
                    if result:
                        BambuFTPClient.cache_mode(ip_address, mode_str)
                        completion["success"] = True
                    return result
                finally:
                    client.disconnect()
            return False
        finally:
            done.set()

    async def _run(force_prot_c: bool) -> bool:
        completion = {"success": False}
        done = threading.Event()
        attempt_cancel = threading.Event()
        worker = loop.run_in_executor(None, _download, force_prot_c, completion, done, attempt_cancel)
        allowed = timeout
        extended = False
        try:
            try:
                return await asyncio.wait_for(asyncio.shield(worker), timeout=timeout)
            except TimeoutError:
                extension = _download_extension(completion.get("size"), timeout)
                if extension <= 0:
                    raise
                allowed += extension
                extended = True
                logger.info(
                    "FTP download of %s reports %s bytes; extending total budget to %.0fs",
                    remote_path,
                    completion.get("size"),
                    allowed,
                )
                return await asyncio.wait_for(asyncio.shield(worker), timeout=extension)
        except asyncio.CancelledError:
            attempt_cancel.set()
            try:
                await asyncio.shield(worker)
            except (DownloadCancelled, OSError, ftplib.Error):
                pass
            raise
        except TimeoutError:
            attempt_cancel.set()
            grace = max(min(socket_timeout or timeout, 30.0), 0.5)
            finished_in_grace = await loop.run_in_executor(None, done.wait, grace)
            if finished_in_grace:
                try:
                    await asyncio.shield(worker)
                except (DownloadCancelled, OSError, ftplib.Error):
                    pass
            else:
                _discard_worker_outcome(worker)
            if finished_in_grace and completion["success"] and local_path.exists() and local_path.stat().st_size > 0:
                logger.info("FTP download of %s completed while its %.0fs deadline unwound", remote_path, allowed)
                return True
            try:
                local_path.unlink(missing_ok=True)
            except OSError:
                pass
            if extended:
                raise DownloadDeadlineExceeded(remote_path)
            logger.warning("FTP download timed out after %.0fs for %s", allowed, remote_path)
            return False

    async with _serialized_download(ip_address, f"download of {remote_path}", enabled=serialize):
        cached_mode = BambuFTPClient._mode_cache.get(ip_address)
        if cached_mode:
            return await _run(cached_mode == "prot_c")
        if await _run(False):
            return True
        if is_a1:
            logger.info("FTP download failed with prot_p for A1 model, trying prot_c fallback...")
            return await _run(True)
        return False


async def download_file_try_paths_async(
    ip_address: str,
    access_code: str,
    remote_paths: list[str],
    local_path: Path,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
    timeout: float = 90.0,
    *,
    max_total_timeout: float | None = None,
) -> bool:
    """Try downloading a file from multiple paths using a single connection.

    Args:
        socket_timeout: FTP socket timeout for slow connections (e.g., A1 printers)
        printer_model: Printer model for A1-specific workarounds
        timeout: Overall async cap so a saturated executor cannot pin callers indefinitely.
        max_total_timeout: Optional higher cap for a recovery transfer with known size.
    """
    loop = asyncio.get_event_loop()
    reported_size: int | None = None

    def remember_size(size: int) -> None:
        nonlocal reported_size
        reported_size = size

    client_ref: dict[str, BambuFTPClient | None] = {"client": None}
    client_lock = threading.Lock()
    cancel = threading.Event()
    done = threading.Event()

    def _download() -> bool:
        nonlocal reported_size
        kwargs = {"size_callback": remember_size} if max_total_timeout is not None else {}
        try:
            client = BambuFTPClient(ip_address, access_code, timeout=socket_timeout, printer_model=printer_model)
            with client_lock:
                client_ref["client"] = client
            if not client.connect():
                return False
            try:
                for remote_path in remote_paths:
                    if cancel.is_set():
                        return False
                    reported_size = None
                    try:
                        if client.download_to_file(remote_path, local_path, cancel_event=cancel, **kwargs):
                            return True
                    except FileNotOnPrinterError:
                        continue
                    except DownloadCancelled:
                        return False
                return False
            finally:
                client.disconnect()
                with client_lock:
                    if client_ref["client"] is client:
                        client_ref["client"] = None
        finally:
            done.set()

    def _abort_download() -> None:
        with client_lock:
            client = client_ref["client"]
        if client is None:
            return
        ftp = getattr(client, "_ftp", None)
        if ftp is not None:
            try:
                ftp.close()
            except (OSError, ftplib.Error, EOFError):
                pass
        client.disconnect()

    async with _serialized_download(ip_address, f"{len(remote_paths)}-path download lookup"):
        future = loop.run_in_executor(None, _download)
        extension = 0.0
        try:
            try:
                return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
            except TimeoutError:
                if max_total_timeout is not None:
                    extension = _download_extension(reported_size, timeout, max_total_timeout)
                if extension <= 0:
                    raise
                logger.info("FTP recovery download reported %s bytes; allowing %.0fs more", reported_size, extension)
                return await asyncio.wait_for(asyncio.shield(future), timeout=extension)
        except asyncio.CancelledError:
            cancel.set()
            await loop.run_in_executor(None, _abort_download)
            await loop.run_in_executor(None, done.wait, _DOWNLOAD_UNWIND_SECONDS)
            _discard_worker_outcome(future)
            raise
        except TimeoutError:
            cancel.set()
            await loop.run_in_executor(None, _abort_download)
            finished_in_grace = await loop.run_in_executor(None, done.wait, _DOWNLOAD_UNWIND_SECONDS)
            if finished_in_grace:
                try:
                    if await asyncio.shield(future):
                        return True
                except (DownloadCancelled, OSError, ftplib.Error):
                    pass
            else:
                _discard_worker_outcome(future)
            logger.warning("FTP download_try_paths exceeded its %ss cap for %s", timeout + extension, ip_address)
            if extension > 0:
                raise DownloadDeadlineExceeded("Archive recovery download exceeded its size-derived deadline")
            return False


def _transfer_deadline(size_bytes: int) -> float:
    """Generous transfer deadline for a file of this size, floored at a
    slow-link speed so a large file over weak Wi-Fi gets a real budget
    instead of a fixed timeout that assumes a fast connection.

    Shared by uploads and downloads (#log-download-timeout) — there's no
    reason to assume a printer's link tolerates one direction better than
    the other.
    """
    return max(_UPLOAD_MIN_TIMEOUT, size_bytes / _UPLOAD_FLOOR_BYTES_PER_SEC)


def _upload_deadline(local_path: Path) -> float:
    try:
        size = local_path.stat().st_size
    except OSError:
        return _UPLOAD_MIN_TIMEOUT
    return _transfer_deadline(size)


def _download_deadline(size_bytes: int) -> float:
    return _transfer_deadline(size_bytes)


_upload_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]] = (
    weakref.WeakKeyDictionary()
)


def _upload_lock(loop: asyncio.AbstractEventLoop, ip_address: str) -> asyncio.Lock:
    per_loop = _upload_locks.setdefault(loop, {})
    lock = per_loop.get(ip_address)
    if lock is None:
        lock = asyncio.Lock()
        per_loop[ip_address] = lock
    return lock


def _swallow_future_result(future: asyncio.Future) -> None:
    if future.cancelled():
        return
    try:
        future.exception()
    except BaseException:
        pass


async def upload_file_async(
    ip_address: str,
    access_code: str,
    local_path: Path,
    remote_path: str,
    timeout: float | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
    respect_handshake_cooldown: bool = True,
    failure: FtpFailureReport | None = None,
) -> bool:
    """Async wrapper for uploading a file with timeout and progress callback.

    For A1/A1 Mini printers, automatically tries prot_p first, then falls back
    to prot_c if the upload fails. The working mode is cached for future uploads.

    Args:
        ip_address: Printer IP address
        access_code: Printer access code
        local_path: Local file path to upload
        remote_path: Remote path on printer
        timeout: Overall operation deadline. None derives it from file size.
        progress_callback: Optional callback for progress updates
        socket_timeout: FTP socket timeout for slow connections (e.g., A1 printers)
        printer_model: Printer model for A1-specific workarounds
    """
    loop = asyncio.get_event_loop()
    is_a1 = printer_model in BambuFTPClient.A1_MODELS if printer_model else False
    deadline = _upload_deadline(local_path) if timeout is None else timeout
    cancel = threading.Event()

    def _guarded_progress(uploaded: int, total: int) -> None:
        if cancel.is_set():
            raise UploadCancelled(f"upload of {remote_path} exceeded its {deadline:.0f}s deadline")
        if progress_callback:
            progress_callback(uploaded, total)

    def _upload(force_prot_c: bool = False) -> bool:
        mode_str = "prot_c" if force_prot_c else "prot_p"
        logger.info(
            f"FTP connecting to {ip_address} for upload (model={printer_model}, "
            f"mode={mode_str}, socket_timeout={socket_timeout}s, deadline={deadline:.0f}s)..."
        )
        client = BambuFTPClient(
            ip_address,
            access_code,
            timeout=socket_timeout,
            printer_model=printer_model,
            force_prot_c=force_prot_c,
            respect_handshake_cooldown=respect_handshake_cooldown,
        )
        try:
            if client.connect():
                logger.info("FTP connected to %s", ip_address)
                result = client.upload_file(local_path, remote_path, _guarded_progress)
                if result:
                    # Cache the working mode
                    BambuFTPClient.cache_mode(ip_address, mode_str)
                return result
            logger.warning("FTP connection failed to %s", ip_address)
            return False
        finally:
            client.disconnect()
            if failure is not None and client.last_failure is not None:
                failure.failure = client.last_failure

    async def _attempt(force_prot_c: bool) -> bool:
        future = loop.run_in_executor(None, lambda: _upload(force_prot_c))
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=deadline)
        except TimeoutError:
            cancel.set()
            logger.warning(
                "FTP upload of %s exceeded its %.0fs deadline; cancelling the transfer",
                remote_path,
                deadline,
            )
            try:
                await asyncio.wait_for(asyncio.shield(future), timeout=_UPLOAD_CANCEL_GRACE)
            except UploadCancelled:
                logger.info("FTP upload of %s cancelled; partial file removed from the printer", remote_path)
            except TimeoutError:
                logger.error(
                    "FTP upload thread for %s did not stop within %.0fs of the cancel signal",
                    remote_path,
                    _UPLOAD_CANCEL_GRACE,
                )
                future.add_done_callback(_swallow_future_result)
            except Exception as e:
                logger.warning("FTP upload of %s errored while cancelling: %s", remote_path, e)
            raise UploadCancelled(
                f"Upload of {remote_path} to {ip_address} exceeded its {deadline:.0f}s deadline "
                f"(link sustained less than {_UPLOAD_FLOOR_BYTES_PER_SEC // 1024} KB/s)"
            ) from None

    async with _upload_lock(loop, ip_address):
        # Check if we have a cached mode for this printer
        cached_mode = BambuFTPClient._mode_cache.get(ip_address)

        if cached_mode:
            # Use cached mode
            return await _attempt(cached_mode == "prot_c")

        # No cached mode - try prot_p first
        if await _attempt(False):
            return True

        # Upload failed - for A1 models, try prot_c fallback
        if is_a1:
            logger.info("FTP upload failed with prot_p for A1 model, trying prot_c fallback...")
            return await _attempt(True)

        return False


async def list_files_result_async(
    ip_address: str,
    access_code: str,
    path: str = "/",
    timeout: float = 30.0,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
) -> FileListResult:
    return await list_files_result(
        BambuFTPClient, ip_address, access_code, path, timeout, socket_timeout, printer_model
    )


async def list_files_async(
    ip_address: str,
    access_code: str,
    path: str = "/",
    timeout: float = 30.0,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
    raise_on_error: bool = False,
) -> list[dict]:
    """List without stacking slow workers; strict callers retain the actual error."""
    result = await list_files_result_async(ip_address, access_code, path, timeout, socket_timeout, printer_model)
    if isinstance(result.error, FtpsCooldownActive):
        raise result.error
    if raise_on_error and not result.available:
        if result.error is not None:
            raise result.error
        raise FileListingError(f"FTP connection failed for {ip_address}")
    return result.files


async def list_files_strict_async(
    ip_address: str,
    access_code: str,
    path: str = "/",
    timeout: float = 30.0,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
) -> list[dict]:
    """List files while preserving connection, directory, and timeout failures."""
    return await list_files_async(
        ip_address,
        access_code,
        path,
        timeout,
        socket_timeout,
        printer_model,
        raise_on_error=True,
    )


async def delete_file_async(
    ip_address: str,
    access_code: str,
    remote_path: str,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
    timeout: float = 60.0,
    respect_handshake_cooldown: bool = True,
) -> DeleteResult:
    """Async wrapper for deleting a file.

    Returns :class:`DeleteResult` so callers can distinguish ``NOT_FOUND``
    (550 — file isn't on the printer, no retry value) from ``FAILED``
    (network / auth / transient — worth retrying or surfacing).

    Args:
        socket_timeout: FTP socket timeout for slow connections (e.g., A1 printers)
        printer_model: Printer model for A1-specific workarounds
        timeout: Overall async cap so a saturated executor cannot pin callers indefinitely.
    """
    loop = asyncio.get_event_loop()

    def _delete() -> DeleteResult:
        client = BambuFTPClient(
            ip_address,
            access_code,
            timeout=socket_timeout,
            printer_model=printer_model,
            respect_handshake_cooldown=respect_handshake_cooldown,
        )
        if client.connect():
            try:
                return client.delete_file(remote_path)
            finally:
                client.disconnect()
        return DeleteResult.FAILED

    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _delete), timeout=timeout)
    except TimeoutError:
        logger.warning("FTP delete_file exceeded its %ss cap for %s", timeout, ip_address)
        return DeleteResult.FAILED


async def download_file_bytes_async(
    ip_address: str,
    access_code: str,
    remote_path: str,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
    timeout: float = 300.0,
    progress_callback: Callable[[int, int], None] | None = None,
    total_bytes: int = 0,
    raise_on_not_found: bool = False,
    expected_size: int | None = None,
    max_total_timeout: float = _DOWNLOAD_MAX_TIMEOUT,
) -> bytes | None:
    """Download complete bytes with the existing printer gate and bounded unwind."""
    size = (
        expected_size
        if type(expected_size) is int and expected_size >= 0
        else (total_bytes if type(total_bytes) is int and total_bytes > 0 else None)
    )
    default_socket_timeout = getattr(BambuFTPClient, "DEFAULT_TIMEOUT", 30.0)
    if type(default_socket_timeout) not in (int, float):
        default_socket_timeout = 30.0
    request = ByteDownloadRequest(
        ip_address,
        access_code,
        remote_path,
        timeout,
        socket_timeout,
        printer_model,
        size,
        progress_callback,
        raise_on_not_found,
        max_total_timeout,
        max(_DOWNLOAD_UNWIND_SECONDS, 2 * (socket_timeout or default_socket_timeout)),
        _DOWNLOAD_FLOOR_BYTES_PER_SEC,
    )
    async with _serialized_download(ip_address, f"byte download of {remote_path}"):
        return await download_bytes(
            BambuFTPClient,
            request,
            extension=_download_extension,
            cancelled_error=DownloadCancelled,
            deadline_error=DownloadDeadlineExceeded,
            discard_worker=_discard_worker_outcome,
        )


async def get_storage_info_async(
    ip_address: str,
    access_code: str,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
    timeout: float = 60.0,
) -> dict | None:
    """Async wrapper for getting storage info.

    Args:
        socket_timeout: FTP socket timeout for slow connections (e.g., A1 printers)
        printer_model: Printer model for A1-specific workarounds
        timeout: Overall async cap so a saturated executor cannot pin callers indefinitely.
    """
    loop = asyncio.get_event_loop()

    def _get_storage():
        client = BambuFTPClient(ip_address, access_code, timeout=socket_timeout, printer_model=printer_model)
        if client.connect():
            try:
                return client.get_storage_info()
            finally:
                client.disconnect()
        return None

    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _get_storage), timeout=timeout)
    except TimeoutError:
        logger.warning("FTP get_storage_info exceeded its %ss cap for %s", timeout, ip_address)
        return None


async def get_file_size_async(
    ip_address: str,
    access_code: str,
    remote_path: str,
    socket_timeout: float | None = None,
    printer_model: str | None = None,
    timeout: float = 30.0,
) -> int | None:
    """Async wrapper for BambuFTPClient.get_file_size (FTP SIZE command).

    Used to size a download's progress/deadline before the transfer starts
    (#log-download-timeout) — a fast, cheap probe compared to the transfer itself.
    """
    loop = asyncio.get_event_loop()

    def _get_size():
        client = BambuFTPClient(ip_address, access_code, timeout=socket_timeout, printer_model=printer_model)
        if client.connect():
            try:
                return client.get_file_size(remote_path)
            finally:
                client.disconnect()
        return None

    try:
        return await asyncio.wait_for(loop.run_in_executor(None, _get_size), timeout=timeout)
    except TimeoutError:
        logger.warning("FTP get_file_size exceeded its %ss cap for %s", timeout, ip_address)
        return None


async def get_ftp_retry_settings() -> tuple[bool, int, float, float]:
    """Get FTP retry settings from database.

    Returns:
        Tuple of (retry_enabled, retry_count, retry_delay, timeout)
    """
    from backend.app.api.routes.settings import get_setting
    from backend.app.core.database import async_session

    async with async_session() as db:
        enabled = (await get_setting(db, "ftp_retry_enabled") or "true") == "true"
        count = int(await get_setting(db, "ftp_retry_count") or "3")
        delay = float(await get_setting(db, "ftp_retry_delay") or "2")
        timeout = float(await get_setting(db, "ftp_timeout") or "30")
    return enabled, count, delay, timeout


async def with_ftp_retry(
    operation: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 3,
    retry_delay: float = 2.0,
    operation_name: str = "FTP operation",
    non_retry_exceptions: tuple[type[BaseException], ...] = (),
    **kwargs,
) -> T | None:
    """Execute FTP operation with retry logic.

    Args:
        operation: Async function to execute
        *args: Positional arguments for the operation
        max_retries: Number of retry attempts (default: 3)
        retry_delay: Seconds to wait between retries (default: 2.0)
        operation_name: Name for logging purposes
        non_retry_exceptions: Exception types that should immediately abort retries
        **kwargs: Keyword arguments for the operation

    Returns:
        Result of the operation, or None if all attempts fail

    Cancelled or size-budget-exhausted transfers are never retried: a second
    transfer would race the first or spend the same full deadline again.
    FtpsCooldownActive is not retried for background work either (#88).
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            result = await operation(*args, **kwargs)
            # Check for "falsy" success indicators
            if result not in (False, None, []):
                if attempt > 0:
                    logger.info("%s succeeded on attempt %s/%s", operation_name, attempt + 1, max_retries + 1)
                return result
            # Operation returned failure indicator
            if attempt > 0:
                logger.info("%s attempt %s/%s returned failure", operation_name, attempt + 1, max_retries + 1)
        except (UploadCancelled, DownloadCancelled):
            raise
        except DownloadDeadlineExceeded:
            raise
        except FtpsCooldownActive:
            # The printer's TLS handshake is broken and already cooling
            # down (#88) — retrying here would just repeat the doomed
            # handshake attempt-for-attempt across every candidate path.
            raise
        except Exception as e:
            if non_retry_exceptions and isinstance(e, non_retry_exceptions):
                raise
            last_error = e
            logger.warning("%s attempt %s/%s failed: %s", operation_name, attempt + 1, max_retries + 1, e)

        # Don't wait after the last attempt
        if attempt < max_retries:
            logger.info("%s will retry in %ss...", operation_name, retry_delay)
            await asyncio.sleep(retry_delay)

    logger.error("%s failed after %s attempts", operation_name, max_retries + 1)
    if last_error:
        logger.debug("Last error: %s", last_error)
    return None
