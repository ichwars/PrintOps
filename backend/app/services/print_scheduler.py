"""Print scheduler service - processes the print queue."""

import asyncio
import json
import logging
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.database import async_session, run_with_retry
from backend.app.core.tasks import spawn_background_task
from backend.app.core.websocket import ws_manager
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem, PrintQueueVariant
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.models.smart_plug import SmartPlug
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.archive_plate_metadata import refresh_archive_plate_metadata
from backend.app.services.automatic_drying_dispatch import check_auto_drying
from backend.app.services.automatic_drying_state import init_drying_state, start_drying, stop_drying, sync_drying_state
from backend.app.services.bambu_ftp import (
    FtpFailureKind,
    FtpFailureReport,
    UploadCancelled,
    cache_3mf_download,
    delete_file_async,
    describe_upload_failure,
    get_ftp_retry_settings,
    upload_file_async,
    with_ftp_retry,
)
from backend.app.services.drying_ownership import claim_queue_item, reserved_printers
from backend.app.services.filament_deficit import compute_deficit_for_queue_item
from backend.app.services.filament_low_monitor import FilamentLowMonitor
from backend.app.services.ha_sensor_manager import ha_sensor_manager
from backend.app.services.library_queue_references import (
    consume_transient_library_source,
    fail_missing_library_source,
)
from backend.app.services.notification_service import notification_service
from backend.app.services.preheat_chamber import derive_chamber_target, normalize_filament_type
from backend.app.services.preheat_config import DEFAULT_PREHEAT_FILAMENT_TARGETS, parse_preheat_filament_targets
from backend.app.services.preheat_ownership import current_preheat_lease, preheat_ownership
from backend.app.services.preheat_stage import preheat_and_soak
from backend.app.services.print_completion_identity import StrandedPrintRecovery, clear_stale_dispatch_claims
from backend.app.services.printer_manager import (
    printer_manager,
    supports_drying,
    supports_drying_while_printing,
)
from backend.app.services.queue_keep_warm import QueueKeepWarm
from backend.app.services.scheduled_drying import scheduled_drying
from backend.app.services.smart_plug_manager import smart_plug_manager
from backend.app.services.smart_plug_selection import (
    pick_power_plug as select_power_plug,
    plugs_for_printer,
)
from backend.app.services.spoolman_sku_reconciliation import SpoolmanSkuReconciler
from backend.app.services.stock_alert_monitor import StockAlertMonitor
from backend.app.utils.filename import derive_remote_filename
from backend.app.utils.printer_models import is_gcode_compatible, normalize_printer_model
from backend.app.utils.threemf_tools import default_plate_number

logger = logging.getLogger(__name__)

# Dispatch-toast progress throttling (#1625 follow-up). Mirrors the legacy
# background_dispatch.py upload_progress_callback (200 ms time gate + 256 KB
# byte gate) from before the scheduler unification. Time gate keeps small
# files from going silent (a single 8 KB chunk fires once and that's it);
# byte gate caps the broadcast rate on slow LAN where 200 ms covers many
# chunks. uploaded >= total always emits so the bar closes cleanly even on
# sub-200 ms files.
_DISPATCH_PROGRESS_BYTE_STEP = 256 * 1024
_DISPATCH_PROGRESS_MIN_INTERVAL_SECS = 0.2

_UPLOAD_REQUEUE_KINDS = frozenset(
    {FtpFailureKind.HANDSHAKE, FtpFailureKind.COOLOFF, FtpFailureKind.TIMEOUT, FtpFailureKind.NETWORK}
)
UPLOAD_FAILURE_BACKOFF_SECONDS = 300
UPLOAD_FAILURE_BACKOFF_MAX_SECONDS = 3600


def _upload_backoff_seconds(refusals: int) -> int:
    # Clamp the exponent before computing it, even during very long outages.
    return min(UPLOAD_FAILURE_BACKOFF_SECONDS * 2 ** min(max(refusals - 1, 0), 4), UPLOAD_FAILURE_BACKOFF_MAX_SECONDS)


def _effective_plate_id(explicit_plate_id: int | None, file_path: Path) -> int:
    """Resolve one plate for injection, usage registration and dispatch.

    A positive explicit selection wins even if absent from the archive;
    redirecting it would print an unrequested model. Unset/non-positive IDs
    use the archive's default G-code number because a lone exported plate can
    retain e.g. ``plate_2.gcode``. Unreadable or unnumbered files retain the
    existing plate-1 fallback.
    """
    if explicit_plate_id is not None and explicit_plate_id > 0:
        return explicit_plate_id
    try:
        with zipfile.ZipFile(file_path) as zf:
            resolved = default_plate_number(zf.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        logger.warning("Dispatch plate: cannot read %s (%s); falling back to plate 1", file_path, exc)
        return 1
    return resolved if resolved is not None else 1


class _UploadProgressBridge:
    """Thread-safe bridge from ``upload_file_async`` to the WS broadcaster.

    ``upload_file_async`` runs the FTP transfer in an executor thread and
    invokes its ``progress_callback`` from that thread, so the callback
    body cannot ``await`` directly. This bridge captures the asyncio loop
    at construction (on the scheduler thread) and uses
    ``run_coroutine_threadsafe`` to hop back. The byte/time throttle
    matches the legacy background_dispatch.py path 1:1 so the toast feels
    identical to the pre-#1625 experience.

    Failures inside the emit are swallowed — progress is a UX nicety, the
    upload itself must not fail because of a WS hiccup.
    """

    def __init__(self, user_id: int | None, queue_item_id: int):
        self._user_id = user_id
        self._queue_item_id = queue_item_id
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._last_emit_bytes = 0
        self._last_emit_monotonic = 0.0
        self._has_emitted = False

    def __call__(self, bytes_transferred: int, total_bytes: int) -> None:
        if self._loop is None or total_bytes <= 0:
            return
        now = time.monotonic()
        # Mirrors legacy bg-dispatch: emit if first call OR upload complete
        # OR 200 ms elapsed OR ≥256 KB transferred since last emit. Two of
        # the four matter most: first-call so the user sees something even
        # for sub-chunk-size files; uploaded >= total so the bar locks at
        # 100% even when the throttle would otherwise eat it.
        should_emit = (
            not self._has_emitted
            or bytes_transferred >= total_bytes
            or now - self._last_emit_monotonic >= _DISPATCH_PROGRESS_MIN_INTERVAL_SECS
            or bytes_transferred - self._last_emit_bytes >= _DISPATCH_PROGRESS_BYTE_STEP
        )
        if not should_emit:
            return
        self._has_emitted = True
        self._last_emit_bytes = bytes_transferred
        self._last_emit_monotonic = now
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.send_queue_item_upload_progress(
                    user_id=self._user_id,
                    queue_item_id=self._queue_item_id,
                    bytes_transferred=bytes_transferred,
                    total_bytes=total_bytes,
                ),
                self._loop,
            )
        except Exception:
            pass  # progress is best-effort, never block the upload


# Bambu firmware states that mean the project_file has actually been accepted
# and the printer is now processing / running / paused mid-print. Used by the
# dispatch watchdog (#1370): a transition into one of these states means the
# print landed, anything else (e.g. FINISH -> IDLE after the user dismisses
# a post-print prompt) is NOT a valid "command landed" signal even though the
# state value did change. SLICING is included because some firmwares park
# briefly in SLICING between PREPARE and RUNNING while parsing the g-code.
_ACTIVE_PRINT_STATES: frozenset[str] = frozenset({"PREPARE", "SLICING", "RUNNING", "PAUSE"})

# Bound retries for printers that accept a project_file but never transition
# into an active print state. Each retry costs a full 3MF upload plus watchdog
# wait, so unbounded retries can starve the rest of a farm.
DISPATCH_MAX_ATTEMPTS = 3

# Filament type equivalence groups — types within the same group are
# interchangeable on the printer side (Bambu Lab firmware treats them as compatible).
_FILAMENT_TYPE_GROUPS: list[list[str]] = [
    ["PA-CF", "PA12-CF", "PAHT-CF"],
]
_FILAMENT_EQUIV_MAP: dict[str, str] = {}
for _group in _FILAMENT_TYPE_GROUPS:
    _canonical = _group[0].upper()
    for _t in _group:
        _FILAMENT_EQUIV_MAP[_t.upper()] = _canonical


def _canonical_filament_type(ftype: str) -> str:
    """Return canonical type for equivalence matching."""
    upper = ftype.upper()
    return _FILAMENT_EQUIV_MAP.get(upper, upper)


@dataclass(slots=True)
class _ModelCandidate:
    """One (file, printer model) pair the model-based matcher may try.

    Model-based assignment used to have exactly one of these per item, held
    directly in the item's own columns. Cross-model queue items (#671) have
    several, held in ``print_queue_variants``. Both shapes are normalised into
    this so the matching, the cross-model gate and the waiting-reason handling
    are written once and an item without variants provably takes the same path
    it took before variants existed.

    ``variant`` is None for the item's own columns and set for a real variant
    row, which is what :meth:`PrintScheduler._resolve_variant` writes onto the
    item once that candidate wins.
    """

    target_model: str | None
    sliced_for: str | None
    required_filament_types: str | None
    filament_overrides: str | None
    variant: "PrintQueueVariant | None" = None


def _sliced_for_model(archive, library_file) -> str | None:
    """Model a 3MF declares it was sliced for, from whichever source holds it."""
    if archive is not None:
        return archive.sliced_for_model
    if library_file is not None and library_file.file_metadata:
        return library_file.file_metadata.get("sliced_for_model")
    return None


def _candidates_for(item: PrintQueueItem) -> list[_ModelCandidate]:
    """Candidate files for ``item``, best first.

    An item with no variant rows yields exactly one candidate built from its own
    columns — the pre-#671 behaviour, unchanged.

    Variants come back least-attempted first, ties broken by the user's
    ``position``. On the first pass every count is zero, so this is purely the
    user's priority order. After a start-watchdog bounce the printer that failed
    drops behind, so the next lap tries the other machine rather than spending the
    item's whole retry budget on the one that is wedged. Once every candidate has
    been tried equally often they cycle again, which keeps the item-level
    ``DISPATCH_MAX_ATTEMPTS`` bound from #2555 intact — a job with alternatives
    still gives up, it just does not give up without trying them.
    """
    if not item.variants:
        if not item.archive_id and not item.library_file_id:
            # Nothing to print at all. Dispatching would fail deep in the upload
            # on "No archive_id or library_file_id"; the caller holds the item
            # with an explanation instead.
            return []
        return [
            _ModelCandidate(
                target_model=item.target_model,
                sliced_for=_sliced_for_model(item.archive, item.library_file),
                required_filament_types=item.required_filament_types,
                filament_overrides=item.filament_overrides,
            )
        ]

    # Drop candidates whose file is gone or in the trash. Both are reachable and
    # neither is covered by the schema: library deletes are soft (the row lives
    # on with ``deleted_at`` set, which no foreign key can express), and SQLite
    # ships with ``PRAGMA foreign_keys`` off, so the ON DELETE CASCADE never
    # fires there and a hard delete leaves the variant row pointing at nothing.
    usable = [v for v in item.variants if v.library_file is not None and v.library_file.deleted_at is None]

    ordered = sorted(usable, key=lambda v: (v.attempt_count or 0, v.position, v.id))
    return [
        _ModelCandidate(
            target_model=v.target_model,
            sliced_for=_sliced_for_model(None, v.library_file),
            required_filament_types=v.required_filament_types,
            filament_overrides=v.filament_overrides,
            variant=v,
        )
        for v in ordered
    ]


def _collapse_waiting_reasons(per_model: list[tuple[str | None, str]]) -> str | None:
    """Fold one waiting reason per candidate into a single line for the item.

    A cross-model item produces a reason per candidate, and pasting them
    together unlabelled reads as gibberish ("No idle printer; PETG not loaded"
    — on which machine?). Each reason is prefixed with its model, except in the
    single-candidate case where the item already displays its target model and
    the prefix would be noise.

    Identical reasons collapse rather than repeat, so three idle-less models
    read as one clause.

    When *every* candidate is merely busy the parts are joined with the ``" | "``
    separator :meth:`PrintScheduler._is_busy_only` already parses, and left
    unprefixed. That case must keep testing busy-only: a fleet that is simply
    printing needs no user action, and labelling the clauses would turn each pass
    over a two-model item into a "job waiting" notification.
    """
    reasons = [(model, reason) for model, reason in per_model if reason]
    if not reasons:
        return None
    if len(reasons) == 1:
        return reasons[0][1]

    distinct = list(dict.fromkeys(reason for _model, reason in reasons))
    if len(distinct) == 1:
        return distinct[0]

    if all(PrintScheduler._is_busy_only(reason) for _model, reason in reasons):
        return " | ".join(distinct)

    return "; ".join(f"{model or 'unassigned'}: {reason}" for model, reason in reasons)


def _candidate_model_label(candidates: list[_ModelCandidate]) -> str | None:
    """Human label for the models an item is waiting on ("H2S or H2C").

    Notifications take a single target model. For a cross-model item the item's
    own ``target_model`` is whichever variant happens to be first, which reads as
    a lie once it is the H2C that actually runs — so name all of them.
    """
    models = list(dict.fromkeys(c.target_model for c in candidates if c.target_model))
    if not models:
        return None
    return " or ".join(models)


def _mapping_is_all_unresolved(mapping: list | None) -> bool:
    """Return True for a non-empty mapping made only of unresolved slots."""
    if not isinstance(mapping, list) or not mapping:
        return False
    return all(slot is None or (isinstance(slot, int) and slot < 0) for slot in mapping)


def _could_take_printer(item: PrintQueueItem, printer_id: int, printer_model: str | None) -> bool:
    if item.printer_id is not None:
        return item.printer_id == printer_id
    if not printer_model:
        return False
    wanted = (normalize_printer_model(printer_model) or printer_model).lower()
    models = [v.target_model for v in item.variants] if item.variants else [item.target_model]
    return any(model and (normalize_printer_model(model) or model).lower() == wanted for model in models)


