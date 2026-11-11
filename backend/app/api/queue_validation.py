"""Queue API preflights that share dispatch's source and printer decisions."""

import logging

from fastapi import HTTPException

from backend.app.core.row_visibility import RowVisibility
from backend.app.services.queue_source_metadata import active_printer_model

logger = logging.getLogger(__name__)


def require_model_target_scope(visibility: RowVisibility) -> None:
    if not visibility.can_use_model_target:
        raise HTTPException(400, "This API key must target a specific printer")


async def require_active_model(db, model: str, printer_ids: set[int] | None = None) -> str:
    active_model = await active_printer_model(db, model, printer_ids)
    if active_model is None:
        raise HTTPException(400, f"No active printers for model: {model}")
    return active_model


async def check_missing_start_filament(db, item) -> None:
    """Offer the same acknowledgement as dispatch's missing-filament hold."""
    from backend.app.services.print_scheduler import scheduler

    try:
        missing = await scheduler.missing_filament_for_start(db, item)
    except Exception:
        # Dispatch still checks before sending a job; a failed convenience
        # preflight must not leave Start permanently unavailable.
        logger.exception("Queue item %s: filament check before start failed", item.id)
        missing = None
    if missing:
        raise HTTPException(409, detail={"code": "unmatched_filament", "missing": missing})
