"""Explicit recovery of inventory weights from connected, idle printers."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.core.websocket import ws_manager
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.services.ams_slot_presence import _find_tray_in_ams_data

logger = logging.getLogger(__name__)


async def sync_builtin_weights(db):
    """Force-sync spool weight_used from live AMS remain% data.

    Overwrites the database weight_used for every assigned spool using the
    current AMS remain% from connected printers.  This is a manual recovery
    tool, it bypasses the normal increase-only guard and releases weight locks.
    Active prints and pending consumption bookings are left alone.
    """
    from backend.app.services.print_usage_lifecycle import printer_is_charging
    from backend.app.services.printer_manager import PrinterManager, printer_manager

    result = await db.execute(select(SpoolAssignment).options(selectinload(SpoolAssignment.spool)))
    assignments = list(result.scalars().all())
    logger.info("AMS weight sync: found %d assignments", len(assignments))

    synced = 0
    skipped = 0
    printing = 0
    changed = False

    for assignment in assignments:
        spool = assignment.spool
        if not spool:
            logger.debug("AMS weight sync: assignment %d has no spool", assignment.id)
            skipped += 1
            continue

        state = printer_manager.get_status(assignment.printer_id)
        if not state or not state.raw_data or getattr(state, "connected", True) is False:
            logger.info(
                "AMS weight sync: printer %d not connected, skipping spool %d",
                assignment.printer_id,
                spool.id,
            )
            skipped += 1
            continue

        if str(getattr(state, "state", "") or "").upper() in PrinterManager.ACTIVE_PRINT_STATES or printer_is_charging(
            assignment.printer_id
        ):
            skipped += 1
            printing += 1
            continue

        ams_raw = state.raw_data.get("ams", [])
        if isinstance(ams_raw, dict):
            ams_raw = ams_raw.get("ams", [])
        tray = _find_tray_in_ams_data(ams_raw, assignment.ams_id, assignment.tray_id)
        if not tray:
            logger.info(
                "AMS weight sync: no tray data for spool %d (printer %d AMS%d-T%d)",
                spool.id,
                assignment.printer_id,
                assignment.ams_id,
                assignment.tray_id,
            )
            skipped += 1
            continue

        remain_raw = tray.get("remain")
        if remain_raw is None:
            logger.debug("AMS weight sync: no remain value for spool %d", spool.id)
            skipped += 1
            continue

        try:
            remain_val = int(remain_raw)
        except (TypeError, ValueError):
            skipped += 1
            continue

        if remain_val < 0 or remain_val > 100:
            logger.debug("AMS weight sync: invalid remain=%s for spool %d", remain_raw, spool.id)
            skipped += 1
            continue

        lw = spool.label_weight or 1000
        new_used = round(lw * (100 - remain_val) / 100.0, 1)
        old_used = spool.weight_used or 0
        changed = changed or bool(spool.weight_locked) or round(old_used, 1) != new_used

        if round(old_used, 1) != new_used:
            logger.info(
                "AMS weight sync: spool %d weight_used %s -> %s (remain=%d%%)",
                spool.id,
                old_used,
                new_used,
                remain_val,
            )
            spool.weight_used = new_used
            spool.weight_locked = False
            synced += 1
        else:
            spool.weight_locked = False
            skipped += 1

    await db.commit()
    if changed:
        await ws_manager.broadcast({"type": "inventory_changed"})
    return {"synced": synced, "skipped": skipped, "printing": printing}


async def sync_automatic_weight(db, assignment, tray) -> bool:
    """Recheck both weight locks and consumption in the atomic update itself."""
    from sqlalchemy import func, update

    from backend.app.models.spool import Spool

    spool = assignment.spool
    if spool is None or spool.weight_locked:
        return False
    try:
        remain = int(tray.get("remain"))
    except (TypeError, ValueError):
        return False
    if not 1 <= remain <= 100:
        return False
    new_used = round((spool.label_weight or 1000) * (100 - remain) / 100.0, 1)
    if new_used <= (spool.weight_used or 0) + 1:
        return False
    result = await db.execute(
        update(Spool)
        .where(
            Spool.id == spool.id, Spool.weight_locked.is_not(True), func.coalesce(Spool.weight_used, 0) < new_used - 1
        )
        .values(weight_used=new_used)
    )
    await db.commit()
    if result.rowcount:
        logger.info("Weight sync: spool %s weight_used -> %s (remain=%s)", spool.id, new_used, remain)
    return bool(result.rowcount)


async def sync_spoolman_weights(db, client, printer_manager, translate_errors):
    from fastapi import HTTPException

    from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
    from backend.app.services.spoolman_weights import spoolman_price_weight

    # Fetch all non-archived Spoolman spools once for label_weight lookup
    async with translate_errors():
        raw_spools = await client.get_all_spools(allow_archived=False)
    spool_lookup: dict[int, dict] = {s["id"]: s for s in raw_spools if s.get("id") is not None}

    result = await db.execute(select(SpoolmanSlotAssignment))
    assignments = list(result.scalars().all())

    from backend.app.services.print_usage_lifecycle import printer_is_charging
    from backend.app.services.printer_manager import PrinterManager

    printing = 0
    synced = 0
    skipped = 0

    for assignment in assignments:
        spool_dict = spool_lookup.get(assignment.spoolman_spool_id)
        if not spool_dict:
            logger.debug("Spoolman AMS sync: spool %d not found in Spoolman, skipping", assignment.spoolman_spool_id)
            skipped += 1
            continue

        label_weight = spoolman_price_weight(spool_dict)
        if label_weight <= 0:
            logger.debug("Spoolman AMS sync: spool %d has no label_weight, skipping", assignment.spoolman_spool_id)
            skipped += 1
            continue

        state = printer_manager.get_status(assignment.printer_id)
        if not state or not state.raw_data or getattr(state, "connected", True) is False:
            logger.info(
                "Spoolman AMS sync: printer %d not connected, skipping spool %d",
                assignment.printer_id,
                assignment.spoolman_spool_id,
            )
            skipped += 1
            continue

        if str(getattr(state, "state", "") or "").upper() in PrinterManager.ACTIVE_PRINT_STATES or printer_is_charging(
            assignment.printer_id
        ):
            skipped += 1
            printing += 1
            continue

        ams_raw = state.raw_data.get("ams", [])
        if isinstance(ams_raw, dict):
            ams_raw = ams_raw.get("ams", [])
        tray = _find_tray_in_ams_data(ams_raw, assignment.ams_id, assignment.tray_id)
        if not tray:
            logger.info(
                "Spoolman AMS sync: no tray data for spool %d (printer %d AMS%d-T%d)",
                assignment.spoolman_spool_id,
                assignment.printer_id,
                assignment.ams_id,
                assignment.tray_id,
            )
            skipped += 1
            continue

        remain_raw = tray.get("remain")
        if remain_raw is None:
            logger.debug(
                "Spoolman AMS sync: no remain value for spool %d (tray %d/%d), skipping",
                assignment.spoolman_spool_id,
                assignment.ams_id,
                assignment.tray_id,
            )
            skipped += 1
            continue

        try:
            remain_val = int(remain_raw)
        except (TypeError, ValueError):
            logger.debug(
                "Spoolman AMS sync: non-numeric remain=%r for spool %d, skipping",
                remain_raw,
                assignment.spoolman_spool_id,
            )
            skipped += 1
            continue

        if remain_val < 0 or remain_val > 100:
            logger.debug("Spoolman AMS sync: invalid remain=%s for spool %d", remain_raw, assignment.spoolman_spool_id)
            skipped += 1
            continue

        remaining = round(label_weight * remain_val / 100.0, 1)
        try:
            async with translate_errors():
                await client.update_spool_full(assignment.spoolman_spool_id, remaining_weight=remaining)
            logger.info(
                "Spoolman AMS sync: spool %d remaining set to %s g (remain=%d%%)",
                assignment.spoolman_spool_id,
                remaining,
                remain_val,
            )
            synced += 1
        except HTTPException as exc:
            if exc.status_code == 404:
                logger.warning(
                    "Spoolman AMS sync: spool %d not found in Spoolman (404), skipping",
                    assignment.spoolman_spool_id,
                )
            else:
                logger.warning(
                    "Spoolman AMS sync: failed to update spool %d (HTTP %d)",
                    assignment.spoolman_spool_id,
                    exc.status_code,
                )
            skipped += 1

    return {"synced": synced, "skipped": skipped, "printing": printing}
