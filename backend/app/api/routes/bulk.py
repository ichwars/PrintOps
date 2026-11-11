"""Coalesce the per-card reads used by fleet and archive views."""

from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.cloud import resolve_api_key_cloud_owner
from backend.app.api.routes.firmware import FirmwareUpdateInfo, printer_firmware_update
from backend.app.api.routes.ha_sensors import card_sensors, serialize_sensor_reading
from backend.app.api.routes.print_queue import enrich_queue_items, queue_read_query
from backend.app.api.routes.printers_ams import read_ams_labels
from backend.app.api.routes.printers_operations import serialize_slot_presets
from backend.app.api.routes.printers_status import build_printer_status, printer_cloud_configured
from backend.app.api.routes.smart_plugs import _plug_response, card_script_plugs
from backend.app.core.auth import (
    OwnershipAccess,
    caller_is_api_key,
    require_ownership_permission,
    require_permission_with_key,
)
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import RowVisibility, resolve_printer_visibility, resolve_row_visibility
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.slot_preset import SlotPresetMapping
from backend.app.models.smart_plug import SmartPlug
from backend.app.models.user import User
from backend.app.schemas.library import FolderResponse
from backend.app.schemas.print_queue import PrintQueueItemResponse
from backend.app.schemas.printer import PrinterStatus
from backend.app.schemas.printer_ha_sensor import PrinterHASensorReading
from backend.app.schemas.smart_plug import SmartPlugResponse
from backend.app.services.library_archive_folders import read_archive_folders
from backend.app.services.smart_plug_selection import pick_power_plug, rank_power_plugs

router = APIRouter(prefix="/bulk", tags=["bulk"])

_PRINTERS_READ = Depends(require_permission_with_key(Permission.PRINTERS_READ))
_PLUGS_READ = Depends(require_permission_with_key(Permission.SMART_PLUGS_READ))
_FIRMWARE_READ = Depends(require_permission_with_key(Permission.FIRMWARE_READ))
_QUEUE_READ = Depends(
    require_ownership_permission(Permission.QUEUE_READ_ALL, Permission.QUEUE_READ_OWN, include_api_key=True)
)
_LIBRARY_READ = Depends(
    require_ownership_permission(Permission.LIBRARY_READ_ALL, Permission.LIBRARY_READ_OWN, include_api_key=True)
)


def _parse_ids(ids: str = Query(max_length=5500)) -> list[int]:
    result: dict[int, None] = {}
    for value in ids.split(","):
        value = value.strip()
        if not value:
            continue
        if len(value) > 10 or not value.isascii() or not value.isdecimal() or not 0 < int(value) <= 2**31 - 1:
            raise HTTPException(422, "Expected a list of positive database ids")
        result[int(value)] = None
    if len(result) > 500:
        raise HTTPException(422, "At most 500 ids per request")
    return list(result)


BulkIds = Annotated[list[int], Depends(_parse_ids)]


async def _printers(db: AsyncSession, visibility: RowVisibility, ids: list[int]) -> dict[int, Printer]:
    wanted = [printer_id for printer_id in ids if visibility.allows_printer(printer_id)]
    if not wanted:
        return {}
    found = {p.id: p for p in await db.scalars(select(Printer).where(Printer.id.in_(wanted)))}
    return {printer_id: found[printer_id] for printer_id in wanted if printer_id in found}


@router.get("/printer-statuses", response_model=list[PrinterStatus])
async def get_printer_statuses(
    ids: BulkIds,
    access: OwnershipAccess = _PRINTERS_READ,
    cloud_owner: User | None = Depends(resolve_api_key_cloud_owner),
    db: AsyncSession = DB_SESSION,
):
    visibility = await resolve_printer_visibility(db, access, Permission.PRINTERS_READ)
    printers = await _printers(db, visibility, ids)
    if not printers:
        return []
    cloud_configured = await printer_cloud_configured(db, visibility, cloud_owner)
    return [await build_printer_status(db, printer, cloud_configured) for printer in printers.values()]


@router.get("/slot-presets")
async def get_slot_presets(ids: BulkIds, access: OwnershipAccess = _PRINTERS_READ, db: AsyncSession = DB_SESSION):
    visibility = await resolve_printer_visibility(db, access, Permission.PRINTERS_READ)
    printers = await _printers(db, visibility, ids)
    mappings: dict[int, list[SlotPresetMapping]] = {printer_id: [] for printer_id in printers}
    if mappings:
        for mapping in await db.scalars(select(SlotPresetMapping).where(SlotPresetMapping.printer_id.in_(mappings))):
            mappings[mapping.printer_id].append(mapping)
    return {printer_id: serialize_slot_presets(slots) for printer_id, slots in mappings.items()}


