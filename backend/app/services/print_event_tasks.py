"""Bounded side tasks for printer callbacks and application startup."""

import logging

from sqlalchemy import select


async def _announce_failed_plate_check(ws_manager, logger, printer_id, printer_name, reason):
    try:
        await ws_manager.broadcast(
            {"type": "plate_check_failed", "printer_id": printer_id, "printer_name": printer_name, "reason": reason}
        )
    except Exception as exc:
        logger.warning("[PLATE CHECK] Could not publish check failure for printer %s: %s", printer_id, exc)


async def check_print_start_plate(
    printer_id,
    printer,
    db,
    logger,
    *,
    printer_manager,
    ws_manager,
    notification_service,
    _capture_snapshot_for_notification,
):
    # Plate detection check - pause if objects detected on build plate
    logger.info(
        f"[PLATE CHECK] printer_id={printer_id}, plate_detection_enabled={printer.plate_detection_enabled if printer else 'NO PRINTER'}"
    )
    if printer and printer.plate_detection_enabled:
        logger.info("[PLATE CHECK] ENTERING plate detection code for printer %s", printer_id)
        try:
            from backend.app.services.camera_light import hold_camera_light
            from backend.app.services.plate_detection import check_plate_empty

            # Build ROI tuple from printer settings if available
            roi = None
            if all(
                [
                    printer.plate_detection_roi_x is not None,
                    printer.plate_detection_roi_y is not None,
                    printer.plate_detection_roi_w is not None,
                    printer.plate_detection_roi_h is not None,
                ]
            ):
                roi = (
                    printer.plate_detection_roi_x,
                    printer.plate_detection_roi_y,
                    printer.plate_detection_roi_w,
                    printer.plate_detection_roi_h,
                )

            client = printer_manager.get_client(printer_id)
            plate_image_data = None
            async with hold_camera_light(printer_id, illuminate_with=client):
                logger.info("[PLATE CHECK] Running plate detection for printer %s", printer_id)
                plate_result = await check_plate_empty(
                    printer_id=printer_id,
                    ip_address=printer.ip_address,
                    access_code=printer.access_code,
                    model=printer.model,
                    include_debug_image=False,
                    external_camera_url=printer.external_camera_url,
                    external_camera_type=printer.external_camera_type,
                    use_external=printer.external_camera_enabled,
                    roi=roi,
                    external_camera_snapshot_url=printer.external_camera_snapshot_url,
                )

                failure = getattr(plate_result, "failure_reason", None)
                if not failure and plate_result.needs_calibration:
                    failure = "not_calibrated"
                objects_detected = not failure and not plate_result.is_empty
                if objects_detected:
                    if client:
                        client.pause_print()
                        logger.info("[PLATE CHECK] Print paused for printer %s", printer_id)
                    plate_image_data = await _capture_snapshot_for_notification(printer_id, printer, logger)
            if objects_detected:
                # Objects detected - pause the print!
                logger.warning(
                    f"[PLATE CHECK] Objects detected on plate for printer {printer_id}! "
                    f"Confidence: {plate_result.confidence:.0%}, Diff: {plate_result.difference_percent:.1f}%"
                )
                # Send notification about plate not empty
                await ws_manager.broadcast(
                    {
                        "type": "plate_not_empty",
                        "printer_id": printer_id,
                        "printer_name": printer.name,
                        "message": f"Objects detected on build plate! Print paused. (Diff: {plate_result.difference_percent:.1f}%)",
                    }
                )

                # Also send push notification
                try:
                    await notification_service.on_plate_not_empty(
                        printer_id=printer_id,
                        printer_name=printer.name,
                        db=db,
                        difference_percent=plate_result.difference_percent,
                        image_data=plate_image_data,
                    )
                except Exception as notif_err:
                    logger.warning("[PLATE CHECK] Failed to send notification: %s", notif_err)
            elif failure:
                logger.warning(
                    "[PLATE CHECK] Could not check printer %s (%s); proceeding with print", printer_id, failure
                )
                await _announce_failed_plate_check(ws_manager, logger, printer_id, printer.name, failure)
            else:
                logger.info("[PLATE CHECK] Plate is empty for printer %s, proceeding with print", printer_id)
        except Exception as plate_err:
            logger.warning("[PLATE CHECK] Could not check printer %s: %s; proceeding with print", printer_id, plate_err)
            await _announce_failed_plate_check(ws_manager, logger, printer_id, printer.name, "error")


async def calculate_print_energy(
    printer_id,
    archive_id,
    logger,
    *,
    async_session,
    read_printer_energy,
    _get_plug_energy,
    run_id,
):
    """Measure and update the exact run that wrote its start reading."""
    from sqlalchemy import func, update

    from backend.app.api.routes.settings import get_setting
    from backend.app.models.archive import PrintArchive
    from backend.app.models.print_log import PrintLogEntry

    if run_id is None:
        return
    try:
        async with async_session() as db:
            run = await db.get(PrintLogEntry, run_id)
            if run is None or run.archive_id != archive_id or run.printer_id != printer_id:
                return
            starting_kwh, starting_plug_id = run.energy_start_kwh, run.energy_start_plug_id
            if starting_kwh is None or starting_plug_id is None:
                return

            selected = await read_printer_energy(
                db,
                printer_id,
                _get_plug_energy,
                log_prefix="ENERGY-BG",
                context=f"run {run_id}",
                plug_id=starting_plug_id,
            )
            if selected is None:
                return
            _, energy = selected
            energy_used = round(energy["total"] - starting_kwh, 4)
            if energy_used < 0:
                logger.warning("[ENERGY-BG] Counter decreased during run %s", run_id)
                return

            energy_cost_per_kwh = await get_setting(db, "energy_cost_per_kwh")
            cost_per_kwh = float(energy_cost_per_kwh) if energy_cost_per_kwh else 0.15
            run.energy_kwh, run.energy_cost = energy_used, round(energy_used * cost_per_kwh, 3)

            runs = await db.scalar(select(func.count(PrintLogEntry.id)).where(PrintLogEntry.archive_id == archive_id))
            if runs == 1:
                await db.execute(
                    update(PrintArchive)
                    .where(
                        PrintArchive.id == archive_id,
                        PrintArchive.printer_id == printer_id,
                        PrintArchive.started_at == run.started_at,
                    )
                    .values(energy_kwh=run.energy_kwh, energy_cost=run.energy_cost)
                )
            await db.commit()
    except Exception:
        logger.warning("[ENERGY-BG] Failed for run %s", run_id, exc_info=True)


