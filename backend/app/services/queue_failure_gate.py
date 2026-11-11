"""Resume failed predecessors only within the caller's printer grants."""

from sqlalchemy import func, select, update

from backend.app.core.auth import allowed_printer_ids_for_user, user_can_access_printer
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.user import User
from backend.app.utils.printer_models import normalize_printer_model


async def resume_printers(db, printer_ids: list[int], *, restore_skipped: bool):
    acknowledged = await db.execute(
        update(PrintQueueItem)
        .where(
            PrintQueueItem.printer_id.in_(printer_ids),
            PrintQueueItem.status.in_(("failed", "aborted")),
            PrintQueueItem.gate_acknowledged.is_(False),
        )
        .values(gate_acknowledged=True)
    )
    restored_count = 0
    if restore_skipped:
        restored = await db.execute(
            update(PrintQueueItem)
            .where(
                PrintQueueItem.printer_id.in_(printer_ids),
                PrintQueueItem.status == "skipped",
                PrintQueueItem.error_message == "Previous print failed or was aborted",
            )
            .values(status="pending", error_message=None, completed_at=None)
        )
        restored_count = restored.rowcount
    await db.commit()
    return {"acknowledged": acknowledged.rowcount, "restored": restored_count}


async def resume_model(db, model: str, user, api_key):
    canonical = normalize_printer_model(model) or model
    printers = (
        await db.scalars(
            select(Printer).where(func.lower(Printer.model) == canonical.lower(), Printer.is_active.is_(True))
        )
    ).all()
    owner_allowed = None
    if api_key is not None and api_key.user_id is not None:
        owner = await db.get(User, api_key.user_id)
        owner_allowed = allowed_printer_ids_for_user(owner) if owner is not None and owner.is_active else set()
    printer_ids = [
        printer.id
        for printer in printers
        if user_can_access_printer(user, printer.id)
        and (owner_allowed is None or printer.id in owner_allowed)
        and (api_key is None or api_key.printer_ids is None or printer.id in api_key.printer_ids)
    ]
    result = await resume_printers(db, printer_ids, restore_skipped=False)
    return {"acknowledged": result["acknowledged"], "printers": len(printer_ids)}
