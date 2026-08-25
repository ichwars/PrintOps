"""Printer file-manager routes.

Split out of ``printers.py`` so printer CRUD/control and slow FTP-backed file
operations can evolve independently.
"""

import asyncio
import io
import json
import logging
import re
import time
import zipfile

import defusedxml.ElementTree as ET
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select

from backend.app.core import database
from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.permissions import Permission
from backend.app.core.websocket import ws_manager
from backend.app.models.printer import Printer
from backend.app.models.user import User
from backend.app.services.bambu_ftp import (
    DeleteResult,
    FileNotOnPrinterError,
    FtpsCooldownActive,
    _download_deadline,
    delete_file_async,
    download_file_bytes_async,
    get_file_size_async,
    get_storage_info_async,
    list_files_async,
)
from backend.app.services.print_scheduler import (
    _DISPATCH_PROGRESS_BYTE_STEP,
    _DISPATCH_PROGRESS_MIN_INTERVAL_SECS,
)
from backend.app.utils.http import build_content_disposition

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/printers", tags=["printers"])


class _DownloadProgressBridge:
    """Thread-safe bridge from download_file_bytes_async's progress_callback
    to the WS broadcaster — mirrors print_scheduler._UploadProgressBridge.

    download_file_bytes_async runs the FTP transfer in an executor thread
    and invokes progress_callback from that thread, so this callback body
    cannot ``await`` directly; it hops back to the request's event loop via
    ``run_coroutine_threadsafe``. Failures inside the emit are swallowed —
    progress is a UX nicety, the download itself must not fail on a WS hiccup.
    """

    def __init__(self, user_id: int | None, download_id: str):
        self._user_id = user_id
        self._download_id = download_id
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._last_emit_bytes = 0
        self._last_emit_monotonic = 0.0
        self._has_emitted = False

    def __call__(self, bytes_transferred: int, total_bytes: int) -> None:
        if self._loop is None or total_bytes <= 0:
            return
        now = time.monotonic()
        should_emit = (
            not self._has_emitted
            or bytes_transferred >= total_bytes
            or now - self._last_emit_monotonic >= _DISPATCH_PROGRESS_MIN_INTERVAL_SECS
            or bytes_transferred - self._last_emit_bytes >= _DISPATCH_PROGRESS_BYTE_STEP
        )
        if not should_emit:
            return
        self._has_emitted = True
        self._last_emit_bytes = bytes_transferred
        self._last_emit_monotonic = now
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.send_file_download_progress(
                    user_id=self._user_id,
                    download_id=self._download_id,
                    bytes_transferred=bytes_transferred,
                    total_bytes=total_bytes,
                ),
                self._loop,
            )
        except Exception:
            pass  # progress is best-effort, never block the download


async def _load_printer_or_404(printer_id: int) -> Printer:
    """Load a printer row and release the DB connection before FTP I/O."""
    async with database.async_session() as db:
        result = await db.execute(select(Printer).where(Printer.id == printer_id))
        printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")
    return printer


@router.get("/{printer_id}/files")
async def list_printer_files(
    printer_id: int,
    path: str = "/",
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_FILES),
):
    """List files on the printer at the specified path."""
    printer = await _load_printer_or_404(printer_id)
    files = await list_files_async(printer.ip_address, printer.access_code, path, printer_model=printer.model)
    for item in files:
        item["path"] = f"{path.rstrip('/')}/{item['name']}" if path != "/" else f"/{item['name']}"
    return {"path": path, "files": files}


