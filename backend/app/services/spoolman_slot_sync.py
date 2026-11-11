"""Writing a Spoolman AMS sync's results to the local slot table.

Shared by the automatic pass in ``on_ams_change`` and the Sync buttons in
Settings. A sync reads the slot table, then awaits Spoolman for every tray, so
by the time it writes, a slot may hold a spool the user assigned meanwhile.
Writing every synced slot back, the unchanged ones included, overwrote that
assignment with what the sync had read (SSA-3). Only a slot whose spool the
sync changed is written, and only while it still holds what the sync read.

What it did change is announced, its grace hold dropped, as a hand assignment
does; the Sync buttons did neither (SSA-2).
"""

import logging
from collections.abc import Iterable, Mapping
from typing import cast

from sqlalchemy import DateTime, bindparam, delete, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.websocket import ws_manager
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services import slot_unlink_grace, spool_swaps
from backend.app.services.ams_assignment_lock import get_ams_assignment_lock, get_spool_move_lock, lock_ams_assignments
from backend.app.utils.local_time import utcnow_naive

logger = logging.getLogger(__name__)

Slot = tuple[int, int, int]  # (printer_id, ams_id, tray_id)


async def write_slot_results(db, read, synced, emptied) -> list[Slot]:
    """Commit sync results under local writer locks, then relocate identified spools."""
    synced, emptied = list(synced), list(emptied)
    printers = {pid for pid, _, _, _ in synced} | {pid for pid, _, _ in emptied}
    async with lock_ams_assignments(printers):
        changed = await _write_slot_results(db, read, synced, emptied)
    await _release_elsewhere(synced, changed)
    return changed