async def check_print_maintenance(
    printer_id,
    print_status,
    logger,
    *,
    async_session,
    ensure_default_types,
    _get_printer_maintenance_internal,
    notification_service,
    mqtt_relay,
):
    """Check for maintenance due in background."""
    if print_status != "completed":
        return
    try:
        logger.info("[MAINT-BG] Starting maintenance check for printer %s", printer_id)
        async with async_session() as db:
            from backend.app.models.printer import Printer

            result = await db.execute(select(Printer).where(Printer.id == printer_id))
            printer = result.scalar_one_or_none()
            printer_name = printer.name if printer else f"Printer {printer_id}"

            await ensure_default_types(db)
            overview = await _get_printer_maintenance_internal(printer_id, db, commit=True)

            attention = [
                item for item in overview.maintenance_items if item.enabled and (item.is_due or item.is_warning)
            ]
            items_needing_attention = [
                {"name": item.maintenance_type_name, "is_due": item.is_due, "is_warning": item.is_warning}
                for item in attention
            ]

            if items_needing_attention:
                for item in attention:
                    try:
                        await mqtt_relay.on_maintenance_alert(
                            printer_id=printer_id,
                            printer_name=printer_name,
                            maintenance_type=item.maintenance_type_name,
                            current_value=item.days_since_maintenance
                            if item.interval_type == "days"
                            else item.hours_since_maintenance,
                            threshold=item.interval_hours,
                            unit=item.interval_type,
                        )
                    except Exception:
                        logger.debug("Could not relay maintenance event", exc_info=True)
                await notification_service.on_maintenance_due(printer_id, printer_name, items_needing_attention, db)
                logger.info("[MAINT-BG] Sent notification: %s items need attention", len(items_needing_attention))
            else:
                logger.info("[MAINT-BG] Completed (no items need attention)")
    except Exception as e:
        logger.warning("[MAINT-BG] Failed: %s", e)


async def complete_layer_timelapse(
    printer_id,
    print_status,
    archive_id,
    logger,
    *,
    async_session,
    ArchiveService,
    asyncio,
    expected_session=None,
    plate_id=None,
    run_id=None,
):
    """Stitch layer timelapse and attach to archive."""
    from backend.app.services.layer_timelapse import cancel_session, on_print_complete as tl_complete

    session_guard = {"expected_session": expected_session} if expected_session is not None else {}
    timelapse_path = None
    try:
        if print_status == "completed":
            logger.info("[LAYER-TL] Stitching layer timelapse for printer %s", printer_id)
            async with async_session() as db:
                previous = await ArchiveService(db).get_archive(archive_id) if archive_id else None
                source = previous
                if run_id is not None and previous is not None:
                    from backend.app.services.print_run_media import run_of

                    source = await run_of(db, archive_id, run_id, printer_id=printer_id)
                run_started_at = source.started_at if source is not None else None
            timelapse_path = await tl_complete(printer_id, **session_guard)
            if timelapse_path and source is not None:
                timelapse_data = await asyncio.to_thread(timelapse_path.read_bytes)
                async with async_session() as db:
                    await ArchiveService(db).attach_timelapse(
                        archive_id,
                        timelapse_data,
                        "layer_timelapse.mp4",
                        expected_started_at=run_started_at,
                        **({"plate_id": plate_id} if plate_id is not None else {}),
                        **({"run_id": run_id, "printer_id": printer_id} if run_id is not None else {}),
                    )
        else:
            # Print failed or cancelled - cancel timelapse session
            cancel_session(printer_id, **session_guard)
            logger.info("[LAYER-TL] Cancelled layer timelapse for printer %s (status: %s)", printer_id, print_status)
    except Exception as e:
        logger.warning("[LAYER-TL] Failed: %s", e)

    finally:
        if timelapse_path:
            await asyncio.to_thread(timelapse_path.unlink, missing_ok=True)


def check_kprofile_status(printer_id, state, spawn_background_task, logger) -> None:
    # A K-only push bypasses on_ams_change and status broadcast deduplication.
    # The recovery pass uses current assignment/context evidence, idle only.
    from backend.app.services import kprofile_drift

    try:
        if not state.connected:
            kprofile_drift.forget_printer(printer_id)
        elif kprofile_drift.needs_check(printer_id, state):
            spawn_background_task(
                kprofile_drift.reapply_lost_kprofiles(printer_id),
                name=f"reapply-kprofiles-{printer_id}",
            )
    except Exception:
        logger.exception("Printer %d K-profile check failed", printer_id)


async def backfill_completed_batches(async_session) -> None:
    # Close out batches that finished before `completed` was a reachable status
    # (#342). Without this the Batches tab opens on every batch created since
    # the feature shipped, all still marked active. Never blocks startup.
    try:
        from backend.app.services.print_batch import backfill_batch_statuses

        async with async_session() as batch_db:
            await backfill_batch_statuses(batch_db)
    except Exception as exc:
        logging.warning("[BATCH] Startup status backfill failed: %s", exc)