@router.get("/{printer_id}/files/download")
async def download_printer_file(
    printer_id: int,
    path: str,
    download_id: str | None = Query(None),
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_FILES),
):
    """Download a file from the printer.

    Large files (printer logs can run several hundred MB) over a slow Wi-Fi
    link routinely exceed a fixed short timeout — the deadline scales with
    the file's actual size instead. When ``download_id`` is supplied (the
    file-manager UI), live byte-level progress is relayed over the WS
    connection so the UI can show percent/speed/ETA instead of nothing.
    """
    printer = await _load_printer_or_404(printer_id)

    try:
        total_bytes = await get_file_size_async(
            printer.ip_address, printer.access_code, path, printer_model=printer.model
        )
        deadline = _download_deadline(total_bytes or 0)
        progress_callback = (
            _DownloadProgressBridge(current_user.id if current_user else None, download_id) if download_id else None
        )
        data = await download_file_bytes_async(
            printer.ip_address,
            printer.access_code,
            path,
            printer_model=printer.model,
            timeout=deadline,
            socket_timeout=deadline,
            progress_callback=progress_callback,
            total_bytes=total_bytes or 0,
            raise_on_not_found=True,
        )
    except FtpsCooldownActive as e:
        raise HTTPException(503, str(e)) from e
    except FileNotOnPrinterError as e:
        raise HTTPException(404, f"File not found: {path}") from e

    if data is None:
        size_hint = f" ({total_bytes} bytes)" if total_bytes else ""
        raise HTTPException(
            504,
            f"Download of '{path}'{size_hint} did not complete within {deadline:.0f}s. "
            f"Check the printer's Wi-Fi signal or try again.",
        )

    filename = path.split("/")[-1]
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    content_types = {
        "3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
        "gcode": "text/plain",
        "mp4": "video/mp4",
        "avi": "video/x-msvideo",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "json": "application/json",
        "txt": "text/plain",
    }
    return Response(
        content=data,
        media_type=content_types.get(ext, "application/octet-stream"),
        headers={"Content-Disposition": build_content_disposition(filename)},
    )


@router.get("/{printer_id}/files/gcode")
async def get_printer_file_gcode(
    printer_id: int,
    path: str,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_FILES),
):
    """Get gcode for a file stored on a printer for preview."""
    printer = await _load_printer_or_404(printer_id)
    data = await download_file_bytes_async(printer.ip_address, printer.access_code, path, printer_model=printer.model)
    if data is None:
        raise HTTPException(404, f"File not found: {path}")

    lower = path.split("/")[-1].lower()
    if lower.endswith(".gcode"):
        return Response(content=data, media_type="text/plain")
    if lower.endswith(".3mf"):
        try:
            with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
                gcode_files = [name for name in zf.namelist() if name.endswith(".gcode")]
                if not gcode_files:
                    raise HTTPException(status_code=404, detail="No gcode found in 3MF file")
                return Response(content=zf.read(gcode_files[0]), media_type="text/plain")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid 3MF file") from None
    raise HTTPException(status_code=400, detail="Unsupported file type")


@router.get("/{printer_id}/files/plates")
async def get_printer_file_plates(
    printer_id: int,
    path: str = Query(..., description="Full path to the 3MF file on the printer"),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_FILES),
):
    """Get available plates from a multi-plate 3MF file stored on a printer."""
    printer = await _load_printer_or_404(printer_id)
    filename = path.split("/")[-1]
    if not filename.lower().endswith(".3mf"):
        return {"printer_id": printer_id, "path": path, "filename": filename, "plates": [], "is_multi_plate": False}

    data = await download_file_bytes_async(printer.ip_address, printer.access_code, path, printer_model=printer.model)
    if data is None:
        raise HTTPException(404, f"File not found: {path}")

    plates = []
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            namelist = zf.namelist()
            plate_indices = _discover_plate_indices(namelist)
            if not plate_indices:
                return {
                    "printer_id": printer_id,
                    "path": path,
                    "filename": filename,
                    "plates": [],
                    "is_multi_plate": False,
                }

            plate_names = _parse_plate_names(zf, namelist)
            plate_metadata = _parse_slice_plate_metadata(zf, namelist, plate_names)
            plate_json_objects = _parse_plate_json_objects(zf, namelist)

            for idx in plate_indices:
                meta = plate_metadata.get(idx, {})
                objects = meta.get("objects", []) or plate_json_objects.get(idx, [])
                plate_name = meta.get("name") or plate_names.get(idx) or (objects[0] if objects else None)
                plates.append(
                    {
                        "index": idx,
                        "name": plate_name,
                        "objects": objects,
                        "object_count": len(objects),
                        "has_thumbnail": f"Metadata/plate_{idx}.png" in namelist,
                        "thumbnail_url": f"/api/v1/printers/{printer_id}/files/plate-thumbnail/{idx}?path={path}",
                        "print_time_seconds": meta.get("prediction"),
                        "filament_used_grams": meta.get("weight"),
                        "filaments": meta.get("filaments", []),
                    }
                )
    except Exception as exc:
        logger.warning("Failed to parse plates from printer file %s: %s", path, exc)

    return {
        "printer_id": printer_id,
        "path": path,
        "filename": filename,
        "plates": plates,
        "is_multi_plate": len(plates) > 1,
    }


