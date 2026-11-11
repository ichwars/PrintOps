"""Persist Spoolman charges independently of the local spool ID namespace."""

import logging
from typing import NamedTuple

from sqlalchemy import delete, select

from backend.app.core.websocket import ws_manager
from backend.app.models.active_print_spoolman import ActivePrintSpoolman
from backend.app.models.archive import PrintArchive
from backend.app.models.spool_usage_history import SpoolUsageHistory

logger = logging.getLogger(__name__)


class SpoolmanUsageCharge(NamedTuple):
    spool_id: int
    grams: float
    cost: float | None
    net_weight: float | None


async def claim_spoolman_tracking(db, printer_id: int, archive_id: int):
    tracking = await db.scalar(
        delete(ActivePrintSpoolman)
        .where(ActivePrintSpoolman.printer_id == printer_id, ActivePrintSpoolman.archive_id == archive_id)
        .returning(ActivePrintSpoolman)
    )
    await db.commit()
    return tracking


async def record_spoolman_usage(db, printer_id: int, archive_id: int, status: str, charges: list[SpoolmanUsageCharge]):
    if not charges:
        return
    row = (
        await db.execute(select(PrintArchive.print_name, PrintArchive.filename).where(PrintArchive.id == archive_id))
    ).one_or_none()
    print_name = (row.print_name or row.filename) if row else None
    db.add_all(
        [
            SpoolUsageHistory(
                spoolman_spool_id=charge.spool_id,
                printer_id=printer_id,
                archive_id=archive_id if row else None,
                print_name=print_name,
                weight_used=charge.grams,
                percent_used=round(100 * charge.grams / charge.net_weight) if charge.net_weight else 0,
                status=status,
                cost=charge.cost,
            )
            for charge in charges
        ]
    )
    await db.commit()
    try:
        await ws_manager.broadcast({"type": "spool_usage_logged", "printer_id": printer_id, "usage": []})
    except Exception:
        logger.warning("Could not broadcast Spoolman usage for printer %s", printer_id, exc_info=True)
