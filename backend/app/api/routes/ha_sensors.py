"""API routes for Home Assistant sensors bound to a printer (#1148, #448)."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.printer import Printer
from backend.app.models.printer_ha_sensor import PrinterHAInterlockAudit, PrinterHASensor
from backend.app.models.user import User
from backend.app.schemas.printer_ha_sensor import (
    HADisplayEntity,
    PrinterHAInterlockAuditResponse,
    PrinterHAInterlockOverrideStatus,
    PrinterHASensorCreate,
    PrinterHASensorReading,
    PrinterHASensorResponse,
    PrinterHASensorUpdate,
)
from backend.app.services.ha_sensor_manager import ha_sensor_manager
from backend.app.services.homeassistant import homeassistant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ha-sensors", tags=["ha-sensors"])

# These reuse the smart-plug permissions rather than introducing their own.
# Both surfaces are "the Home Assistant integration", and a brand-new
# permission would be missing from every existing custom role — users who can
# manage plugs today would silently lose access to the sensors next to them.
_READ = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_READ)
_CREATE = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_CREATE)
_UPDATE = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_UPDATE)
_DELETE = RequirePermissionIfAuthEnabled(Permission.SMART_PLUGS_DELETE)
_OVERRIDE = RequirePermissionIfAuthEnabled(Permission.QUEUE_UPDATE_ALL)


class InterlockOverrideRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


async def _override_status(printer_id: int, db: AsyncSession) -> PrinterHAInterlockOverrideStatus:
    current = ha_sensor_manager.get_interlock_override(printer_id)
    return PrinterHAInterlockOverrideStatus(
        printer_id=printer_id,
        overridden=current is not None,
        username=current.username if current else None,
        reason=current.reason if current else None,
        created_at=current.created_at if current else None,
        overrideable_sensors=await ha_sensor_manager.overrideable_sensor_names(db, printer_id),
    )


async def _refresh_quietly(sensor: PrinterHASensor, db: AsyncSession) -> None:
    """Take a first reading without letting it fail the write that preceded it.

    The sensor row is committed before this runs. A failure here costs the card
    one poll interval of blank state, which is not worth turning a successful
    save into an error response.
    """
    try:
        await ha_sensor_manager.refresh_one(db, sensor)
    except Exception as e:
        logger.warning("Could not read %s right after saving it: %s", sensor.entity_id, e)


async def _stage_override_revocation(
    db: AsyncSession,
    *,
    printer_id: int,
    user: User | None,
    change: str,
) -> bool:
    """Add durable evidence before a sensor mutation revokes a live bypass."""
    current = ha_sensor_manager.get_interlock_override(printer_id)
    if current is None:
        return False
    printer = await db.get(Printer, printer_id)
    reason = f"{current.reason} [auto-revoked: {change}]"[:500]
    db.add(
        PrinterHAInterlockAudit(
            printer_id=printer_id,
            printer_name=printer.name if printer else f"Printer {printer_id}",
            username=user.username if user else "anonymous",
            action="cleared",
            reason=reason,
        )
    )
    return True


@router.get("/", response_model=list[PrinterHASensorResponse])
async def list_ha_sensors(
    printer_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User | None = _READ,
):
    """List configured sensors, grouped by printer and in display order."""
    query = select(PrinterHASensor)
    if printer_id is not None:
        query = query.where(PrinterHASensor.printer_id == printer_id)
    result = await db.execute(query.order_by(PrinterHASensor.printer_id, PrinterHASensor.sort_order))
    return list(result.scalars().all())


# Must precede /{sensor_id} so "entities" is not parsed as an id.
@router.get("/entities", response_model=list[HADisplayEntity])
async def list_bindable_entities(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User | None = _READ,
):
    """List the Home Assistant entities that can be bound to a printer."""
    from backend.app.api.routes.settings import get_homeassistant_settings

    ha_settings = await get_homeassistant_settings(db)
    if not ha_settings["ha_url"] or not ha_settings["ha_token"]:
        raise HTTPException(
            400,
            "Home Assistant not configured. Please set HA URL and token in Settings → Network → Home Assistant.",
        )

    entities = await homeassistant_service.list_display_entities(ha_settings["ha_url"], ha_settings["ha_token"], search)
    return [HADisplayEntity(**e) for e in entities]


@router.get(
    "/printers/{printer_id}/interlock-override",
    response_model=PrinterHAInterlockOverrideStatus,
)
async def get_printer_interlock_override(
    printer_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = _READ,
):
    if await db.get(Printer, printer_id) is None:
        raise HTTPException(404, "Printer not found")
    return await _override_status(printer_id, db)


@router.get(
    "/printers/{printer_id}/interlock-audit",
    response_model=list[PrinterHAInterlockAuditResponse],
)
async def get_printer_interlock_audit(
    printer_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = _OVERRIDE,
):
    result = await db.execute(
        select(PrinterHAInterlockAudit)
        .where(PrinterHAInterlockAudit.printer_id == printer_id)
        .order_by(PrinterHAInterlockAudit.created_at.desc(), PrinterHAInterlockAudit.id.desc())
    )
    return list(result.scalars().all())


@router.post(
    "/printers/{printer_id}/interlock-override",
    response_model=PrinterHAInterlockOverrideStatus,
)
async def override_printer_interlock(
    printer_id: int,
    data: InterlockOverrideRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = _OVERRIDE,
):
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(404, "Printer not found")
    overrideable = await ha_sensor_manager.overrideable_sensor_names(db, printer_id)
    if not overrideable:
        raise HTTPException(409, "No unavailable fail-closed interlock can be overridden")
    username = user.username if user else "anonymous"
    db.add(
        PrinterHAInterlockAudit(
            printer_id=printer_id,
            printer_name=printer.name,
            username=username,
            action="enabled",
            reason=data.reason,
        )
    )
    await db.commit()
    ha_sensor_manager.set_interlock_override(printer_id, username=username, reason=data.reason)
    logger.warning(
        "HA_INTERLOCK_OVERRIDE user=%s printer_id=%s reason=%s",
        username,
        printer_id,
        data.reason,
    )
    return await _override_status(printer_id, db)


@router.delete(
    "/printers/{printer_id}/interlock-override",
    response_model=PrinterHAInterlockOverrideStatus,
)
async def clear_printer_interlock_override(
    printer_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = _OVERRIDE,
):
    printer = await db.get(Printer, printer_id)
    if printer is None:
        raise HTTPException(404, "Printer not found")
    current = ha_sensor_manager.get_interlock_override(printer_id)
    if current:
        db.add(
            PrinterHAInterlockAudit(
                printer_id=printer_id,
                printer_name=printer.name,
                username=user.username if user else "anonymous",
                action="cleared",
                reason=current.reason,
            )
        )
        await db.commit()
        ha_sensor_manager.clear_interlock_override(printer_id)
    logger.warning(
        "HA_INTERLOCK_OVERRIDE_CLEARED user=%s printer_id=%s",
        user.username if user else "anonymous",
        printer_id,
    )
    return await _override_status(printer_id, db)


@router.get("/by-printer/{printer_id}/readings", response_model=list[PrinterHASensorReading])
async def get_printer_sensor_readings(
    printer_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = _READ,
):
    """Live state of a printer's card-visible sensors.

    Served from the poller's cache, so a page full of printer cards costs
    Home Assistant nothing. A sensor the poller has not reached yet falls back
    to its last persisted state, marked unreachable, rather than vanishing
    from the card on every restart.
    """
    result = await db.execute(
        select(PrinterHASensor)
        .where(
            PrinterHASensor.printer_id == printer_id,
            PrinterHASensor.show_on_printer_card.is_(True),
        )
        .order_by(PrinterHASensor.sort_order, PrinterHASensor.id)
    )

    readings = []
    for sensor in result.scalars().all():
        cached = ha_sensor_manager.get_reading(sensor.id)
        readings.append(
            PrinterHASensorReading(
                id=sensor.id,
                name=sensor.name,
                entity_id=sensor.entity_id,
                kind=sensor.kind,
                device_class=sensor.device_class,
                unit=sensor.unit,
                state=cached.state if cached else sensor.last_state,
                value=cached.value if cached else None,
                alerting=cached.alerting if cached else False,
                block_print=sensor.block_print,
                failure_strategy=sensor.failure_strategy,
                reachable=cached.reachable if cached else False,
                last_changed=sensor.last_changed,
            )
        )
    return readings


@router.post("/", response_model=PrinterHASensorResponse)
async def create_ha_sensor(
    data: PrinterHASensorCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = _CREATE,
):
    """Bind a Home Assistant entity to a printer."""
    printer = await db.get(Printer, data.printer_id)
    if not printer:
        raise HTTPException(404, "Printer not found")

    existing = await db.execute(
        select(PrinterHASensor).where(
            PrinterHASensor.printer_id == data.printer_id,
            PrinterHASensor.entity_id == data.entity_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"{data.entity_id} is already bound to this printer")

    sensor = PrinterHASensor(**data.model_dump())
    db.add(sensor)
    await db.commit()
    await db.refresh(sensor)
    logger.info("Bound HA entity %s to printer %s as '%s'", sensor.entity_id, sensor.printer_id, sensor.name)

    # Read it once now so the card shows a state immediately instead of after
    # the next poll tick. Best-effort: the row is already committed, so letting
    # a Home Assistant hiccup 500 the request would report a failure for work
    # that succeeded — and the retry would come back "already bound".
    await _refresh_quietly(sensor, db)
    return sensor


@router.get("/{sensor_id}", response_model=PrinterHASensorResponse)
async def get_ha_sensor(
    sensor_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = _READ,
):
    sensor = await db.get(PrinterHASensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor not found")
    return sensor


@router.patch("/{sensor_id}", response_model=PrinterHASensorResponse)
async def update_ha_sensor(
    sensor_id: int,
    data: PrinterHASensorUpdate,
    db: AsyncSession = Depends(get_db),
    user: User | None = _UPDATE,
):
    sensor = await db.get(PrinterHASensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor not found")

    updates = data.model_dump(exclude_unset=True)

    # Re-run the create-time rules against the merged row. A PATCH that only
    # sets block_print has no entity_id or alert_state in its payload, so the
    # schema alone cannot tell whether the result is coherent.
    merged = {field: getattr(sensor, field) for field in PrinterHASensorCreate.model_fields}
    merged.update(updates)
    try:
        PrinterHASensorCreate(**merged)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    # Same uniqueness rule as create: repointing a sensor at an entity the
    # printer already has would leave two rows fighting over one pill.
    new_entity = updates.get("entity_id")
    if new_entity and new_entity != sensor.entity_id:
        clash = await db.execute(
            select(PrinterHASensor).where(
                PrinterHASensor.printer_id == sensor.printer_id,
                PrinterHASensor.entity_id == new_entity,
                PrinterHASensor.id != sensor.id,
            )
        )
        if clash.scalar_one_or_none():
            raise HTTPException(400, f"{new_entity} is already bound to this printer")

    override_revoked = await _stage_override_revocation(
        db,
        printer_id=sensor.printer_id,
        user=user,
        change="sensor updated",
    )
    for field, value in updates.items():
        setattr(sensor, field, value)
    await db.commit()
    if override_revoked:
        ha_sensor_manager.clear_interlock_override(sensor.printer_id)
    await db.refresh(sensor)

    # The entity or its alert rule may have changed under the cached reading.
    await _refresh_quietly(sensor, db)
    return sensor


@router.delete("/{sensor_id}")
async def delete_ha_sensor(
    sensor_id: int,
    db: AsyncSession = Depends(get_db),
    user: User | None = _DELETE,
):
    sensor = await db.get(PrinterHASensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor not found")

    name = sensor.name
    printer_id = sensor.printer_id
    override_revoked = await _stage_override_revocation(
        db,
        printer_id=printer_id,
        user=user,
        change="sensor deleted",
    )
    await db.delete(sensor)
    await db.commit()
    if override_revoked:
        ha_sensor_manager.clear_interlock_override(printer_id)
    ha_sensor_manager.forget(sensor_id)
    logger.info("Removed HA sensor '%s'", name)
    return {"message": f"Sensor '{name}' removed"}
