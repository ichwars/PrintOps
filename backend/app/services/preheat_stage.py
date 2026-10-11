"""Queue preheat target resolution and the existing warm-up/soak stage."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.services.bambu_ftp import _upload_deadline
from backend.app.services.preheat_ownership import current_preheat_lease, preheat_ownership
from backend.app.services.printer_manager import supports_airduct, supports_chamber_heater, supports_chamber_temp
from backend.app.utils.threemf_tools import extract_bed_temperature_from_3mf

logger = logging.getLogger(__name__)


async def preheat_and_soak(
    self,
    db: AsyncSession,
    item: PrintQueueItem,
    printer: Printer,
    archive: PrintArchive | None,
    printer_manager,
    ftp_settings,
) -> None:
    """Run the per-printer preheat + heat-soak stage before FTP upload (#1468).

    Resolution order:
      1. `item.preheat_override` — 'off' skips entirely; 'inherit' falls back
         to the global `preheat_enabled` setting; 'on' forces the stage on
         even if the global is off.
      2. Chamber target — `item.preheat_chamber_target_override` if non-null;
         else max of `preheat_filament_targets[normalize(t.tray_type)]`
         across the trays selected by this plate's AMS mapping; else 0
         (skips chamber phase, keeps bed phase + soak timer).
      3. Three hardware tiers branch the wait loop:
         - Chamber heater (H2C/H2D/H2DPro/H2S/X2D/X1E via supports_chamber_heater):
           send M141 to the resolved target, then wait for the chamber sensor
           to reach it (or the max-wait timeout to elapse).
         - Chamber sensor only (X1C/P2S via supports_chamber_temp ∧ ¬supports_chamber_heater):
           no M141; the bed is the only heat source, so we wait for the chamber
           sensor to rise via bed radiation OR fall through on timeout.
         - No chamber sensor (P1S/P1P/A1/A1 Mini): no way to verify chamber
           temperature; the function just heats the bed and holds for the
           configured soak duration.

    The bed target comes from the archive's parsed metadata
    (`bed_temperature`); if missing the preheat stage logs and returns
    without dispatching anything, rather than guessing at a default that
    might wreck filament setup.

    Failures are logged but never re-raised — preheat is best-effort. A
    printer that goes offline mid-soak, a refused gcode command, or a
    missing temperature reading must not turn into a failed queue item; the
    normal upload + start path runs immediately after this method returns.
    """
    override = (getattr(item, "preheat_override", None) or "inherit").lower()
    if override == "off":
        return
    if override == "inherit":
        enabled = await self._get_bool_setting(db, "preheat_enabled", default=False)
        if not enabled:
            return
    # override == "on" forces the stage on regardless of the global setting.

    max_wait = await self._get_int_setting(db, "preheat_max_wait_seconds", default=900)
    soak_seconds = await self._get_int_setting(db, "preheat_soak_seconds", default=300)

    # Chamber target resolution:
    #   1. Explicit per-item override beats everything (user knows best).
    #   2. Otherwise derive from the filament trays this plate maps via the
    #      per-filament target map. A parked ASA spool cannot affect PLA.
    explicit_target = getattr(item, "preheat_chamber_target_override", None)
    if explicit_target is not None and explicit_target > 0:
        chamber_target = int(explicit_target)
        chamber_source = "item-override"
    elif explicit_target == 0:
        chamber_target = 0  # explicit 0 means "no chamber, even if filament wants it"
        chamber_source = "item-override-zero"
    else:
        targets = await self._get_preheat_filament_targets(db)
        chamber_target = self._derive_chamber_target(printer, targets, item)
        chamber_source = "filament-map"

    plate_id = getattr(item, "plate_id", None)
    if archive and plate_id is not None:
        path = settings.base_dir / archive.file_path
        selected_temperature = extract_bed_temperature_from_3mf(path, plate_id)
        bed_target = int(selected_temperature) if selected_temperature else 0
    else:
        bed_target = int(archive.bed_temperature) if archive and archive.bed_temperature else 0
    if bed_target <= 0:
        logger.info(
            "Queue item %s: preheat skipped — archive has no bed_temperature metadata",
            item.id,
        )
        return

    client = printer_manager.get_client(printer.id)
    if client is None:
        logger.warning("Queue item %s: preheat skipped — printer client unavailable", item.id)
        return

    model = printer.model or ""
    has_heater = supports_chamber_heater(model)
    has_sensor = supports_chamber_temp(model)
    do_chamber = chamber_target > 0 and (has_heater or has_sensor)

    logger.info(
        "Queue item %s: preheat starting — bed=%d°C chamber_target=%d°C (source=%s override=%s "
        "model=%s has_heater=%s has_sensor=%s) max_wait=%ds soak=%ds",
        item.id,
        bed_target,
        chamber_target if do_chamber else 0,
        chamber_source,
        override,
        model,
        has_heater,
        has_sensor,
        max_wait,
        soak_seconds,
    )

    lease = current_preheat_lease()
    if lease:
        if preheat_ownership.blocks_power_off(printer.id) and preheat_ownership.leases.get(printer.id) is not lease:
            raise RuntimeError("Printer has unresolved preheat ownership")
        enabled, retries, delay, _ = await ftp_settings()
        upload_path = settings.base_dir / archive.file_path if archive else None
        upload_budget = _upload_deadline(upload_path) if upload_path else 600
        lifetime = max_wait + soak_seconds + upload_budget * (retries + 1 if enabled else 1) + retries * delay + 330
        try:
            lease.activate(lifetime)
        except OSError as exc:
            logger.warning("Queue item %s: cannot record preheat ownership, skipping heat: %s", item.id, exc)
            return

    # Dispatch heaters. set_bed_temperature / set_chamber_temperature already
    # cache the target locally so the polling reads below see consistent
    # state (firmware MQTT echoes lag by ~1s).
    try:
        sent = lease.command(client, "bed", bed_target) if lease else client.set_bed_temperature(bed_target)
        if not sent:
            logger.warning("Queue item %s: preheat bed command refused", item.id)
            return
    except Exception as exc:
        logger.warning("Queue item %s: preheat bed M140 failed: %s", item.id, exc)
        return

    # Airduct mode (#1468 follow-up). Models with the cooling/heating flap
    # (H2C/H2D/H2D Pro/H2S/X2D/P2S) keep the flap whatever the user last
    # left it on, regardless of M141. Default cooling actively vents the
    # chamber, so a `chamber_target > 0` print with the flap stuck in
    # cooling never converges — the heater fights the open exhaust. We
    # flip the flap BEFORE M141 to "heating" when the preheat wants
    # chamber heat, and back to "cooling" when it doesn't (PLA-only print
    # on an H2D that was previously running ABS would otherwise stay in
    # heating mode and overheat PLA). The current-state read keeps the
    # command idempotent — no MQTT chatter when the flap is already where
    # we want it.
    if supports_airduct(model):
        desired_airduct = "heating" if chamber_target > 0 else "cooling"
        desired_id = 1 if desired_airduct == "heating" else 0
        current_state = printer_manager.get_status(printer.id)
        current_airduct = getattr(current_state, "airduct_mode", None) if current_state else None
        if current_airduct != desired_id:
            try:
                client.set_airduct_mode(desired_airduct)
            except Exception as exc:
                logger.warning(
                    "Queue item %s: preheat airduct %s mode failed: %s",
                    item.id,
                    desired_airduct,
                    exc,
                )

    if do_chamber and has_heater:
        try:
            if lease:
                lease.command(client, "chamber", chamber_target)
            else:
                client.set_chamber_temperature(chamber_target)
        except Exception as exc:
            logger.warning("Queue item %s: preheat chamber M141 failed: %s", item.id, exc)

    # Wait for convergence. Bed warm-up is fast (~5 min from cold); chamber
    # via M141 takes a few minutes; chamber via bed radiation can take 20+.
    # Poll every 3s — frequent enough for responsive logging without
    # spamming the MQTT state stream. The "converged" predicate is:
    #   bed reached target (within 2°C tolerance for floating-point + heater hysteresis),
    #   AND
    #   chamber phase satisfied (no chamber phase, no sensor, or sensor reached target).
    BED_TOLERANCE = 2.0
    CHAMBER_TOLERANCE = 2.0
    POLL_INTERVAL = 3.0
    deadline = asyncio.get_event_loop().time() + max_wait

    while True:
        state = printer_manager.get_status(printer.id)
        if state is None:
            logger.warning("Queue item %s: preheat lost state during wait", item.id)
            break

        temps = state.temperatures or {}
        bed_now = float(temps.get("bed", 0) or 0)
        chamber_now = float(temps.get("chamber", 0) or 0)
        bed_ok = bed_now >= bed_target - BED_TOLERANCE

        if not do_chamber:
            chamber_ok = True  # phase disabled or model has neither sensor nor heater
        elif not has_sensor:
            chamber_ok = True  # P1S etc — can't read, rely on soak timer only
        else:
            chamber_ok = chamber_now >= chamber_target - CHAMBER_TOLERANCE

        if bed_ok and chamber_ok:
            logger.info(
                "Queue item %s: preheat target reached (bed=%.1f chamber=%.1f) — entering soak",
                item.id,
                bed_now,
                chamber_now,
            )
            break

        if asyncio.get_event_loop().time() >= deadline:
            logger.info(
                "Queue item %s: preheat max_wait reached (bed=%.1f/%d chamber=%.1f/%d) — falling through to soak",
                item.id,
                bed_now,
                bed_target,
                chamber_now,
                chamber_target if do_chamber else 0,
            )
            break

        await asyncio.sleep(POLL_INTERVAL)

    if soak_seconds > 0:
        logger.info("Queue item %s: preheat soak — holding for %ds", item.id, soak_seconds)
        await asyncio.sleep(soak_seconds)

    logger.info("Queue item %s: preheat complete — proceeding to upload", item.id)