class PrintScheduler:
    """Background scheduler that processes the print queue."""

    # Built-in drying presets per filament type (from BambuStudio filament profiles)
    # Format: { n3f_temp, n3s_temp, n3f_hours, n3s_hours }
    DEFAULT_DRYING_PRESETS: dict[str, dict[str, int]] = {
        "PLA": {"n3f": 45, "n3s": 45, "n3f_hours": 12, "n3s_hours": 12},
        "PETG": {"n3f": 65, "n3s": 65, "n3f_hours": 12, "n3s_hours": 12},
        "TPU": {"n3f": 65, "n3s": 75, "n3f_hours": 12, "n3s_hours": 18},
        "ABS": {"n3f": 65, "n3s": 80, "n3f_hours": 12, "n3s_hours": 8},
        "ASA": {"n3f": 65, "n3s": 80, "n3f_hours": 12, "n3s_hours": 8},
        "PA": {"n3f": 65, "n3s": 85, "n3f_hours": 12, "n3s_hours": 12},
        "PC": {"n3f": 65, "n3s": 80, "n3f_hours": 12, "n3s_hours": 8},
        "PVA": {"n3f": 65, "n3s": 85, "n3f_hours": 12, "n3s_hours": 18},
    }

    def __init__(self):
        self._running = False
        self._check_interval = 30  # seconds
        self._fast_check_interval = 3  # seconds after productive queue passes
        self._power_on_wait_time = 180  # seconds to wait for printer after power on (3 min)
        self._power_on_check_interval = 10  # seconds between connection checks
        self._upload_backoff: dict[int, float] = {}
        self._upload_refusals: dict[int, int] = {}
        self._upload_refusal_notified: set[int] = set()
        init_drying_state(self)
        # Defensive in-memory dispatch hold (#1157): a printer that just received
        # a project_file command must not get a second dispatch until either it
        # transitions out of pre_state OR the hard timeout expires. The H2D Pro
        # can take 80–210 s to flip FINISH→PREPARE after project_file, and
        # during that window the DB busy_printers seed is empirically unreliable
        # (multi-plate batches double-/triple-dispatched onto the same printer
        # 30 s apart). Keyed by printer_id; cleared by the watchdog on success
        # or revert.
        # printer_id -> (monotonic_started_at, pre_state, pre_subtask_id)
        self._dispatch_holds: dict[int, tuple[float, str, str | None]] = {}
        # Minimum cooldown between dispatches to the same printer (covers the
        # H2D's project_file digestion window).
        self._dispatch_min_cooldown = 60.0
        # Hard timeout — drop the hold even if we never observed a transition,
        # so a lost MQTT session can't lock a printer out of the queue forever.
        # Matches the watchdog timeout (90 s) plus a safety margin so the
        # watchdog runs first on the unhappy path.
        self._dispatch_max_hold = 180.0
        # item_id -> (upload task, printer_id). Uploads stay pending until the
        # FTP transfer completes, so each queue tick excludes these reservations
        # from re-selection and launches only free pool slots.
        self._inflight: dict[int, tuple[asyncio.Task, int | None]] = {}
        self._stranded_print_recovery = StrandedPrintRecovery()
        self._keep_warm = QueueKeepWarm()
        self._external_skus = SpoolmanSkuReconciler()
        self._stock_alerts = StockAlertMonitor()
        self._filament_low = FilamentLowMonitor()
        self._inventory_alert_task: asyncio.Task | None = None
        self._inventory_alerts_stopped = False

    async def run(self):
        """Main loop - check queue every interval."""
        self._running = True
        self._inventory_alerts_stopped = False
        logger.info("Print scheduler started")

        await preheat_ownership.recover(printer_manager)
        await self._clear_stale_dispatch_claims()

        try:
            while self._running:
                dispatched = False
                try:
                    await self._stranded_print_recovery.tick()
                    await scheduled_drying.tick()
                    dispatched = await self.check_queue()
                except Exception as e:
                    logger.error("Scheduler error: %s", e)

                await asyncio.sleep(self._fast_check_interval if dispatched else self._check_interval)
        finally:
            await self.close_inventory_alerts()

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        init_drying_state(self, reset=True)
        self._inventory_alerts_stopped = True
        if self._inventory_alert_task is not None:
            self._inventory_alert_task.cancel()
        preheat_ownership.stop()
        logger.info("Print scheduler stopped")

    def _schedule_inventory_alerts(self) -> None:
        if self._inventory_alerts_stopped:
            return
        if self._inventory_alert_task is not None and not self._inventory_alert_task.done():
            return
        self._inventory_alert_task = spawn_background_task(
            self._check_inventory_alerts(async_session), name="inventory-alerts"
        )

    async def _check_inventory_alerts(self, session_factory) -> None:
        async with session_factory() as db:
            await self._external_skus.tick(db)
            await self._stock_alerts.tick(db)
            await self._filament_low.tick(db)

    async def close_inventory_alerts(self) -> None:
        """Cancel and drain the owned alert pass before closing database/HTTP clients."""
        self._inventory_alerts_stopped = True
        task = self._inventory_alert_task
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self._inventory_alert_task = None

    async def _clear_stale_dispatch_claims(self) -> None:
        await clear_stale_dispatch_claims(async_session)

    async def _dispatch_with_claim(self, db: AsyncSession, item: PrintQueueItem) -> bool:
        item_id = item.id
        if not await self._claim_for_dispatch(db, item.id):
            preheat_ownership.release_undispatched(item.id)
            logger.info("Queue item %s is no longer claimable for dispatch", item.id)
            return False
        try:
            await db.refresh(item)
            await self._start_print(db, item)
            return True
        finally:
            await self._clear_dispatch_claim(item_id)

    async def _claim_for_dispatch(self, db: AsyncSession, item_id: int) -> bool:
        return await claim_queue_item(db, item_id)

    async def _clear_dispatch_claim(self, item_id: int) -> None:
        try:
            async with async_session() as db:
                await db.execute(update(PrintQueueItem).where(PrintQueueItem.id == item_id).values(dispatching_at=None))
                await db.commit()
        except Exception as exc:
            logger.warning("Queue item %s: failed to clear dispatch claim: %s", item_id, exc)

    async def _pending_queue_items(self, db):
        # Check if shortest-job-first scheduling is enabled
        sjf_enabled = await self._get_bool_setting(db, "queue_shortest_first")

        # Get all pending items in global position or shortest-job-first order
        if sjf_enabled:
            # SJF: items already jumped get top priority (starvation guard),
            # then sort by print_time ascending. Items with no print time go last.
            result = await db.execute(
                select(PrintQueueItem)
                .options(
                    selectinload(PrintQueueItem.archive),
                    selectinload(PrintQueueItem.library_file),
                    selectinload(PrintQueueItem.variants).selectinload(PrintQueueVariant.library_file),
                )
                .where(PrintQueueItem.status == "pending")
                .where(PrintQueueItem.dispatching_at.is_(None))
                .order_by(
                    PrintQueueItem.been_jumped.desc(),
                    PrintQueueItem.print_time_seconds.asc().nullslast(),
                    PrintQueueItem.position,
                    PrintQueueItem.id,
                )
            )
        else:
            result = await db.execute(
                select(PrintQueueItem)
                .options(
                    selectinload(PrintQueueItem.archive),
                    selectinload(PrintQueueItem.library_file),
                    selectinload(PrintQueueItem.variants).selectinload(PrintQueueVariant.library_file),
                )
                .where(PrintQueueItem.status == "pending")
                .where(PrintQueueItem.dispatching_at.is_(None))
                .order_by(PrintQueueItem.position, PrintQueueItem.id)
            )
        items = list(result.scalars().all())

        if self._inflight:
            inflight_ids = set(self._inflight)
            items = [item for item in items if item.id not in inflight_ids]
        return items, sjf_enabled

    async def _refresh_keep_warm(self, db, items, dispatch_ids, interlocked, require_plate_clear):
        try:
            await self._keep_warm.refresh(
                self, db, items, dispatch_ids, interlocked, require_plate_clear, printer_manager
            )
        except Exception as exc:
            logger.warning("Keep-warm pass failed, continuing queue dispatch: %s", exc)

    async def _busy_printers_for_pass(self, db) -> set[int]:
        # Seed busy_printers with printers that already have an item in 'printing'
        # status. _is_printer_idle() alone is not sufficient as a dispatch gate —
        # on H2D / P1 series the MQTT state transition from IDLE to RUNNING can
        # lag several seconds behind the print command, so the next check_queue
        # tick still sees IDLE and would double-dispatch onto the same printer.
        # Without this guard, two pending items targeting the same printer
        # (e.g. a batch with quantity>1) both end up in 'printing' status —
        # surfaced via the "BUG: Multiple queue items" warning in on_print_complete.
        busy_result = await db.execute(
            select(PrintQueueItem.printer_id)
            .where(PrintQueueItem.status == "printing")
            .where(PrintQueueItem.printer_id.is_not(None))
        )
        busy_printers: set[int] = {pid for (pid,) in busy_result.all() if pid is not None}

        busy_printers.update(await reserved_printers(db))
        # Defense-in-depth (#1157): augment busy_printers with any printer
        # still in its post-dispatch hold window. Empirically, the DB seed
        # above can miss in-flight items in a multi-plate batch — same-file
        # plates were being dispatched 30 s apart while the H2D was still
        # digesting the first project_file. The hold is keyed in-memory and
        # released by the watchdog on the success path, so it adds a layer
        # that doesn't depend on DB row visibility or completion-callback
        # timing.
        for held_printer_id in list(self._dispatch_holds.keys()):
            if self._printer_in_dispatch_hold(held_printer_id):
                busy_printers.add(held_printer_id)

        for _task, inflight_printer_id in self._inflight.values():
            if inflight_printer_id is not None:
                busy_printers.add(inflight_printer_id)

        return busy_printers

    async def check_queue(self) -> bool:
        """Check for prints ready to start.

        Returns True while this pass launched or is still tracking uploads so
        the run loop can refill the upload pool promptly.
        """
        self._schedule_inventory_alerts()
        async with async_session() as db:
            items, sjf_enabled = await self._pending_queue_items(db)

            # Read plate-clear setting once per queue check. Default MUST be
            # False to match the schema (SettingsSchema.require_plate_clear
            # defaults False) and the frontend (toggle + card badge both treat a
            # missing value as off). When no settings row exists, a True default
            # here re-enabled the plate-clear gate the UI showed as disabled,
            # blocking dispatch to FINISH-state printers forever with no UI path
            # to clear it (#1865).
            require_plate_clear = await self._get_bool_setting(db, "require_plate_clear", default=False)

            if not items:
                await self._refresh_keep_warm(db, [], [], {}, require_plate_clear)
                # No dispatchable pending items — still check auto-drying, but
                # hold printers with uploads in flight out of it because their
                # print is imminent.
                inflight_printers = {pid for (_task, pid) in self._inflight.values() if pid is not None}
                await self._check_auto_drying(db, [], inflight_printers, require_plate_clear=require_plate_clear)
                return bool(self._inflight)

            logger.info(
                "Queue check: found %d pending items: %s",
                len(items),
                [(i.id, i.printer_id, i.archive_id, i.library_file_id) for i in items],
            )

            busy_printers = await self._busy_printers_for_pass(db)

            now_mono = time.monotonic()
            upload_held: dict[int, str] = {}
            for printer_id, retry_at in list(self._upload_backoff.items()):
                if now_mono >= retry_at:
                    del self._upload_backoff[printer_id]
                else:
                    printer = await self._get_printer(db, printer_id)
                    label = printer.name if printer else f"Printer {printer_id}"
                    upload_held[printer_id] = f"{label} is not accepting files — PrintOps will retry automatically"

            # Printers held by a Home Assistant sensor interlock (#1148) — an
            # enclosure door left open, say. The fixed-printer branch turns
            # this into a waiting_reason the user can act on; the model-based
            # branch hides these printers from the matcher so an "Any <model>"
            # job runs on a sibling instead of queueing behind the held one.
            #
            # Deliberately NOT merged into busy_printers, even though that set
            # already means "unavailable this pass". _check_auto_drying reads
            # it as "is currently printing" and would put an idle-but-held
            # printer down the mid-print drying path, which caps the drying
            # temperature and skips the queue-only gating. A held printer is
            # idle; it should dry exactly as it did before.
            #
            # Only sensors we actually read and found alerting appear here; see
            # ha_sensor_manager.blocked_printers. A Home Assistant that is down
            # holds nothing.
            interlocked: dict[int, str] = {}
            try:
                interlocked = await ha_sensor_manager.blocked_printers(db)
            except Exception as e:
                # Never let the interlock stop the queue running. A broken
                # lookup means no holds, not no dispatches.
                logger.warning("Home Assistant interlock check failed: %s", e)
                interlocked = {}

            skip_reasons: dict[str, int] = {}
            dispatch_ids: list[int] = []
            dispatch_libs: set[int] = set()
            consumed_libs: set[int] = set()

            def _library_row_conflict(candidate: PrintQueueItem) -> bool:
                lib_id = candidate.library_file_id
                if lib_id is None:
                    return False
                if candidate.cleanup_library_after_dispatch:
                    return lib_id in dispatch_libs
                return lib_id in consumed_libs

            def _claim_library_row(candidate: PrintQueueItem) -> None:
                lib_id = candidate.library_file_id
                if lib_id is None:
                    return
                dispatch_libs.add(lib_id)
                if candidate.cleanup_library_after_dispatch:
                    consumed_libs.add(lib_id)

            for item in items:
                # Check scheduled time first (scheduled_time is stored in UTC from ISO string)
                if item.scheduled_time:
                    sched = item.scheduled_time
                    if sched.tzinfo is None:
                        sched = sched.replace(tzinfo=timezone.utc)
                    if sched > datetime.now(timezone.utc):
                        skip_reasons["scheduled_future"] = skip_reasons.get("scheduled_future", 0) + 1
                        continue

                # Skip items that require manual start
                if item.manual_start:
                    skip_reasons["manual_start"] = skip_reasons.get("manual_start", 0) + 1
                    continue

                if item.printer_id:
                    upload_reason = upload_held.get(item.printer_id)
                    if upload_reason:
                        if item.waiting_reason != upload_reason:
                            item.waiting_reason = upload_reason
                            await db.commit()
                        if item.printer_id not in self._upload_refusal_notified:
                            self._upload_refusal_notified.add(item.printer_id)
                            await notification_service.on_queue_job_waiting(
                                job_name=await self._get_job_name(db, item),
                                target_model=item.target_model,
                                waiting_reason=upload_reason,
                                db=db,
                            )
                        skip_reasons["upload_backoff"] = skip_reasons.get("upload_backoff", 0) + 1
                        continue
                    # Held by a sensor interlock (#1148). Checked before the
                    # busy_printers test that would otherwise swallow it
                    # silently — "waiting for a printer" and "waiting for you
                    # to shut the enclosure" need to read differently, and only
                    # one of them is something the user can fix.
                    #
                    # The interlock is the only thing that writes a
                    # waiting_reason on this branch — the model-based branch
                    # nulls it at the moment it assigns a printer — so any
                    # reason still standing once the hold lifts is stale and is
                    # cleared here. Doing it at dispatch instead would leave a
                    # shut door reading "Waiting on Enclosure Door" for as long
                    # as the printer stayed busy with something else.
                    interlock_reason = interlocked.get(item.printer_id)
                    reason = f"Waiting on {interlock_reason}" if interlock_reason else None
                    if item.waiting_reason != reason:
                        item.waiting_reason = reason
                        await db.commit()
                    if interlock_reason:
                        skip_reasons["sensor_interlock"] = skip_reasons.get("sensor_interlock", 0) + 1
                        continue

                    # Specific printer assignment (existing behavior)
                    if item.printer_id in busy_printers:
                        continue

                    # Check if printer is idle
                    printer_idle = self._is_printer_idle(item.printer_id, require_plate_clear)
                    printer_connected = printer_manager.is_connected(item.printer_id)

                    # If printer not connected, try to power on via smart plug
                    if not printer_connected:
                        plugs = await plugs_for_printer(db, item.printer_id)
                        auto_on_plugs = [p for p in plugs if p.auto_on and p.enabled]
                        if auto_on_plugs:
                            logger.info("Printer %s offline, attempting to power on via smart plug(s)", item.printer_id)
                            primary_plug = select_power_plug(auto_on_plugs) or auto_on_plugs[0]
                            powered_on = await self._power_on_and_wait(primary_plug, item.printer_id, db)
                            if powered_on:
                                # Also turn on any remaining auto_on plugs (e.g., filter)
                                for extra_plug in [p for p in auto_on_plugs if p.id != primary_plug.id]:
                                    try:
                                        service = await smart_plug_manager.get_service_for_plug(extra_plug, db)
                                        await service.turn_on(extra_plug)
                                        logger.info(
                                            "Also powered on plug '%s' for printer %s", extra_plug.name, item.printer_id
                                        )
                                    except Exception as e:
                                        logger.warning("Failed to power on extra plug '%s': %s", extra_plug.name, e)
                                printer_connected = True
                                printer_idle = self._is_printer_idle(item.printer_id, require_plate_clear)
                            else:
                                logger.warning("Could not power on printer %s via smart plug", item.printer_id)
                                busy_printers.add(item.printer_id)
                                continue
                        else:
                            # No plug or auto_on disabled
                            busy_printers.add(item.printer_id)
                            continue

                    # Check if printer is idle (busy with another print)
                    if not printer_idle:
                        # If printer is drying (not truly busy), handle based on queue_drying_block
                        if self._drying_in_progress.get(item.printer_id):
                            block_for_drying = await self._get_bool_setting(db, "queue_drying_block")
                            if block_for_drying:
                                # Drying blocks queue — skip this printer
                                busy_printers.add(item.printer_id)
                                continue
                            else:
                                # Print takes priority — stop drying
                                await self._stop_drying(item.printer_id)
                                # Re-check idle after stopping drying
                                printer_idle = self._is_printer_idle(item.printer_id, require_plate_clear)
                                if not printer_idle:
                                    busy_printers.add(item.printer_id)
                                    continue
                        else:
                            busy_printers.add(item.printer_id)
                            continue

                    # Check condition (previous print success)
                    if item.require_previous_success:
                        if not await self._check_previous_success(db, item):
                            item.status = "skipped"
                            item.error_message = "Previous print failed or was aborted"
                            item.completed_at = datetime.now(timezone.utc)
                            await db.commit()
                            logger.info("Skipped queue item %s - previous print failed", item.id)

                            # Send notification
                            job_name = await self._get_job_name(db, item)
                            printer = await self._get_printer(db, item.printer_id)
                            await notification_service.on_queue_job_skipped(
                                job_name=job_name,
                                printer_id=item.printer_id,
                                printer_name=printer.name if printer else "Unknown",
                                reason="Previous print failed or was aborted",
                                db=db,
                            )
                            continue

                    # Resolve AMS mapping when missing or when a status-load race
                    # persisted an all-unresolved [-1] mapping (#2589).
                    await self._ensure_ams_mapping(db, item.printer_id, item)

                    # Filament-deficit pre-dispatch check (#1496). If the
                    # assigned spool can't satisfy any required slot grams,
                    # promote the item to manual_start so the user must
                    # acknowledge via the ▶ button (which re-checks live).
                    if await self._block_on_filament_deficit(db, item):
                        continue

                    if _library_row_conflict(item):
                        skip_reasons["library_row_in_use"] = skip_reasons.get("library_row_in_use", 0) + 1
                        busy_printers.add(item.printer_id)
                        continue

                    _claim_library_row(item)
                    dispatch_ids.append(item.id)
                    busy_printers.add(item.printer_id)

                    # SJF starvation guard: mark items that were jumped
                    if sjf_enabled and item.print_time_seconds is not None:
                        printer = await self._get_printer(db, item.printer_id)
                        for other in items:
                            if (
                                other.id != item.id
                                and other.id not in dispatch_ids
                                and other.status == "pending"
                                and _could_take_printer(other, item.printer_id, printer.model if printer else None)
                                and not other.been_jumped
                                and other.position < item.position
                                and (
                                    other.print_time_seconds is None
                                    or other.print_time_seconds > item.print_time_seconds
                                )
                            ):
                                other.been_jumped = True
                        await db.commit()

                elif item.target_model or item.variants:
                    # Model-based assignment - find any idle printer of matching model.
                    # A plain model-based item has exactly one candidate, built from
                    # its own columns. A cross-model item (#671) has one per sliced
                    # variant and takes the first that matches, walking them in the
                    # user's priority order so the pick is reproducible when more
                    # than one printer is free in the same pass.
                    candidates = _candidates_for(item)
                    printer_id = None
                    chosen: _ModelCandidate | None = None
                    per_model_reasons: list[tuple[str | None, str]] = []

                    if not candidates:
                        # Every candidate file has been deleted or trashed out from
                        # under this item. Hold it with something the user can act
                        # on rather than letting it look dispatchable forever.
                        per_model_reasons.append(
                            (
                                item.target_model,
                                "Every file for this job has been deleted — add a file back or remove the item",
                            )
                        )

                    for candidate in candidates:
                        # Parse required filament types if present
                        required_types = None
                        if candidate.required_filament_types:
                            try:
                                required_types = json.loads(candidate.required_filament_types)
                            except json.JSONDecodeError:
                                pass  # Ignore malformed filament types; treat as no constraint

                        # Parse filament overrides if present
                        filament_overrides = None
                        if candidate.filament_overrides:
                            try:
                                filament_overrides = json.loads(candidate.filament_overrides)
                            except json.JSONDecodeError:
                                pass

                        # If overrides exist, use override types for validation instead
                        effective_types = required_types
                        if filament_overrides:
                            override_types = sorted({o["type"] for o in filament_overrides if "type" in o})
                            if override_types:
                                # Merge: keep original types for non-overridden slots, add override types
                                effective_types = sorted(set(required_types or []) | set(override_types))

                        # Cross-model safety gate (#2578): never hand a 3MF sliced
                        # for an incompatible model to a printer, no matter how the
                        # row got into the DB (old rows, direct API writes). Held
                        # as pending with an actionable waiting_reason — the user
                        # fixes it by editing the item's target model.
                        if not is_gcode_compatible(candidate.sliced_for, candidate.target_model):
                            per_model_reasons.append(
                                (
                                    candidate.target_model,
                                    f"File was sliced for {candidate.sliced_for}, which is not compatible with "
                                    f"{candidate.target_model} — edit the item and fix its target model",
                                )
                            )
                            skip_reasons["sliced_model_mismatch"] = skip_reasons.get("sliced_model_mismatch", 0) + 1
                            continue

                        match_id, match_reason = await self._find_idle_printer_for_model(
                            db,
                            candidate.target_model,
                            # Sensor-held printers are unavailable to the
                            # matcher but stay out of busy_printers itself
                            # (#1148) — see where `interlocked` is built.
                            busy_printers | interlocked.keys() | upload_held.keys(),
                            effective_types,
                            item.target_location,
                            filament_overrides=filament_overrides,
                            require_plate_clear=require_plate_clear,
                        )
                        if match_id:
                            printer_id = match_id
                            chosen = candidate
                            break
                        per_model_reasons.append((candidate.target_model, match_reason or ""))

                    waiting_reason = None if printer_id else _collapse_waiting_reasons(per_model_reasons)

                    # Fold the winning variant's file and settings onto the item
                    # before anything else looks at them — the guards below and
                    # every step of the dispatch read the item's own columns.
                    if chosen is not None:
                        self._resolve_variant(item, chosen)

                    # Update waiting_reason if changed and send notification when first waiting
                    if item.waiting_reason != waiting_reason:
                        was_waiting = item.waiting_reason is not None
                        item.waiting_reason = waiting_reason
                        await db.commit()

                        # Send waiting notification only when transitioning to waiting state
                        # and the reason requires user action (not just "all printers busy")
                        if waiting_reason and not was_waiting and not self._is_busy_only(waiting_reason):
                            job_name = await self._get_job_name(db, item)
                            await notification_service.on_queue_job_waiting(
                                job_name=job_name,
                                target_model=_candidate_model_label(candidates) or item.target_model,
                                waiting_reason=waiting_reason,
                                db=db,
                            )

                    if printer_id:
                        if _library_row_conflict(item):
                            skip_reasons["library_row_in_use"] = skip_reasons.get("library_row_in_use", 0) + 1
                            continue

                        # Check condition (previous print success) before assigning
                        if item.require_previous_success:
                            if not await self._check_previous_success(db, item):
                                item.status = "skipped"
                                item.error_message = "Previous print failed or was aborted"
                                item.completed_at = datetime.now(timezone.utc)
                                await db.commit()
                                logger.info("Skipped queue item %s - previous print failed", item.id)

                                # Send notification
                                job_name = await self._get_job_name(db, item)
                                printer = await self._get_printer(db, printer_id)
                                await notification_service.on_queue_job_skipped(
                                    job_name=job_name,
                                    printer_id=printer_id,
                                    printer_name=printer.name if printer else "Unknown",
                                    reason="Previous print failed or was aborted",
                                    db=db,
                                )
                                continue

                        # Assign printer and start - clear waiting reason
                        item.printer_id = printer_id
                        item.waiting_reason = None
                        logger.info("Model-based assignment: queue item %s assigned to printer %s", item.id, printer_id)

                        # Send assignment notification
                        job_name = await self._get_job_name(db, item)
                        printer = await self._get_printer(db, printer_id)
                        await notification_service.on_queue_job_assigned(
                            job_name=job_name,
                            printer_id=printer_id,
                            printer_name=printer.name if printer else "Unknown",
                            target_model=item.target_model,
                            db=db,
                        )

                        # Resolve AMS mapping for model-based jobs and self-heal
                        # bogus all-unresolved persisted mappings (#2589).
                        await self._ensure_ams_mapping(db, printer_id, item)

                        # Filament-deficit pre-dispatch check (#1496).
                        if await self._block_on_filament_deficit(db, item):
                            continue

                        _claim_library_row(item)
                        dispatch_ids.append(item.id)
                        busy_printers.add(printer_id)

                        # SJF starvation guard: mark model-based items that were jumped
                        if sjf_enabled and item.print_time_seconds is not None:
                            for other in items:
                                if (
                                    other.id != item.id
                                    and other.id not in dispatch_ids
                                    and other.status == "pending"
                                    and _could_take_printer(other, printer_id, printer.model if printer else None)
                                    and not other.been_jumped
                                    and other.position < item.position
                                    and (
                                        other.print_time_seconds is None
                                        or other.print_time_seconds > item.print_time_seconds
                                    )
                                ):
                                    other.been_jumped = True
                            await db.commit()

            # Log summary of skip reasons (helps diagnose why queue items aren't starting)
            if skip_reasons:
                logger.info("Queue skip summary: %s", skip_reasons)
            if busy_printers:
                # Log why each printer was busy (first time it was checked)
                for pid in busy_printers:
                    state = printer_manager.get_status(pid)
                    connected = printer_manager.is_connected(pid)
                    awaiting = printer_manager.is_awaiting_plate_clear(pid)
                    state_name = state.state if state else "NO_STATUS"
                    logger.info(
                        "Queue: printer %d not available — connected=%s, state=%s, awaiting_plate_clear=%s",
                        pid,
                        connected,
                        state_name,
                        awaiting,
                    )

            await self._refresh_keep_warm(db, items, dispatch_ids, {**interlocked, **upload_held}, require_plate_clear)
            upload_limit = max(1, await self._get_int_setting(db, "queue_max_concurrent_uploads", default=4))
            await db.commit()

            if dispatch_ids:
                item_printers = {item.id: item.printer_id for item in items}
                self._launch_uploads(dispatch_ids, item_printers, upload_limit)

            # Auto-drying: start drying on idle printers that have no pending queue items
            await self._check_auto_drying(db, items, busy_printers, require_plate_clear=require_plate_clear)

            return bool(dispatch_ids) or bool(self._inflight)

    def _launch_uploads(self, item_ids: list[int], item_printers: dict[int, int | None], limit: int) -> None:
        free = limit - len(self._inflight)
        if free <= 0:
            logger.info(
                "Upload pool full (%d/%d in flight) — deferring %d item(s): %s",
                len(self._inflight),
                limit,
                len(item_ids),
                item_ids,
            )
            return

        to_launch = item_ids[:free]
        deferred = item_ids[free:]
        logger.info(
            "Launching %d queue upload(s) (pool %d/%d in flight)%s",
            len(to_launch),
            len(self._inflight),
            limit,
            f" — deferring {deferred}" if deferred else "",
        )

        for item_id in to_launch:
            task = spawn_background_task(self._dispatch_one(item_id), name=f"queue-upload-{item_id}")
            self._inflight[item_id] = (task, item_printers.get(item_id))
            task.add_done_callback(lambda _task, iid=item_id: self._inflight.pop(iid, None))

    async def _dispatch_one(self, item_id: int) -> None:
        async with async_session() as item_db:
            item = await item_db.get(PrintQueueItem, item_id)
            if not item:
                preheat_ownership.release_undispatched(item_id)
                logger.info("Queue item %s vanished before dispatch — skipping", item_id)
                return
            await self._dispatch_with_claim(item_db, item)

    async def _find_idle_printer_for_model(
        self,
        db: AsyncSession,
        model: str,
        exclude_ids: set[int],
        required_filament_types: list[str] | None = None,
        target_location: str | None = None,
        filament_overrides: list[dict] | None = None,
        require_plate_clear: bool = True,
    ) -> tuple[int | None, str | None]:
        """Find an idle, connected printer matching the model with compatible filaments.

        Args:
            db: Database session
            model: Printer model to match (e.g., "X1C", "P1S")
            exclude_ids: Printer IDs to exclude (already busy)
            required_filament_types: Optional list of filament types needed (e.g., ["PLA", "PETG"])
                                     If provided, only printers with all required types loaded will match.
            target_location: Optional location filter. If provided, only printers in this location are considered.
            filament_overrides: Optional list of override dicts. Each entry may include
                                 ``force_color_match: true`` to require an exact type+color match
                                 on the printer for that slot. Without the flag the existing
                                 colour-preference logic applies.

        Returns:
            Tuple of (printer_id, waiting_reason):
            - (printer_id, None) if a matching printer was found
            - (None, reason) if no printer is available, with explanation
        """
        # Normalize model name and use case-insensitive matching
        normalized_model = normalize_printer_model(model) or model
        query = (
            select(Printer)
            .where(func.lower(Printer.model) == normalized_model.lower())
            .where(Printer.is_active == True)  # noqa: E712
        )

        # Add location filter if specified
        if target_location:
            query = query.where(Printer.location == target_location)

        result = await db.execute(query)
        printers = list(result.scalars().all())

        location_suffix = f" in {target_location}" if target_location else ""
        if not printers:
            return None, f"No active {normalized_model} printers{location_suffix} configured"

        # Separate force-matched overrides from preference-only overrides
        force_overrides = [o for o in (filament_overrides or []) if o.get("force_color_match")]
        pref_overrides = [o for o in (filament_overrides or []) if not o.get("force_color_match")]

        # Track reasons for skipping printers
        printers_busy = []
        printers_offline = []
        printers_missing_filament: list[tuple[str, list[str]]] = []
        candidates: list[tuple[int, int]] = []  # (printer_id, color_match_count)

        for printer in printers:
            if printer.id in exclude_ids:
                # Printer is already claimed by another job in this scheduling run.
                # For force-color jobs, still check if the color would match — if not,
                # report it as a color mismatch rather than plain "Busy" so the user
                # knows the job needs a filament change, not just to wait for availability.
                if force_overrides and not pref_overrides:
                    missing_colors = self._get_missing_force_color_slots(printer.id, force_overrides)
                    if missing_colors:
                        printers_missing_filament.append((printer.name, missing_colors))
                        continue
                printers_busy.append(printer.name)
                continue

            is_connected = printer_manager.is_connected(printer.id)
            is_idle = self._is_printer_idle(printer.id, require_plate_clear) if is_connected else False

            if not is_connected:
                printers_offline.append(printer.name)
                continue

            if not is_idle:
                # Printer is currently printing.  For force-color jobs, check whether the
                # loaded color would satisfy the requirement — if not, surface it as a
                # color-mismatch reason rather than plain "Busy" so the user understands
                # that the job is waiting for a filament change, not just printer availability.
                if force_overrides and not pref_overrides:
                    missing_colors = self._get_missing_force_color_slots(printer.id, force_overrides)
                    if missing_colors:
                        printers_missing_filament.append((printer.name, missing_colors))
                        logger.debug(
                            "Printer %s (%s) is busy but also has wrong force-color: %s",
                            printer.id,
                            printer.name,
                            missing_colors,
                        )
                        continue
                printers_busy.append(printer.name)
                continue

            # Validate filament compatibility if required types are specified
            if required_filament_types:
                missing = self._get_missing_filament_types(printer.id, required_filament_types)
                if missing:
                    # When force_overrides are present, enrich missing entries with color info
                    # so the "Waiting on" message includes "TYPE (color)" instead of just "TYPE"
                    if force_overrides:
                        force_color_map = {
                            (o.get("type") or "").upper(): o.get("color_name") or o.get("color", "?")
                            for o in force_overrides
                        }
                        missing_enriched = [
                            f"{t} ({force_color_map[t_upper]})" if (t_upper := t.upper()) in force_color_map else t
                            for t in missing
                        ]
                        printers_missing_filament.append((printer.name, missing_enriched))
                    else:
                        printers_missing_filament.append((printer.name, missing))
                    logger.debug("Skipping printer %s (%s) - missing filaments: %s", printer.id, printer.name, missing)
                    continue

            # Force color match: ALL flagged slots must have an exact type+color match
            if force_overrides:
                missing_colors = self._get_missing_force_color_slots(printer.id, force_overrides)
                if missing_colors:
                    printers_missing_filament.append((printer.name, missing_colors))
                    logger.debug(
                        "Skipping printer %s (%s) - missing force-matched colors: %s",
                        printer.id,
                        printer.name,
                        missing_colors,
                    )
                    continue

            # If preference-only overrides exist, rank by color matches (existing behaviour)
            if pref_overrides:
                color_matches = self._count_override_color_matches(printer.id, pref_overrides)
                if color_matches > 0:
                    candidates.append((printer.id, color_matches))
                else:
                    override_colors = [f"{o.get('type', '?')} ({o.get('color', '?')})" for o in pref_overrides]
                    printers_missing_filament.append((printer.name, override_colors))
                    logger.debug("Skipping printer %s (%s) - no matching override colors", printer.id, printer.name)
                    continue
            elif force_overrides:
                # Passed all force checks — immediately eligible (no preference ordering needed)
                return printer.id, None
            else:
                # No overrides at all - take first available (existing behavior)
                return printer.id, None

        # If we have candidates from preference override matching, pick the one with most color matches
        if candidates:
            candidates.sort(key=lambda c: c[1], reverse=True)
            return candidates[0][0], None

        # Build waiting reason from what we found
        reasons = []
        if printers_missing_filament:
            # Filament/color mismatch is most actionable - show first
            if force_overrides and not pref_overrides:
                # All mismatches are force-color failures — use descriptive message only;
                # but only if there are no busy printers that DO have the matching color.
                # If a printer has the right color but is busy, surface "Busy" instead so
                # the user knows the job will start automatically once that printer is free.
                if not printers_busy:
                    all_missing = sorted({c for _, cols in printers_missing_filament for c in cols})
                    return None, f"No matching material/color. Waiting on {', '.join(all_missing)}"
                # else: fall through — printers_busy will be appended below
            else:
                names_and_missing = [
                    f"{name} (needs {', '.join(missing)})" for name, missing in printers_missing_filament
                ]
                reasons.append(f"Waiting for filament: {'; '.join(names_and_missing)}")
        if printers_busy:
            reasons.append(f"Busy: {', '.join(printers_busy)}")
        if printers_offline:
            reasons.append(f"Offline: {', '.join(printers_offline)}")

        return None, " | ".join(reasons) if reasons else f"No available {model} printers{location_suffix}"

    @staticmethod
    def _is_busy_only(waiting_reason: str) -> bool:
        """Check if the waiting reason only contains 'Busy' entries.

        When all matching printers are simply busy printing, the queued job
        will start automatically once a printer finishes — no user action
        is required, so we skip the notification.
        """
        parts = [p.strip() for p in waiting_reason.split(" | ")]
        return all(p.startswith("Busy:") for p in parts)

    def _get_missing_force_color_slots(self, printer_id: int, force_overrides: list[dict]) -> list[str]:
        """Return descriptive strings for force_color_match slots not satisfied by the printer.

        Each entry in ``force_overrides`` must have ``type`` and ``color`` fields and is expected
        to carry ``force_color_match: True``.  The printer must have **every** such slot loaded
        with an exact type+color match.

        When both the override and a candidate tray carry a ``tray_info_idx``, they must also
        match on it: Bambu reports PLA variants as ``tray_type == "PLA"``, while Basic/Matte/Silk
        live in ``tray_info_idx`` (GFA00/GFA01/GFA06/...). If either side lacks an idx we keep
        the historic type+colour behaviour for custom spools and older 3MFs (#2650).

        Returns:
            List of ``"TYPE (color)"`` strings for unmatched slots (empty list means all match).
        """
        status = printer_manager.get_status(printer_id)
        if not status:
            return [f"{o.get('type', '?')} ({o.get('color_name') or o.get('color', '?')})" for o in force_overrides]

        # Build loaded (type, colour, tray_info_idx) triples from AMS and external spool.
        loaded: list[tuple[str, str, str]] = []
        for ams_unit in status.raw_data.get("ams", []):
            for tray in ams_unit.get("tray", []):
                tray_type = tray.get("tray_type")
                if tray_type:
                    color_norm = (tray.get("tray_color", "") or "").replace("#", "").lower()[:6]
                    loaded.append(
                        (_canonical_filament_type(tray_type), color_norm, tray.get("tray_info_idx", "") or "")
                    )
        for vt in status.raw_data.get("vt_tray") or []:
            vt_type = vt.get("tray_type")
            if vt_type:
                color_norm = (vt.get("tray_color", "") or "").replace("#", "").lower()[:6]
                loaded.append((_canonical_filament_type(vt_type), color_norm, vt.get("tray_info_idx", "") or ""))

        missing = []
        for o in force_overrides:
            o_type = _canonical_filament_type(o.get("type") or "")
            o_color = (o.get("color") or "").replace("#", "").lower()[:6]
            o_idx = o.get("tray_info_idx") or ""
            satisfied = any(
                t_type == o_type and t_color == o_color and (not o_idx or not t_idx or o_idx == t_idx)
                for t_type, t_color, t_idx in loaded
            )
            if not satisfied:
                color_label = o.get("color_name") or o.get("color", "?")
                missing.append(f"{o_type} ({color_label})")
        return missing

    def _get_missing_filament_types(self, printer_id: int, required_types: list[str]) -> list[str]:
        """Get the list of required filament types that are not loaded on the printer.

        Args:
            printer_id: The printer ID
            required_types: List of filament types needed (e.g., ["PLA", "PETG"])

        Returns:
            List of missing filament types (empty if all are loaded)
        """
        status = printer_manager.get_status(printer_id)
        if not status:
            return required_types  # Can't determine, assume all missing

        # Collect all filament types loaded on this printer (AMS units + external spool)
        # Use canonical types so equivalence groups (e.g. PA-CF/PA12-CF/PAHT-CF) match.
        loaded_types: set[str] = set()

        # Check AMS units (stored in raw_data["ams"])
        ams_data = status.raw_data.get("ams", [])
        if ams_data:
            for ams_unit in ams_data:
                for tray in ams_unit.get("tray", []):
                    tray_type = tray.get("tray_type")
                    if tray_type:
                        loaded_types.add(_canonical_filament_type(tray_type))

        # Check external spool(s) (virtual tray, stored in raw_data["vt_tray"] as list)
        for vt in status.raw_data.get("vt_tray") or []:
            vt_type = vt.get("tray_type")
            if vt_type:
                loaded_types.add(_canonical_filament_type(vt_type))

        # Find which required types are missing (using canonical type for equivalence)
        missing = []
        for req_type in required_types:
            if _canonical_filament_type(req_type) not in loaded_types:
                missing.append(req_type)

        return missing

    def _count_override_color_matches(self, printer_id: int, overrides: list[dict]) -> int:
        """Count how many filament overrides have an exact color match on the printer.

        Used to prefer printers that already have the desired override colors loaded.
        """
        status = printer_manager.get_status(printer_id)
        if not status:
            return 0

        # Collect loaded filaments' type+color pairs
        loaded: set[tuple[str, str]] = set()
        for ams_unit in status.raw_data.get("ams", []):
            for tray in ams_unit.get("tray", []):
                tray_type = tray.get("tray_type")
                tray_color = tray.get("tray_color", "")
                if tray_type:
                    color_norm = tray_color.replace("#", "").lower()[:6]
                    loaded.add((tray_type.upper(), color_norm))
        for vt in status.raw_data.get("vt_tray") or []:
            vt_type = vt.get("tray_type")
            if vt_type:
                color_norm = (vt.get("tray_color", "") or "").replace("#", "").lower()[:6]
                loaded.add((vt_type.upper(), color_norm))

        matches = 0
        for o in overrides:
            o_type = (o.get("type") or "").upper()
            o_color = (o.get("color") or "").replace("#", "").lower()[:6]
            if (o_type, o_color) in loaded:
                matches += 1
        return matches

    def _resolve_variant(self, item: PrintQueueItem, candidate: _ModelCandidate) -> None:
        """Fold the winning candidate's file and settings onto the queue row (#671).

        This is the whole trick that keeps cross-model items cheap: the many-to-many
        never escapes the selection loop. By the time the pass commits, the row
        looks exactly like an ordinary single-file model-based item, so the upload,
        archive creation, expected-print registration, print history and reprint
        paths need no knowledge that variants exist.

        No-ops for a non-variant candidate, which is already the item's own columns.

        Safe to run and re-run: the item's file columns are only ever *read* when it
        has no variants, so an item that gets resolved and then skipped (library-row
        conflict, previous-print gate) is simply resolved again on the next pass.
        """
        variant = candidate.variant
        if variant is None:
            return

        item.library_file_id = variant.library_file_id
        item.library_file = variant.library_file
        # The dispatcher checks archive_id first and would print that instead of
        # the file we just picked. Creation refuses to combine the two, so this
        # only ever fires on a hand-written row — clear it rather than silently
        # dispatch something the matcher never considered.
        item.archive_id = None
        item.archive = None

        item.target_model = variant.target_model
        item.plate_id = variant.plate_id
        item.ams_mapping = variant.ams_mapping
        item.nozzle_mapping = variant.nozzle_mapping
        item.filament_overrides = variant.filament_overrides
        item.required_filament_types = variant.required_filament_types
        if variant.print_time_seconds is not None:
            # The row carried the shortest candidate's estimate so SJF could order
            # it before a printer was known; now that one is chosen, record what is
            # actually going to run so history and the ETA agree with reality.
            item.print_time_seconds = variant.print_time_seconds

    async def _compute_ams_mapping_for_printer(
        self, db: AsyncSession, printer_id: int, item: PrintQueueItem
    ) -> list[int] | None:
        """Compute AMS mapping for a printer based on filament requirements.

        Called when a queue item has no ams_mapping set — either for model-based
        items after printer assignment, or printer-specific items (e.g. from VP).

        Args:
            db: Database session
            printer_id: The assigned printer ID
            item: The queue item (contains archive_id or library_file_id)

        Returns:
            AMS mapping array or None if no mapping needed/possible
        """
        # Get printer status
        status = printer_manager.get_status(printer_id)
        if not status:
            logger.warning("Cannot compute AMS mapping: printer %s status unavailable", printer_id)
            return None

        # Filament Track Switch (FTS): when installed it routes any AMS slot to
        # either extruder, so the per-nozzle hard filter below must NOT apply.
        # Otherwise a print on one nozzle can't use a spool physically loaded in
        # an AMS on the *other* nozzle, and the matcher falls through to a
        # same-type wrong-colour spool on the target nozzle — the H2C + FTS
        # wrong-filament bug (#2186). Mirrors the frontend skip added for #1162.
        fts_installed = bool(getattr(getattr(status, "fila_switch", None), "installed", False))

        # Get filament requirements from source file
        filament_reqs = await self._get_filament_requirements(db, item)
        if not filament_reqs:
            # When the 3MF can't be read but force-color overrides are present, build a
            # direct mapping from the overrides so the printer uses the correct AMS slot.
            if item.filament_overrides:
                try:
                    overrides = json.loads(item.filament_overrides)
                    force_overrides = [o for o in overrides if o.get("force_color_match")]
                    if force_overrides:
                        logger.info(
                            "Queue item %s: No filament reqs from 3MF; building AMS mapping from %d "
                            "force-color override(s)",
                            item.id,
                            len(force_overrides),
                        )
                        return self._build_override_direct_mapping(force_overrides, status)
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.warning("Queue item %s: Force-color fallback mapping failed: %s", item.id, e)
            logger.debug("No filament requirements found for queue item %s", item.id)
            return None

        # Apply filament overrides if present
        if item.filament_overrides:
            try:
                overrides = json.loads(item.filament_overrides)
                override_map = {o["slot_id"]: o for o in overrides}
                for req in filament_reqs:
                    if req["slot_id"] in override_map:
                        override = override_map[req["slot_id"]]
                        req["type"] = override["type"]
                        req["color"] = override["color"]
                        # Manual/preference overrides swap the slot's filament, so the
                        # original 3MF tray_info_idx would point at the old spool. Force-color
                        # overrides carry the intended variant, so keep it to pin the right
                        # same-colour spool when possible.
                        req["tray_info_idx"] = (
                            override.get("tray_info_idx", "") if override.get("force_color_match") else ""
                        )
                        logger.debug(
                            "Queue item %s: Override slot %d -> %s %s",
                            item.id,
                            req["slot_id"],
                            override["type"],
                            override["color"],
                        )
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.warning("Failed to apply filament overrides for queue item %s: %s", item.id, e)

        # Build loaded filaments from printer status
        loaded_filaments = self._build_loaded_filaments(status)
        if not loaded_filaments:
            logger.debug("No filaments loaded on printer %s", printer_id)
            return None

        # Check if user prefers lowest remaining filament when multiple spools match
        prefer_lowest = await self._get_bool_setting(db, "prefer_lowest_filament")

        # Gate prefer_lowest on the printer's AMS Filament Backup state (#1766).
        # Without backup, the printer will not switch to a second spool when the
        # picked one runs out — so sorting toward the lowest leaves the print
        # at risk of running dry mid-job. None (unknown / A1 family) preserves
        # today's behaviour intentionally.
        if prefer_lowest and status.ams_filament_backup is False:
            logger.info("[prefer-lowest] skipped (AMS Backup OFF on printer %s)", printer_id)
            prefer_lowest = False

        # When the preference is on, surface PrintOps's inventory-side
        # remaining for each slot that's bound to a tracked spool, so the
        # sort beats the MQTT-only blind spot (#1508). Skip the lookup
        # entirely when the preference is off — no behaviour change for
        # users who haven't opted in.
        inventory_remain_overrides: dict[int, float] | None = None
        if prefer_lowest:
            inventory_remain_overrides = await self._build_inventory_remain_overrides(db, printer_id, loaded_filaments)

        # Compute mapping: match required filaments to available slots
        return self._match_filaments_to_slots(
            filament_reqs, loaded_filaments, prefer_lowest, inventory_remain_overrides, fts_installed
        )

    def _build_override_direct_mapping(self, force_overrides: list[dict], status) -> list[int] | None:
        """Build an AMS mapping directly from force-color overrides without a 3MF.

        Used when ``_get_filament_requirements`` returns nothing (e.g. the 3MF's
        slice_info is missing or unreadable) but ``force_color_match`` overrides
        are present. Each override's ``slot_id``, ``type``, and ``color`` are
        treated as the filament requirement for that slot and matched against the
        current AMS state of the printer.

        Returns the same format as ``_match_filaments_to_slots``, or None when
        the AMS has no loaded filaments.
        """
        loaded = self._build_loaded_filaments(status)
        if not loaded:
            return None

        reqs = [
            {
                "slot_id": o["slot_id"],
                "type": o.get("type", ""),
                "color": o.get("color", ""),
                "tray_info_idx": o.get("tray_info_idx", ""),
            }
            for o in force_overrides
        ]
        return self._match_filaments_to_slots(reqs, loaded)

    async def _ensure_ams_mapping(self, db: AsyncSession, printer_id: int, item: PrintQueueItem) -> None:
        """Ensure a queue item does not dispatch with a bogus all-unresolved mapping.

        A stored ``[-1]`` can be produced when the UI persists a mapping before
        AMS status has loaded. Recompute it from live status when possible; if it
        is still unresolved, clear it so the downstream command builder does not
        silently downgrade the job to external-spool mode (#2589).
        """
        stored_mapping: list | None = None
        if item.ams_mapping:
            try:
                stored_mapping = json.loads(item.ams_mapping)
            except (json.JSONDecodeError, TypeError):
                stored_mapping = None

        if item.ams_mapping and not _mapping_is_all_unresolved(stored_mapping):
            return

        computed_mapping = await self._compute_ams_mapping_for_printer(db, printer_id, item)
        if computed_mapping and not _mapping_is_all_unresolved(computed_mapping):
            item.ams_mapping = json.dumps(computed_mapping)
            logger.info(
                "Queue item %s: Computed AMS mapping for printer %s: %s",
                item.id,
                printer_id,
                computed_mapping,
            )
            await db.commit()
        elif _mapping_is_all_unresolved(stored_mapping):
            logger.warning(
                "Queue item %s: stored ams_mapping %s is unresolved and could not be recomputed "
                "from live status on printer %s; clearing it",
                item.id,
                stored_mapping,
                printer_id,
            )
            item.ams_mapping = None
            await db.commit()

    async def _get_filament_requirements(self, db: AsyncSession, item: PrintQueueItem) -> list[dict] | None:
        """Resolve the queue item's source 3MF and parse the per-slot
        filament requirements out of it. Thin DB-resolver wrapper around
        ``filament_requirements.extract_filament_requirements`` so the VP
        queue-mode write path (#1188) can reuse the same parser at upload
        time.
        """
        from backend.app.services.filament_requirements import extract_filament_requirements

        file_path: Path | None = None
        if item.archive_id:
            result = await db.execute(select(PrintArchive).where(PrintArchive.id == item.archive_id))
            archive = result.scalar_one_or_none()
            if archive:
                file_path = settings.base_dir / archive.file_path
        elif item.library_file_id:
            result = await db.execute(LibraryFile.active().where(LibraryFile.id == item.library_file_id))
            library_file = result.scalar_one_or_none()
            if library_file:
                lib_path = Path(library_file.file_path)
                file_path = lib_path if lib_path.is_absolute() else settings.base_dir / library_file.file_path

        if not file_path or not file_path.exists():
            return None

        filaments = extract_filament_requirements(file_path, plate_id=item.plate_id)
        return filaments if filaments else None

    def _build_loaded_filaments(self, status) -> list[dict]:
        """Build list of loaded filaments from printer status.

        Args:
            status: PrinterState from printer_manager

        Returns:
            List of loaded filament dicts with type, color, ams_id, tray_id, global_tray_id
        """
        filaments = []

        # Get ams_extruder_map for dual-nozzle printers (H2D, H2D Pro)
        ams_extruder_map = status.raw_data.get("ams_extruder_map", {})

        # Parse AMS units from raw_data
        ams_data = status.raw_data.get("ams", [])
        for ams_unit in ams_data:
            ams_id = int(ams_unit.get("id", 0))
            trays = ams_unit.get("tray", [])
            is_ht = len(trays) == 1  # AMS-HT has single tray

            for tray in trays:
                tray_type = tray.get("tray_type")
                if tray_type:
                    tray_id = int(tray.get("id", 0))
                    tray_color = tray.get("tray_color", "")
                    # tray_info_idx identifies the specific spool (e.g., "GFA00", "P4d64437")
                    tray_info_idx = tray.get("tray_info_idx", "")
                    # Normalize color: remove alpha, add hash
                    color = self._normalize_color(tray_color)
                    # Calculate global tray ID
                    # AMS-HT units have IDs starting at 128 with a single tray
                    global_tray_id = ams_id if ams_id >= 128 else ams_id * 4 + tray_id

                    filaments.append(
                        {
                            "type": tray_type,
                            "color": color,
                            "tray_info_idx": tray_info_idx,
                            "ams_id": ams_id,
                            "tray_id": tray_id,
                            "is_ht": is_ht,
                            "is_external": False,
                            "global_tray_id": global_tray_id,
                            "extruder_id": ams_extruder_map.get(str(ams_id)),
                            "remain": tray.get("remain", -1),
                        }
                    )

        # Check external spool(s) (vt_tray is a list)
        for idx, vt in enumerate(status.raw_data.get("vt_tray") or []):
            if vt.get("tray_type"):
                color = self._normalize_color(vt.get("tray_color", ""))
                tray_id = int(vt.get("id", 254))
                filaments.append(
                    {
                        "type": vt["tray_type"],
                        "color": color,
                        "tray_info_idx": vt.get("tray_info_idx", ""),
                        "ams_id": -1,
                        "tray_id": idx,
                        "is_ht": False,
                        "is_external": True,
                        "global_tray_id": tray_id,
                        "extruder_id": (255 - tray_id) if ams_extruder_map else None,
                        "remain": vt.get("remain", -1),
                    }
                )

        return filaments

    def _normalize_color(self, color: str | None) -> str:
        """Normalize color to #RRGGBB format."""
        if not color:
            return "#808080"
        hex_color = color.replace("#", "")[:6]
        return f"#{hex_color}"

    def _normalize_color_for_compare(self, color: str | None) -> str:
        """Normalize color for comparison (lowercase, no hash)."""
        if not color:
            return ""
        return color.replace("#", "").lower()[:6]

    def _colors_are_similar(self, color1: str | None, color2: str | None, threshold: int = 40) -> bool:
        """Check if two colors are visually similar within a threshold."""
        hex1 = self._normalize_color_for_compare(color1)
        hex2 = self._normalize_color_for_compare(color2)
        if not hex1 or not hex2 or len(hex1) < 6 or len(hex2) < 6:
            return False

        try:
            r1 = int(hex1[0:2], 16)
            g1 = int(hex1[2:4], 16)
            b1 = int(hex1[4:6], 16)
            r2 = int(hex2[0:2], 16)
            g2 = int(hex2[2:4], 16)
            b2 = int(hex2[4:6], 16)
            return abs(r1 - r2) <= threshold and abs(g1 - g2) <= threshold and abs(b1 - b2) <= threshold
        except ValueError:
            return False

    async def _build_inventory_remain_overrides(
        self, db: AsyncSession, printer_id: int, loaded: list[dict]
    ) -> dict[int, float]:
        """Return ``{global_tray_id: remaining_grams}`` for AMS slots the user
        has bound to an inventory spool — PrintOps-side or Spoolman-side.

        The MQTT ``remain`` field on a tray is the printer firmware's
        RFID-decremented value, which has two limitations the "Prefer Lowest
        Remaining Filament" feature has been ignoring (#1508):

        - it's only meaningful for Bambu RFID spools; everything else reports
          ``-1`` (then clamped to a sentinel), so multiple non-RFID trays
          compare equal and the sort collapses to AMS-slot order — the user
          who's curating inventory weights gets the lower-slot pick instead
          of the lower-remaining pick;
        - even when set, it's the *printer's* counter, not PrintOps's
          ``label_weight - weight_used`` (internal mode) or Spoolman's
          ``remaining_weight`` (Spoolman mode) — the two diverge any time the
          user re-spools, swaps cardboard, or runs a print outside PrintOps.

        When the user has bound a spool to a slot, their own inventory
        tracking is authoritative; this helper surfaces that value so the
        sort can prefer it. Slots without a binding are absent from the
        returned map — the caller then falls back to MQTT ``remain`` for
        those, preserving the pre-#1508 behaviour for un-tracked spools.

        Returns an empty map on any failure (no inventory bindings, DB
        error, Spoolman unreachable). A best-effort lookup; "Prefer Lowest"
        is a preference, not a guarantee.
        """
        if not loaded:
            return {}
        # External / virtual-tray slots are tracked separately from AMS — skip
        # them so a VT-loaded spool doesn't accidentally inherit a tracked
        # AMS binding (the tables use ams_id 254/255 for VT, but the cross
        # match is fiddly and out of scope for this fix).
        tracked_slots = [(f["ams_id"], f["tray_id"], f["global_tray_id"]) for f in loaded if not f.get("is_external")]
        if not tracked_slots:
            return {}

        is_spoolman = await self._is_spoolman_mode(db)
        overrides: dict[int, float] = {}

        if is_spoolman:
            result = await db.execute(
                select(SpoolmanSlotAssignment).where(SpoolmanSlotAssignment.printer_id == printer_id)
            )
            assignments = list(result.scalars().all())
            by_slot = {(a.ams_id, a.tray_id): a.spoolman_spool_id for a in assignments}
            from backend.app.services.filament_deficit import _spoolman_remaining_grams

            for ams_id, tray_id, gtid in tracked_slots:
                spoolman_id = by_slot.get((ams_id, tray_id))
                if spoolman_id is None:
                    continue
                grams = await _spoolman_remaining_grams(spoolman_id)
                if grams is not None:
                    overrides[gtid] = grams
            return overrides

        # Internal inventory mode (default). selectinload matches the pattern
        # used elsewhere (inventory.py, spoolman.py routes) — a single query
        # plus an eager-loaded relationship rather than an explicit join, so
        # the row-attribute shape is exactly what those routes already rely on.
        result = await db.execute(
            select(SpoolAssignment)
            .options(selectinload(SpoolAssignment.spool))
            .where(SpoolAssignment.printer_id == printer_id)
        )
        assignments = list(result.scalars().all())
        by_slot = {(a.ams_id, a.tray_id): a.spool for a in assignments}
        for ams_id, tray_id, gtid in tracked_slots:
            spool = by_slot.get((ams_id, tray_id))
            if spool is None:
                continue
            label = float(spool.label_weight or 0)
            used = float(spool.weight_used or 0)
            overrides[gtid] = max(0.0, label - used)
        return overrides

    @staticmethod
    async def _is_spoolman_mode(db: AsyncSession) -> bool:
        """Mirror of ``filament_deficit._is_spoolman_mode`` — kept private
        here to avoid making this module import-dependent on that private
        helper's signature."""
        try:
            from backend.app.api.routes.settings import get_setting

            v = await get_setting(db, "spoolman_enabled")
            return bool(v) and v.lower() == "true"
        except Exception:
            return False

    @staticmethod
    def _slot_priority(ams_id: int | None, tray_id: int | None) -> int:
        """Deterministic slot-position tie-breaker for the prefer-lowest sort.

        Three bands, matched to the emission order in ``_build_loaded_filaments``
        so a tied sort produces the same physical-position order the pre-#1508
        stable sort did (preserves the regression-free baseline):

        - Regular AMS (``ams_id`` 0..7): ``ams_id * 4 + tray_id`` → 0..31
        - AMS-HT (``ams_id`` >= 128, single tray): ``1000 + (ams_id - 128) * 4``
        - External / VT (``ams_id`` < 0, or ``None``): ``10_000``

        Banding ensures regular AMS < AMS-HT < external on ties, regardless of
        what the raw ``ams_id`` happens to be (in particular, ``ams_id = -1``
        for VT must NOT sort to a negative number or it would beat AMS slot 0).
        """
        if ams_id is None or ams_id < 0:
            return 10_000
        if ams_id >= 128:
            return 1_000 + (ams_id - 128) * 4 + (tray_id or 0)
        return ams_id * 4 + (tray_id or 0)

    @staticmethod
    def _prefer_lowest_sort_key(f: dict, overrides: dict[int, float] | None) -> tuple[int, float, int]:
        """Sort key for the "Prefer Lowest Remaining Filament" preference.

        Two-tier ordering: inventory-tracked spools always sort BEFORE
        non-tracked spools (the user has told us they care about these
        specifically), then ascending by remaining within each tier, then
        ascending by AMS slot position as the deterministic tie-breaker.

        Tiers are flagged by the first tuple element (0 = inventory-tracked,
        1 = MQTT-only / unknown). Cross-tier value comparisons never run
        because the tier flag dominates — which is what lets us mix grams
        (inventory) and percent (MQTT) without a unit conversion.

        Within the MQTT tier ``remain = -1`` (unknown) is mapped to 101 so
        spools the printer DOES know something about sort ahead of those
        it knows nothing about — preserves pre-#1508 behaviour for the
        no-inventory-binding case.

        Slot tie-breaker via ``_slot_priority`` so regular AMS < AMS-HT <
        external on ties, matching the legacy emission-order stable sort.
        """
        gtid = f.get("global_tray_id")
        slot_order = PrintScheduler._slot_priority(f.get("ams_id"), f.get("tray_id"))
        if overrides and gtid in overrides:
            return (0, overrides[gtid], slot_order)
        remain = f.get("remain", -1)
        return (1, float(remain) if remain is not None and remain >= 0 else 101.0, slot_order)

    def _match_filaments_to_slots(
        self,
        required: list[dict],
        loaded: list[dict],
        prefer_lowest: bool = False,
        inventory_remain_overrides: dict[int, float] | None = None,
        fts_installed: bool = False,
    ) -> list[int] | None:
        """Match required filaments to loaded filaments and build AMS mapping.

        Priority: unique tray_info_idx match > exact color match > similar color match > type-only match

        The tray_info_idx is a filament type identifier stored in the 3MF file when the user
        slices (e.g., "GFA00" for generic PLA, "P4d64437" for custom presets). If the same
        tray_info_idx appears in only ONE available tray, we use that tray. If multiple trays
        have the same tray_info_idx (e.g., two spools of generic PLA), we fall back to color
        matching among those trays.

        Args:
            required: List of required filaments with slot_id, type, color, tray_info_idx
            loaded: List of loaded filaments with type, color, tray_info_idx, global_tray_id

        Returns:
            AMS mapping array (position = slot_id - 1, value = global_tray_id or -1)
        """
        if not required:
            return None

        # Track used trays to avoid duplicate assignment
        used_tray_ids: set[int] = set()
        comparisons = []

        for req in required:
            req_type = (req.get("type") or "").upper()
            req_color = req.get("color", "")
            req_tray_info_idx = req.get("tray_info_idx", "")

            # Find best match: unique tray_info_idx > exact color > similar color > type-only
            idx_match = None
            exact_match = None
            similar_match = None
            type_only_match = None

            # Get available trays (not already used)
            available = [f for f in loaded if f["global_tray_id"] not in used_tray_ids]

            # Nozzle-aware filtering: restrict to trays on the correct nozzle.
            # Hard filter — cross-nozzle assignment causes print failures
            # ("position of left hotend is abnormal"), so never fall back.
            # Skipped when an FTS is installed: it routes any AMS slot to either
            # extruder, so restricting to one nozzle would wrongly exclude the
            # correct spool sitting in the other nozzle's AMS (#2186).
            req_nozzle_id = req.get("nozzle_id")
            if req_nozzle_id is not None and not fts_installed:
                available = [f for f in available if f.get("extruder_id") == req_nozzle_id]

            # Sort by remaining filament (ascending) so lowest-remain spool wins .find().
            # Inventory-tracked spools sort before MQTT-only ones (#1508); see
            # _prefer_lowest_sort_key for the full rationale.
            if prefer_lowest:
                available.sort(key=lambda f: self._prefer_lowest_sort_key(f, inventory_remain_overrides))
                # INFO-level decision trace for "Prefer Lowest Filament" #1766.
                # One line per filament req so a bug report can be diagnosed
                # without enabling debug logging: shows what the matcher saw
                # (req shape + sorted candidate trays with their remain values
                # and any inventory override that was applied). Mirrored by
                # the picked-match log at the bottom of the loop.
                logger.info(
                    "[prefer-lowest] req slot=%s type=%r color=%r tii=%r nozzle=%s; available (sorted lowest-first): %s",
                    req.get("slot_id"),
                    req_type,
                    req_color,
                    req_tray_info_idx,
                    req_nozzle_id,
                    [
                        {
                            "gtid": f.get("global_tray_id"),
                            "type": f.get("type"),
                            "color": f.get("color"),
                            "tii": f.get("tray_info_idx"),
                            "remain": f.get("remain"),
                            "inv_g": (
                                inventory_remain_overrides.get(f.get("global_tray_id"))
                                if inventory_remain_overrides
                                else None
                            ),
                        }
                        for f in available
                    ],
                )

            # Check if tray_info_idx is unique among available trays
            if req_tray_info_idx:
                idx_matches = [f for f in available if f.get("tray_info_idx") == req_tray_info_idx]
                if len(idx_matches) == 1:
                    # Unique tray_info_idx - use it as definitive match
                    idx_match = idx_matches[0]
                    logger.debug(
                        f"Matched filament slot {req.get('slot_id')} by unique tray_info_idx={req_tray_info_idx} "
                        f"-> tray {idx_match['global_tray_id']}"
                    )
                elif len(idx_matches) > 1:
                    # Multiple trays with same tray_info_idx - use color matching among them
                    logger.debug(
                        f"Non-unique tray_info_idx={req_tray_info_idx} found in {len(idx_matches)} trays, "
                        f"using color matching among trays: {[f['global_tray_id'] for f in idx_matches]}"
                    )
                    if prefer_lowest:
                        idx_matches.sort(key=lambda f: self._prefer_lowest_sort_key(f, inventory_remain_overrides))
                    # Use color matching within this subset
                    for f in idx_matches:
                        f_color = f.get("color", "")
                        if self._normalize_color_for_compare(f_color) == self._normalize_color_for_compare(req_color):
                            if not exact_match:
                                exact_match = f
                        elif self._colors_are_similar(f_color, req_color):
                            if not similar_match:
                                similar_match = f
                        elif not type_only_match:
                            type_only_match = f

            # If no idx_match yet, do standard type/color matching on all available trays
            if not idx_match and not exact_match and not similar_match and not type_only_match:
                for f in available:
                    f_type = (f.get("type") or "").upper()
                    if _canonical_filament_type(f_type) != _canonical_filament_type(req_type):
                        continue

                    # Type matches - check color
                    f_color = f.get("color", "")
                    if self._normalize_color_for_compare(f_color) == self._normalize_color_for_compare(req_color):
                        if not exact_match:
                            exact_match = f
                    elif self._colors_are_similar(f_color, req_color):
                        if not similar_match:
                            similar_match = f
                    elif not type_only_match:
                        type_only_match = f

            match = idx_match or exact_match or similar_match or type_only_match
            if match:
                used_tray_ids.add(match["global_tray_id"])
                comparisons.append({"slot_id": req.get("slot_id", 0), "global_tray_id": match["global_tray_id"]})
            else:
                comparisons.append({"slot_id": req.get("slot_id", 0), "global_tray_id": -1})
            if prefer_lowest:
                # Pair with the "available (sorted)" log above so the reporter
                # bundle shows BOTH what the matcher saw AND which match bucket
                # won — fast triage when "Prefer Lowest Filament" picks the
                # wrong slot (#1766).
                if match:
                    bucket = (
                        "idx"
                        if idx_match is not None
                        else "exact_color"
                        if exact_match is not None
                        else "similar_color"
                        if similar_match is not None
                        else "type_only"
                    )
                    logger.info(
                        "[prefer-lowest] picked gtid=%s via %s for req slot=%s",
                        match["global_tray_id"],
                        bucket,
                        req.get("slot_id"),
                    )
                else:
                    logger.info(
                        "[prefer-lowest] NO MATCH for req slot=%s (type=%r color=%r tii=%r)",
                        req.get("slot_id"),
                        req_type,
                        req_color,
                        req_tray_info_idx,
                    )

        # Build mapping array
        if not comparisons:
            return None

        max_slot_id = max(c["slot_id"] for c in comparisons)
        if max_slot_id <= 0:
            return None

        mapping = [-1] * max_slot_id
        for c in comparisons:
            slot_id = c["slot_id"]
            if slot_id and slot_id > 0:
                mapping[slot_id - 1] = c["global_tray_id"]

        return mapping

    def _mark_printer_dispatched(
        self,
        printer_id: int,
        pre_state: str | None,
        pre_subtask_id: str | None,
    ) -> None:
        """Record that a print command was just sent to ``printer_id``.

        Held until either the watchdog observes a state/subtask transition
        (success path) or the hard timeout expires. See ``_dispatch_holds``.
        """
        if not pre_state:
            # No pre_state means we can't detect a transition — fall back to a
            # pure time-based hold using empty string as a sentinel that won't
            # match any real printer state.
            pre_state = ""
        self._dispatch_holds[printer_id] = (time.monotonic(), pre_state, pre_subtask_id)

    def _release_dispatch_hold(self, printer_id: int) -> None:
        """Drop the dispatch hold for ``printer_id`` (called by the watchdog)."""
        self._dispatch_holds.pop(printer_id, None)

    def _printer_in_dispatch_hold(self, printer_id: int) -> bool:
        """True if ``printer_id`` is still inside its post-dispatch hold window.

        Returns False (and clears the hold) once any of these are true:
          - hard timeout (``_dispatch_max_hold``) has elapsed
          - the printer has transitioned out of pre_state and we're past the
            minimum cooldown
          - the printer's subtask_id has advanced past pre_subtask_id and we're
            past the minimum cooldown
        Otherwise the printer is held — caller should treat it as busy.
        """
        entry = self._dispatch_holds.get(printer_id)
        if not entry:
            return False
        started_at, pre_state, pre_subtask_id = entry
        elapsed = time.monotonic() - started_at

        if elapsed >= self._dispatch_max_hold:
            self._dispatch_holds.pop(printer_id, None)
            return False

        # Without a pre_state we can't detect a transition — fall back to the
        # min cooldown alone, then drop the hold.
        if not pre_state:
            if elapsed >= self._dispatch_min_cooldown:
                self._dispatch_holds.pop(printer_id, None)
                return False
            return True

        status = printer_manager.get_status(printer_id)
        current_state = getattr(status, "state", None) if status else None
        current_subtask_id = getattr(status, "subtask_id", None) if status else None
        transitioned = (current_state is not None and current_state != pre_state) or (
            pre_subtask_id is not None and current_subtask_id is not None and current_subtask_id != pre_subtask_id
        )

        if transitioned and elapsed >= self._dispatch_min_cooldown:
            self._dispatch_holds.pop(printer_id, None)
            return False

        return True

    def _is_printer_idle(self, printer_id: int, require_plate_clear: bool = True) -> bool:
        """Check if a printer is connected and idle."""
        if not printer_manager.is_connected(printer_id):
            logger.debug("Printer %d: not connected", printer_id)
            return False

        state = printer_manager.get_status(printer_id)
        if not state:
            logger.debug("Printer %d: no status available", printer_id)
            return False

        # Plate-clear gate: if the printer finished/failed a previous print and the user
        # hasn't acknowledged the plate was cleared, the queue must not dispatch the next
        # job — even if the printer currently reports IDLE. After Auto Off cycles the
        # printer, it boots back into IDLE with no memory of the previous finish; without
        # the persisted awaiting flag we'd bypass the confirmation prompt (#961).
        if require_plate_clear and printer_manager.is_awaiting_plate_clear(printer_id):
            logger.debug(
                "Printer %d: not idle — awaiting plate-clear acknowledgment (state=%s)",
                printer_id,
                state.state,
            )
            return False

        idle = state.state in ("IDLE", "FINISH", "FAILED")
        if not idle:
            logger.debug("Printer %d: not idle — state=%s", printer_id, state.state)
        return idle

    async def _get_setting(self, db: AsyncSession, key: str) -> str | None:
        """Read a setting value from the database."""
        result = await db.execute(select(Settings).where(Settings.key == key))
        setting = result.scalar_one_or_none()
        return setting.value if setting else None

    async def _get_bool_setting(self, db: AsyncSession, key: str, default: bool = False) -> bool:
        """Read a boolean setting from the database."""
        result = await db.execute(select(Settings).where(Settings.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            return setting.value.lower() == "true"
        return default

    async def _get_int_setting(self, db: AsyncSession, key: str, default: int) -> int:
        """Read an int setting; falls back to default on missing/unparseable rows."""
        result = await db.execute(select(Settings).where(Settings.key == key))
        setting = result.scalar_one_or_none()
        if setting and setting.value:
            try:
                return int(setting.value)
            except ValueError:
                pass
        return default

    async def _get_drying_presets(self, db: AsyncSession) -> dict[str, dict[str, int]]:
        """Get drying presets (user-configured or built-in defaults)."""
        result = await db.execute(select(Settings).where(Settings.key == "drying_presets"))
        setting = result.scalar_one_or_none()
        if setting and setting.value:
            try:
                presets = json.loads(setting.value)
                if isinstance(presets, dict) and presets:
                    return presets
            except json.JSONDecodeError:
                pass
        return self.DEFAULT_DRYING_PRESETS

    async def _get_humidity_thresholds(self, db: AsyncSession) -> dict[str, int]:
        """Per-filament humidity thresholds (#1605).

        Returns the user-configured overrides map keyed by normalized filament
        type (uppercase base, e.g. ``PLA``, ``ASA``) plus a ``default`` key for
        unknown / unmapped types. Empty / unset → empty dict, in which case
        callers fall back to ``ams_humidity_fair``.
        """
        result = await db.execute(select(Settings).where(Settings.key == "ams_humidity_thresholds"))
        setting = result.scalar_one_or_none()
        if not setting or not setting.value:
            return {}
        try:
            data = json.loads(setting.value)
        except json.JSONDecodeError:
            return {}
        if not isinstance(data, dict):
            return {}
        out: dict[str, int] = {}
        for key, value in data.items():
            try:
                out[str(key).upper() if key != "default" else "default"] = int(value)
            except (TypeError, ValueError):
                continue
        return out

    @staticmethod
    def resolve_humidity_threshold(trays: list[dict], thresholds: dict[str, int], fallback: int) -> int:
        """Resolve the effective humidity threshold for an AMS unit (#1605).

        For mixed filament types loaded into one AMS, returns the most
        restrictive (lowest) threshold across all loaded tray types — matches
        the conservative-params strategy already used for drying temp/hours.
        Empty / unloaded trays contribute no constraint. Unknown types use the
        ``default`` key, falling through to ``fallback`` (= ``ams_humidity_fair``)
        when no per-type map is configured at all.
        """
        default = thresholds.get("default", fallback)
        if not thresholds:
            return fallback
        candidates: list[int] = []
        for tray in trays:
            tray_type = str(tray.get("tray_type") or "").strip()
            if not tray_type:
                continue
            base_type = tray_type.split()[0].upper()
            candidates.append(thresholds.get(base_type, default))
        if not candidates:
            return default
        return min(candidates)

    def _get_conservative_drying_params(
        self, trays: list[dict], module_type: str, presets: dict[str, dict[str, int]]
    ) -> tuple[int, int, str] | None:
        """Get the most conservative drying params for mixed filament types in an AMS unit.

        Returns (temp, duration_hours, filament_type) or None if no drying-eligible filaments.
        """
        temp_key = module_type if module_type in ("n3f", "n3s") else "n3f"
        hours_key = f"{temp_key}_hours"

        min_temp = None
        max_hours = None
        filament_type = ""

        for tray in trays:
            tray_type = tray.get("tray_type", "")
            if not tray_type:
                continue
            # Normalize filament type for preset lookup (e.g., "PLA Basic" -> "PLA")
            base_type = tray_type.split()[0].upper()
            preset = presets.get(base_type)
            if not preset:
                continue

            temp = preset.get(temp_key, 55)
            hours = preset.get(hours_key, 12)

            # Conservative: lowest temp, longest duration
            if min_temp is None or temp < min_temp:
                min_temp = temp
            if max_hours is None or hours > max_hours:
                max_hours = hours
            if not filament_type:
                filament_type = base_type

        if min_temp is None:
            return None
        return (min_temp, max_hours or 12, filament_type)

    async def _check_auto_drying(
        self,
        db: AsyncSession,
        queue_items: list[PrintQueueItem],
        busy_printers: set[int],
        *,
        require_plate_clear: bool = True,
    ):
        await check_auto_drying(
            self,
            db,
            queue_items,
            busy_printers,
            require_plate_clear=require_plate_clear,
            printer_manager=printer_manager,
            reserved_printers=reserved_printers,
            supports_drying=supports_drying,
            supports_drying_while_printing=supports_drying_while_printing,
            start_drying=start_drying,
            time=time,
            logger=logger,
        )

    def _sync_drying_state(self):
        sync_drying_state(self._drying_in_progress, printer_manager, owner=self)

    async def _stop_drying(self, printer_id: int):
        await stop_drying(self._drying_in_progress, printer_id, printer_manager, async_session, owner=self)

    DEFAULT_PREHEAT_FILAMENT_TARGETS = DEFAULT_PREHEAT_FILAMENT_TARGETS

    async def _get_preheat_filament_targets(self, db: AsyncSession) -> dict[str, int]:
        return parse_preheat_filament_targets(await self._get_setting(db, "preheat_filament_targets"))

    @staticmethod
    def _normalize_filament_type(tray_type: str) -> str:
        return normalize_filament_type(tray_type)

    def _derive_chamber_target(
        self,
        printer: Printer,
        targets: dict[str, int],
        item: PrintQueueItem | None = None,
    ) -> int:
        """Return the target required by the trays this queue item maps."""
        state = printer_manager.get_status(printer.id)
        mapping = getattr(item, "ams_mapping", None)
        return derive_chamber_target(getattr(state, "raw_data", None), targets, mapping)

    async def _preheat_and_soak(self, db, item, printer, archive) -> None:
        await preheat_and_soak(self, db, item, printer, archive, printer_manager, get_ftp_retry_settings)

    async def _power_on_and_wait(self, plug: SmartPlug, printer_id: int, db: AsyncSession) -> bool:
        """Turn on smart plug and wait for printer to connect.

        Returns True if printer connected successfully within timeout.
        """
        # Get the appropriate service for the plug type (Tasmota or Home Assistant)
        service = await smart_plug_manager.get_service_for_plug(plug, db)

        # Check current plug state
        status = await service.get_status(plug)
        if not status.get("reachable"):
            logger.warning("Smart plug '%s' is not reachable", plug.name)
            return False

        # Turn on if not already on
        if status.get("state") != "ON":
            success = await service.turn_on(plug)
            if not success:
                logger.warning("Failed to turn on smart plug '%s'", plug.name)
                return False
            logger.info("Powered on smart plug '%s' for printer %s", plug.name, printer_id)

        # Get printer from database for connection
        result = await db.execute(select(Printer).where(Printer.id == printer_id))
        printer = result.scalar_one_or_none()
        if not printer:
            logger.error("Printer %s not found in database", printer_id)
            return False

        # Wait for printer to boot (give it some time before trying to connect)
        logger.info("Waiting 30s for printer %s to boot...", printer_id)
        await asyncio.sleep(30)

        # Try to connect to the printer periodically
        elapsed = 30  # Already waited 30s
        while elapsed < self._power_on_wait_time:
            # Try to connect
            logger.info("Attempting to connect to printer %s...", printer_id)
            try:
                connected = await printer_manager.connect_printer(printer)
                if connected:
                    logger.info("Printer %s connected after %ss", printer_id, elapsed)
                    # Give it a moment to stabilize and get status
                    await asyncio.sleep(5)
                    return True
            except Exception as e:
                logger.debug("Connection attempt failed: %s", e)

            await asyncio.sleep(self._power_on_check_interval)
            elapsed += self._power_on_check_interval
            logger.debug("Waiting for printer %s to connect... (%ss)", printer_id, elapsed)

        logger.warning("Printer %s did not connect within %ss after power on", printer_id, self._power_on_wait_time)
        return False

    async def _check_previous_success(self, db: AsyncSession, item: PrintQueueItem) -> bool:
        """Check if the previous print on this printer succeeded.

        A user-cancelled predecessor is treated as neutral — `cancelled` is a
        deliberate action, not a failure, so subsequent items should still
        dispatch (#1667). `skipped` is excluded from the lookback entirely:
        a skip isn't an actual print attempt, so it must not gate downstream
        items — counting it as a failed predecessor was the cascade bug that
        let a single cancellation block 18 items over 3 days for the reporter.
        Only `failed` and `aborted` — real print-attempt failures — block.

        Failures with `gate_acknowledged=True` (set by the per-printer Resume
        action — #1818) are also excluded from the lookback so the user can
        clear the gate after fixing the physical issue without having to
        re-queue every downstream job.
        """
        result = await db.execute(
            select(PrintQueueItem)
            .where(PrintQueueItem.printer_id == item.printer_id)
            .where(PrintQueueItem.id != item.id)
            .where(PrintQueueItem.status.in_(["completed", "failed", "cancelled", "aborted"]))
            .where(PrintQueueItem.gate_acknowledged == False)  # noqa: E712
            .order_by(PrintQueueItem.completed_at.desc())
            .limit(1)
        )
        prev_item = result.scalar_one_or_none()

        # If no previous item, assume success (first in queue)
        if not prev_item:
            return True

        return prev_item.status in ("completed", "cancelled")

    async def _power_off_if_needed(self, db: AsyncSession, item: PrintQueueItem):
        """Schedule power-off if the queue item enabled auto_off_after.

        Delegates to the smart-plug manager so the off honours each plug's
        configured strategy (time delay or temperature threshold), is cancelled
        if the printer starts printing again, and never cuts power on a loaded
        print (#1890). Previously this hardcoded a 50°C / 600s cooldown wait and
        powered off on the timeout regardless of print state.
        """
        if not item.auto_off_after:
            return
        try:
            await smart_plug_manager.schedule_off_after_queue_job(item.printer_id, db)
        except Exception as e:
            logger.warning("Auto-off: Failed to schedule power-off for printer %s: %s", item.printer_id, e)

    async def _get_job_name(self, db: AsyncSession, item: PrintQueueItem) -> str:
        """Get a human-readable name for a queue item."""
        if item.archive_id:
            result = await db.execute(select(PrintArchive).where(PrintArchive.id == item.archive_id))
            archive = result.scalar_one_or_none()
            if archive:
                return archive.filename.replace(".gcode.3mf", "").replace(".3mf", "")
        if item.library_file_id:
            result = await db.execute(LibraryFile.active().where(LibraryFile.id == item.library_file_id))
            library_file = result.scalar_one_or_none()
            if library_file:
                return library_file.filename.replace(".gcode.3mf", "").replace(".3mf", "")
        # A cross-model item (#671) holds no file of its own until a printer is
        # picked, so name it after its first candidate — otherwise every waiting
        # notification for one reads "Job #12". Queried rather than read off
        # item.variants because callers outside the selection loop have not
        # eager-loaded them, and a lazy load raises in async.
        first_variant_name = (
            await db.execute(
                select(LibraryFile.filename)
                .join(PrintQueueVariant, PrintQueueVariant.library_file_id == LibraryFile.id)
                .where(PrintQueueVariant.queue_item_id == item.id)
                .order_by(PrintQueueVariant.position, PrintQueueVariant.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if first_variant_name:
            return first_variant_name.replace(".gcode.3mf", "").replace(".3mf", "")
        return f"Job #{item.id}"

    async def _get_printer(self, db: AsyncSession, printer_id: int) -> Printer | None:
        """Get printer by ID."""
        result = await db.execute(select(Printer).where(Printer.id == printer_id))
        return result.scalar_one_or_none()

    async def _block_on_filament_deficit(
        self,
        db: AsyncSession,
        item: PrintQueueItem,
    ) -> bool:
        """Promote the item to manual_start when the assigned spool is short (#1496).

        Returns True when this dispatch attempt was blocked, False when the
        item is clear to start. A previously-flagged item whose spool has
        since been swapped to one with enough material clears the flag here
        so the next scheduler tick dispatches it.
        """
        # User has explicitly acknowledged the deficit ("Print Anyway") —
        # don't re-flag, don't even compute. Without this short-circuit the
        # scheduler bounces between "user said anyway" (route clears
        # manual_start) and "scheduler re-blocked" (this method re-flags it
        # on identical spool state) (#1698-followup).
        if item.skip_filament_check:
            # #1762 diagnostic: surface the short-circuit at INFO so a
            # future "Print Anyway didn't work" report (e.g. issue #1762
            # comment 3) has actionable evidence in the support bundle
            # without needing DEBUG enabled.
            logger.info(
                "Queue item %s honouring user's Print Anyway acknowledgement — skipping deficit check",
                item.id,
            )
            return False

        try:
            deficit = await compute_deficit_for_queue_item(db, item)
        except Exception as e:
            # Never let a flaky deficit check wedge the queue — log and let
            # dispatch proceed. The PrintModal-side check still runs on the
            # manual paths.
            logger.warning("Filament deficit check failed for item %s: %s", item.id, e)
            return False

        if deficit:
            item.filament_short = True
            item.manual_start = True
            await db.commit()
            job_name = await self._get_job_name(db, item)
            printer = await self._get_printer(db, item.printer_id) if item.printer_id else None
            logger.info(
                "Queue item %s blocked on filament deficit (%d slot(s)) — promoted to manual_start",
                item.id,
                len(deficit),
            )
            try:
                await notification_service.on_queue_job_waiting(
                    job_name=job_name,
                    target_model=(printer.model if printer else "") or "",
                    waiting_reason="filament_short",
                    db=db,
                )
            except Exception as e:
                logger.debug("filament_short notification failed for item %s: %s", item.id, e)
            return True

        # No deficit — clear any stale flag from a previous tick.
        if item.filament_short:
            item.filament_short = False
            await db.commit()
        return False

    async def _propagate_owner_to_printer_manager(self, db: AsyncSession, item: PrintQueueItem) -> None:
        """Hand the queue item's owner to printer_manager so the
        print-complete callback can credit the user in PrintLogEntry (#1670).

        No-ops when the item has no `created_by_id` or the referenced user
        row is missing (e.g. user deleted between queue-add and dispatch —
        in that case the print log row falls back to the existing un-credited
        behaviour rather than crashing the dispatch).
        """
        if not item.created_by_id:
            return
        from backend.app.models.user import User

        owner = await db.get(User, item.created_by_id)
        if owner:
            printer_manager.set_current_print_user(item.printer_id, owner.id, owner.username)

    async def _prepare_print_source(self, db, item):
        # Get printer first (needed for both paths)
        result = await db.execute(select(Printer).where(Printer.id == item.printer_id))
        printer = result.scalar_one_or_none()
        if not printer:
            item.status = "failed"
            item.error_message = "Printer not found"
            item.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error("Queue item %s: Printer %s not found", item.id, item.printer_id)
            await self._power_off_if_needed(db, item)
            return

        # Check printer is connected
        if not printer_manager.is_connected(item.printer_id):
            item.status = "failed"
            item.error_message = "Printer not connected"
            item.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error("Queue item %s: Printer %s not connected", item.id, item.printer_id)
            await self._power_off_if_needed(db, item)
            return

        # Re-read before FTP to avoid wasted upload after a concurrent cancel;
        # the pending→printing CAS below remains the load-bearing guard (#1853).
        await db.refresh(item)
        if item.status != "pending":
            logger.info(
                "Queue item %s no longer pending (status=%s) — aborting dispatch",
                item.id,
                item.status,
            )
            return

        pre_dispatch_state = getattr(printer_manager.get_status(item.printer_id), "state", None)
        if pre_dispatch_state in _ACTIVE_PRINT_STATES:
            logger.info(
                "Queue item %s: printer %s is busy (state=%s), deferring dispatch",
                item.id,
                item.printer_id,
                pre_dispatch_state,
            )
            return

        archive = None
        library_file = None
        file_path = None
        filename = None
        cleanup_disk_paths: list[Path] = []

        if item.archive_id:
            # Print from archive
            result = await db.execute(select(PrintArchive).where(PrintArchive.id == item.archive_id))
            archive = result.scalar_one_or_none()
            if not archive:
                item.status = "failed"
                item.error_message = "Archive not found"
                item.completed_at = datetime.now(timezone.utc)
                await db.commit()
                logger.error("Queue item %s: Archive %s not found", item.id, item.archive_id)
                await self._power_off_if_needed(db, item)
                return

            file_path = settings.base_dir / archive.file_path
            filename = archive.filename

        elif item.library_file_id:
            # Print from library file (file manager)
            result = await db.execute(LibraryFile.active().where(LibraryFile.id == item.library_file_id))
            library_file = result.scalar_one_or_none()
            if not library_file:
                await fail_missing_library_source(db, item)
                await self._power_off_if_needed(db, item)
                return
            # Library files store absolute paths
            lib_path = Path(library_file.file_path)
            file_path = lib_path if lib_path.is_absolute() else settings.base_dir / library_file.file_path
            filename = library_file.filename

            # Create archive from library file so usage tracking has access to the 3MF
            queue_item_id = item.id
            source_library_file_id = item.library_file_id
            try:
                from backend.app.services.archive import ArchiveService

                archive_service = ArchiveService(db)
                archive = await archive_service.archive_print(
                    printer_id=item.printer_id,
                    source_file=file_path,
                    original_filename=filename,
                    created_by_id=item.created_by_id,
                    project_id=item.project_id,
                    plate_id=item.plate_id,
                )
                if archive:
                    item.archive_id = archive.id
                    if item.cleanup_library_after_dispatch and not library_file.is_external:
                        cleanup_disk_paths.append(file_path)
                        if library_file.thumbnail_path:
                            thumb_path = Path(library_file.thumbnail_path)
                            if not thumb_path.is_absolute():
                                thumb_path = settings.base_dir / library_file.thumbnail_path
                            cleanup_disk_paths.append(thumb_path)
                        await consume_transient_library_source(db, item, library_file, archive.id)
                        file_path = settings.base_dir / archive.file_path
                        filename = archive.filename
                    # Commit before FTP so SQLite does not hold the WAL writer lock (#1853).
                    await db.commit()
                    logger.info(
                        "Queue item %s: Created archive %s from library file %s",
                        item.id,
                        archive.id,
                        source_library_file_id,
                    )
            except Exception as e:
                logger.warning(
                    "Queue item %s: Failed to create archive from library file: %s",
                    queue_item_id,
                    e,
                    exc_info=True,
                )
                await db.rollback()
                item = await db.get(PrintQueueItem, queue_item_id)
                if item:
                    item.status = "failed"
                    item.error_message = "Failed to create archive from library file"
                    item.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    await self._power_off_if_needed(db, item)
                return

            if not archive:
                item.status = "failed"
                item.error_message = "Failed to create archive from library file"
                item.completed_at = datetime.now(timezone.utc)
                await db.commit()
                logger.error("Queue item %s: Archive creation from library file returned no archive", item.id)
                await self._power_off_if_needed(db, item)
                return

        else:
            # Neither archive nor library file specified
            item.status = "failed"
            item.error_message = "No source file specified"
            item.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error("Queue item %s: No archive_id or library_file_id specified", item.id)
            await self._power_off_if_needed(db, item)
            return

        if archive:
            from backend.app.services.print_confirmation import initialize_queue_outcome

            await initialize_queue_outcome(db, item, archive)
            await db.commit()

        # Check file exists on disk
        if not file_path.exists():
            item.status = "failed"
            item.error_message = "Source file not found on disk"
            item.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error("Queue item %s: File not found: %s", item.id, file_path)
            await self._power_off_if_needed(db, item)
            return

        if archive and archive.plate_id is None and item.plate_id is not None:
            refresh_archive_plate_metadata(archive, file_path, item.plate_id)
            await db.commit()

        return printer, archive, library_file, file_path, filename, cleanup_disk_paths

    async def _requeue_after_upload_refused(self, db, item, printer, error_msg, toast_uid):
        # Keep the assigned printer: persisted AMS mappings belong to its trays.
        # The caller refreshed status, so never overwrite a concurrent cancel.
        refusals = self._upload_refusals.get(printer.id, 0) + 1
        self._upload_refusals[printer.id] = refusals
        delay = _upload_backoff_seconds(refusals)
        self._upload_backoff[printer.id] = time.monotonic() + delay
        if item.error_message:
            item.error_message = None
            await db.commit()
        logger.warning(
            "Queue item %s: upload refused (%s); retained, retrying printer %s in %ss",
            item.id,
            error_msg,
            printer.id,
            delay,
        )
        try:
            await ws_manager.send_queue_item_failed(
                user_id=toast_uid, queue_item_id=item.id, printer_id=item.printer_id, reason="upload_failed"
            )
        except Exception:
            pass

    async def _upload_print_file(self, db, item, printer, file_path, filename, injected_path):
        # Upload to root directory (not /cache/) - the start_print command references
        # files by name only (ftp://{filename}), so they must be in the root
        remote_filename = derive_remote_filename(filename)
        remote_path = f"/{remote_filename}"
        # Get FTP retry settings
        ftp_retry_enabled, ftp_retry_count, ftp_retry_delay, ftp_timeout = await get_ftp_retry_settings()
        logger.info(
            f"Queue item {item.id}: FTP upload starting - printer={printer.name} ({printer.model}), "
            f"ip={printer.ip_address}, file={remote_filename}, local_path={file_path}, "
            f"retry_enabled={ftp_retry_enabled}, retry_count={ftp_retry_count}, timeout={ftp_timeout}"
        )
        # Delete existing file if present (avoids 553 error on overwrite)
        try:
            logger.debug("Queue item %s: Deleting existing file %s if present...", item.id, remote_path)
            delete_result = await delete_file_async(
                printer.ip_address,
                printer.access_code,
                remote_path,
                socket_timeout=ftp_timeout,
                printer_model=printer.model,
                respect_handshake_cooldown=False,
            )
            logger.debug("Queue item %s: Delete result: %s", item.id, delete_result)
        except Exception as e:
            logger.debug("Queue item %s: Delete failed (may not exist): %s", item.id, e)
        # Dispatch toast — announce the upload start with the total byte
        # count so the frontend can render an honest progress bar.
        toast_uid = item.created_by_id
        toast_file_name = filename.replace(".gcode.3mf", "").replace(".3mf", "")
        try:
            total_bytes = file_path.stat().st_size
        except OSError:
            total_bytes = 0
        try:
            await ws_manager.send_queue_item_uploading(
                user_id=toast_uid,
                queue_item_id=item.id,
                printer_id=item.printer_id,
                printer_name=printer.name,
                file_name=toast_file_name,
                total_bytes=total_bytes,
            )
        except Exception:
            pass  # toast is best-effort
        progress_bridge = _UploadProgressBridge(toast_uid, item.id)
        upload_error: str | None = None
        upload_failure = FtpFailureReport()
        try:
            if ftp_retry_enabled:
                uploaded = await with_ftp_retry(
                    upload_file_async,
                    printer.ip_address,
                    printer.access_code,
                    file_path,
                    remote_path,
                    socket_timeout=ftp_timeout,
                    printer_model=printer.model,
                    progress_callback=progress_bridge,
                    respect_handshake_cooldown=False,
                    failure=upload_failure,
                    max_retries=ftp_retry_count,
                    retry_delay=ftp_retry_delay,
                    operation_name=f"Upload print to {printer.name}",
                )
            else:
                uploaded = await upload_file_async(
                    printer.ip_address,
                    printer.access_code,
                    file_path,
                    remote_path,
                    socket_timeout=ftp_timeout,
                    printer_model=printer.model,
                    progress_callback=progress_bridge,
                    respect_handshake_cooldown=False,
                    failure=upload_failure,
                )
        except UploadCancelled as e:
            uploaded = False
            upload_error = (
                "Upload was too slow to finish and was cancelled. The printer's connection could not sustain "
                "the transfer. Check its Wi-Fi signal or move it closer to the access point."
            )
            logger.error("Queue item %s: upload deadline exceeded: %s", item.id, e)
        except Exception as e:
            uploaded = False
            logger.error("Queue item %s: FTP error: %s (type: %s)", item.id, e, type(e).__name__)

        finally:
            if injected_path and injected_path.exists():
                injected_path.unlink(missing_ok=True)

        if not uploaded:
            await db.refresh(item)
            if item.status != "pending":
                return  # A concurrent cancellation/removal also owns the failure outcome.
            error_msg = upload_error or describe_upload_failure(upload_failure.failure)
            failure = upload_failure.failure
            if upload_error is None and failure is not None and failure.kind in _UPLOAD_REQUEUE_KINDS:
                await self._requeue_after_upload_refused(db, item, printer, error_msg, toast_uid)
                return
            item.status = "failed"
            item.error_message = error_msg
            item.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error(
                f"Queue item {item.id}: FTP upload failed - printer={printer.name}, model={printer.model}, "
                f"ip={printer.ip_address}. Check logs above for storage diagnostics and specific error codes."
            )

            # Send failure notification
            await notification_service.on_queue_job_failed(
                job_name=filename.replace(".gcode.3mf", "").replace(".3mf", ""),
                printer_id=printer.id,
                printer_name=printer.name,
                reason=error_msg,
                db=db,
            )
            try:
                await ws_manager.send_queue_item_failed(
                    user_id=toast_uid,
                    queue_item_id=item.id,
                    printer_id=item.printer_id,
                    reason="upload_failed",
                )
            except Exception:
                pass
            await self._power_off_if_needed(db, item)
            return

        self._upload_backoff.pop(printer.id, None)
        self._upload_refusals.pop(printer.id, None)
        self._upload_refusal_notified.discard(printer.id)
        return remote_filename, remote_path, ftp_timeout, toast_uid

    async def _inject_dispatch_gcode(self, db, item, printer, file_path, effective_plate_id):
        # G-code injection for auto-print systems (#422)
        injected_path = None
        if item.gcode_injection:
            try:
                snippets_raw = await self._get_setting(db, "gcode_snippets")
                if snippets_raw:
                    snippets = json.loads(snippets_raw)
                    model_snippets = snippets.get(printer.model, {})
                    start_gc = (model_snippets.get("start_gcode") or "").strip()
                    end_gc = (model_snippets.get("end_gcode") or "").strip()
                    if start_gc or end_gc:
                        from backend.app.utils.threemf_tools import inject_gcode_into_3mf

                        injected_path = inject_gcode_into_3mf(
                            file_path, effective_plate_id, start_gc or None, end_gc or None
                        )
                        if injected_path:
                            file_path = injected_path
                            logger.info("Queue item %s: G-code injected for model %s", item.id, printer.model)
                        else:
                            logger.warning(
                                "Queue item %s: G-code injection returned no result, using original", item.id
                            )
            except Exception as e:
                logger.warning("Queue item %s: G-code injection failed, using original: %s", item.id, e)
        return file_path, injected_path

    async def _start_print(self, db: AsyncSession, item: PrintQueueItem):
        if preheat_ownership.blocks_power_off(item.printer_id) and not preheat_ownership.can_adopt(item):
            logger.info("Queue item %s deferred: printer has unresolved preheat ownership", item.id)
            return
        async with preheat_ownership.dispatch(item, printer_manager, db):
            await self._start_print_owned(db, item)

    @staticmethod
    def _parse_dispatch_mapping(item):
        # Parse AMS mapping if stored
        ams_mapping = None
        if item.ams_mapping:
            try:
                ams_mapping = json.loads(item.ams_mapping)
            except json.JSONDecodeError:
                logger.warning("Queue item %s: Invalid AMS mapping JSON, ignoring", item.id)

        return ams_mapping

    async def _start_print_owned(self, db: AsyncSession, item: PrintQueueItem):
        """Upload file and start print for a queue item.

        Supports two sources:
        - archive_id: Print from an existing archive
        - library_file_id: Print from a library file (file manager)
        """
        logger.info("Starting queue item %s", item.id)

        prepared = await self._prepare_print_source(db, item)
        if prepared is None:
            return
        printer, archive, library_file, file_path, filename, cleanup_disk_paths = prepared

        # Preheat / heat-soak (#1468) before upload. Best-effort: any failure logs and
        # falls through to the normal upload+start path rather than turning a
        # configuration issue into a failed queue item.
        await self._preheat_and_soak(db, item, printer, archive)
        preheat_ownership.release_skipped_preheat()

        # Resolve against the original file before injection/upload replaces or
        # removes the temporary path. All dispatch consumers share this ID.
        effective_plate_id = _effective_plate_id(item.plate_id, file_path)
        file_path, injected_path = await self._inject_dispatch_gcode(db, item, printer, file_path, effective_plate_id)
        uploaded = await self._upload_print_file(db, item, printer, file_path, filename, injected_path)
        if uploaded is None:
            return
        remote_filename, remote_path, ftp_timeout, toast_uid = uploaded

        ams_mapping = self._parse_dispatch_mapping(item)

        # Register as expected print so we don't create a duplicate archive
        # Only applicable for archive-based prints
        if archive:
            from backend.app.main import register_expected_print

            register_expected_print(
                item.printer_id,
                remote_filename,
                archive.id,
                ams_mapping=ams_mapping,
                created_by_id=item.created_by_id,
                plate_id=effective_plate_id,
            )

        # Propagate the queue item's owner into printer_manager so the
        # print-complete callback can credit the user in the PrintLogEntry
        # (#1670). `created_by_id` is set either at queue-add time (UI-added
        # items) or when the user clicks the manual-start button.
        await self._propagate_owner_to_printer_manager(db, item)
        require_plate_clear = await self._get_bool_setting(db, "require_plate_clear", default=False)

        # K recovery may yield to a user cancellation. Keep it before the
        # pending-to-printing CAS so that cancellation wins before MQTT send.
        from backend.app.services import kprofile_drift

        try:
            await kprofile_drift.reapply_lost_kprofiles(
                item.printer_id, kprofile_drift.dispatch_trays(ams_mapping, item.use_ams), throttle=False
            )
        except Exception:
            logger.exception("Queue item %s: K-profile recovery before dispatch failed", item.id)

        # Persist "printing" before MQTT to prevent phantom retries after a crash.
        # The CAS also lets a concurrent cancellation win before printer dispatch (#1853).
        now_utc = datetime.now(timezone.utc)
        cas = await db.execute(
            update(PrintQueueItem)
            .where(PrintQueueItem.id == item.id)
            .where(PrintQueueItem.status == "pending")
            .values(status="printing", started_at=now_utc)
        )
        await db.commit()
        if cas.rowcount == 0:
            logger.info(
                "Queue item %s no longer pending at print-command time "
                "(cancelled or removed mid-dispatch) — aborting before MQTT send (#1853)",
                item.id,
            )
            try:
                await delete_file_async(
                    printer.ip_address,
                    printer.access_code,
                    remote_path,
                    socket_timeout=ftp_timeout,
                    printer_model=printer.model,
                )
            except Exception as cleanup_err:
                logger.debug(
                    "Queue item %s: best-effort cleanup of uploaded file failed: %s",
                    item.id,
                    cleanup_err,
                )
            try:
                await ws_manager.send_queue_item_failed(
                    user_id=toast_uid,
                    queue_item_id=item.id,
                    printer_id=item.printer_id,
                    reason="cancelled_mid_dispatch",
                )
            except Exception:
                pass
            return
        # Sync the in-memory item so subsequent code that reads item.status /
        # item.started_at sees the values we just persisted.
        item.status = "printing"
        item.started_at = now_utc

        for cleanup_path in cleanup_disk_paths:
            try:
                if cleanup_path.exists():
                    cleanup_path.unlink()
            except OSError as cleanup_err:
                logger.warning(
                    "TRANSIENT_LIBRARY_FILE_ORPHAN %s",
                    json.dumps(
                        {
                            "queue_item_id": item.id,
                            "path": str(cleanup_path),
                            "error": str(cleanup_err),
                        },
                        sort_keys=True,
                    ),
                )

        logger.info("Queue item %s: Status set to 'printing', sending print command...", item.id)

        # Capture state before dispatch so the watchdog can detect whether the
        # printer actually transitioned (#967). Also capture subtask_id so the
        # watchdog can recognise "command landed but state hasn't flipped yet"
        # on slow H2D transitions (#1078).
        pre_status = printer_manager.get_status(item.printer_id)
        pre_state = getattr(pre_status, "state", None) if pre_status else None
        pre_subtask_id = getattr(pre_status, "subtask_id", None) if pre_status else None
        pre_gcode_file = getattr(pre_status, "gcode_file", None) if pre_status else None

        # #1721: respect the user's explicit timelapse choice. The #1397
        # force-on at dispatch was removed because it caused per-layer nozzle
        # parking on slicer profiles with Timelapse Type = Smooth. Finish-photo
        # capture is now driven by the stg_cur=22 transition in bambu_mqtt.py
        # ("Filament unloading", toolhead parked, bed not yet dropped) with a
        # FINISH-state fallback — no need to force a video.
        effective_timelapse = bool(item.timelapse)

        # Start with the stored AMS/nozzle mapping and plate options.
        # nozzle_mapping comes from slicer project_file VP intake (#1780);
        # the MQTT builder applies it only to dual-nozzle models.
        preheat_ownership.guard_plate_clear(item.printer_id, require_plate_clear, printer_manager)
        started = printer_manager.start_print(
            item.printer_id,
            remote_filename,
            plate_id=effective_plate_id,
            ams_mapping=ams_mapping,
            bed_levelling=item.bed_levelling,
            flow_cali=item.flow_cali,
            vibration_cali=item.vibration_cali,
            layer_inspect=item.layer_inspect,
            timelapse=effective_timelapse,
            use_ams=item.use_ams,
            nozzle_offset_cali=item.nozzle_offset_cali,
            nozzle_mapping=item.nozzle_mapping,
        )

        if started:
            printer_manager.set_awaiting_plate_clear(item.printer_id, False)
            if lease := current_preheat_lease():
                if lease.expires_at:
                    lease.dispatched()
            logger.info("Queue item %s: Print started successfully - %s", item.id, filename)
            # No dispatch-toast event here: the legacy bg-dispatch path kept
            # status='processing' from upload start until the printer acked
            # (or timed out). The frontend derives "Awaiting printer…" purely
            # from upload_progress_pct >= 99.9; an explicit 'dispatched' WS
            # event would push the status chip out of 'PROCESSING' prematurely
            # — which is exactly what the screenshot at #1625-followup
            # complained about.

            # Register the local 3MF in the cover-cache so /cover skips FTP
            # (#1166 follow-up). file_path was resolved earlier from either the
            # archive or the library file row.
            if file_path is not None:
                cache_3mf_download(item.printer_id, remote_filename, file_path)

            # Hold the printer against further dispatches until the watchdog
            # confirms the printer transitioned (or until the hard timeout).
            # Prevents multi-plate batches from triple-dispatching onto the
            # same H2D Pro while it digests the first project_file (#1157).
            self._mark_printer_dispatched(item.printer_id, pre_state, pre_subtask_id)

            # Watchdog: if the printer never transitions out of pre_state AND
            # never advances subtask_id, the MQTT publish was accepted locally but
            # didn't reach the printer (half-broken session — same shape as
            # #887/#936). Revert the queue item so the next dispatch can pick it
            # up instead of leaving it stuck in "printing" (#967). subtask_id
            # check avoids false reverts on slow H2D FINISH→PREPARE transitions
            # that would otherwise cause the item to re-dispatch as a reprint
            # of the just-finished job (#1078).
            if pre_state:
                spawn_background_task(
                    self._watchdog_print_start(
                        item.id,
                        item.printer_id,
                        pre_state,
                        pre_subtask_id,
                        pre_gcode_file,
                        created_by_id=toast_uid,
                    ),
                    name=f"watchdog-print-start-{item.id}",
                )

            # Get estimated time for notification
            estimated_time = None
            if archive and archive.print_time_seconds:
                estimated_time = archive.print_time_seconds
            elif library_file and library_file.print_time_seconds:
                estimated_time = library_file.print_time_seconds

            # Send job started notification
            await notification_service.on_queue_job_started(
                job_name=filename.replace(".gcode.3mf", "").replace(".3mf", ""),
                printer_id=printer.id,
                printer_name=printer.name,
                db=db,
                estimated_time=estimated_time,
            )

            # MQTT relay - publish queue job started
            try:
                from backend.app.services.mqtt_relay import mqtt_relay

                await mqtt_relay.on_queue_job_started(
                    job_id=item.id,
                    filename=filename,
                    printer_id=printer.id,
                    printer_name=printer.name,
                    printer_serial=printer.serial_number,
                )
            except Exception:
                pass  # Don't fail if MQTT fails
        else:
            # Clean up uploaded file from SD card to prevent phantom prints
            try:
                await delete_file_async(
                    printer.ip_address,
                    printer.access_code,
                    remote_path,
                    printer_model=printer.model,
                )
            except Exception:
                pass  # Best-effort — don't fail the error handler

            post_dispatch_state = getattr(printer_manager.get_status(item.printer_id), "state", None)
            if post_dispatch_state in _ACTIVE_PRINT_STATES:
                logger.info(
                    "Queue item %s: printer %s became busy (state=%s) before start command, reverting to pending",
                    item.id,
                    item.printer_id,
                    post_dispatch_state,
                )
                item.status = "pending"
                item.started_at = None
                await db.commit()
                return

            # Print command failed - revert status
            item.status = "failed"
            item.error_message = "Failed to send print command to printer"
            item.completed_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error(
                f"Queue item {item.id}: Failed to start print on {printer.name} ({printer.model}) - "
                f"printer_manager.start_print() returned False. "
                f"This may indicate: printer not connected, MQTT error, unsupported model configuration, or firmware issue. "
                f"Check printer status and backend logs for details."
            )

            # Send failure notification
            await notification_service.on_queue_job_failed(
                job_name=filename.replace(".gcode.3mf", "").replace(".3mf", ""),
                printer_id=printer.id,
                printer_name=printer.name,
                reason="Failed to send print command to printer - check printer connection and status",
                db=db,
            )
            try:
                await ws_manager.send_queue_item_failed(
                    user_id=toast_uid,
                    queue_item_id=item.id,
                    printer_id=item.printer_id,
                    reason="start_command_failed",
                )
            except Exception:
                pass

            await self._power_off_if_needed(db, item)

    async def _notify_dispatch_gave_up(
        self,
        queue_item_id: int,
        printer_id: int,
        created_by_id: int | None,
    ) -> None:
        try:
            async with async_session() as db:
                item = await db.get(PrintQueueItem, queue_item_id)
                if not item:
                    return
                job_name = await self._get_job_name(db, item)
                printer = await self._get_printer(db, printer_id)
                await notification_service.on_queue_job_failed(
                    job_name=job_name,
                    printer_id=printer_id,
                    printer_name=printer.name if printer else "Unknown",
                    reason="Printer accepted the file but never started printing",
                    db=db,
                )
        except Exception as exc:
            logger.warning("Queue item %s: give-up notification failed: %s", queue_item_id, exc)

        try:
            await ws_manager.send_queue_item_failed(
                user_id=created_by_id,
                queue_item_id=queue_item_id,
                printer_id=printer_id,
                reason="never_started",
            )
        except Exception:
            pass

    @staticmethod
    async def _watchdog_print_start(
        queue_item_id: int,
        printer_id: int,
        pre_state: str,
        pre_subtask_id: str | None = None,
        pre_gcode_file: str | None = None,
        timeout: float = 90.0,
        phase_b_timeout: float = 180.0,
        poll_interval: float = 3.0,
        created_by_id: int | None = None,
    ) -> None:
        """Revert a queue item if the printer never acknowledges the start command.

        PrintOps optimistically marks the queue item as "printing" right after the
        MQTT project_file publish succeeds locally. The watchdog runs in two phases:

        Phase A (up to ``timeout``): wait for either an active-state transition
        or a ``subtask_id`` advance past ``pre_subtask_id``. State alone is the
        primary signal; subtask_id advance handles the H2D case where state can
        sit at FINISH for ~50 s after the printer accepted ``project_file``
        before flipping to PREPARE (#1078). If neither happens, the MQTT publish
        was lost on a half-broken session (#887/#936) — revert and force
        reconnect (the #967 recovery path).

        Phase B (up to ``phase_b_timeout``, only if Phase A exited on subtask_id
        alone): keep watching for the active-state transition. subtask_id alone
        proves the file landed but not that the printer started — and a printer
        that accepts the command but stays at IDLE/FINISH indefinitely (e.g.
        cloud+LAN re-auth dance after a power cycle on old firmware, #1678)
        used to leave the queue item stuck in 'printing' forever because the
        old watchdog returned success as soon as subtask_id advanced. If Phase
        B times out, revert the queue item so the user can retry without
        restarting PrintOps. Skip ``force_reconnect`` here: the file landed and
        a forced reconnect mid-parse triggers 0500_4003 (#1150).

        Phase A timeout raised from 45 s → 90 s as belt-and-braces for slow
        transitions that also don't emit an early subtask_id tick.
        """
        last_status = None
        landed_on_subtask = False
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            status = printer_manager.get_status(printer_id)
            if not status:
                # Printer disconnected — don't mess with the DB. Drop the
                # in-memory dispatch hold too so a fresh dispatch can retry
                # once the printer comes back; the hard timeout would
                # otherwise hold the printer unnecessarily.
                scheduler._release_dispatch_hold(printer_id)
                return
            last_status = status
            if status.state in _ACTIVE_PRINT_STATES:
                # Printer is actively processing the job — release the
                # post-dispatch hold so the next pending item for this printer
                # can be evaluated normally. We do NOT accept arbitrary state
                # transitions: a printer going FINISH -> IDLE (user dismissed
                # the post-print prompt without accepting our project_file)
                # would otherwise look like "command landed" and leave the
                # queue item stuck in 'printing' forever (#1370).
                scheduler._release_dispatch_hold(printer_id)
                try:
                    await ws_manager.send_queue_item_acked(
                        user_id=created_by_id,
                        queue_item_id=queue_item_id,
                        printer_id=printer_id,
                    )
                except Exception:
                    pass
                return
            if pre_subtask_id is not None and status.subtask_id is not None and status.subtask_id != pre_subtask_id:
                # Phase A exit — printer accepted the file (subtask_id flipped
                # to our submission id). Don't return yet: the printer may
                # have accepted the command but never actually start (e.g.
                # cloud+LAN re-auth dance after a power cycle, #1678). Phase
                # B watches for the active-state transition.
                landed_on_subtask = True
                break

        if landed_on_subtask:
            phase_b_deadline = time.monotonic() + phase_b_timeout
            while time.monotonic() < phase_b_deadline:
                await asyncio.sleep(poll_interval)
                status = printer_manager.get_status(printer_id)
                if not status:
                    scheduler._release_dispatch_hold(printer_id)
                    return
                last_status = status
                if status.state in _ACTIVE_PRINT_STATES:
                    scheduler._release_dispatch_hold(printer_id)
                    try:
                        await ws_manager.send_queue_item_acked(
                            user_id=created_by_id,
                            queue_item_id=queue_item_id,
                            printer_id=printer_id,
                        )
                    except Exception:
                        pass
                    return

        # No active-state transition. Revert the item so the scheduler can retry.
        # Drop the in-memory hold so the retry isn't blocked by it.
        scheduler._release_dispatch_hold(printer_id)

        # Three outcomes from the revert attempt, each routed differently:
        #   "reverted":          row flipped from printing -> pending, run recovery
        #   "already_moved_on":  item.status != 'printing' (completed/cancelled by
        #                        on_print_complete or user). Skip recovery entirely
        #                        — the print clearly landed somewhere even if the
        #                        watchdog didn't see the active-state transition.
        #   "revert_failed":     SQLite contention exhausted retries. Still run
        #                        recovery so the MQTT session gets a fresh client_id
        #                        on the half-broken-session path.
        async def _do_revert(db):
            item = await db.get(PrintQueueItem, queue_item_id)
            if not item or item.status != "printing":
                return "already_moved_on"
            item.dispatch_attempts = (item.dispatch_attempts or 0) + 1
            item.started_at = None
            # Charge the candidate that was actually copied onto the row.
            if item.library_file_id is not None:
                charged = await db.execute(
                    update(PrintQueueVariant)
                    .where(PrintQueueVariant.queue_item_id == item.id)
                    .where(PrintQueueVariant.library_file_id == item.library_file_id)
                    .values(attempt_count=PrintQueueVariant.attempt_count + 1)
                )
                if charged.rowcount:
                    # Return the resolved candidate to model selection on retry.
                    item.printer_id = None
            if item.dispatch_attempts >= DISPATCH_MAX_ATTEMPTS:
                item.status = "failed"
                item.error_message = (
                    "The printer accepted the file but never started printing, after "
                    f"{item.dispatch_attempts} attempts. Check the printer's screen for a prompt or error, "
                    "confirm its SD card is readable, and start the job again."
                )
                item.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return "gave_up"
            item.status = "pending"
            await db.commit()
            return "reverted"

        try:
            revert_outcome = await run_with_retry(_do_revert, label=f"watchdog revert item={queue_item_id}")
        except Exception as e:
            logger.warning(
                "Queue item %s: failed to revert to 'pending' (printer %d): %s — "
                "scheduler may keep treating this item as in-flight",
                queue_item_id,
                printer_id,
                e,
            )
            revert_outcome = "revert_failed"

        if revert_outcome == "already_moved_on":
            # Preserves the pre-#1370 early-return: if on_print_complete (or any
            # other path) already moved the item past 'printing', don't run the
            # MQTT session-recovery logic below — a forced reconnect on a healthy
            # session breaks ongoing prints on the same printer.
            return

        total_timeout = timeout + (phase_b_timeout if landed_on_subtask else 0.0)
        if revert_outcome == "gave_up":
            logger.warning(
                "Queue item %s: printer %d never started after %d dispatch attempts — marking failed (#2555)",
                queue_item_id,
                printer_id,
                DISPATCH_MAX_ATTEMPTS,
            )
            await scheduler._notify_dispatch_gave_up(queue_item_id, printer_id, created_by_id)

            async def _schedule_auto_off(db):
                item = await db.get(PrintQueueItem, queue_item_id)
                if item:
                    await scheduler._power_off_if_needed(db, item)

            try:
                await run_with_retry(_schedule_auto_off, label=f"watchdog auto-off item={queue_item_id}")
            except Exception as e:
                logger.warning(
                    "Queue item %s: failed to schedule auto-off after watchdog give-up: %s", queue_item_id, e
                )
        elif revert_outcome == "reverted":
            if landed_on_subtask:
                logger.warning(
                    "Queue item %s: printer %d accepted project_file (subtask_id "
                    "advanced) but never transitioned to an active state within "
                    "%.0fs — printer wedged post-acceptance; reverted to 'pending' "
                    "for retry (#1678)",
                    queue_item_id,
                    printer_id,
                    total_timeout,
                )
            else:
                logger.warning(
                    "Queue item %s: printer %d did not respond to print command within "
                    "%.0fs (state still %s, subtask_id still %s) — reverted to 'pending' "
                    "for retry (#967)",
                    queue_item_id,
                    printer_id,
                    timeout,
                    pre_state,
                    pre_subtask_id,
                )

        # Phase B was entered iff subtask_id advanced, which means the
        # project_file landed on the printer. A forced reconnect at this point
        # would interrupt the printer's parse and trigger 0500_4003 (#1150) —
        # skip the recovery entirely.
        if landed_on_subtask:
            return

        # Phase A timeout path: if the printer's gcode_file changed since
        # pre-dispatch, the project_file command landed and the printer is
        # parsing — a forced reconnect mid-parse triggers 0500_4003 (#1150).
        # If gcode_file is unchanged, the publish was silently swallowed
        # (#887/#936) and force_reconnect recovery is what we want.
        client = printer_manager.get_client(printer_id)
        current_gcode_file = getattr(last_status, "gcode_file", None) if last_status else None
        publish_landed = current_gcode_file is not None and current_gcode_file != pre_gcode_file
        if publish_landed:
            logger.warning(
                "Queue item %s: gcode_file changed to %r (was %r) — printer "
                "received the command and is parsing slowly. Skipping forced "
                "MQTT reconnect to avoid 0500_4003 mid-parse (#1150).",
                queue_item_id,
                current_gcode_file,
                pre_gcode_file,
            )
        elif client and hasattr(client, "force_reconnect_stale_session"):
            client.force_reconnect_stale_session(
                f"queue print command unacknowledged after {timeout:.0f}s "
                f"(state still {pre_state}, gcode_file {current_gcode_file!r})"
            )


# Global scheduler instance
scheduler = PrintScheduler()
