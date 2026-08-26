"""Match printer completion events to queue jobs and recover stranded rows."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import select, update

from backend.app.core.database import async_session
from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.printer_manager import printer_manager

logger = logging.getLogger(__name__)

STRANDED_PRINTING_GRACE_SECONDS = 300.0
_TRUNCATION_MARKER = "..."
_TERMINAL_QUEUE_STATUS = {"FINISH": "completed", "FAILED": "failed", "IDLE": "cancelled"}


def subtask_name_from_filename(filename: str) -> str:
    """Recover the printer-facing subtask name from an archive filename."""
    name = PurePosixPath(filename).name
    for suffix in (".3mf", ".gcode"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
    return name


def _normalise_subtask_name(name: str) -> str:
    return name.strip().replace(" ", "_").casefold()


def subtask_names_match(expected: str, observed: str) -> bool:
    """Compare names using the printer's whitespace and truncation rules."""
    expected_n = _normalise_subtask_name(expected)
    observed_n = _normalise_subtask_name(observed)
    if expected_n == observed_n:
        return True
    for full, cut in ((expected_n, observed_n), (observed_n, expected_n)):
        if cut.endswith(_TRUNCATION_MARKER) and full.startswith(cut[: -len(_TRUNCATION_MARKER)]):
            return True
    return False


def _event_subtask_id(data: dict) -> str | None:
    value = data.get("subtask_id")
    if value is None and isinstance(data.get("raw_data"), dict):
        raw = data["raw_data"]
        payload = raw.get("print") if isinstance(raw.get("print"), dict) else raw
        value = payload.get("subtask_id")
    value = str(value).strip() if value is not None else ""
    return value if value not in ("", "0") else None


async def completion_belongs_to_queue_item(
    db,
    item: PrintQueueItem,
    data: dict,
    *,
    event_archive_id: int | None,
) -> bool:
    """Reject only a positive identity disagreement with the printing row."""
    item_archive_id = item.archive_id
    if isinstance(item_archive_id, int) and isinstance(event_archive_id, int):
        if item_archive_id == event_archive_id:
            return True
        logger.warning(
            "Ignoring completion for archive %s: queue item %s is printing archive %s",
            event_archive_id,
            item.id,
            item_archive_id,
        )
        return False
    if not isinstance(item_archive_id, int):
        return True

    archive = await db.get(PrintArchive, item_archive_id)
    if archive is None or not isinstance(getattr(archive, "filename", None), str):
        return True

    expected_subtask_id = str(archive.subtask_id).strip() if archive.subtask_id else None
    observed_subtask_id = _event_subtask_id(data)
    if expected_subtask_id and observed_subtask_id:
        if expected_subtask_id == observed_subtask_id:
            return True
        logger.warning(
            "Ignoring completion for queue item %s: subtask id %r does not match %r",
            item.id,
            observed_subtask_id,
            expected_subtask_id,
        )
        return False

    observed_names = [name for name in (data.get("subtask_name"),) if isinstance(name, str) and name]
    if isinstance(data.get("filename"), str) and data["filename"]:
        observed_names.append(subtask_name_from_filename(data["filename"]))
    if not observed_names:
        return True
    expected_names = [
        name
        for name in (getattr(archive, "print_name", None), subtask_name_from_filename(archive.filename))
        if isinstance(name, str) and name
    ]
    if not expected_names or any(
        subtask_names_match(expected, observed) for expected in expected_names for observed in observed_names
    ):
        return True

    logger.warning(
        "Ignoring completion for queue item %s: archive %s names %r do not match event names %r",
        item.id,
        archive.id,
        expected_names,
        observed_names,
    )
    return False


async def update_queue_status_for_completion(
    db,
    *,
    printer_id: int,
    data: dict,
    event_archive_id: int | None,
    failure_summary: str,
    bump_usage,
) -> tuple[int, str, bool] | None:
    """Update only the printing row positively matched to this completion."""
    result = await db.execute(
        select(PrintQueueItem).where(PrintQueueItem.printer_id == printer_id).where(PrintQueueItem.status == "printing")
    )
    items = list(result.scalars().all())
    if len(items) > 1:
        logger.warning(
            "BUG: Multiple queue items in 'printing' status for printer %s: %s",
            printer_id,
            [(item.id, item.archive_id, item.library_file_id) for item in items],
        )
    item = items[0] if items else None
    if item is None or not await completion_belongs_to_queue_item(db, item, data, event_archive_id=event_archive_id):
        return None

    queue_status = data.get("status", "completed")
    if queue_status == "aborted":
        queue_status = "cancelled"
    item.status = queue_status
    item.completed_at = datetime.now(timezone.utc)
    if queue_status == "failed" and not item.error_message:
        item.error_message = failure_summary
    await bump_usage(db, item, queue_status)
    await db.commit()
    logger.info("Updated queue item %s status to %s", item.id, queue_status)
    return item.id, queue_status, item.auto_off_after


def terminal_queue_status(state: Any) -> str | None:
    """Return the queue status proven by a connected terminal printer state."""
    if state is None or not getattr(state, "connected", False):
        return None
    return _TERMINAL_QUEUE_STATUS.get(str(getattr(state, "state", "")).upper())


async def clear_stale_dispatch_claims(session_factory=async_session) -> None:
    """Clear dispatch claims left behind by a process restart."""
    try:
        async with session_factory() as db:
            result = await db.execute(
                update(PrintQueueItem).where(PrintQueueItem.dispatching_at.is_not(None)).values(dispatching_at=None)
            )
            await db.commit()
            if result.rowcount:
                logger.info("Cleared %d stale queue dispatch claim(s)", result.rowcount)
    except Exception as exc:
        logger.error("Failed to clear stale queue dispatch claims: %s", exc)


class StrandedPrintRecovery:
    """Close printing rows that remain stranded after a terminal state."""

    def __init__(
        self,
        *,
        session_factory: Callable = async_session,
        status_getter: Callable[[int], Any] = printer_manager.get_status,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._status_getter = status_getter
        self._monotonic = monotonic
        self._terminal_since: dict[int, float] = {}

    async def tick(self) -> None:
        try:
            await self._tick()
        except Exception as exc:
            logger.error("Failed to recover stranded printing queue items: %s", exc)

    async def _tick(self) -> None:
        async with self._session_factory() as db:
            result = await db.execute(
                select(PrintQueueItem)
                .where(PrintQueueItem.status == "printing")
                .where(PrintQueueItem.printer_id.is_not(None))
            )
            items = list(result.scalars().all())
            if not items:
                self._terminal_since.clear()
                return

            now = self._monotonic()
            seen_printers: set[int] = set()
            closed = False
            for item in items:
                printer_id = item.printer_id
                seen_printers.add(printer_id)
                status = terminal_queue_status(self._status_getter(printer_id))
                if status is None:
                    self._terminal_since.pop(printer_id, None)
                    continue
                since = self._terminal_since.setdefault(printer_id, now)
                if now - since < STRANDED_PRINTING_GRACE_SECONDS:
                    continue
                item.status = status
                item.completed_at = datetime.now(timezone.utc)
                self._terminal_since.pop(printer_id, None)
                closed = True
                logger.warning(
                    "Recovered queue item %s as %s after printer %s remained terminal for %.0fs",
                    item.id,
                    status,
                    printer_id,
                    now - since,
                )
            for printer_id in set(self._terminal_since) - seen_printers:
                self._terminal_since.pop(printer_id, None)
            if closed:
                await db.commit()
