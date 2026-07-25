import asyncio
import logging
import re
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    RequireCameraStreamTokenIfAuthEnabled,
    RequirePermissionIfAuthEnabled,
    is_auth_enabled,
)
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.printer import Printer
from backend.app.models.user import User
from backend.app.schemas.printer import (
    PrinterCreate,
    PrinterResponse,
    PrinterResponseWithSecret,
    PrinterUpdate,
)
from backend.app.services.bambu_ftp import (
    cache_3mf_download,
    download_file_try_paths_async,
    get_cached_3mf,
)
from backend.app.services.printer_filaments import collect_available_filaments
from backend.app.services.printer_manager import (
    printer_manager,
    resolve_plate_id,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/printers", tags=["printers"])

# Seconds the /hms/execute-action route waits for a printer status push
# confirming the command landed before reporting 502 to the UI. Module-level
# so tests can monkeypatch a near-zero value instead of mocking asyncio.sleep.
HMS_ACTION_ACK_WAIT_SECONDS = 2.5


async def _caller_can_view_printer_secrets(user: User | None, db: AsyncSession) -> bool:
    """Whether the caller is trusted enough to see ``access_code`` on a printer
    response. Fail-CLOSED: anything that isn't an authenticated user holding
    PRINTERS_UPDATE returns False.

    - Auth disabled  → True (single trust domain — same as today's local UI).
    - JWT user with PRINTERS_UPDATE → True (Admin or Operator; the same roles
      that already manage printers and the Virtual Printer card UX that
      surfaces a target's code for slicer configuration).
    - JWT Viewer → False (the bug fix: Viewers must not be able to read
      access_code via PRINTERS_READ and then go around PrintOps to MQTT).
    - API-key principal (``user is None`` because the dep returns None for
      API keys) → False. PRINTERS_UPDATE is admin-only and absent from
      ``_APIKEY_SCOPE_BY_PERMISSION``, so no API key can hold it.
    """
    if not await is_auth_enabled(db):
        return True
    if user is None:
        return False
    return user.has_permission(Permission.PRINTERS_UPDATE.value)


def _serialize_printer(printer: Printer, *, include_secret: bool):
    """Build the response shape that matches the caller's authority."""
    if include_secret:
        return PrinterResponseWithSecret.model_validate(printer)
    return PrinterResponse.model_validate(printer)


@router.get("/")
async def list_printers(
    user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """List all configured printers.

    ``access_code`` is included in each item only when the caller is trusted
    to see it (Admin / Operator JWT, or auth-disabled mode). Viewers and
    API keys never receive it.
    """
    result = await db.execute(select(Printer).order_by(Printer.name))
    printers = list(result.scalars().all())
    include_secret = await _caller_can_view_printer_secrets(user, db)
    return [_serialize_printer(p, include_secret=include_secret) for p in printers]


@router.post("/", response_model=PrinterResponse)
async def create_printer(
    printer_data: PrinterCreate,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CREATE),
    db: AsyncSession = Depends(get_db),
):
    """Add a new printer.

    Verifies the MQTT connection succeeds before persisting. A wrong access
    code or unreachable IP would otherwise create a printer row that shows
    as an empty / never-connecting card on the dashboard — those reports
    were turning into support tickets that all traced back to a mistyped
    access code.
    """
    # Check if serial number already exists
    result = await db.execute(select(Printer).where(Printer.serial_number == printer_data.serial_number))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Printer with this serial number already exists")

    test_result = await printer_manager.test_connection(
        ip_address=printer_data.ip_address,
        serial_number=printer_data.serial_number,
        access_code=printer_data.access_code,
    )
    if not test_result.get("success"):
        # The frontend renders the user-facing message via i18n on `code`;
        # `message` is an English fallback for non-UI clients (curl / scripts).
        raise HTTPException(
            status_code=400,
            detail={
                "code": "printer_connection_failed",
                "message": (
                    "Could not connect to the printer. Verify IP address, serial number, "
                    "and access code, and confirm LAN-only mode is enabled. "
                    "The printer was not added."
                ),
            },
        )

    printer = Printer(**printer_data.model_dump())
    db.add(printer)
    await db.commit()
    await db.refresh(printer)

    # Connect to the printer
    if printer.is_active:
        await printer_manager.connect_printer(printer)

    return printer


@router.get("/usb-cameras")
async def list_usb_cameras(
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
):
    """List available USB cameras connected to the system.

    Returns a list of detected V4L2 video devices with their info.
    Only works on Linux systems with V4L2 support.

    Returns:
        List of dicts with {device: str, name: str, capabilities: list, formats?: list}
    """
    from backend.app.services.external_camera import list_usb_cameras

    cameras = list_usb_cameras()
    return {"cameras": cameras}


@router.get("/available-filaments")
async def get_available_filaments(
    model: str = Query(..., description="Target printer model"),
    location: str | None = Query(None, description="Optional location filter"),
    _=RequirePermissionIfAuthEnabled(Permission.QUEUE_CREATE),
    db: AsyncSession = Depends(get_db),
):
    """Get deduplicated list of filaments loaded across all active printers of a given model.

    Used by the frontend to offer filament override options for model-based queue assignment.
    """
    from backend.app.utils.printer_models import normalize_printer_model, normalize_printer_model_id

    # Normalize model name
    normalized_model = normalize_printer_model(model) or normalize_printer_model_id(model) or model

    query = (
        select(Printer).where(func.lower(Printer.model) == normalized_model.lower()).where(Printer.is_active == True)  # noqa: E712
    )
    if location:
        query = query.where(Printer.location == location)

    result = await db.execute(query)
    printers_list = list(result.scalars().all())

    return collect_available_filaments(printers_list, printer_manager.get_status)


@router.get("/developer-mode-warnings")
async def get_developer_mode_warnings(
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Check if any connected printer lacks developer LAN mode."""
    result = await db.execute(select(Printer).where(Printer.is_active == True))  # noqa: E712
    printers = result.scalars().all()
    statuses = printer_manager.get_all_statuses()

    warnings = []
    for printer in printers:
        state = statuses.get(printer.id)
        if state and state.connected and state.developer_mode is False:
            warnings.append(
                {
                    "printer_id": printer.id,
                    "name": printer.name,
                }
            )
    return warnings


@router.get("/{printer_id}")
async def get_printer(
    printer_id: int,
    user: User | None = RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific printer.

    ``access_code`` is included only when the caller is trusted to see it
    (Admin / Operator JWT, or auth-disabled mode). Viewers and API keys
    never receive it.
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")
    include_secret = await _caller_can_view_printer_secrets(user, db)
    return _serialize_printer(printer, include_secret=include_secret)


@router.patch("/{printer_id}", response_model=PrinterResponse)
async def update_printer(
    printer_id: int,
    printer_data: PrinterUpdate,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_UPDATE),
    db: AsyncSession = Depends(get_db),
):
    """Update a printer."""
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    update_data = printer_data.model_dump(exclude_unset=True)

    # Handle nested ROI object - flatten to individual columns
    if "plate_detection_roi" in update_data:
        roi = update_data.pop("plate_detection_roi")
        if roi:
            update_data["plate_detection_roi_x"] = roi.get("x")
            update_data["plate_detection_roi_y"] = roi.get("y")
            update_data["plate_detection_roi_w"] = roi.get("w")
            update_data["plate_detection_roi_h"] = roi.get("h")
        else:
            # Clear ROI if set to null
            update_data["plate_detection_roi_x"] = None
            update_data["plate_detection_roi_y"] = None
            update_data["plate_detection_roi_w"] = None
            update_data["plate_detection_roi_h"] = None

    for field, value in update_data.items():
        setattr(printer, field, value)

    await db.commit()
    await db.refresh(printer)

    # Reconnect if connection settings changed
    if any(k in update_data for k in ["ip_address", "access_code", "is_active"]):
        printer_manager.disconnect_printer(printer_id)
        if printer.is_active:
            await printer_manager.connect_printer(printer)

    return printer


@router.delete("/{printer_id}")
async def delete_printer(
    printer_id: int,
    delete_archives: bool = True,
    _=RequirePermissionIfAuthEnabled(Permission.PRINTERS_DELETE),
    db: AsyncSession = Depends(get_db),
):
    """Delete a printer.

    Args:
        printer_id: ID of the printer to delete
        delete_archives: If True (default), delete all print archives for this printer.
                        If False, keep archives but remove their printer association.
    """
    from sqlalchemy import delete as sql_delete

    from backend.app.models.archive import PrintArchive
    from backend.app.models.maintenance import MaintenanceHistory, PrinterMaintenance
    from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment

    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    printer_manager.disconnect_printer(printer_id)

    if delete_archives:
        # Delete all archives for this printer
        await db.execute(sql_delete(PrintArchive).where(PrintArchive.printer_id == printer_id))
    else:
        # Orphan the archives instead of deleting them
        from sqlalchemy import update

        await db.execute(update(PrintArchive).where(PrintArchive.printer_id == printer_id).values(printer_id=None))

    # Delete slot assignments for this printer (SQLite doesn't enforce FK cascades)
    await db.execute(sql_delete(SpoolmanSlotAssignment).where(SpoolmanSlotAssignment.printer_id == printer_id))

    # Delete maintenance history and items for this printer
    # (SQLite doesn't enforce FK cascades, so do it explicitly)
    maintenance_ids = (
        (await db.execute(select(PrinterMaintenance.id).where(PrinterMaintenance.printer_id == printer_id)))
        .scalars()
        .all()
    )
    if maintenance_ids:
        await db.execute(
            sql_delete(MaintenanceHistory).where(MaintenanceHistory.printer_maintenance_id.in_(maintenance_ids))
        )
        await db.execute(sql_delete(PrinterMaintenance).where(PrinterMaintenance.printer_id == printer_id))

    await db.delete(printer)
    await db.commit()

    return {"status": "deleted", "archives_deleted": delete_archives}


# Cache for cover images (printer_id -> {(subtask_name, view_key) -> image_bytes}).
# Cleared on every print start by main.py::on_print_start, so re-dispatches with
# different plates always fetch a fresh thumbnail without needing plate in the key.
_cover_cache: dict[int, dict[tuple[str, str], bytes]] = {}

# Negative cache (#1420): when a cover lookup exhausts every FTP path with 550
# (file sliced on SD card, not on printer storage), remember the failure so the
# next request short-circuits to 404 instead of re-hammering FTP 8 paths deep.
# Cleared on print start alongside _cover_cache.
_cover_404_cache: dict[int, set[tuple[str, str]]] = {}


def clear_cover_cache(printer_id: int) -> None:
    """Clear cached cover images for a printer. Call on print start to avoid stale thumbnails."""
    _cover_cache.pop(printer_id, None)
    _cover_404_cache.pop(printer_id, None)


@router.get("/{printer_id}/cover")
async def get_printer_cover(
    printer_id: int,
    view: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: None = RequireCameraStreamTokenIfAuthEnabled,
):
    """Get the cover image for the current print job.

    Args:
        view: Optional view type. Use "top" for top-down build plate view (useful for skip objects).
              Default returns angled 3D perspective view.
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")

    state = printer_manager.get_status(printer_id)
    if not state:
        raise HTTPException(404, "Printer not connected")

    # Use subtask_name as the 3MF filename (gcode_file is the path inside the 3MF)
    subtask_name = state.subtask_name
    if not subtask_name:
        raise HTTPException(404, f"No subtask_name in printer state (state={state.state})")

    # Resolve the active plate. Precedence (#1166):
    #   1. The plate PrintOps dispatched (authoritative when we sent the print)
    #   2. plate_(\d+)\.gcode regex on state.gcode_file (works on firmware that
    #      reflects the full path, e.g. some X1C builds)
    #   3. Scan the downloaded 3MF for a unique Metadata/plate_*.gcode (covers
    #      per-plate archives sliced separately in Bambu Studio, where the
    #      printer's gcode_file echo is just the .3mf filename)
    #   4. Fall back to plate 1
    # The 3MF-scan fallback runs later — after the file is on disk.
    plate_num = resolve_plate_id(state)
    if plate_num is not None:
        logger.info("Cover: resolved plate %s before download (subtask=%s)", plate_num, subtask_name)

    # Normalize view parameter
    view_key = view or "default"

    # Check cache. Cache by (subtask_name, view_key) only — clear_cover_cache()
    # runs on every print start, so a re-dispatch with a different plate gets
    # a fresh image regardless. Pre-#1166 the key included plate_num, but with
    # late plate resolution the cache check would always miss.
    cache_key = (subtask_name, view_key)
    if printer_id in _cover_cache and cache_key in _cover_cache[printer_id]:
        return Response(content=_cover_cache[printer_id][cache_key], media_type="image/png")

    # Negative-cache short-circuit (#1420): if a prior lookup for this same
    # subtask + view already failed, don't replay 8 FTP retries on every page
    # refresh. _cover_404_cache is cleared on print start.
    if printer_id in _cover_404_cache and cache_key in _cover_404_cache[printer_id]:
        raise HTTPException(404, f"No cover available for '{subtask_name}' (cached)")

    # Build possible 3MF filenames from subtask_name
    # Bambu printers may store files as "name.gcode.3mf" (sliced via Bambu Studio)
    # or just "name.3mf" (uploaded directly)
    possible_filenames = []
    if subtask_name.endswith(".3mf"):
        possible_filenames.append(subtask_name)
    else:
        # Try both naming patterns
        possible_filenames.append(f"{subtask_name}.gcode.3mf")
        possible_filenames.append(f"{subtask_name}.3mf")

    # Also try with spaces converted to underscores (Bambu Studio may normalize filenames)
    if " " in subtask_name:
        normalized = subtask_name.replace(" ", "_")
        if normalized.endswith(".3mf"):
            possible_filenames.append(normalized)
        else:
            possible_filenames.append(f"{normalized}.gcode.3mf")
            possible_filenames.append(f"{normalized}.3mf")

    # Build list of all remote paths to try
    remote_paths = []
    for filename in possible_filenames:
        remote_paths.extend(
            [
                f"/{filename}",  # Root directory (most common)
                f"/cache/{filename}",
                f"/model/{filename}",
                f"/data/{filename}",
            ]
        )

    # Use first filename for temp path (will be reused)
    temp_filename = possible_filenames[0]
    temp_path = settings.archive_dir / "temp" / f"cover_{printer_id}_{temp_filename}"
    temp_path.parent.mkdir(parents=True, exist_ok=True)

    # Cache check (#972): the archive-metadata flow in main.py may have already
    # downloaded this 3MF during the print-start handler. Reusing that file
    # avoids a second 36MB transfer competing with the printer's single FTP
    # socket (which produces the 425 errors that feed the retry storm).
    downloaded = False
    using_cached = False
    for candidate_name in possible_filenames:
        cached = get_cached_3mf(printer_id, candidate_name)
        if cached:
            logger.info("Cover using cached 3MF from %s (avoided duplicate FTP)", cached)
            temp_path = cached
            downloaded = True
            using_cached = True
            break

    if not downloaded:
        logger.info(
            f"Trying to download cover for '{subtask_name}' from {printer.ip_address} (trying {len(remote_paths)} paths)"
        )

        # Retry logic for transient FTP failures
        max_retries = 2
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                downloaded = await download_file_try_paths_async(
                    printer.ip_address,
                    printer.access_code,
                    remote_paths,
                    temp_path,
                    printer_model=printer.model,
                )
                if downloaded:
                    break
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    logger.warning("FTP download attempt %s failed: %s, retrying...", attempt + 1, e)
                    await asyncio.sleep(0.5 * (attempt + 1))  # Brief backoff
                else:
                    logger.error("FTP download failed after %s attempts: %s", max_retries + 1, e)

        if last_error and not downloaded:
            raise HTTPException(503, f"FTP download temporarily unavailable: {last_error}")

        if not downloaded:
            # Remember this failure so subsequent requests for the same print
            # skip the 8-path FTP fan-out (#1420).
            _cover_404_cache.setdefault(printer_id, set()).add(cache_key)
            raise HTTPException(
                404,
                f"Could not download 3MF file for '{subtask_name}' from printer {printer.ip_address}. Tried: {possible_filenames}",
            )

        # Share the fresh download with the archive flow.
        cache_3mf_download(printer_id, temp_filename, temp_path)

    # Verify file actually exists and has content
    if not temp_path.exists():
        raise HTTPException(500, f"Download reported success but file not found: {temp_path}")

    file_size = temp_path.stat().st_size
    logger.info("Downloaded file size: %s bytes", file_size)

    if file_size == 0:
        if not using_cached:
            temp_path.unlink()
        raise HTTPException(500, f"Downloaded file is empty for '{subtask_name}'")

    try:
        # Extract thumbnail from 3MF (which is a ZIP file)
        try:
            zf = zipfile.ZipFile(temp_path, "r")
        except zipfile.BadZipFile:
            raise HTTPException(500, "Downloaded file is not a valid 3MF/ZIP archive")
        except OSError as e:
            logger.error("Failed to open 3MF file: %s", e, exc_info=True)
            raise HTTPException(500, "Failed to open 3MF file. Check server logs for details.")

        try:
            # 3MF-scan fallback for plate detection (#1166). Per-plate archives
            # sliced separately in Bambu Studio contain a single
            # Metadata/plate_N.gcode for the active plate, even though
            # thumbnails for all plates are bundled. Using that gcode's plate
            # number prevents falling back to plate_1.png.
            if plate_num is None:
                plate_gcodes = [name for name in zf.namelist() if re.match(r"^Metadata/plate_\d+\.gcode$", name)]
                if len(plate_gcodes) == 1:
                    match = re.search(r"plate_(\d+)\.gcode", plate_gcodes[0])
                    if match:
                        plate_num = int(match.group(1))
                        logger.info("Cover: detected plate %s from 3MF contents", plate_num)
            if plate_num is None:
                plate_num = 1

            # Try common thumbnail paths in 3MF files
            # Use plate_num to get the correct plate's thumbnail for multi-plate projects
            # Use top-down view if requested (better for skip objects modal)
            if view == "top":
                thumbnail_paths = [
                    f"Metadata/top_{plate_num}.png",
                    # Fall back to plate 1 if specific plate not found
                    "Metadata/top_1.png",
                    f"Metadata/plate_{plate_num}.png",
                    "Metadata/plate_1.png",
                    "Metadata/thumbnail.png",
                ]
            else:
                thumbnail_paths = [
                    f"Metadata/plate_{plate_num}.png",
                    # Fall back to plate 1 if specific plate not found
                    "Metadata/plate_1.png",
                    "Metadata/thumbnail.png",
                    f"Metadata/plate_{plate_num}_small.png",
                    "Metadata/plate_1_small.png",
                    "Thumbnails/thumbnail.png",
                    "thumbnail.png",
                ]

            for thumb_path in thumbnail_paths:
                try:
                    image_data = zf.read(thumb_path)
                    if printer_id not in _cover_cache:
                        _cover_cache[printer_id] = {}
                    _cover_cache[printer_id][(subtask_name, view_key)] = image_data
                    return Response(content=image_data, media_type="image/png")
                except KeyError:
                    continue

            # If no specific thumbnail found, try any PNG in Metadata
            for name in zf.namelist():
                if name.startswith("Metadata/") and name.endswith(".png"):
                    image_data = zf.read(name)
                    if printer_id not in _cover_cache:
                        _cover_cache[printer_id] = {}
                    _cover_cache[printer_id][(subtask_name, view_key)] = image_data
                    return Response(content=image_data, media_type="image/png")

            _cover_404_cache.setdefault(printer_id, set()).add(cache_key)
            raise HTTPException(404, "No thumbnail found in 3MF file")
        finally:
            zf.close()

    finally:
        # Only delete when this invocation owns the file. A cached path is
        # shared with the archive flow — removing it would force a refetch
        # the next time either flow needs the 3MF.
        if not using_cached and temp_path.exists():
            temp_path.unlink()


# Split routers keep the public /printers URL surface while limiting this
# compatibility facade to core CRUD and cover-cache behavior.
from backend.app.api.routes.printers_ams import (  # noqa: E402
    _apply_pa_after_refresh,
    router as ams_router,
)
from backend.app.api.routes.printers_controls import router as controls_router  # noqa: E402
from backend.app.api.routes.printers_operations import (  # noqa: E402
    _slot_preset_key,
    get_inventory_remain,
    router as operations_router,
)
from backend.app.api.routes.printers_status import router as status_router  # noqa: E402

__all__ = [
    "HMS_ACTION_ACK_WAIT_SECONDS",
    "_apply_pa_after_refresh",
    "_slot_preset_key",
    "clear_cover_cache",
    "get_inventory_remain",
    "printer_manager",
    "router",
]

router.include_router(status_router)
router.include_router(operations_router)
router.include_router(ams_router)
router.include_router(controls_router)
