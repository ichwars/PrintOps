"""Persist drying observed by firmware on spools assigned during the cycle."""

import json
import logging
from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes._spoolman_helpers import (
    BAMBU_LAST_DRIED_AT_KEY,
    BAMBU_LAST_DRIED_HOURS_KEY,
    BAMBU_LAST_DRIED_TEMP_KEY,
    spoolman_last_dried_at,
)
from backend.app.core.websocket import ws_manager
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.ams_assignment_lock import get_ams_assignment_lock
from backend.app.services.drying_cycle import DryingCycleEnd
from backend.app.services.inventory_mode import spoolman_owns_assignments
from backend.app.services.spoolman import (
    SpoolmanClient,
    SpoolmanClientError,
    SpoolmanNotFoundError,
    SpoolmanUnavailableError,
    get_spoolman_client,
)

logger = logging.getLogger(__name__)


def spoolman_drying_fields(
    dried_at: datetime | None, temp: int | None = None, hours: float | None = None
) -> dict[str, str]:
    return {
        BAMBU_LAST_DRIED_AT_KEY: json.dumps(dried_at.isoformat() if dried_at else ""),
        BAMBU_LAST_DRIED_TEMP_KEY: json.dumps(str(temp) if temp is not None else ""),
        BAMBU_LAST_DRIED_HOURS_KEY: json.dumps(str(hours) if hours is not None else ""),
    }


async def ensure_spoolman_drying_fields(client: SpoolmanClient) -> None:
    for field in spoolman_drying_fields(None):
        if not await client.ensure_extra_field(field):
            raise SpoolmanUnavailableError(f"Could not register Spoolman extra field {field}")


def _assignment_filter(model, timestamp, printer_id: int, cycle: DryingCycleEnd) -> tuple:
    return (
        model.printer_id == printer_id,
        model.ams_id == cycle.ams_id,
        timestamp <= cycle.first_observed_at,
        model.tray_id.not_in(cycle.excluded_slots),
    )


async def _stamp_native(db: AsyncSession, printer_id: int, cycle: DryingCycleEnd) -> int:
    eligible = select(SpoolAssignment.spool_id).where(
        *_assignment_filter(SpoolAssignment, SpoolAssignment.created_at, printer_id, cycle)
    )
    stamped = await db.scalars(
        update(Spool)
        .where(
            Spool.id.in_(eligible),
            Spool.archived_at.is_(None),
            or_(Spool.last_dried_at.is_(None), Spool.last_dried_at < cycle.ended_at),
        )
        .values(last_dried_at=cycle.ended_at, last_dried_temp=cycle.target_temp, last_dried_hours=cycle.hours)
        .returning(Spool.id)
    )
    count = len(stamped.all())
    await db.commit()
    return count


async def _stamp_spoolman(spool_ids: set[int], cycle: DryingCycleEnd) -> int:
    client = await get_spoolman_client()
    if client is None:
        return 0
    await ensure_spoolman_drying_fields(client)
    fields = spoolman_drying_fields(cycle.ended_at, cycle.target_temp, cycle.hours)
    stamped = 0
    for spool_id in sorted(spool_ids):
        try:
            async with client.extra_lock(spool_id):
                spool = await client.get_spool(spool_id)
                if spool.get("archived"):
                    continue
                extra = spool.get("extra") or {}
                saved = spoolman_last_dried_at(extra)
                if saved is not None and saved >= cycle.ended_at:
                    continue
                await client.update_spool_full(spool_id=spool_id, extra={**extra, **fields})
                stamped += 1
        except (SpoolmanClientError, SpoolmanNotFoundError, SpoolmanUnavailableError):
            logger.warning("Could not record drying on Spoolman spool %d", spool_id, exc_info=True)
    return stamped


async def record_drying_cycle(db: AsyncSession, printer_id: int, cycle: DryingCycleEnd) -> int:
    async with get_ams_assignment_lock(printer_id):
        spoolman = await spoolman_owns_assignments(db)
        if spoolman:
            model = SpoolmanSlotAssignment
            spool_ids = set(
                await db.scalars(
                    select(model.spoolman_spool_id).where(
                        *_assignment_filter(model, model.assigned_at, printer_id, cycle)
                    )
                )
            )
            await db.commit()
        else:
            stamped = await _stamp_native(db, printer_id, cycle)
    if spoolman:
        stamped = await _stamp_spoolman(spool_ids, cycle) if spool_ids else 0
    if stamped:
        await ws_manager.broadcast({"type": "inventory_changed"})
    return stamped