@router.get("/ams-labels", response_model=dict[int, dict[int, str]])
async def get_ams_labels(ids: BulkIds, access: OwnershipAccess = _PRINTERS_READ, db: AsyncSession = DB_SESSION):
    visibility = await resolve_printer_visibility(db, access, Permission.PRINTERS_READ)
    printers = await _printers(db, visibility, ids)
    return {printer_id: await read_ams_labels(db, printer_id) for printer_id in printers}


class PrinterCardPlugs(BaseModel):
    plug: SmartPlugResponse | None
    scripts: list[SmartPlugResponse]


@router.get("/card-plugs", response_model=dict[int, PrinterCardPlugs])
async def get_card_plugs(
    ids: BulkIds,
    access: OwnershipAccess = _PLUGS_READ,
    is_api_key: bool = Depends(caller_is_api_key),
    db: AsyncSession = DB_SESSION,
):
    visibility = await resolve_printer_visibility(db, access, Permission.SMART_PLUGS_READ)
    printers = await _printers(db, visibility, ids)
    grouped: dict[int, list[SmartPlug]] = {printer_id: [] for printer_id in printers}
    if grouped:
        for plug in await db.scalars(select(SmartPlug).where(SmartPlug.printer_id.in_(grouped))):
            grouped[plug.printer_id].append(plug)
    cards: dict[int, PrinterCardPlugs] = {}
    for printer_id, plugs in grouped.items():
        main = pick_power_plug(plugs)
        cards[printer_id] = PrinterCardPlugs(
            plug=_plug_response(main, visibility.user, is_api_key) if main else None,
            scripts=card_script_plugs(rank_power_plugs(plugs), visibility.user, is_api_key),
        )
    return cards


@router.get("/ha-sensor-readings", response_model=dict[int, list[PrinterHASensorReading]])
async def get_ha_readings(ids: BulkIds, access: OwnershipAccess = _PLUGS_READ, db: AsyncSession = DB_SESSION):
    visibility = await resolve_printer_visibility(db, access, Permission.SMART_PLUGS_READ)
    printers = await _printers(db, visibility, ids)
    grouped: dict[int, list[PrinterHASensorReading]] = {printer_id: [] for printer_id in printers}
    if grouped:
        for sensor in await card_sensors(db, list(grouped)):
            grouped[sensor.printer_id].append(serialize_sensor_reading(sensor))
    return grouped


@router.get("/firmware-updates", response_model=list[FirmwareUpdateInfo])
async def get_firmware_updates(ids: BulkIds, access: OwnershipAccess = _FIRMWARE_READ, db: AsyncSession = DB_SESSION):
    visibility = await resolve_printer_visibility(db, access, Permission.FIRMWARE_READ)
    printers = await _printers(db, visibility, ids)
    return [await printer_firmware_update(printer) for printer in printers.values()]


@router.get("/printer-queues", response_model=dict[int, list[PrintQueueItemResponse]])
async def get_printer_queues(
    ids: BulkIds, status: str | None = Query(None), access: OwnershipAccess = _QUEUE_READ, db: AsyncSession = DB_SESSION
):
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    printers = await _printers(db, visibility, ids)
    grouped: dict[int, list[PrintQueueItemResponse]] = {printer_id: [] for printer_id in printers}
    if not grouped:
        return grouped
    by_model: dict[str, list[int]] = defaultdict(list)
    for printer in printers.values():
        if printer.model:
            by_model[printer.model.lower()].append(printer.id)

    query = (
        queue_read_query(visibility)
        .where(
            or_(
                PrintQueueItem.printer_id.in_(grouped),
                and_(PrintQueueItem.printer_id.is_(None), func.lower(PrintQueueItem.target_model).in_(by_model)),
            )
        )
        .order_by(PrintQueueItem.position, PrintQueueItem.id)
    )
    if status:
        query = query.where(PrintQueueItem.status.in_([value.strip() for value in status.split(",") if value.strip()]))
    items = (await db.scalars(query)).all()
    responses = await enrich_queue_items(db, items)
    for item, response in zip(items, responses, strict=True):
        if item.printer_id is not None:
            grouped[item.printer_id].append(response)
        elif item.target_model:
            for printer_id in by_model.get(item.target_model.lower(), ()):
                grouped[printer_id].append(response)
    return grouped


@router.get("/archive-folders", response_model=dict[int, list[FolderResponse]])
async def get_archive_folders(ids: BulkIds, access: OwnershipAccess = _LIBRARY_READ, db: AsyncSession = DB_SESSION):
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    return await read_archive_folders(db, visibility, ids)
