"""Per-printer lock for writes to a printer's spool assignments (AMS slots).

on_ams_change serialises its spool-assignment side (auto-unlink stale +
auto-assign new) when MQTT bursts deliver multiple AMS updates for the same
printer in quick succession (~30 ms apart, observed in the wild on H2D + dual
AMS).

Without this serialisation, two concurrent on_ams_change callbacks each read
"no assignment for (printer, ams, tray)", each call auto_assign_spool, and
the second commit hits
  IntegrityError: duplicate key value violates unique constraint
                  "spool_assignment_printer_id_ams_id_tray_id_key"
SQLite's WAL serial-write semantics had been silently swallowing the race
until optional Postgres support landed (asyncpg allows true concurrent
transactions and surfaces the constraint violation).

The assign, unassign and create-from-slot routes write the same rows and take
the same lock (SA-5), before their first write: on SQLite a session that
already holds the write lock would otherwise wait here on an AMS update that
waits for that write lock.

Remote spool discovery and preset resolution run before the writer lock.
Local assignment writes, publication of their prepared configuration, and
slot-preset metadata share this lock. Batch sync locks printers in ID order;
RFID relocation takes its spool lock before any printer locks.
"""

import asyncio
from collections.abc import Iterable
from contextlib import AsyncExitStack, asynccontextmanager

ams_assignment_locks: dict[int, asyncio.Lock] = {}


def get_ams_assignment_lock(printer_id: int) -> asyncio.Lock:
    """Return the per-printer assignment lock, creating it on first use."""
    lock = ams_assignment_locks.get(printer_id)
    if lock is None:
        lock = asyncio.Lock()
        ams_assignment_locks[printer_id] = lock
    return lock


_spool_move_locks: dict[tuple[str, int], asyncio.Lock] = {}


def get_spool_move_lock(inventory: str, spool_id: int) -> asyncio.Lock:
    """Serialize relocation of one physical spool within its inventory mode."""
    return _spool_move_locks.setdefault((inventory, spool_id), asyncio.Lock())


@asynccontextmanager
async def lock_ams_assignments(printer_ids: Iterable[int]):
    """Lock a batch's printer slots in a consistent order before its first write."""
    async with AsyncExitStack() as stack:
        for printer_id in sorted(set(printer_ids)):
            await stack.enter_async_context(get_ams_assignment_lock(printer_id))
        yield


@asynccontextmanager
async def lock_spoolman_assignments(db, spool_id: int):
    """Serialize deletion of one remote spool's current local slot rows."""
    from sqlalchemy import select

    from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment

    query = select(SpoolmanSlotAssignment.printer_id).where(SpoolmanSlotAssignment.spoolman_spool_id == spool_id)
    async with get_spool_move_lock("spoolman", spool_id):
        held: set[int] = set()
        while True:
            held.update((await db.scalars(query)).all())
            async with lock_ams_assignments(held):
                current = set((await db.scalars(query)).all())
                if not current <= held:
                    held.update(current)
                    continue
                yield
                return
