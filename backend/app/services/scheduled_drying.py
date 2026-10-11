"""Daily drying claims are durable before publication and are never retried."""

import asyncio
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from backend.app.core.database import async_session
from backend.app.models.drying_schedule import DryingSchedule, DryingScheduleRun
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.schemas.drying_schedule import DryingScheduleWrite
from backend.app.services.drying_ownership import printer_operation, reserved_printers
from backend.app.services.drying_schedule_time import daily_occurrence
from backend.app.services.printer_manager import _DRYING_MIN_FIRMWARE, printer_manager
from backend.app.utils.printer_models import normalize_printer_model

logger = logging.getLogger(__name__)
MAX_TELEMETRY_AGE = 60
START_CONFIRM_SECONDS = 120
MISSED_GRACE_SECONDS = 300


def utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def is_fresh(value: float, now: datetime) -> bool:
    return (
        isinstance(value, (int, float))
        and math.isfinite(value)
        and value > 0
        and 0 <= now.timestamp() - value <= MAX_TELEMETRY_AGE
    )


def scheduled_drying_block_reason(printer, state, ams_id, temperature, now, *, require_stopped=True):
    if not printer.is_active or not state or not state.connected:
        return "offline"
    model = (printer.model or "").strip().upper()
    firmware = state.firmware_version or ""
    minimum = _DRYING_MIN_FIRMWARE.get(model)
    if not minimum or not re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{2}", firmware) or firmware < minimum:
        return "unsupported_printer"
    telemetry = state.drying_telemetry
    if not telemetry.firmware_observed_at or not is_fresh(telemetry.idle_observed_at, now):
        return "telemetry_stale"
    if state.state not in ("IDLE", "FINISH", "FAILED") or state.stg_cur not in (-1, 0):
        return "printer_busy"
    module, ams_firmware = telemetry.modules.get(ams_id, (None, ""))
    if (
        module not in ("n3f", "n3s")
        or not re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{2}", ams_firmware)
        or module == "n3f"
        and not 0 <= ams_id <= 3
        or module == "n3s"
        and not 128 <= ams_id <= 135
    ):
        return "unsupported_ams"
    if temperature > (65 if module == "n3f" else 85):
        return "temperature_unsupported"
    observation = telemetry.units.get(ams_id)
    if not observation or not is_fresh(observation.observed_at, now) or observation.remaining_minutes is None:
        return "telemetry_stale"
    if observation.module_type != module:
        return "unsupported_ams"
    if not observation.reasons_known:
        return "capability_unknown"
    if observation.blocked:
        return "ams_busy"
    if require_stopped and observation.remaining_minutes != 0:
        return "already_drying"
    if require_stopped and any(
        module_type in ("n3f", "n3s") and identifier not in telemetry.units
        for identifier, (module_type, _) in telemetry.modules.items()
    ):
        return "capability_unknown"
    if require_stopped and any(
        not is_fresh(unit.observed_at, now) or unit.remaining_minutes != 0 for unit in telemetry.units.values()
    ):
        return "ams_busy"
    return None


async def configuration_conflict(db, printer):
    modes = list(
        (
            await db.execute(
                select(Settings).where(
                    Settings.key.in_(["queue_drying_enabled", "ambient_drying_enabled", "print_drying_enabled"])
                )
            )
        ).scalars()
    )
    if any(str(mode.value).lower() == "true" for mode in modes):
        return "automatic_mode_conflict"
    queued = list(
        (
            await db.execute(
                select(PrintQueueItem).where(
                    or_(PrintQueueItem.status.in_(["pending", "printing"]), PrintQueueItem.dispatching_at.is_not(None))
                )
            )
        ).scalars()
    )
    model = normalize_printer_model(printer.model)
    for item in queued:
        if (
            item.printer_id == printer.id
            or item.printer_id is None
            and (not item.target_model or normalize_printer_model(item.target_model) == model)
        ):
            return "queue_conflict"
    if printer.id in await reserved_printers(db):
        return "drying_owner_conflict"
    return None


