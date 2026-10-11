"""Bounded side tasks for printer callbacks and application startup."""

import logging

from sqlalchemy import select


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
    asyncio,
):
    # Plate detection check - pause if objects detected on build plate
    logger.info(
        f"[PLATE CHECK] printer_id={printer_id}, plate_detection_enabled={printer.plate_detection_enabled if printer else 'NO PRINTER'}"
    )
    if printer and printer.plate_detection_enabled:
        logger.info("[PLATE CHECK] ENTERING plate detection code for printer %s", printer_id)
        try:
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

            # Auto-turn on chamber light if it's off for better detection
            light_was_off = False
            client = printer_manager.get_client(printer_id)
            plate_image_data = None
            try:
                if client and client.state:
                    light_was_off = not client.state.chamber_light
                    if light_was_off:
                        logger.info("[PLATE CHECK] Turning on chamber light for printer %s", printer_id)
                        client.set_chamber_light(True)
                        # Wait for light to physically turn on and camera to adjust exposure
                        await asyncio.sleep(2.5)

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

                if not plate_result.needs_calibration and not plate_result.is_empty:
                    if client:
                        client.pause_print()
                        logger.info("[PLATE CHECK] Print paused for printer %s", printer_id)
                    plate_image_data = await _capture_snapshot_for_notification(printer_id, printer, logger)
            finally:
                if light_was_off and client:
                    logger.info("[PLATE CHECK] Restoring chamber light to off for printer %s", printer_id)
                    client.set_chamber_light(False)

            if not plate_result.needs_calibration and not plate_result.is_empty:
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
            else:
                logger.info("[PLATE CHECK] Plate is empty for printer %s, proceeding with print", printer_id)
        except Exception as plate_err:
            # Don't block print on plate detection errors
            logger.warning("[PLATE CHECK] Plate detection failed for printer %s: %s", printer_id, plate_err)


async def calculate_print_energy(
    printer_id,
    archive_id,
    logger,
    *,
    async_session,
    read_printer_energy,
    _get_plug_energy,
):
    """Calculate energy from the persisted start reading without blocking."""
    try:
        logger.info("[ENERGY-BG] Starting energy calculation for archive %s", archive_id)
        async with async_session() as db:
            from backend.app.models.archive import PrintArchive

            archive = await db.get(PrintArchive, archive_id)
            if archive is None:
                logger.warning("[ENERGY-BG] Archive %s no longer exists", archive_id)
                return
            starting_kwh, starting_plug_id = archive.energy_start_kwh, archive.energy_start_plug_id
            if starting_kwh is None or not isinstance(starting_plug_id, int):
                logger.info("[ENERGY-BG] No start energy source recorded for archive %s", archive_id)
                return

            selected = await read_printer_energy(
                db,
                printer_id,
                _get_plug_energy,
                log_prefix="ENERGY-BG",
                context=f"archive {archive_id}",
                plug_id=starting_plug_id,
            )
            if selected is None:
                return
            plug, energy = selected
            logger.info("[ENERGY-BG] Energy response from plug '%s': %s", plug.name, energy)

            energy_used = round(energy["total"] - starting_kwh, 4)
            logger.info("[ENERGY-BG] Per-print energy: %s kWh", energy_used)
            if energy_used < 0:
                logger.warning(
                    "[ENERGY-BG] Negative energy delta for archive %s (start=%s, end=%s) — counter reset?",
                    archive_id,
                    starting_kwh,
                    energy["total"],
                )
                return

            from backend.app.api.routes.settings import get_setting

            energy_cost_per_kwh = await get_setting(db, "energy_cost_per_kwh")
            cost_per_kwh = float(energy_cost_per_kwh) if energy_cost_per_kwh else 0.15
            energy_cost_value = round(energy_used * cost_per_kwh, 3)

            # Do not let reprints clobber source-archive energy (#1378).
            from sqlalchemy import func

            from backend.app.models.print_log import PrintLogEntry

            existing_runs = await db.scalar(
                select(func.count(PrintLogEntry.id)).where(PrintLogEntry.archive_id == archive_id)
            )
            if (existing_runs or 0) <= 1:
                # 0 = legacy archive that pre-dates per-run logging; 1 = the row
                # we just wrote for THIS print. Either way it's the first run.
                archive.energy_kwh = energy_used
                archive.energy_cost = energy_cost_value

            # Backfill the latest PrintLogEntry for this archive with energy
            # (write_log_entry above ran before this background task completed,
            # so energy fields are still NULL on that row).
            latest_run = await db.execute(
                select(PrintLogEntry)
                .where(PrintLogEntry.archive_id == archive_id)
                .order_by(PrintLogEntry.id.desc())
                .limit(1)
            )
            run_row = latest_run.scalar_one_or_none()
            if run_row is not None:
                run_row.energy_kwh = energy_used
                run_row.energy_cost = energy_cost_value

            await db.commit()
            logger.info("[ENERGY-BG] Saved: %s kWh, cost=%s", energy_used, energy_cost_value)
    except Exception as e:
        logger.warning("[ENERGY-BG] Failed: %s", e)


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

            items_needing_attention = [
                {"name": item.maintenance_type_name, "is_due": item.is_due, "is_warning": item.is_warning}
                for item in overview.maintenance_items
                if item.enabled and (item.is_due or item.is_warning)
            ]

            if items_needing_attention:
                await notification_service.on_maintenance_due(printer_id, printer_name, items_needing_attention, db)
                logger.info("[MAINT-BG] Sent notification: %s items need attention", len(items_needing_attention))

                # MQTT relay - publish maintenance alerts
                for item in items_needing_attention:
                    try:
                        await mqtt_relay.on_maintenance_alert(
                            printer_id=printer_id,
                            printer_name=printer_name,
                            maintenance_type=item["name"],
                            current_value=0,  # Not easily available here
                            threshold=0,  # Not easily available here
                        )
                    except Exception:
                        pass  # Don't fail if MQTT fails
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
):
    """Stitch layer timelapse and attach to archive."""
    from backend.app.services.layer_timelapse import cancel_session, on_print_complete as tl_complete

    try:
        if print_status == "completed":
            logger.info("[LAYER-TL] Stitching layer timelapse for printer %s", printer_id)
            timelapse_path = await tl_complete(printer_id)
            if timelapse_path and archive_id:
                logger.info("[LAYER-TL] Attaching timelapse %s to archive %s", timelapse_path, archive_id)
                async with async_session() as db:
                    service = ArchiveService(db)
                    timelapse_data = await asyncio.to_thread(timelapse_path.read_bytes)
                    await service.attach_timelapse(archive_id, timelapse_data, "layer_timelapse.mp4")
                    # Clean up the temp file
                    await asyncio.to_thread(timelapse_path.unlink, missing_ok=True)
                    logger.info("[LAYER-TL] Layer timelapse attached successfully")
            elif timelapse_path:
                # Timelapse created but no archive - just clean up
                await asyncio.to_thread(timelapse_path.unlink, missing_ok=True)
        else:
            # Print failed or cancelled - cancel timelapse session
            cancel_session(printer_id)
            logger.info("[LAYER-TL] Cancelled layer timelapse for printer %s (status: %s)", printer_id, print_status)
    except Exception as e:
        logger.warning("[LAYER-TL] Failed: %s", e)
        # Try to cancel session on error
        try:
            cancel_session(printer_id)
        except Exception:
            pass  # Best-effort timelapse session cancellation on error


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
