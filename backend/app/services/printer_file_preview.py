"""Keep printer preview failures distinct without changing file authorization."""

from fastapi import HTTPException

from backend.app.services.bambu_ftp import DownloadDeadlineExceeded, FileNotOnPrinterError, FtpsCooldownActive
from backend.app.services.printer_file_cache import printer_file_cache

MAX_PREVIEW_TRANSFER_SECONDS = 1800.0


async def _fetch_preview_bytes(printer, path, downloader):
    try:
        data = await downloader(
            printer.ip_address,
            printer.access_code,
            path,
            printer_model=printer.model,
            raise_on_not_found=True,
            max_total_timeout=MAX_PREVIEW_TRANSFER_SECONDS,
        )
    except FileNotOnPrinterError as error:
        raise HTTPException(404, f"File not found: {path}") from error
    except DownloadDeadlineExceeded as error:
        raise HTTPException(504, "Printer file download exceeded its transfer budget") from error
    except FtpsCooldownActive as error:
        raise HTTPException(503, str(error)) from error
    if data is None:
        raise HTTPException(502, "Printer file could not be downloaded. Check the printer connection and try again.")
    return data


async def download_preview_bytes(printer, path, downloader):
    return await printer_file_cache.get(printer.id, path, lambda: _fetch_preview_bytes(printer, path, downloader))
