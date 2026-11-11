"""Track scheduled pauses against the current print run."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.app.core.config import settings
from backend.app.core.database import async_session
from backend.app.core.tasks import spawn_background_task
from backend.app.schemas.settings import DEFAULT_PAUSE_WARNING_MINUTES, MAX_PAUSE_WARNING_MINUTES
from backend.app.utils.gcode_pause_points import PausePoint, extract_pause_points

if TYPE_CHECKING:
    from backend.app.services.bambu_mqtt import PrinterState
    from backend.app.services.printer_manager import PrinterManager


@dataclass
class PauseTracking:
    identity: tuple[str | None, str | None, str | None]
    run_id: int | None = None
    points: tuple[PausePoint, ...] = ()
    warned_through_layer: int = 0
    next_check: float = 0
    task: asyncio.Task[None] | None = None


def _identity(state: PrinterState) -> tuple[str | None, str | None, str | None]:
    return (state.subtask_id, state.subtask_name, state.gcode_file)


def next_pause(state: PrinterState) -> dict | None:
    tracking = getattr(state, "pause_tracking", None)
    if not state.connected or state.state != "RUNNING" or tracking is None or tracking.identity != _identity(state):
        return None
    for point in tracking.points:
        if point.layer > (state.layer_num or 0):
            minutes = None
            if state.speed_level == 2 and state.remaining_time and state.remaining_time > 0:
                if point.remaining_minutes is not None:
                    minutes = max(0, state.remaining_time - point.remaining_minutes)
            return {"layer": point.layer, "minutes": minutes}
    return None


def _within_lead(upcoming: dict | None, lead: int, tracking: PauseTracking) -> bool:
    return bool(
        upcoming
        and upcoming["minutes"] is not None
        and upcoming["minutes"] <= lead
        and upcoming["layer"] > tracking.warned_through_layer
    )


def observe(printer_id: int, state: PrinterState, manager: PrinterManager) -> None:
    if not state.connected or state.state != "RUNNING":
        return
    identity = _identity(state)
    if not any(identity):
        return
    tracking = state.pause_tracking
    if tracking is None or tracking.identity != identity:
        tracking = state.pause_tracking = PauseTracking(identity)
    now = time.monotonic()
    if now < tracking.next_check or (tracking.task is not None and not tracking.task.done()):
        return
    if tracking.run_id is not None and not _within_lead(next_pause(state), MAX_PAUSE_WARNING_MINUTES, tracking):
        return
    tracking.next_check = now + (10 if tracking.run_id is None else 30)
    tracking.task = spawn_background_task(
        _refresh(printer_id, state, tracking, manager), name=f"print-pause-{printer_id}"
    )


async def _refresh(printer_id: int, state: PrinterState, tracking: PauseTracking, manager: PrinterManager) -> None:
    from backend.app.api.routes.settings import get_setting
    from backend.app.services.notification_service import notification_service
    from backend.app.services.running_print_archive import find_open_print, job_id, local_archive_file, reported_names

    def current() -> bool:
        return (
            manager.get_status(printer_id) is state
            and state.connected
            and state.state == "RUNNING"
            and state.pause_tracking is tracking
            and tracking.identity == _identity(state)
        )

    if not current():
        return
    if tracking.run_id is None:
        # The lookup also covers direct-to-printer starts and restored runs as
        # soon as their durable run entry is available.
        subtask = job_id(state.subtask_id)
        reported = reported_names(state) if str(state.subtask_id) == "0" else ()
        async with async_session() as db:
            archive, run = await find_open_print(db, printer_id, subtask, reported=reported)
            path = local_archive_file(archive, settings.base_dir)
            if path is None or run is None:
                return
            run_id = run.id
            plate_id = run.plate_id
            warned_through = run.pause_warned_layer or 0
        points = await asyncio.to_thread(extract_pause_points, path, plate_id)
        if not current():
            return
        tracking.points = points
        tracking.run_id = run_id
        tracking.warned_through_layer = warned_through
        if points:
            await manager.broadcast_status_change(printer_id)

    upcoming = next_pause(state)
    if not _within_lead(upcoming, MAX_PAUSE_WARNING_MINUTES, tracking):
        return
    async with async_session() as db:
        raw = await get_setting(db, "pause_warning_minutes")
        try:
            lead = max(1, min(MAX_PAUSE_WARNING_MINUTES, int(raw)))
        except (TypeError, ValueError):
            lead = DEFAULT_PAUSE_WARNING_MINUTES
        printer = manager.get_printer(printer_id)
        upcoming = next_pause(state)
        if not current() or printer is None or not _within_lead(upcoming, lead, tracking):
            return
        if await notification_service.on_print_pause_upcoming(
            printer_id,
            printer.name,
            state.subtask_name or state.gcode_file or "Unknown",
            run_id=tracking.run_id,
            minutes=upcoming["minutes"],
            layer=upcoming["layer"],
            total_layers=state.total_layers,
            db=db,
        ):
            tracking.warned_through_layer = upcoming["layer"]
