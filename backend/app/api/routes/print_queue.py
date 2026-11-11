"""API routes for print queue management."""

import json
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import defusedxml.ElementTree as ET
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import and_, func, inspect, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.queue_validation import (
    check_missing_start_filament,
    require_active_model,
    require_model_target_scope,
)
from backend.app.api.routes.library_variants import normalize_model_name, resolve_variant_model
from backend.app.core.auth import (
    OwnershipAccess,
    RequirePermissionIfAuthEnabled,
    allowed_printer_ids_for_user,
    require_ownership_permission,
    require_permission_with_key,
    resolve_optional_api_key,
    user_can_access_printer,
)
from backend.app.core.config import settings
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import (
    RowVisibility,
    library_read_criteria,
    require_archive_source,
    require_library_source,
    require_queue_creation,
    resolve_row_visibility,
)
from backend.app.models.api_key import APIKey
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_batch import PrintBatch, PrintBatchPlate
from backend.app.models.print_queue import PrintQueueItem, PrintQueueVariant
from backend.app.models.printer import Printer
from backend.app.models.project import Project
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.schemas.print_queue import (
    ColorSubstitution,
    PrintBatchCreate,
    PrintBatchDispatchRequest,
    PrintBatchPlateProgress,
    PrintBatchPlateTarget,
    PrintBatchResponse,
    PrintBatchUngroupResponse,
    PrintBatchUpdate,
    PrintQueueBulkUpdate,
    PrintQueueBulkUpdateResponse,
    PrintQueueItemCreate,
    PrintQueueItemResponse,
    PrintQueueItemUpdate,
    PrintQueueReorder,
    QueueVariantCreate,
    QueueVariantSummary,
)
from backend.app.services.archive_plate_estimates import queue_source_estimate
from backend.app.services.filament_deficit import compute_deficit_for_queue_item
from backend.app.services.filament_requirements import overrides_for_plate
from backend.app.services.print_batch import (
    BatchDispatchError,
    batch_dispatch_lock,
    batch_jobs_outside_printer_scope,
    delete_or_retain_queue_item,
    dispatch_remaining,
    load_progress,
    refresh_batch_status,
    refresh_batches_after,
    reopen_batch_for_add,
)
from backend.app.services.print_defaults import default_print_options
from backend.app.services.queue_announcements import announce_queue_jobs_added
from backend.app.services.queue_failure_gate import resume_model, resume_printers
from backend.app.services.queue_item_printer import PRINTER_RESOLVED_DEFAULTS
from backend.app.services.queue_item_updates import apply_bulk_queue_updates
from backend.app.services.queue_position import lock_queue_positions, reorder_queue_positions
from backend.app.services.queue_source_metadata import (
    active_printer_model,
    printed_plate_of_multi_plate_file,
    saved_slicer_ams_mapping,
)
from backend.app.utils.local_time import to_naive_utc
from backend.app.utils.printer_models import is_gcode_compatible
from backend.app.utils.safe_path import safe_join_under
from backend.app.utils.threemf_tools import (
    extract_bed_type_from_3mf,
    extract_print_time_from_3mf,
    inspect_3mf_gcode,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/queue", tags=["queue"])


def _ensure_queue_printer_access(user: User | None, item: PrintQueueItem) -> None:
    if not user_can_access_printer(user, item.printer_id):
        raise HTTPException(404, "Queue item not found")


def _variant_summaries(item: PrintQueueItem) -> list[QueueVariantSummary]:
    """Cross-model candidates for display (#671), or [] if they weren't loaded.

    Every response route eager-loads ``variants``. If a future route forgets,
    avoid an async lazy-load failure and degrade to an empty summary instead.
    """
    if "variants" in inspect(item).unloaded:
        return []
    return [
        QueueVariantSummary(
            library_file_id=v.library_file_id,
            filename=v.library_file.filename if v.library_file else "",
            target_model=v.target_model,
            position=v.position,
        )
        for v in item.variants
    ]


def _extract_filament_types_from_3mf(file_path: Path, plate_id: int | None = None) -> list[str]:
    """Extract unique filament types from a 3MF file.

    Args:
        file_path: Path to the 3MF file
        plate_id: Optional plate index to filter for (for multi-plate files)

    Returns:
        List of unique filament types (e.g., ["PLA", "PETG"])
    """
    types: set[str] = set()

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            if "Metadata/slice_info.config" not in zf.namelist():
                return []

            content = zf.read("Metadata/slice_info.config").decode()
            root = ET.fromstring(content)

            if plate_id is not None:
                # Find the plate element with matching index
                for plate_elem in root.findall(".//plate"):
                    plate_index = None
                    for meta in plate_elem.findall("metadata"):
                        if meta.get("key") == "index":
                            try:
                                plate_index = int(meta.get("value", "0"))
                            except ValueError:
                                pass  # Skip plate with unparseable index
                            break

                    if plate_index == plate_id:
                        for filament_elem in plate_elem.findall("filament"):
                            filament_type = filament_elem.get("type", "")
                            used_g = filament_elem.get("used_g", "0")
                            try:
                                used_grams = float(used_g)
                            except (ValueError, TypeError):
                                used_grams = 0
                            if used_grams > 0 and filament_type:
                                types.add(filament_type)
                        break
            else:
                # No plate_id specified - extract all filaments with used_g > 0
                for filament_elem in root.findall(".//filament"):
                    filament_type = filament_elem.get("type", "")
                    used_g = filament_elem.get("used_g", "0")
                    try:
                        used_grams = float(used_g)
                    except (ValueError, TypeError):
                        used_grams = 0
                    if used_grams > 0 and filament_type:
                        types.add(filament_type)

    except Exception as e:
        logger.warning("Failed to extract filament types from %s: %s", file_path, e)

    return sorted(types)


# Local alias kept so existing call sites stay compact; the implementation lives
# in utils/threemf_tools.py so the notification path (main.py) can reuse it
# without importing from a routes module (#1785).
_extract_print_time_from_3mf = extract_print_time_from_3mf


async def _assert_can_dispatch_batch_sources(db: AsyncSession, batch_id: int, visibility: RowVisibility) -> None:
    """Check every source a dispatch can clone, including cross-model variants."""
    members = PrintQueueItem.batch_id == batch_id
    archive_ids = await db.scalars(
        select(PrintQueueItem.archive_id).where(members, PrintQueueItem.archive_id.is_not(None)).distinct()
    )
    library_ids = set(
        await db.scalars(
            select(PrintQueueItem.library_file_id).where(members, PrintQueueItem.library_file_id.is_not(None))
        )
    )
    variant_ids = set(await db.scalars(select(PrintQueueVariant.library_file_id).join(PrintQueueItem).where(members)))
    if not visibility.can_use_model_target and (
        variant_ids
        or await db.scalar(select(PrintQueueItem.id).where(members, PrintQueueItem.target_model.is_not(None)).limit(1))
    ):
        require_model_target_scope(visibility)
    library_ids.update(variant_ids)
    for archive_id in archive_ids:
        await require_archive_source(db, archive_id, visibility)
    for file_id in library_ids:
        await require_library_source(db, file_id, visibility)


async def _resolve_source_path(db: AsyncSession, item: PrintQueueItem) -> Path | None:
    """Resolve an existing queue item's source 3MF on disk, or None."""
    if item.archive_id:
        result = await db.execute(select(PrintArchive).where(PrintArchive.id == item.archive_id))
        archive = result.scalar_one_or_none()
        if archive:
            return settings.base_dir / archive.file_path
    if item.library_file_id:
        result = await db.execute(LibraryFile.active().where(LibraryFile.id == item.library_file_id))
        library_file = result.scalar_one_or_none()
        if library_file:
            lib_path = Path(library_file.file_path)
            return lib_path if lib_path.is_absolute() else settings.base_dir / library_file.file_path
    return None


def _source_sliced_for(archive: PrintArchive | None, library_file: LibraryFile | None) -> str | None:
    if archive:
        return archive.sliced_for_model
    if library_file and library_file.file_metadata:
        value = library_file.file_metadata.get("sliced_for_model")
        return str(value) if value else None
    return None


_COLOR_SUBSTITUTIONS = TypeAdapter(list[ColorSubstitution])


def _enrich_response(item: PrintQueueItem, shortest_first: bool | None = None) -> PrintQueueItemResponse:
    """Add nested archive/printer/library_file info to response."""
    # Parse ams_mapping from JSON string BEFORE model_validate
    ams_mapping_parsed = None
    if item.ams_mapping:
        try:
            ams_mapping_parsed = json.loads(item.ams_mapping)
        except json.JSONDecodeError:
            ams_mapping_parsed = None

    # Parse required_filament_types from JSON string
    required_filament_types_parsed = None
    if item.required_filament_types:
        try:
            required_filament_types_parsed = json.loads(item.required_filament_types)
        except json.JSONDecodeError:
            required_filament_types_parsed = None

    # Parse filament_overrides from JSON string
    filament_overrides_parsed = None
    if item.filament_overrides:
        try:
            filament_overrides_parsed = json.loads(item.filament_overrides)
        except json.JSONDecodeError:
            filament_overrides_parsed = None

    # Parse the opaque H2C rack slicer-pick JSON retained from project_file (#1780).
    nozzle_mapping_parsed = None
    if item.nozzle_mapping:
        try:
            nozzle_mapping_parsed = json.loads(item.nozzle_mapping)
        except json.JSONDecodeError:
            nozzle_mapping_parsed = None

    nozzles_info_parsed = None
    if item.nozzles_info:
        try:
            nozzles_info_parsed = json.loads(item.nozzles_info)
        except json.JSONDecodeError:
            nozzles_info_parsed = None

    color_substitutions = None
    if item.color_substitutions:
        try:
            color_substitutions = _COLOR_SUBSTITUTIONS.validate_json(item.color_substitutions)
        except ValidationError:
            pass

    # Create response with parsed ams_mapping
    item_dict = {
        "id": item.id,
        "printer_id": item.printer_id,
        "target_model": item.target_model,
        "target_location": item.target_location,
        "required_filament_types": required_filament_types_parsed,
        "filament_overrides": filament_overrides_parsed,
        "waiting_reason": item.waiting_reason,
        "archive_id": item.archive_id,
        "library_file_id": item.library_file_id,
        "position": item.position,
        "scheduled_time": item.scheduled_time,
        "require_previous_success": item.require_previous_success,
        "auto_off_after": item.auto_off_after,
        "manual_start": item.manual_start,
        "filament_short": bool(item.filament_short),
        "color_substitutions": color_substitutions,
        "skip_filament_check": bool(item.skip_filament_check),
        "ams_mapping": ams_mapping_parsed,
        "plate_id": item.plate_id,
        "bed_levelling": item.bed_levelling,
        "flow_cali": item.flow_cali,
        "vibration_cali": item.vibration_cali,
        "layer_inspect": item.layer_inspect,
        "timelapse": item.timelapse,
        "use_ams": item.use_ams,
        "nozzle_offset_cali": item.nozzle_offset_cali,
        "confirm_outcome": item.confirm_outcome,
        "expected_parts": item.expected_parts,
        "preheat_override": item.preheat_override,
        "preheat_chamber_target_override": item.preheat_chamber_target_override,
        "status": item.status,
        "started_at": item.started_at,
        "completed_at": item.completed_at,
        "error_message": item.error_message,
        "created_at": item.created_at,
        # User tracking (Issue #206)
        "created_by_id": item.created_by_id,
        "created_by_username": item.created_by.username if item.created_by else None,
        # Batch grouping
        "batch_id": item.batch_id,
        "batch_name": item.batch.name if item.batch else None,
        # SJF scheduling
        "been_jumped": item.been_jumped,
        "scheduler_print_time_seconds": item.print_time_seconds,
        "scheduler_shortest_first": shortest_first,
        "dispatching": item.dispatching_at is not None,
        # Auto-print G-code injection
        "gcode_injection": item.gcode_injection,
        # H2C rack-swap nozzle pick (#1780)
        "nozzle_mapping": nozzle_mapping_parsed,
        "nozzles_info": nozzles_info_parsed,
        "cleanup_library_after_dispatch": item.cleanup_library_after_dispatch,
        # Cross-model alternatives (#671); the helper avoids async lazy loads
        # if a caller forgets to eagerly load variants.
        "variants": _variant_summaries(item),
    }
    response = PrintQueueItemResponse(**item_dict)
    if item.archive:
        # Soft-deleted archive: files are gone from disk but the row stays
        # (its filament/cost contribution still flows into stats per #1343).
        # Suppress the archive-derived UI surface so the queue page doesn't
        # 404-storm the thumbnail / plates / plate-thumbnail endpoints — the
        # frontend's existing truthy gate on archive_thumbnail covers it
        # (#1348 follow-up). The archive_deleted flag lets the UI render a
        # "source deleted" badge on these rows.
        if item.archive.deleted_at is not None:
            response.archive_deleted = True
        else:
            response.archive_name = item.archive.print_name or item.archive.filename
            response.archive_thumbnail = item.archive.thumbnail_path
            response.print_time_seconds, response.filament_used_grams = queue_source_estimate(
                item.archive, None, item.plate_id, settings.base_dir
            )
            response.filament_type = item.archive.filament_type
            response.filament_color = item.archive.filament_color
            response.layer_height = item.archive.layer_height
            response.nozzle_diameter = item.archive.nozzle_diameter
            response.sliced_for_model = item.archive.sliced_for_model
            response.bed_type = item.archive.bed_type
            if item.plate_id:
                archive_path = settings.base_dir / item.archive.file_path
                if archive_path.exists():
                    plate_bed = extract_bed_type_from_3mf(archive_path, item.plate_id)
                    if plate_bed:
                        response.bed_type = plate_bed
    if item.library_file:
        response.library_file_name = (
            item.library_file.file_metadata.get("print_name") if item.library_file.file_metadata else None
        )
        if not response.library_file_name:
            response.library_file_name = item.library_file.filename
        response.library_file_thumbnail = item.library_file.thumbnail_path
        if not item.archive:
            response.print_time_seconds, response.filament_used_grams = queue_source_estimate(
                None, item.library_file, item.plate_id, settings.base_dir
            )
        # Get metadata from library file if no archive
        if not item.archive and item.library_file.file_metadata:
            response.filament_type = item.library_file.file_metadata.get("filament_type")
            response.filament_color = item.library_file.file_metadata.get("filament_color")
            response.layer_height = item.library_file.file_metadata.get("layer_height")
            response.nozzle_diameter = item.library_file.file_metadata.get("nozzle_diameter")
            response.sliced_for_model = item.library_file.file_metadata.get("sliced_for_model")
            response.bed_type = item.library_file.file_metadata.get("bed_type")
        if item.plate_id:
            lib_path = Path(item.library_file.file_path)
            library_file_path = lib_path if lib_path.is_absolute() else settings.base_dir / item.library_file.file_path
            if library_file_path.exists():
                plate_bed = extract_bed_type_from_3mf(library_file_path, item.plate_id)
                if plate_bed:
                    response.bed_type = plate_bed
    if item.printer:
        response.printer_name = item.printer.name
    return response


def queue_read_query(visibility: RowVisibility):
    return (
        select(PrintQueueItem)
        .options(
            selectinload(PrintQueueItem.archive),
            selectinload(PrintQueueItem.printer),
            selectinload(PrintQueueItem.library_file),
            selectinload(PrintQueueItem.created_by),
            selectinload(PrintQueueItem.batch),
            selectinload(PrintQueueItem.variants).selectinload(PrintQueueVariant.library_file),
        )
        .where(
            *visibility.criteria(
                PrintQueueItem.created_by_id,
                Permission.QUEUE_READ_ALL,
                Permission.QUEUE_READ_OWN,
                PrintQueueItem.printer_id,
            )
        )
    )


async def enrich_queue_items(db: AsyncSession, items) -> list[PrintQueueItemResponse]:
    # Queue readers need only the effective ordering bit.
    sjf = await db.scalar(select(Settings.value).where(Settings.key == "queue_shortest_first"))
    return [_enrich_response(item, str(sjf).lower() == "true") for item in items]


@router.get("/", response_model=list[PrintQueueItemResponse])
async def list_queue(
    printer_id: int | None = Query(None, description="Filter by printer (-1 for unassigned)"),
    status: str | None = Query(None, description="Filter by one or several comma-separated statuses"),
    target_model: str | None = Query(
        None, description="Filter by target model (also includes model-based items when combined with printer_id)"
    ),
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(
        require_ownership_permission(Permission.QUEUE_READ_ALL, Permission.QUEUE_READ_OWN, include_api_key=True)
    ),
):
    """List all queue items, optionally filtered by printer or status."""
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    if printer_id is not None and printer_id != -1 and not visibility.allows_printer(printer_id):
        raise HTTPException(404, "Printer not found")
    query = queue_read_query(visibility).order_by(PrintQueueItem.position, PrintQueueItem.id)

    if printer_id is not None:
        if printer_id == -1:
            # Special value: filter for unassigned items
            query = query.where(PrintQueueItem.printer_id.is_(None))
        else:
            # Include model jobs even when the client omits the printer model.
            effective_model = target_model
            if not effective_model:
                printer_row = (
                    await db.execute(select(Printer.model).where(Printer.id == printer_id))
                ).scalar_one_or_none()
                effective_model = printer_row

            if effective_model:
                # Include both printer-specific items AND model-based (unassigned) items
                query = query.where(
                    or_(
                        PrintQueueItem.printer_id == printer_id,
                        and_(
                            PrintQueueItem.printer_id.is_(None),
                            func.lower(PrintQueueItem.target_model) == effective_model.lower(),
                        ),
                    )
                )
            else:
                query = query.where(PrintQueueItem.printer_id == printer_id)
    elif target_model:
        query = query.where(func.lower(PrintQueueItem.target_model) == target_model.lower())
    if status:
        query = query.where(PrintQueueItem.status.in_([value.strip() for value in status.split(",") if value.strip()]))

    return await enrich_queue_items(db, (await db.scalars(query)).all())


def _print_source_path(stored_path: str) -> Path:
    path = Path(stored_path)
    # SEC-PATH-OK: absolute paths are stored by the managed library, including external mounts.
    return path if path.is_absolute() else safe_join_under(settings.base_dir, stored_path)


def _ensure_sliced_3mf(file_path: Path, filename: str) -> None:
    if (filename.lower().endswith(".3mf") or file_path.suffix.lower() == ".3mf") and (
        inspect_3mf_gcode(file_path) is False
    ):
        raise HTTPException(400, f"{filename} isn't sliced yet. Slice it first, then print the sliced file.")


async def _resolve_queue_variants(
    db: AsyncSession,
    specs: list[QueueVariantCreate],
    visibility: RowVisibility,
) -> list[tuple[QueueVariantCreate, LibraryFile, str]]:
    """Validate a cross-model candidate set and pair each file with its model (#671).

    Validated as a set, not file by file, because the failure modes are about the
    set: two candidates for the same printer give the resolver no basis to choose,
    and a set where nothing can ever run is a job that waits forever.

    At least one candidate must have an active printer — the rest may not, which
    is deliberate. Grouping the H2C slice before the H2C arrives is a reasonable
    thing to do, and refusing the whole queue action over it would be worse than
    letting that candidate simply never match.
    """
    file_ids = [s.library_file_id for s in specs]
    if len(set(file_ids)) != len(file_ids):
        raise HTTPException(400, "The same file cannot be listed twice as a variant")

    rows = (
        (await db.execute(LibraryFile.active().where(LibraryFile.id.in_(file_ids), *library_read_criteria(visibility))))
        .scalars()
        .all()
    )
    by_id = {f.id: f for f in rows}

    resolved: list[tuple[QueueVariantCreate, LibraryFile, str]] = []
    seen_models: dict[str, str] = {}
    any_active_printer = False

    for spec in specs:
        library_file = by_id.get(spec.library_file_id)
        if library_file is None:
            raise HTTPException(404, f"Library file not found: {spec.library_file_id}")

        from backend.app.utils.filename import InvalidFilenameError, validate_print_filename

        try:
            validate_print_filename(library_file.filename)
        except InvalidFilenameError as e:
            raise HTTPException(400, str(e)) from e

        _ensure_sliced_3mf(_print_source_path(library_file.file_path), library_file.filename)

        model = resolve_variant_model(library_file, spec.target_model)
        if not model:
            raise HTTPException(
                400,
                f"{library_file.filename} does not say which printer it was sliced for — "
                "set its target model explicitly",
            )

        # Cross-model safety gate (#2578), per candidate. A set is only as safe as
        # its worst member, and model-based dispatch has no human in the loop.
        sliced_for = (library_file.file_metadata or {}).get("sliced_for_model")
        if not is_gcode_compatible(sliced_for, model):
            raise HTTPException(
                400,
                f"{library_file.filename} was sliced for {sliced_for} and cannot be dispatched to {model} printers",
            )

        active_model = await active_printer_model(db, model, visibility.printer_ids)
        model = active_model or model
        if model.lower() in seen_models:
            raise HTTPException(
                400,
                f"{library_file.filename} and {seen_models[model.lower()]} are both for {model}; variants must target different printers",
            )
        seen_models[model.lower()] = library_file.filename
        any_active_printer = any_active_printer or active_model is not None

        resolved.append((spec, library_file, model))

    if not any_active_printer:
        raise HTTPException(400, f"No active printers for any of: {', '.join(seen_models)}")

    return resolved


def _variant_values(
    spec: QueueVariantCreate,
    library_file: LibraryFile,
    model: str,
    position: int,
) -> dict:
    """Column values for one candidate, extracted from its own 3MF.

    Each candidate is a different slice, so its filament requirements and print
    time come from its own file rather than being inherited from the item.

    Returns values rather than a row so a quantity>1 batch can build one row per
    copy without re-opening the 3MF for each.
    """
    file_path = _print_source_path(library_file.file_path)

    required_types = None
    filament_overrides_json = None
    print_time = (library_file.file_metadata or {}).get("print_time_seconds")

    if file_path.exists():
        types = _extract_filament_types_from_3mf(file_path, spec.plate_id)
        if types:
            required_types = json.dumps(types)
        if spec.plate_id:
            plate_time = _extract_print_time_from_3mf(file_path, spec.plate_id)
            if plate_time is not None:
                print_time = plate_time
        if spec.filament_overrides:
            plate_overrides = overrides_for_plate(spec.filament_overrides, file_path, spec.plate_id)
            if plate_overrides:
                filament_overrides_json = json.dumps(plate_overrides)
                override_types = sorted({o["type"] for o in plate_overrides if "type" in o})
                if override_types:
                    existing = set(json.loads(required_types)) if required_types else set()
                    required_types = json.dumps(sorted(existing | set(override_types)))

    return {
        "position": position,
        "library_file_id": library_file.id,
        "target_model": model,
        "plate_id": spec.plate_id,
        "ams_mapping": json.dumps(spec.ams_mapping) if spec.ams_mapping else None,
        "nozzle_mapping": json.dumps(spec.nozzle_mapping) if spec.nozzle_mapping else None,
        "filament_overrides": filament_overrides_json,
        "required_filament_types": required_types,
        "print_time_seconds": print_time,
    }


@router.post("/", response_model=PrintQueueItemResponse)
async def add_to_queue(
    data: PrintQueueItemCreate,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.QUEUE_CREATE)),
):
    """Add an item to the print queue."""
    return await create_queue_items(data, db, access)