def _discover_plate_indices(namelist: list[str]) -> list[int]:
    gcode_files = [name for name in namelist if name.startswith("Metadata/plate_") and name.endswith(".gcode")]
    if gcode_files:
        indices = []
        for name in gcode_files:
            try:
                indices.append(int(name[15:-6]))
            except ValueError:
                continue
        return sorted(indices)

    plate_re = re.compile(r"^Metadata/plate_(\d+)\.(json|png)$")
    indices = set()
    for name in namelist:
        if "_small" in name or "no_light" in name:
            continue
        match = plate_re.match(name)
        if match:
            indices.add(int(match.group(1)))
    return sorted(indices)


def _parse_plate_names(zf: zipfile.ZipFile, namelist: list[str]) -> dict[int, str]:
    if "Metadata/model_settings.config" not in namelist:
        return {}
    try:
        root = ET.fromstring(zf.read("Metadata/model_settings.config").decode())
    except Exception:
        return {}

    names = {}
    for plate_elem in root.findall(".//plate"):
        plater_id = None
        plater_name = None
        for meta in plate_elem.findall("metadata"):
            key = meta.get("key")
            value = meta.get("value")
            if key == "plater_id" and value:
                try:
                    plater_id = int(value)
                except ValueError:
                    pass
            elif key == "plater_name" and value:
                plater_name = value.strip()
        if plater_id is not None and plater_name:
            names[plater_id] = plater_name
    return names


def _parse_slice_plate_metadata(
    zf: zipfile.ZipFile,
    namelist: list[str],
    plate_names: dict[int, str],
) -> dict[int, dict]:
    if "Metadata/slice_info.config" not in namelist:
        return {}

    content = zf.read("Metadata/slice_info.config").decode()
    root = ET.fromstring(content)
    plate_metadata = {}
    for plate_elem in root.findall(".//plate"):
        plate_info = {"filaments": [], "prediction": None, "weight": None, "name": None, "objects": []}
        plate_index = None
        for meta in plate_elem.findall("metadata"):
            key = meta.get("key")
            value = meta.get("value")
            if key == "index" and value:
                try:
                    plate_index = int(value)
                except ValueError:
                    pass
            elif key == "prediction" and value:
                try:
                    plate_info["prediction"] = int(value)
                except ValueError:
                    pass
            elif key == "weight" and value:
                try:
                    plate_info["weight"] = float(value)
                except ValueError:
                    pass

        for filament_elem in plate_elem.findall("filament"):
            filament_id = filament_elem.get("id")
            try:
                used_grams = float(filament_elem.get("used_g", "0"))
            except (ValueError, TypeError):
                used_grams = 0
            if used_grams > 0 and filament_id:
                plate_info["filaments"].append(
                    {
                        "slot_id": int(filament_id),
                        "type": filament_elem.get("type", ""),
                        "color": filament_elem.get("color", ""),
                        "used_grams": round(used_grams, 1),
                        "used_meters": float(filament_elem.get("used_m", "0") or 0),
                    }
                )
        plate_info["filaments"].sort(key=lambda item: item["slot_id"])

        for obj_elem in plate_elem.findall("object"):
            obj_name = obj_elem.get("name")
            if obj_name and obj_name not in plate_info["objects"]:
                plate_info["objects"].append(obj_name)

        if plate_index is not None:
            plate_info["name"] = plate_names.get(plate_index) or (
                plate_info["objects"][0] if plate_info["objects"] else None
            )
            plate_metadata[plate_index] = plate_info
    return plate_metadata


