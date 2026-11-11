"""Raise the process's soft descriptor limit and report its usage."""

import logging
import os
from collections import Counter

logger = logging.getLogger(__name__)
startup_status: dict | None = None


def _limit_value(value: int, infinity: int) -> int | str:
    return "unlimited" if value == infinity else value


def raise_open_file_limit() -> None:
    global startup_status
    try:
        import resource
    except ImportError:
        return

    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (OSError, ValueError) as exc:
        logger.warning("Could not read the open-file limit (%s)", type(exc).__name__)
        return

    infinity = resource.RLIM_INFINITY
    status = {
        "soft_at_start": _limit_value(soft, infinity),
        "hard": _limit_value(hard, infinity),
        "soft": _limit_value(soft, infinity),
        "raised": False,
    }
    startup_status = status
    if soft == infinity:
        return
    # Some platforms report an unlimited hard limit and reject raising the soft
    # limit past a separate system maximum.
    targets = (65536, 10240) if hard == infinity else (hard,)
    error = None
    for target in targets:
        if target <= soft:
            continue
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
        except (OSError, ValueError) as exc:
            error = type(exc).__name__
            continue
        status.update(soft=target, raised=True)
        logger.info("Raised the open-file soft limit from %d to %d", soft, target)
        return
    if error:
        status["error"] = error
        logger.warning("Could not raise the open-file soft limit from %d (%s)", soft, error)


def _fd_kind(target: str) -> str:
    for prefix, kind in (("socket:", "socket"), ("pipe:", "pipe"), ("anon_inode:", "anon_inode"), ("/dev/", "device")):
        if target.startswith(prefix):
            return kind
    path = target.removesuffix(" (deleted)")
    for extension in (".db", ".sqlite", ".sqlite3"):
        if path.endswith(extension):
            return "database"
        if path.endswith(f"{extension}-wal"):
            return "database_wal"
        if path.endswith(f"{extension}-shm"):
            return "database_shm"
    return "file"


def collect_fd_usage() -> dict:
    """Report descriptor counts and limits without recording any targets."""
    result: dict = {}
    if startup_status is not None:
        result["fd_limit_at_startup"] = dict(startup_status)
    try:
        import resource

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        result["fd_limit"] = {
            "soft": _limit_value(soft, resource.RLIM_INFINITY),
            "hard": _limit_value(hard, resource.RLIM_INFINITY),
        }
    except (ImportError, OSError, ValueError):
        pass

    try:
        entries = os.listdir("/proc/self/fd")
    except OSError:
        # The aggregate is available on some platforms without Linux procfs.
        try:
            import psutil
        except ImportError:
            return result
        try:
            result["num_fds"] = psutil.Process().num_fds()
        except (AttributeError, OSError, psutil.Error):
            pass
        return result

    counts: Counter[str] = Counter()
    for entry in entries:
        try:
            counts[_fd_kind(os.readlink(f"/proc/self/fd/{entry}"))] += 1
        except OSError:
            # Includes the directory descriptor used to list procfs.
            continue
    result["num_fds"] = counts.total()
    result["fds_by_type"] = dict(counts)
    return result