async def create_queue_items(
    data: PrintQueueItemCreate, db: AsyncSession, access: OwnershipAccess, *, announce: bool = True
) -> PrintQueueItemResponse:
    visibility = await require_queue_creation(db, access.user, access.api_key)
    current_user = visibility.user
    archive_id, library_file_id = data.archive_id or None, data.library_file_id or None
    target_model_norm = normalize_model_name(data.target_model)
    if target_model_norm or data.variants:
        require_model_target_scope(visibility)

    # Validate every cross-model alternative before creating the job (#671).
    variant_specs: list[tuple[QueueVariantCreate, LibraryFile, str]] = []
    if data.variants:
        if data.printer_id:
            raise HTTPException(
                400, "Cannot specify both printer_id and variants — pick a printer or offer alternatives"
            )
        if archive_id or library_file_id:
            raise HTTPException(
                400, "Cannot combine variants with archive_id or library_file_id — the variants are the files"
            )
        variant_specs = await _resolve_queue_variants(db, data.variants, visibility)
        # Mirror the first candidate onto the item so the queue listing, the SJF
        # grouping and the "Any H2S" label have something before a printer is
        # picked. Resolution overwrites it with whichever candidate actually runs.
        target_model_norm = variant_specs[0][2]

    # Variant files belong on their own rows so deleting one preserves the job.
    if not archive_id and not library_file_id and not data.variants:
        raise HTTPException(400, "Either archive_id or library_file_id must be provided")

    # Cannot specify both printer_id and target_model
    if data.printer_id and target_model_norm:
        raise HTTPException(400, "Cannot specify both printer_id and target_model")

    assigned_printer_model = None
    if data.printer_id is not None:
        if not visibility.allows_printer(data.printer_id):
            raise HTTPException(404, "Printer not found")
        result = await db.execute(select(Printer).where(Printer.id == data.printer_id))
        assigned_printer = result.scalar_one_or_none()
        if assigned_printer is None:
            raise HTTPException(400, "Printer not found")
        assigned_printer_model = assigned_printer.model

    # Cross-model validation has already found an active candidate.
    if target_model_norm and not data.variants:
        target_model_norm = await require_active_model(db, target_model_norm, visibility.printer_ids)

    # Validate archive exists (if provided) and get it for filament extraction
    archive = await require_archive_source(db, archive_id, visibility) if archive_id else None
    library_file = None
    if library_file_id:
        library_file = await require_library_source(db, library_file_id, visibility)
        # Bambu SD card is FAT32/exFAT — illegal filename chars would 553 at
        # FTP upload time (#1540). Reject at queue time so the user gets the
        # actionable error before waiting in queue.
        from backend.app.utils.filename import InvalidFilenameError, validate_print_filename

        try:
            validate_print_filename(library_file.filename)
        except InvalidFilenameError as e:
            raise HTTPException(400, str(e)) from e

    target_hardware_model = target_model_norm or assigned_printer_model
    sliced_for_model = _source_sliced_for(archive, library_file)
    if target_hardware_model and not is_gcode_compatible(sliced_for_model, target_hardware_model):
        raise HTTPException(
            400,
            f"File was sliced for {sliced_for_model} and cannot be dispatched to {target_hardware_model} printers",
        )

    # Extract filament types for model-based assignment (used by scheduler for validation)
    required_filament_types = None
    file_path = None
    # Both concrete-printer and model jobs need the source for plate filtering.
    source = archive or library_file
    if source:
        file_path = _print_source_path(source.file_path)
        _ensure_sliced_3mf(file_path, source.filename)

    plate_id = data.plate_id or printed_plate_of_multi_plate_file(file_path)
    if target_model_norm:
        if file_path and file_path.exists():
            filament_types = _extract_filament_types_from_3mf(file_path, plate_id)
            if filament_types:
                required_filament_types = json.dumps(filament_types)
                logger.info("Extracted filament types for model-based queue: %s", filament_types)

    # If filament overrides are provided, update required_filament_types to match override types
    filament_overrides_json = None
    if data.filament_overrides:
        plate_overrides = overrides_for_plate(data.filament_overrides, file_path, plate_id)
        if plate_overrides:
            filament_overrides_json = json.dumps(plate_overrides)
            # Update required_filament_types from overrides so scheduler validates against overridden types
            override_types = sorted({o["type"] for o in plate_overrides if "type" in o})
            if override_types:
                # Merge with existing types (overrides may only cover some slots)
                existing_types = set(json.loads(required_filament_types)) if required_filament_types else set()
                # Replace types for overridden slots, keep others
                all_types = existing_types | set(override_types)
                required_filament_types = json.dumps(sorted(all_types))

    # Validate quantity
    quantity = max(1, data.quantity)

    # Validate batch_id if provided. Client passes batch_id when adding items
    # into a pre-created batch (multi-plate auto-batch or "Group as batch" flow).
    # 404 keeps the existing-id leak surface low.
    batch = None
    batch_id = None
    if data.batch_id is not None:
        result = await db.execute(select(PrintBatch).where(PrintBatch.id == data.batch_id))
        existing_batch = result.scalar_one_or_none()
        if not existing_batch:
            raise HTTPException(404, "Batch not found")
        if (
            current_user is not None
            and existing_batch.created_by_id is not None
            and existing_batch.created_by_id != current_user.id
            and not current_user.has_permission(Permission.QUEUE_UPDATE_ALL.value)
        ):
            raise HTTPException(404, "Batch not found")
        await _ensure_batch_in_scope(db, existing_batch.id, visibility.printer_ids)
        if not reopen_batch_for_add(existing_batch):
            raise HTTPException(400, "Cannot add items to a non-active batch")
        batch = existing_batch
        batch_id = existing_batch.id

    # Create batch if quantity > 1 and no batch_id provided
    if batch_id is None and quantity > 1:
        # Derive batch name from source file
        batch_name_base = "Batch"
        if archive:
            batch_name_base = archive.print_name or archive.filename or "Batch"
        elif library_file:
            if library_file.file_metadata:
                batch_name_base = library_file.file_metadata.get("print_name") or library_file.filename
            else:
                batch_name_base = library_file.filename
        batch_name_base = batch_name_base.replace(".gcode.3mf", "").replace(".3mf", "")

        batch = PrintBatch(
            name=f"{batch_name_base} ×{quantity}",
            archive_id=archive_id,
            library_file_id=library_file_id,
            quantity=quantity,
            status="active",
            created_by_id=current_user.id if current_user else None,
        )
        db.add(batch)
        await db.flush()  # Get batch.id before creating items
        batch_id = batch.id

    # The UI reorders one list, so every producer shares its sequence.
    queue_scope = (PrintQueueItem.status == "pending",)
    await lock_queue_positions(db)

    insert_position = max(1, data.insert_position or 1)
    if data.insert_at_top or data.insert_position is not None:
        result = await db.execute(select(func.max(PrintQueueItem.position)).where(*queue_scope))
        max_pos = result.scalar() or 0
        insert_position = min(insert_position, max_pos + 1)
        await db.execute(
            update(PrintQueueItem)
            .where(*queue_scope)
            .where(PrintQueueItem.position >= insert_position)
            .values(position=PrintQueueItem.position + quantity)
        )
        start_position = insert_position
    else:
        result = await db.execute(select(func.max(PrintQueueItem.position)).where(*queue_scope))
        max_pos = result.scalar() or 0
        start_position = max_pos + 1

    cached_print_time, _ = queue_source_estimate(archive, library_file, plate_id, settings.base_dir)

    # Validate project exists before insert so a bogus ID yields 404, not an FK-constraint 500
    if data.project_id is not None:
        project_result = await db.execute(select(Project).where(Project.id == data.project_id))
        if not project_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Project not found")

    ams_mapping_json = json.dumps(data.ams_mapping) if data.ams_mapping else None
    wants_live_color_match = any(o.get("force_color_match") for o in (data.filament_overrides or []))
    if ams_mapping_json is None and not wants_live_color_match:
        ams_mapping_json = saved_slicer_ams_mapping(archive, data.printer_id, plate_id)
    print_options = await default_print_options(db, data.model_dump(exclude_unset=True))
    items = []
    for i in range(quantity):
        item = PrintQueueItem(
            printer_id=data.printer_id,
            target_model=target_model_norm,
            target_location=data.target_location,
            required_filament_types=required_filament_types,
            filament_overrides=filament_overrides_json,
            archive_id=archive_id,
            library_file_id=library_file_id,
            scheduled_time=to_naive_utc(data.scheduled_time),
            require_previous_success=data.require_previous_success,
            auto_off_after=data.auto_off_after,
            manual_start=data.manual_start,
            skip_filament_check=data.skip_filament_check,
            ams_mapping=ams_mapping_json,
            plate_id=plate_id,
            use_ams=data.use_ams,
            **print_options,
            confirm_outcome=data.confirm_outcome,
            expected_parts=data.expected_parts,
            preheat_override=data.preheat_override,
            preheat_chamber_target_override=data.preheat_chamber_target_override,
            gcode_injection=data.gcode_injection,
            cleanup_library_after_dispatch=data.cleanup_library_after_dispatch,
            project_id=data.project_id,
            position=start_position + i,
            status="pending",
            created_by_id=current_user.id if current_user else None,
            batch_id=batch_id,
            print_time_seconds=cached_print_time,
        )
        db.add(item)
        items.append(item)

    if variant_specs:
        variant_values = [
            _variant_values(spec, library_file, model, position)
            for position, (spec, library_file, model) in enumerate(variant_specs)
        ]
        # SJF orders pending items before any printer is known, so the row carries
        # the shortest candidate's estimate. Resolution replaces it with the one
        # that actually runs.
        estimates = [v["print_time_seconds"] for v in variant_values if v["print_time_seconds"]]
        for item in items:
            # Each copy in a quantity>1 batch gets its own candidate rows —
            # attempt counts are per-item, and two copies must be free to land on
            # different printers.
            item.variants.extend(PrintQueueVariant(**values) for values in variant_values)
            item.print_time_seconds = min(estimates) if estimates else None

    await db.commit()

    if announce:
        await announce_queue_jobs_added([item.id for item in items])

    # Refresh the first item for the response
    item = items[0]
    await db.refresh(item)
    await db.refresh(item, ["archive", "printer", "library_file", "created_by", "batch"])

    source_name = f"archive {archive_id}" if archive_id else f"library file {library_file_id}"
    target_desc = data.printer_id or (f"model {target_model_norm}" if target_model_norm else "unassigned")
    qty_desc = f" (×{quantity})" if quantity > 1 else ""
    logger.info("Added %s to queue for %s%s", source_name, target_desc, qty_desc)

    return _enrich_response(item)