def _parse_plate_json_objects(zf: zipfile.ZipFile, namelist: list[str]) -> dict[int, list[str]]:
    plate_json_objects: dict[int, list[str]] = {}
    for name in namelist:
        match = re.match(r"^Metadata/plate_(\d+)\.json$", name)
        if not match:
            continue
        try:
            plate_index = int(match.group(1))
            payload = json.loads(zf.read(name).decode())
        except Exception:
            continue
        names = []
        for obj in payload.get("bbox_objects", []):
            obj_name = obj.get("name") if isinstance(obj, dict) else None
            if obj_name and obj_name not in names:
                names.append(obj_name)
        if names:
            plate_json_objects[plate_index] = names
    return plate_json_objects


@router.get("/{printer_id}/files/plate-thumbnail/{plate_index}")
async def get_printer_file_plate_thumbnail(
    printer_id: int,
    plate_index: int,
    path: str = Query(..., description="Full path to the 3MF file on the printer"),
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_FILES),
):
    """Get a plate thumbnail image from a printer-stored 3MF file."""
    printer = await _load_printer_or_404(printer_id)
    data = await download_file_bytes_async(printer.ip_address, printer.access_code, path, printer_model=printer.model)
    if data is None:
        raise HTTPException(404, f"File not found: {path}")

    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            thumb_path = f"Metadata/plate_{plate_index}.png"
            if thumb_path in zf.namelist():
                return Response(content=zf.read(thumb_path), media_type="image/png")
    except Exception:
        pass
    raise HTTPException(status_code=404, detail=f"Thumbnail for plate {plate_index} not found")


@router.post("/{printer_id}/files/download-zip")
async def download_printer_files_as_zip(
    printer_id: int,
    request: dict,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_FILES),
):
    """Download multiple files from the printer as a ZIP archive."""
    paths = request.get("paths", [])
    if not paths:
        raise HTTPException(400, "No files specified")

    printer = await _load_printer_or_404(printer_id)
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            try:
                data = await download_file_bytes_async(
                    printer.ip_address,
                    printer.access_code,
                    path,
                    printer_model=printer.model,
                )
                if data:
                    zf.writestr(path.split("/")[-1], data)
            except Exception as exc:
                logging.warning("Failed to add %s to ZIP: %s", path, exc)

    zip_buffer.seek(0)
    zip_data = zip_buffer.read()
    if not zip_data:
        raise HTTPException(404, "No files could be downloaded")
    return Response(
        content=zip_data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="printer-files.zip"'},
    )


@router.delete("/{printer_id}/files")
async def delete_printer_file(
    printer_id: int,
    path: str,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_FILES),
):
    """Delete a file from the printer."""
    printer = await _load_printer_or_404(printer_id)
    result = await delete_file_async(printer.ip_address, printer.access_code, path, printer_model=printer.model)
    if result == DeleteResult.NOT_FOUND:
        raise HTTPException(404, f"File not found on printer: {path}")
    if result == DeleteResult.FAILED:
        raise HTTPException(500, f"Failed to delete file: {path}")
    return {"status": "deleted", "path": path}


@router.get("/{printer_id}/storage")
async def get_printer_storage(
    printer_id: int,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
):
    """Get storage information from the printer."""
    printer = await _load_printer_or_404(printer_id)
    storage_info = await get_storage_info_async(printer.ip_address, printer.access_code, printer_model=printer.model)
    return storage_info or {"used_bytes": None, "free_bytes": None}
