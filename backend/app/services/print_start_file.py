"""Find a print's 3MF without downloading a failed path twice."""

from __future__ import annotations

import logging
import posixpath
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import uuid4

from backend.app.services.bambu_ftp import DownloadDeadlineExceeded, FileNotOnPrinterError
from backend.app.services.threemf_identity import normalized_model_name
from backend.app.utils.safe_path import safe_join_under

logger = logging.getLogger(__name__)
SEARCH_DIRS = ("/cache", "/model", "/data", "/data/Metadata", "/")


@dataclass
class StartFile:
    path: Path | None = None
    filename: str | None = None
    listed_transfer_failed: bool = False


def safe_filename(value):
    return (
        isinstance(value, str)
        and bool(value)
        and "\x00" not in value
        and "\\" not in value
        and PurePosixPath(value).name == value
        and value.lower().endswith(".3mf")
    )


def matching_paths(paths, search_term):
    """An exact model name on the card excludes substring lookalikes."""
    stem = normalized_model_name(search_term)
    if not stem:
        return []
    exact, loose = [], []
    for path in dict.fromkeys(paths):
        name = PurePosixPath(path).name
        candidate = normalized_model_name(name)
        if candidate == stem:
            exact.append(path)
        elif candidate and stem in candidate:
            loose.append(path)
    return exact or (loose if len(loose) == 1 else [])


async def find_start_file(
    printer, names, search_term, *, archive_dir, retry_settings, get_cached, cache_file, download, retry, list_files
):
    result = StartFile()
    names = list(dict.fromkeys(name for name in names if safe_filename(name)))
    for name in names:
        cached = get_cached(printer.id, name)
        if cached:
            return StartFile(cached, name)

    enabled, count, delay, timeout = retry_settings
    # Only generated components enter the temporary path. The remote filename
    # remains metadata, never a local path supplied by the printer.
    temp = safe_join_under(archive_dir / "temp", f"start_{printer.id}_{uuid4().hex}.3mf", http=False)
    temp.parent.mkdir(parents=True, exist_ok=True)
    failed = set()

    async def transfer(remote):
        kwargs = {"timeout": timeout, "socket_timeout": timeout, "printer_model": printer.model}
        try:
            if enabled:
                ok = await retry(
                    download,
                    printer.ip_address,
                    printer.access_code,
                    remote,
                    temp,
                    **kwargs,
                    max_retries=count,
                    retry_delay=delay,
                    operation_name=f"Download 3MF from {remote}",
                    non_retry_exceptions=(FileNotOnPrinterError,),
                )
            else:
                ok = await download(printer.ip_address, printer.access_code, remote, temp, **kwargs)
            if ok:
                return True
            failed.add(remote)
        except FileNotOnPrinterError:
            pass
        except DownloadDeadlineExceeded:
            # An FTP worker may still own the connection during bounded unwind.
            # Do not start another candidate behind that unfinished transfer.
            raise
        except Exception as error:
            failed.add(remote)
            logger.debug("Print-start transfer failed for %s: %s", remote, error)
        return False

    def found(remote):
        name = PurePosixPath(remote).name
        result.path, result.filename = temp, name
        cache_file(printer.id, name, temp)
        return result

    try:
        for name in names:
            for directory in ("/", *SEARCH_DIRS[:-1]):
                remote = posixpath.join(directory, name)
                if await transfer(remote):
                    return found(remote)

        listed = []
        for directory in SEARCH_DIRS:
            try:
                rows = await list_files(printer.ip_address, printer.access_code, directory, printer_model=printer.model)
                listed.extend(
                    posixpath.join(directory, row["name"])
                    for row in rows
                    if not row.get("is_directory") and safe_filename(row.get("name"))
                )
            except Exception as error:
                logger.debug("Could not list print-start directory %s: %s", directory, error)
        for remote in matching_paths(listed, search_term):
            if remote in failed:
                result.listed_transfer_failed = True
                continue
            if await transfer(remote):
                return found(remote)
            result.listed_transfer_failed = True
        return result
    except DownloadDeadlineExceeded:
        result.listed_transfer_failed = True
        return result
    finally:
        if result.path is None:
            temp.unlink(missing_ok=True)