@router.patch("/bulk", response_model=PrintQueueBulkUpdateResponse)
async def bulk_update_queue_items(
    data: PrintQueueBulkUpdate,
    db: AsyncSession = DB_SESSION,
    auth_result: tuple[User | None, bool] = Depends(
        require_ownership_permission(
            Permission.QUEUE_UPDATE_ALL,
            Permission.QUEUE_UPDATE_OWN,
        )
    ),
):
    """Bulk update multiple queue items with the same values.

    Only pending items can be updated. Non-pending items are skipped.
    Items not owned by the user are also skipped (unless user has *_all permission).
    """
    user, can_modify_all = auth_result

    if not data.item_ids:
        raise HTTPException(400, "No item IDs provided")

    # Get fields to update (exclude item_ids and unset fields)
    update_data = data.model_dump(exclude={"item_ids"}, exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No fields to update")

    # Validate printer_id if being changed
    if "printer_id" in update_data and update_data["printer_id"] is not None:
        result = await db.execute(select(Printer).where(Printer.id == update_data["printer_id"]))
        printer = result.scalar_one_or_none()
        if not printer:
            raise HTTPException(400, "Printer not found")
        if not user_can_access_printer(user, printer.id):
            raise HTTPException(404, "Printer not found")

    updated_count, skipped_count = await apply_bulk_queue_updates(
        db,
        data.item_ids,
        update_data,
        owner_id=user.id if user else None,
        can_modify_all=can_modify_all,
        allowed_printer_ids=allowed_printer_ids_for_user(user),
    )

    await db.commit()

    logger.info("Bulk updated %s queue items, skipped %s", updated_count, skipped_count)
    return PrintQueueBulkUpdateResponse(
        updated_count=updated_count,
        skipped_count=skipped_count,
        message=f"Updated {updated_count} items"
        + (f", skipped {skipped_count} non-pending/not-owned" if skipped_count else ""),
    )


# --- Batch endpoints ---


def _validate_plate_targets(
    plates: list[PrintBatchPlateTarget] | None,
) -> list[PrintBatchPlateTarget] | None:
    """Reject duplicate plates, including NULL, and orders with no target."""
    if plates is None:
        return None
    if not plates:
        raise HTTPException(400, "plates must contain at least one plate")

    seen: set[int | None] = set()
    for target in plates:
        if target.plate_id in seen:
            label = target.plate_id if target.plate_id is not None else "whole file"
            raise HTTPException(400, f"Duplicate plate in order: {label}")
        seen.add(target.plate_id)

    if all(target.quantity_target == 0 for target in plates):
        raise HTTPException(400, "Order must request at least one print")
    return plates


async def _validate_batch_project(db: AsyncSession, project_id: int | None, current_user: User | None) -> None:
    """404 on a bogus project id rather than letting the FK blow up as a 500."""
    if project_id is None:
        return
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Project not found")


async def _ensure_batch_in_scope(db: AsyncSession, batch_id: int, printer_scope: set[int] | None) -> None:
    if printer_scope is not None and await db.scalar(select(batch_jobs_outside_printer_scope(batch_id, printer_scope))):
        raise HTTPException(404, "Batch not found")


async def _load_batch_for_write(
    db: AsyncSession, batch_id: int, current_user: User | None, printer_scope: set[int] | None, permission: Permission
) -> PrintBatch:
    """Fetch a writable batch or return the same 404 as a missing batch."""
    result = await db.execute(
        select(PrintBatch).options(selectinload(PrintBatch.plates)).where(PrintBatch.id == batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(404, "Batch not found")
    if (
        current_user is not None
        and batch.created_by_id is not None
        and batch.created_by_id != current_user.id
        and not current_user.has_permission(permission.value)
    ):
        raise HTTPException(404, "Batch not found")
    await _ensure_batch_in_scope(db, batch_id, printer_scope)
    return batch


@router.post("/batches", response_model=PrintBatchResponse)
async def create_batch(
    data: PrintBatchCreate,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.QUEUE_CREATE)),
):
    """Group existing pending jobs or create a new order with per-plate targets."""
    if not data.name or not data.name.strip():
        raise HTTPException(400, "Batch name is required")

    visibility = await require_queue_creation(db, access.user, access.api_key)
    current_user = visibility.user
    plate_targets = _validate_plate_targets(data.plates)
    await _validate_batch_project(db, data.project_id, current_user)

    archive_id, library_file_id = data.archive_id or None, data.library_file_id or None
    if archive_id is not None:
        await require_archive_source(db, archive_id, visibility)
    if library_file_id is not None:
        await require_library_source(db, library_file_id, visibility)

    batch = PrintBatch(
        name=data.name.strip()[:255],
        archive_id=archive_id,
        library_file_id=library_file_id,
        quantity=len(data.item_ids) if data.item_ids else 1,
        status="active",
        created_by_id=current_user.id if current_user else None,
        project_id=data.project_id,
        due_date=data.due_date,
        notes=data.notes,
    )
    db.add(batch)
    await db.flush()  # Need batch.id before assigning to items

    if plate_targets is not None:
        for target in plate_targets:
            db.add(
                PrintBatchPlate(
                    batch_id=batch.id,
                    plate_id=target.plate_id,
                    plate_name=target.plate_name,
                    quantity_target=target.quantity_target,
                    sort_order=target.sort_order,
                )
            )
        # The legacy `quantity` column is display-only; keep it meaningful for
        # anything still reading it by making it the order's total.
        batch.quantity = max(1, sum(t.quantity_target for t in plate_targets))

    assigned = 0
    if data.item_ids:
        result = await db.execute(select(PrintQueueItem).where(PrintQueueItem.id.in_(data.item_ids)).with_for_update())
        items = result.scalars().all()
        for item in items:
            if item.status != "pending":
                continue
            if item.printer_id is not None and not visibility.allows_printer(item.printer_id):
                continue
            if item.batch_id is not None:
                continue
            if (
                current_user is not None
                and item.created_by_id != current_user.id
                and not current_user.has_permission(Permission.QUEUE_UPDATE_ALL.value)
            ):
                continue
            item.batch_id = batch.id
            assigned += 1
        batch.quantity = max(assigned, 1)

    await db.commit()
    await db.refresh(batch)

    logger.info("Created batch %s '%s' with %s assigned items", batch.id, batch.name, assigned)
    return await _build_batch_response(db, batch)


@router.patch("/batches/{batch_id}", response_model=PrintBatchResponse)
async def update_batch(
    batch_id: int,
    data: PrintBatchUpdate,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.QUEUE_UPDATE_OWN)),
):
    """Edit an order's header and targets, retaining previously dispatched jobs."""
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    current_user = visibility.user
    batch = await _load_batch_for_write(db, batch_id, current_user, visibility.printer_ids, Permission.QUEUE_UPDATE_ALL)

    plate_targets = _validate_plate_targets(data.plates)
    if data.project_id is not None:
        await _validate_batch_project(db, data.project_id, current_user)

    if data.name is not None:
        if not data.name.strip():
            raise HTTPException(400, "Batch name is required")
        batch.name = data.name.strip()[:255]
    if data.project_id is not None:
        batch.project_id = data.project_id
    if data.due_date is not None:
        batch.due_date = data.due_date
    if data.notes is not None:
        batch.notes = data.notes
    if data.status is not None:
        batch.status = data.status

    if plate_targets is not None:
        existing = {row.plate_id: row for row in batch.plates}
        for target in plate_targets:
            row = existing.pop(target.plate_id, None)
            if row is None:
                db.add(
                    PrintBatchPlate(
                        batch_id=batch.id,
                        plate_id=target.plate_id,
                        plate_name=target.plate_name,
                        quantity_target=target.quantity_target,
                        sort_order=target.sort_order,
                    )
                )
            else:
                row.quantity_target = target.quantity_target
                row.sort_order = target.sort_order
                if target.plate_name is not None:
                    row.plate_name = target.plate_name
        # Plates absent from the payload are dropped — the list is the order.
        for orphan in existing.values():
            await db.delete(orphan)
        batch.quantity = max(1, sum(t.quantity_target for t in plate_targets))

    await db.flush()
    await db.refresh(batch)
    # Raising a target on a finished order reopens it; lowering one on a
    # running order can complete it.
    await refresh_batch_status(db, batch)
    await db.commit()
    await db.refresh(batch)

    logger.info("Updated batch %s", batch.id)
    return await _build_batch_response(db, batch)


