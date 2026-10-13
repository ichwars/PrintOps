"""Evaluate humidity-triggered drying without moving scheduler ownership."""

from sqlalchemy import select

from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.services.ambient_humidity import read_humidity


async def check_auto_drying(
    self,
    db,
    queue_items,
    busy_printers,
    *,
    require_plate_clear,
    printer_manager,
    reserved_printers,
    supports_drying,
    supports_drying_while_printing,
    start_drying,
    time,
    logger,
):
    """Start drying on idle printers based on humidity.

    Three modes (can all be enabled independently):
    - queue_drying_enabled: Dry between scheduled queue prints
    - ambient_drying_enabled: Dry any idle printer when humidity is high, regardless of queue
    - print_drying_enabled: Also evaluate printers that are currently printing,
      when model+firmware supports "Print While Drying" (gated by
      supports_drying_while_printing). Drying temperature is capped at
      max(40, preset_temp - 5) to protect spools mid-print.
    """
    queue_drying_enabled = await self._get_bool_setting(db, "queue_drying_enabled")
    ambient_drying_enabled = await self._get_bool_setting(db, "ambient_drying_enabled")
    print_drying_enabled = await self._get_bool_setting(db, "print_drying_enabled")
    sustained_minutes = 0
    if ambient_drying_enabled:
        result = await db.execute(select(Settings).where(Settings.key == "ambient_drying_sustained_minutes"))
        setting = result.scalar_one_or_none()
        sustained_minutes = int(setting.value) if setting else 0
    if not ambient_drying_enabled:
        self._ambient_humidity.streaks.clear()
    if not queue_drying_enabled and not ambient_drying_enabled and not print_drying_enabled:
        # Stop our active drying when all automatic modes are disabled
        if self._drying_in_progress:
            for pid in list(self._drying_in_progress):
                logger.info("Auto-drying: printer %d — stopping, auto-drying disabled", pid)
                await self._stop_drying(pid)
        return

    # Reconcile only AMS cycles successfully started by this scheduler
    self._sync_drying_state()

    # Find printers with scheduled items (for queue drying mode)
    printers_with_scheduled: set[int] = set()
    printers_with_items: set[int] = set()
    for item in queue_items:
        if item.printer_id:
            printers_with_items.add(item.printer_id)
            if item.scheduled_time and not item.manual_start:
                printers_with_scheduled.add(item.printer_id)

    # If only queue mode is on and no printers have scheduled items, stop drying
    # (but skip this short-circuit when print_drying_enabled is on — busy printers
    # may still be eligible for mid-print drying regardless of queue state).
    if not ambient_drying_enabled and not printers_with_scheduled and not print_drying_enabled:
        for pid in list(self._drying_in_progress):
            logger.info("Auto-drying: printer %d — stopping, no scheduled prints in queue", pid)
            await self._stop_drying(pid)
        return

    # Get humidity threshold (global fallback)
    result = await db.execute(select(Settings).where(Settings.key == "ams_humidity_fair"))
    setting = result.scalar_one_or_none()
    global_humidity_threshold = int(setting.value) if setting else 60

    # Per-filament humidity threshold overrides (#1605). Empty → fall back
    # to the global threshold for every AMS unit.
    per_type_thresholds = await self._get_humidity_thresholds(db)

    # Get drying presets
    presets = await self._get_drying_presets(db)

    # Determine if drying should be skipped for printers with pending items
    block_for_drying = await self._get_bool_setting(db, "queue_drying_block")

    # Get all active printers
    scheduled_owners = await reserved_printers(db)
    all_printers = await db.execute(select(Printer).where(Printer.is_active.is_(True)))
    printers = list(all_printers.scalars())
    active_ids = {printer.id for printer in printers}
    tracked_ids = {key[0] for key in self._ambient_humidity.streaks} | set(self._drying_owned_ams)
    for pid in tracked_ids - active_ids:
        self._ambient_humidity.clear_printer(pid)
        self._drying_in_progress.pop(pid, None)
        self._drying_owned_ams.pop(pid, None)
    now = time.monotonic()
    for printer in printers:
        pid = printer.id
        if pid in scheduled_owners:
            self._ambient_humidity.clear_printer(pid)
            continue

        # Resolve model+firmware up front — needed to decide whether this printer
        # qualifies for mid-print drying (busy printer on capable hardware).
        state = printer_manager.get_status(pid)
        if not state:
            self._ambient_humidity.clear_printer(pid)
            logger.debug("Auto-drying: printer %d skipped — no state", pid)
            continue
        if not printer_manager.is_connected(pid):
            self._ambient_humidity.clear_printer(pid)
            continue
        ready_ams = (
            self._ambient_humidity.observe(
                pid,
                state.raw_data.get("ams", []),
                per_type_thresholds,
                global_humidity_threshold,
                self.resolve_humidity_threshold,
                sustained_minutes,
                now,
                max(4 * self._check_interval, 120),
            )
            if ambient_drying_enabled
            else set()
        )
        model = printer_manager.get_model(pid)
        firmware = state.firmware_version

        mid_print = pid in busy_printers and print_drying_enabled and supports_drying_while_printing(model, firmware)

        if pid in busy_printers and not mid_print:
            logger.debug("Auto-drying: printer %d skipped — busy", pid)
            continue

        if not mid_print:
            # In queue-only mode, only dry printers that have scheduled prints
            if not ambient_drying_enabled and pid not in printers_with_scheduled:
                if self._drying_in_progress.get(pid):
                    logger.info("Auto-drying: printer %d — stopping, no scheduled prints for this printer", pid)
                    await self._stop_drying(pid)
                logger.debug("Auto-drying: printer %d skipped — no scheduled prints", pid)
                continue
            # When block mode is on, don't START new drying on printers with pending items.
            # But allow already-drying printers through so humidity auto-stop logic still runs.
            if block_for_drying and pid in printers_with_items and not self._drying_in_progress.get(pid):
                logger.debug("Auto-drying: printer %d skipped — has pending items (block mode)", pid)
                continue
        if not printer_manager.is_connected(pid):
            logger.debug("Auto-drying: printer %d skipped — not connected", pid)
            continue
        if not mid_print and not self._is_printer_idle(pid, require_plate_clear):
            logger.debug("Auto-drying: printer %d skipped — not idle", pid)
            continue

        # Check drying capability. For mid-print path, supports_drying_while_printing
        # was already verified when computing mid_print above.
        if not mid_print and not supports_drying(model, firmware):
            logger.debug("Auto-drying: printer %d skipped — model %s does not support drying", pid, model)
            continue

        # Check each AMS unit from raw_data
        ams_list = state.raw_data.get("ams", [])
        logger.debug("Auto-drying: printer %d — checking %d AMS units", pid, len(ams_list))
        for ams_data in ams_list:
            module_type = str(ams_data.get("module_type") or "")
            ams_id = int(ams_data.get("id", 0))
            # Only n3f/n3s support drying
            if module_type not in ("n3f", "n3s"):
                logger.debug("Auto-drying: printer %d AMS %d skipped — module_type=%s", pid, ams_id, module_type)
                continue

            # Resolve per-filament humidity threshold for this AMS unit (#1605).
            # Most-restrictive of all loaded tray types; falls back to the
            # global threshold when no overrides are configured.
            trays = ams_data.get("tray", []) or []
            humidity_threshold = self.resolve_humidity_threshold(trays, per_type_thresholds, global_humidity_threshold)

            dry_time = int(ams_data.get("dry_time") or 0)

            humidity = read_humidity(ams_data)
            # Already drying — let it run to its configured duration (#1892).
            #
            # We deliberately do NOT stop drying from a humidity re-check here.
            # Relative humidity drops steeply in heated air, so the AMS sensor
            # reads ~15-20% within minutes of the dryer starting even while the
            # filament is still saturated. A humidity-based early-stop therefore
            # always fires at the minimum-time floor, truncating both user-started
            # manual cycles and PrintOps's own preset-duration dries to ~30 min.
            # The firmware stops when the configured duration elapses; scheduling
            # stops (print takes priority, queue no longer needs drying) are
            # handled separately via _stop_drying().
            if dry_time > 0:
                logger.debug(
                    "Auto-drying: printer %d AMS %d — drying (%dm left, humidity %s%%), letting it run",
                    pid,
                    ams_id,
                    dry_time,
                    humidity,
                )
                continue

            # Humidity below threshold — no need to start drying
            if humidity is None or humidity <= humidity_threshold:
                logger.debug(
                    "Auto-drying: printer %d AMS %d skipped — humidity %s <= threshold %d",
                    pid,
                    ams_id,
                    humidity,
                    humidity_threshold,
                )
                continue

            # Queue deadlines and print-only drying are exempt from ambient waiting.
            if ambient_drying_enabled and pid not in printers_with_scheduled and ams_id not in ready_ams:
                continue

            # Check cannot-dry reasons (power constraints etc.)
            sf_reasons = ams_data.get("dry_sf_reason", [])
            if sf_reasons:
                logger.debug(
                    "Auto-drying: printer %d AMS %d skipped — cannot dry reasons: %s",
                    pid,
                    ams_id,
                    sf_reasons,
                )
                continue

            # Get conservative drying params for mixed filaments
            params = self._get_conservative_drying_params(trays, module_type, presets)
            if not params:
                logger.debug(
                    "Auto-drying: printer %d AMS %d skipped — no drying-eligible filaments in trays", pid, ams_id
                )
                continue

            temp, duration_hours, filament_type = params

            # Mid-print drying: cap drying temperature to protect spools (Bambu warns
            # "drying temperature must not exceed the filament's softening temperature"
            # for Print While Drying). Floor at 40 degC — below that the dryer is
            # ineffective and firmware will reject anyway.
            if mid_print:
                temp = max(40, temp - 5)

            # Start drying
            logger.info(
                "Auto-drying: printer %d AMS %d — humidity %d%% > threshold %d%%, starting %s drying at %d°C for %dh%s",
                pid,
                ams_id,
                humidity,
                humidity_threshold,
                filament_type,
                temp,
                duration_hours,
                " (mid-print)" if mid_print else "",
            )
            success = await start_drying(db, printer_manager, pid, ams_id, temp, duration_hours, filament_type)
            if success:
                self._drying_in_progress[pid] = time.monotonic()
                self._drying_owned_ams.setdefault(pid, set()).add(ams_id)
                self._ambient_humidity.streaks.pop((pid, ams_id), None)
