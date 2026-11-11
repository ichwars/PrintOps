"""Apply queue drying decisions equally to pinned and model-based jobs."""

from sqlalchemy import func, select

from backend.app.models.printer import Printer
from backend.app.services.printer_manager import supports_drying_while_printing
from backend.app.services.queue_filament_mapping import creator_printer_ids
from backend.app.utils.local_time import to_naive_utc, utcnow_naive
from backend.app.utils.printer_models import normalize_printer_model


def only_parked_countdowns(manager, printer_id: int) -> bool:
    state = manager.get_status(printer_id)
    if state is None:
        return False
    parked = getattr(getattr(state, "drying_telemetry", None), "parked_countdowns", set())
    positive = []
    for unit in state.raw_data.get("ams", []):
        try:
            if int(unit.get("dry_time", 0)) > 0:
                positive.append(int(unit.get("id", -1)))
        except (TypeError, ValueError):
            return False
    return bool(positive) and all(ams_id in parked for ams_id in positive)


async def drying_holds(scheduler, db, manager) -> set[int]:
    if not scheduler._drying_in_progress or not await scheduler._get_bool_setting(db, "queue_drying_block"):
        return set()
    return {pid for pid in scheduler._drying_in_progress if not only_parked_countdowns(manager, pid)}


async def stop_drying_before_print(scheduler, db, manager, printer_id: int) -> None:
    if printer_id not in scheduler._drying_in_progress:
        return
    if await scheduler._get_bool_setting(db, "print_drying_enabled"):
        client = manager.get_client(printer_id)
        firmware = getattr(getattr(client, "state", None), "firmware_version", None)
        if supports_drying_while_printing(manager.get_model(printer_id), firmware):
            return
    # Stop authority stays with the existing ownership service. Publication or
    # a live timer alone never authorizes stopping somebody else's dry cycle.
    await scheduler._stop_drying(printer_id)


async def queue_printer_sets(scheduler, db, queue_items) -> tuple[set[int], set[int]]:
    scheduled: set[int] = set()
    ready: set[int] = set()
    now = utcnow_naive()
    scopes: dict[int | None, set[int] | None] = {}
    cache: dict[tuple[str, str | None, int | None], set[int]] = {}
    for item in queue_items:
        if item.printer_id:
            item_printers = {item.printer_id}
        elif getattr(item, "target_model", None) or getattr(item, "variants", None):
            user_id = item.created_by_id
            if user_id not in scopes:
                scopes[user_id] = await creator_printer_ids(db, user_id)
            item_printers = set()
            for candidate in scheduler._queue_model_candidates(item):
                if not candidate.target_model:
                    continue
                model = normalize_printer_model(candidate.target_model) or candidate.target_model
                key = (model.lower(), item.target_location, user_id)
                if key not in cache:
                    query = select(Printer.id).where(
                        func.lower(Printer.model) == model.lower(), Printer.is_active.is_(True)
                    )
                    if item.target_location:
                        query = query.where(Printer.location == item.target_location)
                    if scopes[user_id] is not None:
                        query = query.where(Printer.id.in_(scopes[user_id]))
                    cache[key] = set((await db.scalars(query)).all())
                item_printers |= cache[key]
        else:
            continue
        scheduled_at = to_naive_utc(item.scheduled_time)
        if scheduled_at is not None and not item.manual_start:
            scheduled |= item_printers
        if scheduled_at is None or scheduled_at <= now:
            ready |= item_printers
    return scheduled, ready