@router.post("/batches/{batch_id}/dispatch", response_model=PrintBatchResponse)
async def dispatch_batch(
    batch_id: int,
    data: PrintBatchDispatchRequest,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.QUEUE_CREATE)),
):
    """Queue the runs this order still owes (#342).

    Each new item is cloned from the most recent item for the same plate in
    this batch, so it inherits the printer/model target, AMS mapping, filament
    overrides and print options the user already chose — and the validation
    those went through at creation time.
    """
    visibility = await require_queue_creation(db, access.user, access.api_key)
    current_user = visibility.user
    async with batch_dispatch_lock(db, batch_id):
        batch = await _load_batch_for_write(
            db, batch_id, current_user, visibility.printer_ids, Permission.QUEUE_UPDATE_ALL
        )
        if batch.status == "cancelled":
            raise HTTPException(400, "Cannot dispatch a cancelled batch")
        await _assert_can_dispatch_batch_sources(db, batch.id, visibility)
        try:
            created = await dispatch_remaining(
                db,
                batch,
                plate_id=data.plate_id,
                only_plate=data.only_plate,
                limit=data.limit,
                created_by_id=current_user.id if current_user else None,
            )
        except BatchDispatchError as exc:
            raise HTTPException(400, str(exc)) from exc

        await db.commit()
        await db.refresh(batch)

    logger.info("Batch %s dispatched %d item(s)", batch.id, len(created))
    await announce_queue_jobs_added([item.id for item in created])
    return await _build_batch_response(db, batch)