class ScheduledDryingService:
    def __init__(self, session_factory=async_session, manager=printer_manager):
        self.session_factory = session_factory
        self.manager = manager
        self._tick_lock = asyncio.Lock()
        self.clock = lambda: datetime.now(timezone.utc)

    async def tick(self, now=None):
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            return
        async with self._tick_lock, self.session_factory() as db:
            await self._observe_runs(db, now)
            plans = list(
                (
                    await db.execute(
                        select(DryingSchedule.id, DryingSchedule.printer_id)
                        .where(DryingSchedule.enabled.is_(True), DryingSchedule.deleted_at.is_(None))
                        .order_by(DryingSchedule.id)
                    )
                ).all()
            )
            for plan_id, printer_id in plans:
                await self._evaluate(db, plan_id, printer_id, now)

    async def _evaluate(self, db, plan_id, printer_id, now):
        async with printer_operation(db, printer_id):
            plan = await db.get(DryingSchedule, plan_id, populate_existing=True)
            if not plan or not plan.enabled or plan.deleted_at:
                await db.rollback()
                return
            try:
                config = DryingScheduleWrite.model_validate(plan)
                local = now.astimezone(ZoneInfo(config.timezone))
                occurrence_date = local.date()
                due = daily_occurrence(occurrence_date, config.local_time, config.timezone)
                if due and now < due:
                    previous = daily_occurrence(occurrence_date - timedelta(days=1), config.local_time, config.timezone)
                    if previous and 0 <= (now - previous).total_seconds() <= MISSED_GRACE_SECONDS:
                        occurrence_date, due = occurrence_date - timedelta(days=1), previous
                if due is None and local.strftime("%H:%M") < config.local_time or due and now < due:
                    await db.rollback()
                    return
                reason = (
                    "dst_gap"
                    if due is None
                    else "missed"
                    if (now - due).total_seconds() > MISSED_GRACE_SECONDS
                    else None
                )
            except (ValueError, ValidationError):
                occurrence_date, due, reason = now.date(), now, "invalid_plan"
            day = occurrence_date.isoformat()
            existing = await db.scalar(
                select(DryingScheduleRun.id).where(
                    DryingScheduleRun.schedule_id == plan_id, DryingScheduleRun.occurrence_day == day
                )
            )
            if existing:
                await db.rollback()
                return
            printer = await db.get(Printer, printer_id)
            if printer is None:
                await db.rollback()
                return
            if reason is None:
                reason = scheduled_drying_block_reason(
                    printer, self.manager.get_status(printer.id), plan.ams_id, plan.temperature, now
                )
            if reason is None:
                reason = await configuration_conflict(db, printer)
            state = self.manager.get_status(printer.id)
            module_type = state.drying_telemetry.modules.get(plan.ams_id, (None, ""))[0] if state else None
            module_firmware = state.drying_telemetry.modules.get(plan.ams_id, (None, ""))[1] if state else None
            claim_now = max(now, self.clock())
            run = DryingScheduleRun(
                schedule_id=plan.id,
                printer_id=printer.id,
                ams_id=plan.ams_id,
                module_type=module_type,
                module_firmware=module_firmware,
                parameters_json=config.model_dump_json() if reason != "invalid_plan" else None,
                occurrence_day=day,
                due_at=utc_naive(due or now),
                claimed_at=utc_naive(claim_now),
                status="skipped" if reason else "claimed",
                reason=reason,
                active_printer_id=None if reason else printer.id,
            )
            db.add(run)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                return
            if reason:
                return
            recheck = scheduled_drying_block_reason(
                printer, self.manager.get_status(printer.id), config.ams_id, config.temperature, max(now, self.clock())
            )
            if recheck:
                run.status, run.reason, run.active_printer_id = "skipped", recheck, None
                await db.commit()
                return
            # Nothing after this durable claim may replay the command, including a crash.
            try:
                delivered = self.manager.send_drying_command(
                    printer.id,
                    config.ams_id,
                    config.temperature,
                    config.duration_hours,
                    mode=1,
                    filament=config.filament,
                    rotate_tray=config.rotate_tray,
                    qos=0,
                )
            except Exception:
                logger.exception("Scheduled drying run %d publication uncertain", run.id)
                delivered = False
            run.status = "awaiting_ack" if delivered else "uncertain"
            run.reason = None if delivered else "publish_uncertain"
            run.publication_at = utc_naive(max(claim_now, self.clock()))
            await db.commit()

    async def _observe_runs(self, db, now):
        runs = list(
            (
                await db.execute(
                    select(DryingScheduleRun.id, DryingScheduleRun.printer_id).where(
                        DryingScheduleRun.active_printer_id.is_not(None)
                    )
                )
            ).all()
        )
        for run_id, printer_id in runs:
            async with printer_operation(db, printer_id):
                run = await db.get(DryingScheduleRun, run_id, populate_existing=True)
                if run.active_printer_id is None:
                    await db.rollback()
                    continue
                state = self.manager.get_status(printer_id)
                observation = state.drying_telemetry.units.get(run.ams_id) if state and state.connected else None
                claim_time = run.claimed_at.replace(tzinfo=timezone.utc).timestamp()
                fresh = (
                    observation
                    and observation.remaining_minutes is not None
                    and is_fresh(observation.observed_at, now)
                    and observation.observed_at > claim_time
                    and run.publication_at
                    and observation.observed_at > run.publication_at.replace(tzinfo=timezone.utc).timestamp()
                    and observation.module_type == run.module_type
                    and state.drying_telemetry.modules.get(run.ams_id) == (run.module_type, run.module_firmware)
                )
                if fresh:
                    if observation.remaining_minutes > 0:
                        run.status, run.reason = "running", None
                        run.observed_running_at = utc_naive(
                            datetime.fromtimestamp(observation.observed_at, timezone.utc)
                        )
                    elif (
                        run.observed_running_at
                        and observation.observed_at > run.observed_running_at.replace(tzinfo=timezone.utc).timestamp()
                    ):
                        run.status, run.reason = "completed", None
                        run.finished_at = utc_naive(datetime.fromtimestamp(observation.observed_at, timezone.utc))
                        run.active_printer_id = None
                if run.status == "running" and state and state.state not in ("IDLE", "FINISH", "FAILED"):
                    run.status, run.reason = "uncertain", "printer_busy"
                if run.active_printer_id is not None:
                    if run.status == "running" and not fresh:
                        run.status, run.reason = "uncertain", "telemetry_stale"
                    elif (
                        run.status in ("claimed", "awaiting_ack")
                        and (utc_naive(now) - run.claimed_at).total_seconds() >= START_CONFIRM_SECONDS
                    ):
                        run.status, run.reason = "uncertain", "start_unconfirmed"
                await db.commit()


scheduled_drying = ScheduledDryingService()