async def _write_slot_results(
    db: AsyncSession,
    read: Mapping[Slot, int] | None,
    synced: Iterable[tuple[int, int, int, int]],
    emptied: Iterable[Slot],
) -> list[Slot]:
    """Write the slots the sync changed and commit; returns them.

    ``read`` is the slot table as the sync read it, ``synced`` the
    (printer_id, ams_id, tray_id, spoolman_spool_id) it found in the slots, and
    ``emptied`` the slots it found empty. Raises on a database error, as the
    callers report it.

    ``read`` None: the table could not be read, so there is nothing to compare
    against, and every slot is written as it was before the compare existed. A
    swap and a removal must not be dropped for want of a snapshot.
    """
    if read is None:
        return await _write_unconditionally(db, synced, emptied)
    changed: list[Slot] = []
    assigned: list[Slot] = []
    for printer_id, ams_id, tray_id, spool_id in synced:
        slot = (printer_id, ams_id, tray_id)
        before = read.get(slot)
        if before == spool_id:
            continue
        where = (
            SpoolmanSlotAssignment.printer_id == printer_id,
            SpoolmanSlotAssignment.ams_id == ams_id,
            SpoolmanSlotAssignment.tray_id == tray_id,
        )
        if before is None:
            statement = text(
                "INSERT INTO spoolman_slot_assignments (printer_id, ams_id, tray_id, spoolman_spool_id, assigned_at)"
                " VALUES (:printer_id, :ams_id, :tray_id, :spool_id, :assigned_at)"
                " ON CONFLICT(printer_id, ams_id, tray_id) DO NOTHING"
            ).bindparams(
                bindparam("assigned_at", utcnow_naive(), type_=DateTime()),
                printer_id=printer_id,
                ams_id=ams_id,
                tray_id=tray_id,
                spool_id=spool_id,
            )
        else:
            statement = (
                update(SpoolmanSlotAssignment)
                .where(*where, SpoolmanSlotAssignment.spoolman_spool_id == before)
                .values(spoolman_spool_id=spool_id, assigned_at=utcnow_naive())
                .execution_options(synchronize_session=False)
            )
        if cast(CursorResult, await db.execute(statement)).rowcount:
            changed.append(slot)
            assigned.append(slot)
            await spool_swaps.record_assignment(db, printer_id, ams_id, tray_id, spool_id, spool_swaps.SPOOLMAN)
    for slot in emptied:
        # A slot the sync read without a spool matches no row below: there is
        # nothing of the sync's own to remove.
        before = read.get(slot)
        printer_id, ams_id, tray_id = slot
        result = cast(
            CursorResult,
            await db.execute(
                delete(SpoolmanSlotAssignment)
                .where(
                    SpoolmanSlotAssignment.printer_id == printer_id,
                    SpoolmanSlotAssignment.ams_id == ams_id,
                    SpoolmanSlotAssignment.tray_id == tray_id,
                    SpoolmanSlotAssignment.spoolman_spool_id == before,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        if result.rowcount:
            changed.append(slot)
    await db.commit()
    await _announce(assigned, changed)
    return changed


async def _write_unconditionally(
    db: AsyncSession, synced: Iterable[tuple[int, int, int, int]], emptied: Iterable[Slot]
) -> list[Slot]:
    assigned: list[Slot] = []
    for printer_id, ams_id, tray_id, spool_id in synced:
        await upsert_spoolman_slot(db, (printer_id, ams_id, tray_id), spool_id)
        assigned.append((printer_id, ams_id, tray_id))
        await spool_swaps.record_assignment(db, printer_id, ams_id, tray_id, spool_id, spool_swaps.SPOOLMAN)
    removed: list[Slot] = []
    for printer_id, ams_id, tray_id in emptied:
        await db.execute(
            delete(SpoolmanSlotAssignment)
            .where(
                SpoolmanSlotAssignment.printer_id == printer_id,
                SpoolmanSlotAssignment.ams_id == ams_id,
                SpoolmanSlotAssignment.tray_id == tray_id,
            )
            .execution_options(synchronize_session=False)
        )
        removed.append((printer_id, ams_id, tray_id))
    await db.commit()
    changed = assigned + removed
    await _announce(assigned, changed)
    return changed


async def _announce(assigned: list[Slot], changed: list[Slot]) -> None:
    for printer_id, ams_id, tray_id in assigned:
        slot_unlink_grace.forget_slot(printer_id, ams_id, tray_id)
    for printer_id, ams_id, tray_id in changed:
        await ws_manager.broadcast(
            {"type": "spool_assignment_changed", "printer_id": printer_id, "ams_id": ams_id, "tray_id": tray_id}
        )


async def refresh_synced_presets(db, candidates, *, reconcile=False):
    """Refresh only metadata belonging to the spool that still owns the slot."""
    from sqlalchemy import select

    from backend.app.services.slot_preset_writer import upsert_slot_preset_for_spoolman_spool
    from backend.app.services.spool_filament_presets import reconcile_spoolman_rfid_slot

    for printer_id, ams_id, tray_id, spool, tray in candidates:
        async with get_ams_assignment_lock(printer_id):
            current = await db.scalar(
                select(SpoolmanSlotAssignment.spoolman_spool_id).where(
                    SpoolmanSlotAssignment.printer_id == printer_id,
                    SpoolmanSlotAssignment.ams_id == ams_id,
                    SpoolmanSlotAssignment.tray_id == tray_id,
                )
            )
            if current != spool.get("id"):
                continue
            params = {
                "db": db,
                "spoolman_spool": spool,
                "printer_id": printer_id,
                "ams_id": ams_id,
                "tray_id": tray_id,
                "tray_info_idx": tray.tray_info_idx or "",
                "tray_sub_brands": tray.tray_sub_brands or "",
                "tray_type": tray.tray_type or "",
            }
            if reconcile:
                await reconcile_spoolman_rfid_slot(**params)
            else:
                await upsert_slot_preset_for_spoolman_spool(**params)


async def _release_elsewhere(synced: Iterable[tuple[int, int, int, int]], assigned: list[Slot]) -> None:
    """Take each spool this write put in a slot out of its other slots (#3427).

    Only where the slot reports a tag, which ``release_other_slots`` checks:
    the sync also fills slots from what they held before, which proves
    nothing about where the spool is. A failure leaves the assignment written.
    """
    from backend.app.services.spool_relocation import SPOOLMAN, release_other_slots

    written = set(assigned)
    for printer_id, ams_id, tray_id, spool_id in synced:
        slot = (printer_id, ams_id, tray_id)
        if slot not in written:
            continue
        try:
            await release_other_slots(SPOOLMAN, spool_id, slot)
        except Exception as e:
            logger.warning("Releasing Spoolman spool %s from its other slots failed: %s", spool_id, e, exc_info=True)


async def slot_matches_spool(db, printer_id: int, ams_id: int, tray_id: int, spool_id: int) -> bool:
    """Check current ownership from SQL while the caller holds the printer's writer lock."""
    from sqlalchemy import select

    current = await db.scalar(
        select(SpoolmanSlotAssignment.spoolman_spool_id).where(
            SpoolmanSlotAssignment.printer_id == printer_id,
            SpoolmanSlotAssignment.ams_id == ams_id,
            SpoolmanSlotAssignment.tray_id == tray_id,
        )
    )
    return current == spool_id


async def persist_slot_assignment(db, printer_id: int, ams_id: int, tray_id: int, spool_id: int) -> None:
    """Persist a prepared manual tag-to-slot binding under the shared writer locks."""
    async with get_spool_move_lock("spoolman", spool_id), get_ams_assignment_lock(printer_id):
        await upsert_spoolman_slot(db, (printer_id, ams_id, tray_id), spool_id)
        await spool_swaps.record_assignment(db, printer_id, ams_id, tray_id, spool_id, spool_swaps.SPOOLMAN)
        await db.commit()
        slot_unlink_grace.forget_slot(printer_id, ams_id, tray_id)


async def upsert_spoolman_slot(db: AsyncSession, slot: Slot, spool_id: int) -> None:
    """Keep the time the current spool took over this slot."""
    printer_id, ams_id, tray_id = slot
    await db.execute(
        text(
            "INSERT INTO spoolman_slot_assignments (printer_id, ams_id, tray_id, spoolman_spool_id, assigned_at)"
            " VALUES (:printer_id, :ams_id, :tray_id, :spool_id, :assigned_at)"
            " ON CONFLICT(printer_id, ams_id, tray_id)"
            " DO UPDATE SET spoolman_spool_id = excluded.spoolman_spool_id, assigned_at = excluded.assigned_at"
            " WHERE spoolman_slot_assignments.spoolman_spool_id <> excluded.spoolman_spool_id"
        ).bindparams(
            bindparam("assigned_at", utcnow_naive(), type_=DateTime()),
            printer_id=printer_id,
            ams_id=ams_id,
            tray_id=tray_id,
            spool_id=spool_id,
        )
    )