@router.post("/batches/{batch_id}/ungroup", response_model=PrintBatchUngroupResponse)
async def ungroup_batch(
    batch_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.QUEUE_UPDATE_OWN)),
):
    """Disband a batch: clear batch_id from all members and delete the batch row.

    Items stay in the queue. Only ungroups items the caller owns (unless they
    hold QUEUE_UPDATE_ALL). A batch with all members ungrouped is deleted.
    """
    result = await db.execute(select(PrintBatch).where(PrintBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(404, "Batch not found")

    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    current_user = visibility.user
    can_modify_all = current_user is None or current_user.has_permission(Permission.QUEUE_UPDATE_ALL.value)
    if not can_modify_all and batch.created_by_id != (current_user.id if current_user else None):
        raise HTTPException(404, "Batch not found")

    await _ensure_batch_in_scope(db, batch_id, visibility.printer_ids)
    result = await db.execute(select(PrintQueueItem).where(PrintQueueItem.batch_id == batch_id))
    items = result.scalars().all()
    ungrouped = 0
    remaining = 0
    for item in items:
        if not can_modify_all and item.created_by_id != (current_user.id if current_user else None):
            remaining += 1
            continue
        item.batch_id = None
        ungrouped += 1

    # Delete the batch row only when all members were ungrouped — otherwise it
    # still owns the items the caller couldn't touch.
    if remaining == 0:
        await db.delete(batch)

    await db.commit()

    logger.info("Ungrouped batch %s (%s items)", batch_id, ungrouped)
    return PrintBatchUngroupResponse(
        ungrouped_count=ungrouped,
        message=f"Ungrouped {ungrouped} item(s)",
    )


@router.get("/batches", response_model=list[PrintBatchResponse])
async def list_batches(
    status: str | None = Query(None, description="Filter by status (active, completed, cancelled)"),
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(
        require_ownership_permission(
            Permission.QUEUE_READ_ALL,
            Permission.QUEUE_READ_OWN,
            include_api_key=True,
        )
    ),
):
    """List print batches with progress stats.

    Batches with neither queue items nor per-plate targets are omitted. Those
    are empty shells — a grouping whose items were deleted with their source
    archive, or a create that never got as far as adding any — and they carry
    nothing to show, track or dispatch. A brand-new order is still listed
    before its first dispatch, because its targets say what it owes.
    """
    current_user, can_read_all, _ = access
    query = (
        select(PrintBatch)
        .where(
            select(PrintQueueItem.id).where(PrintQueueItem.batch_id == PrintBatch.id).exists()
            | select(PrintBatchPlate.id).where(PrintBatchPlate.batch_id == PrintBatch.id).exists()
        )
        .order_by(PrintBatch.created_at.desc())
    )
    if status:
        query = query.where(PrintBatch.status == status)
    if current_user is not None and not can_read_all:
        query = query.where(PrintBatch.created_by_id == current_user.id)
    if (scope := access.printer_ids) is not None:
        query = query.where(~batch_jobs_outside_printer_scope(PrintBatch.id, scope))
    result = await db.execute(query)
    batches = result.scalars().all()

    # Resolve creator names in one query rather than one per batch.
    creator_ids = {b.created_by_id for b in batches if b.created_by_id is not None}
    usernames: dict[int, str] = {}
    if creator_ids:
        rows = await db.execute(select(User.id, User.username).where(User.id.in_(creator_ids)))
        usernames = {row[0]: row[1] for row in rows.all()}

    return [await _build_batch_response(db, batch, usernames=usernames) for batch in batches]


@router.get("/batches/{batch_id}", response_model=PrintBatchResponse)
async def get_batch(
    batch_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(
        require_ownership_permission(
            Permission.QUEUE_READ_ALL,
            Permission.QUEUE_READ_OWN,
            include_api_key=True,
        )
    ),
):
    """Get a print batch with progress stats."""
    current_user, can_read_all, _ = access
    result = await db.execute(select(PrintBatch).where(PrintBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(404, "Batch not found")
    if (
        current_user is not None
        and not can_read_all
        and (batch.created_by_id is None or batch.created_by_id != current_user.id)
    ):
        raise HTTPException(404, "Batch not found")
    await _ensure_batch_in_scope(db, batch_id, access.printer_ids)
    return await _build_batch_response(db, batch)


@router.delete("/batches/{batch_id}")
async def cancel_batch(
    batch_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.QUEUE_DELETE_ALL)),
):
    """Cancel all pending items in a batch and mark batch as cancelled."""
    result = await db.execute(select(PrintBatch).where(PrintBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(404, "Batch not found")

    await _ensure_batch_in_scope(db, batch_id, access.printer_ids)
    # Cancel all pending queue items in this batch
    result = await db.execute(
        select(PrintQueueItem).where(and_(PrintQueueItem.batch_id == batch_id, PrintQueueItem.status == "pending"))
    )
    pending_items = result.scalars().all()
    cancelled_count = 0
    for item in pending_items:
        item.status = "cancelled"
        item.completed_at = datetime.now(timezone.utc)
        cancelled_count += 1

    batch.status = "cancelled"
    await db.commit()

    from backend.app.services.print_scheduler import scheduler

    for item in pending_items:
        scheduler.notify_dispatch_cancelled(item.id)
    return {"message": f"Batch cancelled, {cancelled_count} pending items cancelled"}


async def _build_batch_response(
    db: AsyncSession, batch: PrintBatch, *, usernames: dict[int, str] | None = None
) -> PrintBatchResponse:
    """Build a batch response with per-plate progress derived from queue items.

    ``usernames`` lets the list endpoint resolve every creator in one query
    instead of one per batch.
    """
    progress = await load_progress(db, batch)

    created_by_username = None
    if batch.created_by_id:
        if usernames is not None:
            created_by_username = usernames.get(batch.created_by_id)
        else:
            result = await db.execute(select(User).where(User.id == batch.created_by_id))
            user = result.scalar_one_or_none()
            if user:
                created_by_username = user.username

    return PrintBatchResponse(
        id=batch.id,
        name=batch.name,
        archive_id=batch.archive_id,
        library_file_id=batch.library_file_id,
        quantity=batch.quantity,
        status=batch.status,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
        created_by_id=batch.created_by_id,
        created_by_username=created_by_username,
        project_id=batch.project_id,
        due_date=batch.due_date,
        notes=batch.notes,
        pending_count=progress.pending,
        printing_count=progress.printing,
        completed_count=progress.completed,
        accepted_count=progress.accepted,
        unconfirmed_count=progress.unconfirmed,
        rejected_count=progress.rejected,
        good_quantity=progress.good_quantity,
        reject_quantity=progress.reject_quantity,
        failed_count=progress.failed,
        cancelled_count=progress.cancelled,
        skipped_count=progress.skipped,
        has_targets=progress.has_targets,
        target_count=progress.target,
        remaining_count=progress.remaining,
        dispatchable_count=progress.dispatchable_remaining,
        actual_cost=progress.actual_cost,
        estimated_remaining_cost=progress.estimated_remaining_cost,
        filament_used_grams=progress.filament_used_grams,
        print_time_seconds=progress.print_time_seconds,
        plates=[
            PrintBatchPlateProgress(
                plate_id=plate.plate_id,
                plate_name=plate.plate_name,
                quantity_target=plate.quantity_target,
                dispatched=plate.dispatched,
                remaining=plate.remaining,
                pending_count=plate.pending,
                printing_count=plate.printing,
                completed_count=plate.completed,
                accepted_count=plate.accepted,
                unconfirmed_count=plate.unconfirmed,
                rejected_count=plate.rejected,
                good_quantity=plate.good_quantity,
                reject_quantity=plate.reject_quantity,
                failed_count=plate.failed,
                cancelled_count=plate.cancelled,
                skipped_count=plate.skipped,
                actual_cost=plate.actual_cost,
                estimated_remaining_cost=plate.estimated_remaining_cost,
                filament_used_grams=plate.filament_used_grams,
                print_time_seconds=plate.print_time_seconds,
                can_dispatch=plate.can_dispatch,
            )
            for plate in progress.plates
        ],
    )


@router.get("/{item_id}", response_model=PrintQueueItemResponse)
async def get_queue_item(
    item_id: int,
    db: AsyncSession = DB_SESSION,
    auth_result: tuple[User | None, bool] = Depends(
        require_ownership_permission(
            Permission.QUEUE_READ_ALL,
            Permission.QUEUE_READ_OWN,
        )
    ),
):
    """Get a specific queue item."""
    current_user, can_read_all = auth_result
    result = await db.execute(
        select(PrintQueueItem)
        .options(
            selectinload(PrintQueueItem.archive),
            selectinload(PrintQueueItem.printer),
            selectinload(PrintQueueItem.library_file),
            selectinload(PrintQueueItem.created_by),
            selectinload(PrintQueueItem.batch),
            # Cross-model candidates (#671) and their files, for the card label.
            selectinload(PrintQueueItem.variants).selectinload(PrintQueueVariant.library_file),
        )
        .where(PrintQueueItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Queue item not found")
    if (
        current_user is not None
        and not can_read_all
        and (item.created_by_id is None or item.created_by_id != current_user.id)
    ):
        raise HTTPException(404, "Queue item not found")
    if not user_can_access_printer(current_user, item.printer_id):
        raise HTTPException(404, "Queue item not found")
    return _enrich_response(item)


@router.patch("/{item_id}", response_model=PrintQueueItemResponse)
async def update_queue_item(
    item_id: int,
    data: PrintQueueItemUpdate,
    db: AsyncSession = DB_SESSION,
    auth_result: tuple[User | None, bool] = Depends(
        require_ownership_permission(
            Permission.QUEUE_UPDATE_ALL,
            Permission.QUEUE_UPDATE_OWN,
        )
    ),
):
    """Update a queue item."""
    user, can_modify_all = auth_result

    result = await db.execute(
        select(PrintQueueItem)
        # Needed by the cross-model guard below, and by the response builder —
        # without it _variant_summaries falls back to [] and a PATCH would strip
        # the alternatives out of the payload it echoes back.
        .options(selectinload(PrintQueueItem.variants).selectinload(PrintQueueVariant.library_file))
        .where(PrintQueueItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Queue item not found")

    # Ownership check
    if not can_modify_all:
        if item.created_by_id != user.id:
            raise HTTPException(403, "You can only update your own queue items")
    _ensure_queue_printer_access(user, item)

    if item.status != "pending":
        raise HTTPException(400, "Can only update pending items")

    if item.dispatching_at is not None:
        raise HTTPException(409, "Item is being dispatched; cancel it first to make changes")

    update_data = data.model_dump(exclude_unset=True)

    # Normalize target_model if being updated (see add_to_queue for why the
    # code map has to run first).
    if "target_model" in update_data and update_data["target_model"]:
        update_data["target_model"] = normalize_model_name(update_data["target_model"])

    # A cross-model item (#671) owns its own printer decision: each candidate
    # carries its model, and the resolver folds the winner onto the row at
    # dispatch. Assigning a printer here would leave a row with variants *and* a
    # printer_id, and the fixed-printer branch of the scheduler wins that race —
    # so it would dispatch a row whose library_file_id is still null and die in
    # the upload. Narrowing target_model is refused for the same reason: it
    # would silently discard every alternative the user queued.
    #
    # Compared against the current value rather than merely present, because the
    # edit dialog re-sends target_model unchanged on every save.
    if item.variants:
        for field in ("printer_id", "target_model"):
            if field in update_data and update_data[field] != getattr(item, field):
                raise HTTPException(
                    400,
                    "This job has printer alternatives — remove them before assigning a printer or model",
                )

    # Cannot specify both printer_id and target_model
    new_printer_id = update_data.get("printer_id", item.printer_id)
    new_target_model = update_data.get("target_model", item.target_model)
    if new_printer_id and new_target_model:
        raise HTTPException(400, "Cannot specify both printer_id and target_model")

    # Validate new printer_id if being changed (and not None)
    new_printer_model = None
    if "printer_id" in update_data and update_data["printer_id"] is not None:
        result = await db.execute(select(Printer).where(Printer.id == update_data["printer_id"]))
        new_printer = result.scalar_one_or_none()
        if new_printer is None:
            raise HTTPException(400, "Printer not found")
        if not user_can_access_printer(user, new_printer.id):
            raise HTTPException(404, "Printer not found")
        new_printer_model = new_printer.model

    # Validate target_model using the same case-insensitive spelling as dispatch.
    if "target_model" in update_data and update_data["target_model"]:
        active_model = await active_printer_model(db, update_data["target_model"])
        if active_model is None:
            raise HTTPException(400, f"No active printers for model: {update_data['target_model']}")
        update_data["target_model"] = active_model

    target_hardware_model = new_target_model or new_printer_model
    if target_hardware_model:
        sliced_for = None
        if item.archive_id:
            result = await db.execute(select(PrintArchive.sliced_for_model).where(PrintArchive.id == item.archive_id))
            sliced_for = result.scalar_one_or_none()
        elif item.library_file_id:
            result = await db.execute(select(LibraryFile).where(LibraryFile.id == item.library_file_id))
            library_file = result.scalar_one_or_none()
            if library_file and library_file.file_metadata:
                value = library_file.file_metadata.get("sliced_for_model")
                sliced_for = str(value) if value else None
        if not is_gcode_compatible(sliced_for, target_hardware_model):
            raise HTTPException(
                400,
                f"File was sliced for {sliced_for} and cannot be dispatched to {target_hardware_model} printers",
            )

    # A new printer has different trays and nozzles. Explicit values supplied
    # for that printer win; unresolved values must be recomputed at dispatch.
    if item.printer_id is not None and new_printer_id != item.printer_id:
        for field, default in PRINTER_RESOLVED_DEFAULTS.items():
            update_data.setdefault(field, default)

    if new_target_model and not new_printer_id:
        update_data["ams_mapping"] = None

    # Serialize ams_mapping to JSON for TEXT column storage
    if "ams_mapping" in update_data:
        update_data["ams_mapping"] = json.dumps(update_data["ams_mapping"]) if update_data["ams_mapping"] else None

    # Serialize filament_overrides to JSON for TEXT column storage
    if "filament_overrides" in update_data:
        overrides = update_data["filament_overrides"]
        if overrides:
            overrides = overrides_for_plate(
                overrides,
                await _resolve_source_path(db, item),
                update_data.get("plate_id", item.plate_id),
            )
        update_data["filament_overrides"] = json.dumps(overrides) if overrides else None

    # Serialize H2C rack-swap nozzle pick (#1780) to JSON for TEXT column
    # storage; same Text-as-opaque-blob convention as ams_mapping above.
    if "nozzle_mapping" in update_data:
        update_data["nozzle_mapping"] = (
            json.dumps(update_data["nozzle_mapping"]) if update_data["nozzle_mapping"] else None
        )

    if "plate_id" in update_data and update_data["plate_id"] != item.plate_id:
        archive = await db.get(PrintArchive, item.archive_id) if item.archive_id else None
        library_file = await db.get(LibraryFile, item.library_file_id) if item.library_file_id else None
        update_data["print_time_seconds"], _ = queue_source_estimate(
            archive, library_file, update_data["plate_id"], settings.base_dir
        )

    if update_data:
        conditions = [
            PrintQueueItem.id == item_id,
            PrintQueueItem.status == "pending",
            PrintQueueItem.dispatching_at.is_(None),
        ]
        if not can_modify_all:
            conditions.append(PrintQueueItem.created_by_id == user.id)

        result = await db.execute(update(PrintQueueItem).where(*conditions).values(**update_data))
        if not result.rowcount:
            await db.rollback()
            raise HTTPException(409, "Item is being dispatched; cancel it first to make changes")

        await db.commit()
    result = await db.execute(
        select(PrintQueueItem)
        .options(
            selectinload(PrintQueueItem.archive),
            selectinload(PrintQueueItem.printer),
            selectinload(PrintQueueItem.library_file),
            selectinload(PrintQueueItem.created_by),
            selectinload(PrintQueueItem.batch),
        )
        .where(PrintQueueItem.id == item_id)
    )
    item = result.scalar_one()

    logger.info("Updated queue item %s", item_id)
    return _enrich_response(item)


@router.delete("/{item_id}")
async def delete_queue_item(
    item_id: int,
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(
        require_ownership_permission(Permission.QUEUE_DELETE_ALL, Permission.QUEUE_DELETE_OWN, include_api_key=True)
    ),
):
    """Remove an item from the queue."""
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    item = await db.scalar(
        select(PrintQueueItem).where(
            PrintQueueItem.id == item_id, *visibility.printer_criteria(PrintQueueItem.printer_id)
        )
    )
    if item is None:
        raise HTTPException(404, "Queue item not found")
    if not visibility.can_access_owner(item.created_by_id, Permission.QUEUE_DELETE_ALL, Permission.QUEUE_DELETE_OWN):
        raise HTTPException(403, "You can only delete your own queue items")

    if item.status == "printing":
        raise HTTPException(400, "Cannot delete item that is currently printing")

    removal = await delete_or_retain_queue_item(db, item)

    logger.info("Queue item %s removal result: deleted=%s", item_id, removal["deleted"])
    return removal


@router.post("/reorder")
async def reorder_queue(
    data: PrintQueueReorder,
    db: AsyncSession = DB_SESSION,
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_UPDATE_ALL),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
):
    """Merge a visible subset's order into its existing global queue slots."""
    await reorder_queue_positions(db, data.items, current_user, api_key)

    await db.commit()
    logger.info("Reordered %s queue items", len(data.items))
    return {"message": f"Reordered {len(data.items)} items"}


@router.post("/printer/{printer_id}/resume")
async def resume_queue_after_failure(
    printer_id: int,
    db: AsyncSession = DB_SESSION,
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_UPDATE_ALL),
):
    """Clear the previous-success gate for a printer and restore skipped items.

    Single atomic op (#1818):

    * Sets ``gate_acknowledged=True`` on every ``failed`` / ``aborted`` queue
      item for this printer that's still in the scheduler's lookback window,
      so the next ``_check_previous_success`` call ignores them.
    * Restores ``skipped`` items whose ``error_message`` matches the
      scheduler's exact "Previous print failed or was aborted" gate string
      back to ``pending`` (clears ``error_message`` + ``completed_at``).

    Returns counts so the UI can render a precise toast. No-op endpoint
    (zero counts) when called against a printer with no gate to clear.
    """
    result = await db.execute(select(Printer).where(Printer.id == printer_id))
    printer = result.scalar_one_or_none()
    if not printer:
        raise HTTPException(404, "Printer not found")
    if not user_can_access_printer(current_user, printer.id):
        raise HTTPException(404, "Printer not found")

    return await resume_printers(db, [printer_id], restore_skipped=True)


@router.post("/model/{model}/resume")
async def resume_model_queue_after_failure(
    model: str,
    db: AsyncSession = DB_SESSION,
    current_user: User | None = RequirePermissionIfAuthEnabled(Permission.QUEUE_UPDATE_ALL),
    api_key: APIKey | None = Depends(resolve_optional_api_key),
):
    """Clear predecessor failures on the model's printers the caller may use."""
    return await resume_model(db, model, current_user, api_key)


@router.post("/{item_id}/cancel")
async def cancel_queue_item(
    item_id: int,
    db: AsyncSession = DB_SESSION,
    auth_result: tuple[User | None, bool] = Depends(
        require_ownership_permission(
            Permission.QUEUE_UPDATE_ALL,
            Permission.QUEUE_UPDATE_OWN,
        )
    ),
):
    """Cancel a pending queue item."""
    user, can_modify_all = auth_result

    result = await db.execute(select(PrintQueueItem).where(PrintQueueItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Queue item not found")

    # Ownership check
    if not can_modify_all:
        if item.created_by_id != user.id:
            raise HTTPException(403, "You can only cancel your own queue items")
    _ensure_queue_printer_access(user, item)

    if item.status not in ("pending",):
        raise HTTPException(400, f"Cannot cancel item with status '{item.status}'")

    item.status = "cancelled"
    item.completed_at = datetime.now(timezone.utc)
    await db.commit()

    from backend.app.services.print_scheduler import scheduler

    scheduler.notify_dispatch_cancelled(item_id)
    await refresh_batches_after([item_id])
    logger.info("Cancelled queue item %s", item_id)
    return {"message": "Queue item cancelled"}


@router.post("/{item_id}/stop")
async def stop_queue_item(
    item_id: int,
    db: AsyncSession = DB_SESSION,
    auth_result: tuple[User | None, bool] = Depends(
        require_ownership_permission(
            Permission.QUEUE_UPDATE_ALL,
            Permission.QUEUE_UPDATE_OWN,
        )
    ),
):
    """Stop an actively printing queue item.

    Ownership-scoped (#1625-followup): callers with QUEUE_UPDATE_OWN can stop
    their own items; callers with QUEUE_UPDATE_ALL can stop any item. Mirrors
    the /cancel shape. Pre-fix this required QUEUE_UPDATE_ALL — Operators
    holding only _OWN saw the Stop button in the queue UI but got 403 on click.
    """

    from backend.app.services.print_control import stop_print_by_user

    user, can_modify_all = auth_result

    result = await db.execute(select(PrintQueueItem).where(PrintQueueItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Queue item not found")

    # Ownership check — mirrors /cancel. Ownerless items (created_by_id IS NULL)
    # require _ALL: stop is destructive and an _OWN holder can't claim "they
    # own it" the way /start does (#1670).
    if not can_modify_all and user is not None:
        if item.created_by_id is None or item.created_by_id != user.id:
            raise HTTPException(403, "You can only stop your own queue items")
    _ensure_queue_printer_access(user, item)

    if item.status != "printing":
        raise HTTPException(400, f"Can only stop items that are printing, current status: '{item.status}'")

    # Capture values we need for background task
    printer_id = item.printer_id
    auto_off_after = item.auto_off_after

    # Try to send stop command to printer
    stop_sent = False
    try:
        stop_sent = printer_id is not None and stop_print_by_user(printer_id, mark_when_unsent=True)
        if not stop_sent:
            logger.warning("stop_print returned False for printer %s - printer may not be connected", printer_id)
    except Exception as e:
        logger.error("Error sending stop command for queue item %s: %s", item_id, e)

    # Update queue item status regardless - if printer is off, print is already stopped
    item.status = "cancelled"
    item.completed_at = datetime.now(timezone.utc)
    item.error_message = "Stopped by user" if stop_sent else "Stopped by user (printer was offline)"
    offline_run, archive_status = None, None
    if not stop_sent:
        from backend.app.services.offline_queue_stop import record_offline_stop

        offline_run, archive_status = await record_offline_stop(db, item)
    await db.commit()
    if offline_run is not None:
        from backend.app.core.websocket import ws_manager
        from backend.app.services.mqtt_relay import mqtt_relay

        if archive_status is not None:
            await ws_manager.send_archive_updated({"id": offline_run.archive_id, "status": archive_status})
        await mqtt_relay.on_run_event("completed", offline_run, await db.get(Printer, printer_id))

    if not stop_sent:
        from backend.app.services.print_scheduler import scheduler

        scheduler.notify_dispatch_cancelled(item_id)
    await refresh_batches_after([item_id])
    logger.info("Stopped printing queue item %s (stop command sent: %s)", item_id, stop_sent)

    # Schedule power-off if the queue item opted in. Delegates to the smart-plug
    # manager so the off honours each plug's configured strategy (time delay or
    # temperature threshold), is cancelled if the printer starts printing again,
    # and never cuts power on a loaded print (#1890). Previously an inline block
    # hardcoded a 50°C / 600s cooldown wait and powered off on the timeout
    # regardless of print state.
    if auto_off_after:
        from backend.app.services.smart_plug_manager import smart_plug_manager

        try:
            await smart_plug_manager.schedule_off_after_queue_job(printer_id, db)
        except Exception as e:
            logger.warning("Auto-off: Failed to schedule power-off for printer %s: %s", printer_id, e)

    return {"message": "Print stopped" if stop_sent else "Queue item cancelled (printer was offline)"}


@router.post("/{item_id}/start")
async def start_queue_item(
    item_id: int,
    skip_filament_check: bool = Query(default=False),
    db: AsyncSession = DB_SESSION,
    auth_result: tuple[User | None, bool] = Depends(
        require_ownership_permission(
            Permission.QUEUE_UPDATE_ALL,
            Permission.QUEUE_UPDATE_OWN,
        )
    ),
):
    """Manually start a staged (manual_start) queue item.

    Ownership-scoped (#1625-followup): callers with QUEUE_UPDATE_OWN can
    start their own items + claim ownership of NULL-owner items (VP-uploaded
    items arrive unattributed per #1670). Callers with QUEUE_UPDATE_ALL can
    start any item. Pre-fix this required QUEUE_UPDATE_OWN with no ownership
    check, so _OWN holders could start anyone's queue items via direct API.

    Clears the manual_start flag so the scheduler picks it up. When
    ``skip_filament_check`` is false (the default) the live filament
    deficit (#1496) is checked first — if the assigned spool can't satisfy
    a slot's required grams, the route returns ``409`` with the deficit
    payload so the caller can show a confirm dialog and retry with
    ``skip_filament_check=true``. The same goes for a filament the printer has
    no tray for at all (#2799): ``409`` with ``code=unmatched_filament`` and
    the missing filaments.
    """
    user, can_modify_all = auth_result

    result = await db.execute(
        select(PrintQueueItem)
        .options(
            selectinload(PrintQueueItem.archive),
            selectinload(PrintQueueItem.printer),
            selectinload(PrintQueueItem.library_file),
            selectinload(PrintQueueItem.batch),
            selectinload(PrintQueueItem.variants).selectinload(PrintQueueVariant.library_file),
        )
        .where(PrintQueueItem.id == item_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Queue item not found")

    # Ownership check — softer than /cancel because /start is the entry point
    # for #1670's VP-import flow: an unowned item is claimable by the first
    # _OWN holder who clicks ▶, and the route below credits them as owner.
    # An item with a DIFFERENT owner → 403.
    if not can_modify_all and user is not None:
        if item.created_by_id is not None and item.created_by_id != user.id:
            raise HTTPException(403, "You can only start your own queue items")
    _ensure_queue_printer_access(user, item)

    if item.status != "pending":
        raise HTTPException(400, f"Can only start pending items, current status: '{item.status}'")

    # Live deficit check — re-evaluated against current spool state, so a
    # spool swap between scheduler flagging and the user clicking ▶ clears
    # the block automatically.
    if not skip_filament_check:
        deficit = await compute_deficit_for_queue_item(db, item)
        if deficit:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "insufficient_filament",
                    "deficit": [d.to_dict() for d in deficit],
                },
            )

        await check_missing_start_filament(db, item)

    # Print Anyway / no deficit: clear the flags and let the scheduler dispatch.
    item.manual_start = False
    item.filament_short = False
    # Persist the user's "Print Anyway" decision so the scheduler does not
    # immediately re-flag this item on the next tick (#1698-followup). The
    # pre-fix behaviour bounced between "user said anyway" and
    # "scheduler re-blocked on same deficit" forever.
    if skip_filament_check:
        item.skip_filament_check = True
    # Credit the clicker as the item's owner when no prior owner is set —
    # VP-uploaded queue items arrive over FTP unattributed, so without this
    # the print log's User column stays blank even when auth is on
    # (#1670). An item that already has a creator (UI-added queue items)
    # keeps that attribution; the dispatcher is not promoted over the
    # original uploader.
    if user is not None and item.created_by_id is None:
        item.created_by_id = user.id
    await db.commit()
    await db.refresh(item, ["archive", "printer", "library_file", "created_by", "batch"])

    logger.info(
        "Manually started queue item %s (cleared manual_start; skip_filament_check=%s)",
        item_id,
        skip_filament_check,
    )
    return _enrich_response(item)
