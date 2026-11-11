"""Taking a spool out of its other slots once an AMS has read its tag (#3427).

A tag read in a slot says where the physical spool is, so any other slot the
spool is still assigned to is stale. The RFID auto-assign and the Spoolman AMS
sync wrote the slot they read and left those rows alone: a spool assigned by
hand to printer A's empty slot and then loaded into printer B stayed assigned
to both, and A's slot was configured from, and charged to, a spool in B.

Relocation takes the spool's move lock, then each holding printer's assignment
lock in ID order. It runs after the caller releases its own printer lock,
so it never takes another printer's lock in the opposite order. The tag and
slot owner are checked again after waiting for the locks.

The removed slots get no MQTT command and keep what the printer has set, as a
manual unassign does. A Spoolman spool also loses a vacated slot's fallback
tag. Callers only pass spools already known by the tag
read: a material/colour match proves nothing about where a spool is.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager

from sqlalchemy import delete, select

from backend.app.core.websocket import ws_manager
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services import spool_swaps
from backend.app.services.ams_assignment_lock import get_ams_assignment_lock, get_spool_move_lock, lock_ams_assignments
from backend.app.services.spoolman_slot_sync import upsert_spoolman_slot
from backend.app.utils.tag_normalization import normalize_tag_uid, normalize_tray_uuid

logger = logging.getLogger(__name__)

Slot = tuple[int, int, int]  # (printer_id, ams_id, tray_id)

INTERNAL = "inventory"
SPOOLMAN = "spoolman"


@asynccontextmanager
async def lock_spool_assignment(db, inventory: str, spool_id: int, target: Slot, *, move: bool, printer_ids):
    """Lock the destination and any previous slots this caller can change."""
    model = SpoolAssignment if inventory == INTERNAL else SpoolmanSlotAssignment
    spool_col = SpoolAssignment.spool_id if inventory == INTERNAL else SpoolmanSlotAssignment.spoolman_spool_id
    assignments = select(model).where(spool_col == spool_id)
    if printer_ids is not None:
        assignments = assignments.where(model.printer_id.in_(printer_ids))

    async with get_spool_move_lock(inventory, spool_id):
        locked = {target[0]}
        while True:
            async with lock_ams_assignments(locked):
                rows = list(await db.scalars(assignments)) if move else []
                holders = {row.printer_id for row in rows}
                if not holders <= locked:
                    locked.update(holders)
                    continue
                yield [row for row in rows if (row.printer_id, row.ams_id, row.tray_id) != target]
                return


def _live_tray(printer_id: int, ams_id: int, tray_id: int) -> dict | None:
    """The tray the printer reports for a slot, or None."""
    from backend.app.services.printer_manager import printer_manager

    state = printer_manager.get_status(printer_id)
    raw = getattr(state, "raw_data", None) if state is not None else None
    if not isinstance(raw, dict):
        return None
    if ams_id == 255:
        vt_trays = raw.get("vt_tray") or []
        for tray in [vt_trays] if isinstance(vt_trays, dict) else vt_trays:
            if isinstance(tray, dict) and str(tray.get("id", 254)) == str(254 + tray_id):
                return tray
        return None
    units = raw.get("ams") or []
    if isinstance(units, dict):  # also stored as the push's {"ams": [...]}
        units = units.get("ams") or []
    for unit in units:
        if not isinstance(unit, dict) or str(unit.get("id")) != str(ams_id):
            continue
        for tray in unit.get("tray") or []:
            if isinstance(tray, dict) and str(tray.get("id")) == str(tray_id):
                return tray
    return None


def _tag_ids(tray: dict | None) -> set[str]:
    """The tag's usable identifiers (tag_uid, tray_uuid), normalised; empty when untagged."""
    if not tray:
        return set()
    ids = set()
    uid = normalize_tag_uid(tray.get("tag_uid") or "")
    if uid and uid != "0" * len(uid):
        ids.add(f"uid:{uid}")
    uuid = normalize_tray_uuid(tray.get("tray_uuid") or "")
    if uuid and uuid != "0" * len(uuid):
        ids.add(f"uuid:{uuid}")
    return ids


async def _fallback_tags(db, slots: list[Slot]) -> set[str]:
    from backend.app.models.printer import Printer
    from backend.app.services.spoolman_tracking import get_fallback_spool_tag_for_slot

    query = select(Printer.id, Printer.serial_number).where(Printer.id.in_({pid for pid, _, _ in slots}))
    serials = dict((await db.execute(query)).tuples().all())
    return {get_fallback_spool_tag_for_slot(serials.get(pid) or "", aid, tid) for pid, aid, tid in slots} - {""}


