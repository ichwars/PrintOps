"""Environmental HA bindings use storage permissions, never printer controls."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.location import Location
from backend.app.models.storage_ha_sensor import StorageHASensor
from backend.app.models.user import User
from backend.app.schemas.printer_ha_sensor import HADisplayEntity
from backend.app.schemas.storage_ha_sensor import (
    StorageHASensorCreate,
    StorageHASensorReading,
    StorageHASensorResponse,
    StorageHASensorUpdate,
)
from backend.app.services.ha_sensor_manager import STALE_AFTER
from backend.app.services.homeassistant import homeassistant_service
from backend.app.services.storage_ha_sensors import storage_ha_sensor_manager
from backend.app.utils.local_time import utcnow_naive

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/storage-ha-sensors", tags=["storage-ha-sensors"])
_READ = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ)
_WRITE = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE)


@router.get("/entities", response_model=list[HADisplayEntity])
async def entities(db: AsyncSession = Depends(get_db), _: User | None = _READ):
    from backend.app.api.routes.settings import get_homeassistant_settings

    settings = await get_homeassistant_settings(db)
    if not settings["ha_enabled"] or not settings["ha_url"] or not settings["ha_token"]:
        raise HTTPException(400, "Home Assistant not configured or disabled")
    safe_url = homeassistant_service._validate_url(settings["ha_url"])
    if safe_url is None:
        raise HTTPException(400, "Invalid Home Assistant URL")
    rows = await homeassistant_service.list_display_entities(safe_url, settings["ha_token"])
    return [
        row
        for row in rows
        if row["domain"] == "sensor"
        and (
            row.get("device_class") == "humidity"
            and row.get("unit_of_measurement") == "%"
            or row.get("device_class") == "temperature"
            and row.get("unit_of_measurement") in ("°C", "°F", "K")
        )
    ]


@router.get("/", response_model=list[StorageHASensorResponse])
async def list_sensors(location_id: int | None = None, db: AsyncSession = Depends(get_db), _: User | None = _READ):
    query = select(StorageHASensor)
    if location_id is not None:
        query = query.where(StorageHASensor.location_id == location_id)
    return list((await db.execute(query.order_by(StorageHASensor.location_id, StorageHASensor.id))).scalars().all())


@router.get("/readings", response_model=list[StorageHASensorReading])
async def readings(db: AsyncSession = Depends(get_db), _: User | None = _READ):
    sensors = (await db.execute(select(StorageHASensor).order_by(StorageHASensor.id))).scalars().all()
    output = []
    now = utcnow_naive()
    for sensor in sensors:
        cached = storage_ha_sensor_manager.get_reading(sensor.id)
        stale = sensor.last_read_at is not None and now - sensor.last_read_at > STALE_AFTER
        if cached is None:
            status = "stale" if sensor.last_read_at else "pending"
        elif not cached.reachable:
            status = "unavailable"
        else:
            status = "stale" if stale or sensor.last_read_at is None else "fresh"
        output.append(
            StorageHASensorReading(
                id=sensor.id,
                location_id=sensor.location_id,
                name=sensor.name,
                entity_id=sensor.entity_id,
                device_class=sensor.device_class,
                unit=sensor.unit,
                value=cached.value if cached and status == "fresh" else None,
                alerting=bool(cached and status == "fresh" and cached.alerting),
                status=status,
                last_checked=sensor.last_checked,
                last_read_at=sensor.last_read_at,
            )
        )
    return output


async def _save(db: AsyncSession, sensor: StorageHASensor):
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Entity already bound to this location or location removed") from exc
    await db.refresh(sensor)
    try:
        await storage_ha_sensor_manager.refresh_one(db, sensor)
    except Exception:
        await db.rollback()
        await db.refresh(sensor)
        logger.warning("Could not refresh storage sensor id=%s after saving", sensor.id, exc_info=True)
    return sensor


@router.post("/", response_model=StorageHASensorResponse, status_code=201)
async def create(data: StorageHASensorCreate, db: AsyncSession = Depends(get_db), _: User | None = _WRITE):
    if await db.get(Location, data.location_id) is None:
        raise HTTPException(404, "Location not found")
    sensor = StorageHASensor(**data.model_dump())
    db.add(sensor)
    return await _save(db, sensor)


@router.patch("/{sensor_id}", response_model=StorageHASensorResponse)
async def update(
    sensor_id: int, data: StorageHASensorUpdate, db: AsyncSession = Depends(get_db), _: User | None = _WRITE
):
    sensor = await db.get(StorageHASensor, sensor_id)
    if sensor is None:
        raise HTTPException(404, "Sensor not found")
    changes = data.model_dump(exclude_unset=True)
    merged = {field: getattr(sensor, field) for field in StorageHASensorCreate.model_fields}
    merged.update(changes)
    try:
        StorageHASensorCreate(**merged)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid storage sensor configuration") from exc
    for field, value in changes.items():
        setattr(sensor, field, value)
    sensor.last_state = sensor.last_read_at = sensor.last_checked = sensor.last_changed = None
    storage_ha_sensor_manager.forget(sensor.id)
    return await _save(db, sensor)


@router.delete("/{sensor_id}", status_code=204)
async def delete(sensor_id: int, db: AsyncSession = Depends(get_db), _: User | None = _WRITE):
    sensor = await db.get(StorageHASensor, sensor_id)
    if sensor is None:
        raise HTTPException(404, "Sensor not found")
    await db.delete(sensor)
    await db.commit()
    storage_ha_sensor_manager.forget(sensor_id)
