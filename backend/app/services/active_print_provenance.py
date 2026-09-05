"""Lifecycle orchestration for durable per-print filament provenance."""

import logging

from backend.app.core.database import async_session


def printer_is_printing(state) -> bool:
    return (getattr(state, "state", "") or "").upper() in ("RUNNING", "PAUSE")


async def capture_print_start(printer_id: int, data: dict, printer_manager, db) -> None:
    from backend.app.api.routes.settings import get_setting
    from backend.app.services.usage_tracker import on_print_start

    spoolman_enabled = await get_setting(db, "spoolman_enabled")
    await on_print_start(
        printer_id,
        data,
        printer_manager,
        db=db,
        spoolman_owns_usage=bool(spoolman_enabled) and spoolman_enabled.lower() == "true",
    )


async def restore_for_running_print(printer_id: int, state, db, logger) -> None:
    """Restore durable attribution evidence after a restart mid-print."""
    try:
        from backend.app.api.routes.settings import get_setting
        from backend.app.services.usage_tracker import (
            clear_persisted_session,
            get_persisted_print_identity,
            restore_session,
        )

        persisted_name, persisted_subtask_id = await get_persisted_print_identity(db, printer_id)
        current_name = (getattr(state, "subtask_name", "") or "").strip()
        current_subtask_id = str(getattr(state, "subtask_id", "") or "").strip() or None
        if persisted_subtask_id and current_subtask_id:
            stale_session = persisted_subtask_id != current_subtask_id
        else:
            stale_session = bool(persisted_name and current_name and persisted_name.strip() != current_name)
        if stale_session:
            logger.info(
                "[RESTART] Discarding stale print session for printer %s (name=%r/%r, subtask_id=%r/%r)",
                printer_id,
                persisted_name,
                current_name,
                persisted_subtask_id,
                current_subtask_id,
            )
            await clear_persisted_session(db, printer_id)
            persisted_log = None
        else:
            spoolman_enabled = await get_setting(db, "spoolman_enabled")
            persisted_log = await restore_session(
                db,
                printer_id,
                register_active=not (bool(spoolman_enabled) and spoolman_enabled.lower() == "true"),
            )

        current_log = list(getattr(state, "tray_change_log", None) or [])
        if persisted_log:
            restored = [tuple(entry) for entry in persisted_log if isinstance(entry, (list, tuple)) and len(entry) == 2]
            for entry in current_log:
                if tuple(entry) not in restored:
                    restored.append(tuple(entry))
            state.tray_change_log = restored

        tray_now = getattr(state, "tray_now", -1)
        if isinstance(tray_now, int) and not isinstance(tray_now, bool) and 0 <= tray_now <= 254:
            if not getattr(state, "tray_change_log", None):
                state.tray_change_log = [(tray_now, getattr(state, "layer_num", 0))]
                logger.info(
                    "[RESTART] Seeded tray change log for printer %s: tray=%d at layer=%d",
                    printer_id,
                    tray_now,
                    getattr(state, "layer_num", 0),
                )
            state.last_loaded_tray = tray_now
    except Exception:
        logger.exception("[RESTART] Failed to restore usage-tracking session for printer %s", printer_id)


async def restore_from_manager(printer_id: int, printer_manager, db, logger) -> None:
    state = printer_manager.get_status(printer_id)
    if state is not None:
        await restore_for_running_print(printer_id, state, db, logger)


def handle_missing_assignment(current_tray, print_active: bool, assignment, stale: list, logger) -> bool:
    """Handle an absent slot and report whether the caller should continue."""
    if current_tray:
        return False
    if not print_active:
        logger.info(
            "Auto-unlink: spool %d AMS%d-T%d — tray not found in AMS data (slot empty?)",
            assignment.spool_id,
            assignment.ams_id,
            assignment.tray_id,
        )
        stale.append(assignment)
    return True


async def persist_tray_change(printer_id: int, tray_global: int, layer_num: int) -> None:
    try:
        from backend.app.services.usage_tracker import record_tray_change

        async with async_session() as db:
            await record_tray_change(db, printer_id, tray_global, layer_num)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to persist tray change for printer %d (tray=%d, layer=%d): %s",
            printer_id,
            tray_global,
            layer_num,
            exc,
        )


async def enrich_print_session(
    printer_id: int,
    ams_mapping: list[int] | None,
    plate_id: int | None,
    subtask_id: str | None,
    db,
    logger,
) -> None:
    """Persist dispatch evidence that becomes authoritative after start capture."""
    from backend.app.services.usage_tracker import update_session_context

    if await update_session_context(
        db,
        printer_id,
        ams_mapping=ams_mapping,
        plate_id=plate_id,
        subtask_id=subtask_id,
    ):
        logger.info(
            "[CALLBACK] Persisted print session context: ams_mapping=%s, plate_id=%s, subtask_id=%s",
            ams_mapping,
            plate_id,
            subtask_id,
        )


async def claim_print_session(printer_id: int, data: dict, logger):
    """Claim the completing generation before another print can replace it."""
    from backend.app.services.usage_tracker import (
        load_persisted_session_for_completion,
        take_active_session_for_completion,
    )

    session, active_seen = take_active_session_for_completion(printer_id, data)
    if active_seen:
        return session
    try:
        async with async_session() as db:
            return await load_persisted_session_for_completion(db, printer_id, data)
    except Exception as exc:
        logger.warning("Failed to claim persisted print session for printer %s: %s", printer_id, exc)
        return None


async def discard_print_session(printer_id: int, session, logger) -> None:
    if session is None:
        return
    try:
        from backend.app.services.usage_tracker import discard_session

        async with async_session() as db:
            await discard_session(db, printer_id, expected_session=session)
    except Exception as exc:
        logger.warning("Failed to clear persisted print session for printer %s: %s", printer_id, exc)