@asynccontextmanager
async def detach_spoolman_fallback_tag(client, db, spool_id: int, slots: list[Slot]):
    """Remove the vacated slot's fallback tag, restoring it if the local move fails."""
    import json

    from backend.app.services.spoolman import _extra_string_value

    tags = await _fallback_tags(db, slots) if slots else set()
    if not tags:
        yield
        return

    async with client.extra_lock(spool_id):
        spool = await client.get_spool(spool_id)
        extra = spool.get("extra") or {}
        if _extra_string_value(extra, "tag") not in tags:
            yield
            return
        await client.update_spool_full(spool_id=spool_id, extra={**extra, "tag": json.dumps("")})
        try:
            yield
        except BaseException:
            try:
                await client.update_spool_full(spool_id=spool_id, extra=extra)
            except Exception:
                logger.exception("Could not restore the previous fallback tag of Spoolman spool %s", spool_id)
            raise


async def save_spoolman_assignment(db, client, spool_id: int, target: Slot, *, move: bool, printer_ids) -> list[Slot]:
    """Save a slot assignment and any requested relocation in the same commit."""
    printer_id, ams_id, tray_id = target
    async with lock_spool_assignment(db, SPOOLMAN, spool_id, target, move=move, printer_ids=printer_ids) as old_slots:
        vacated = [(row.printer_id, row.ams_id, row.tray_id) for row in old_slots]
        async with detach_spoolman_fallback_tag(client, db, spool_id, vacated):
            for row in old_slots:
                await db.delete(row)
            await upsert_spoolman_slot(db, target, spool_id)
            await spool_swaps.record_assignment(db, printer_id, ams_id, tray_id, spool_id, spool_swaps.SPOOLMAN)
            await db.commit()
    return vacated


async def _clear_fallback_tag(spool_id: int, vacated: list[Slot]) -> None:
    """Clear a vacated slot's legacy tag without a DB transaction during the remote write."""
    import json

    from backend.app.core.database import async_session
    from backend.app.services.spoolman import _extra_string_value, get_spoolman_client

    try:
        async with async_session() as db:
            old_tags = await _fallback_tags(db, vacated)
        client = await get_spoolman_client()
        if not client or not old_tags:
            return
        async with client.extra_lock(spool_id):
            spool = await client.get_spool(spool_id)
            extra = spool.get("extra") or {}
            if _extra_string_value(extra, "tag") in old_tags:
                await client.update_spool_full(spool_id=spool_id, extra={**extra, "tag": json.dumps("")})
    except Exception as exc:
        logger.warning("Could not clear the old slot's fallback tag from Spoolman spool %s: %s", spool_id, exc)


async def release_other_slots(inventory: str, spool_id: int, keep: Slot) -> list[Slot]:
    """Unassign ``spool_id`` from every slot but ``keep``, where a tag was just read.

    Only acts while ``keep`` reports a tag and still holds the spool. A slot
    whose printer reports the same tag right now keeps its assignment: one tag
    in two slots is a misread, and taking turns removing each other would be
    worse than leaving both. Returns the slots it removed, already announced.
    """
    from backend.app.core.database import async_session

    tag = _tag_ids(_live_tray(*keep))
    if not tag:
        return []

    model = SpoolAssignment if inventory == INTERNAL else SpoolmanSlotAssignment
    spool_col = SpoolAssignment.spool_id if inventory == INTERNAL else SpoolmanSlotAssignment.spoolman_spool_id

    async def _holders() -> set[int]:
        async with async_session() as db:
            rows = await db.execute(select(model.printer_id).where(spool_col == spool_id).distinct())
            return set(rows.scalars())

    locked = {keep[0]} | await _holders()
    vacated: list[Slot] = []
    while True:
        async with AsyncExitStack() as locks:
            await locks.enter_async_context(get_spool_move_lock(inventory, spool_id))
            for pid in sorted(locked):
                await locks.enter_async_context(get_ams_assignment_lock(pid))
            async with async_session() as db:
                rows = (await db.execute(select(model).where(spool_col == spool_id))).scalars().all()
                if not {row.printer_id for row in rows} <= locked:
                    locked |= {row.printer_id for row in rows}
                    continue
                if keep not in {(row.printer_id, row.ams_id, row.tray_id) for row in rows}:
                    # Reassigned since the read: whatever holds the slot now decides.
                    return []
                if not _tag_ids(_live_tray(*keep)) & tag:
                    return []
                for row in rows:
                    slot = (row.printer_id, row.ams_id, row.tray_id)
                    if slot == keep or _tag_ids(_live_tray(*slot)) & tag:
                        continue
                    result = await db.execute(
                        delete(model)
                        .where(
                            model.id == row.id,
                            spool_col == spool_id,
                        )
                        .execution_options(synchronize_session=False)
                    )
                    if result.rowcount:
                        vacated.append(slot)
                await db.commit()
        break

    if inventory == SPOOLMAN and vacated:
        await _clear_fallback_tag(spool_id, vacated)
    if vacated:
        logger.info(
            "Tag of spool %s read on printer %d AMS%d-T%d: unassigned it from %s",
            spool_id,
            *keep,
            ", ".join(f"printer {p} AMS{a}-T{t}" for p, a, t in vacated),
        )
    for printer_id, ams_id, tray_id in vacated:
        await ws_manager.broadcast(
            {"type": "spool_assignment_changed", "printer_id": printer_id, "ams_id": ams_id, "tray_id": tray_id}
        )
    return vacated
