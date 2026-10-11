"""Daily native AMS drying, using the existing printer read/control permissions."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import (
    RequirePermissionIfAuthEnabled,
    check_printer_access,
    resolve_optional_api_key,
    user_can_access_printer,
)
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.drying_schedule import DryingSchedule, DryingScheduleRun
from backend.app.models.printer import Printer
from backend.app.schemas.drying_schedule import DryingRunResponse, DryingScheduleResponse, DryingScheduleWrite
from backend.app.services.drying_ownership import printer_operation
from backend.app.services.printer_manager import printer_manager
from backend.app.services.scheduled_drying import configuration_conflict, scheduled_drying_block_reason, utc_naive

router = APIRouter(tags=["drying schedules"])


def _access(printer_id, user, api_key):
    if not user_can_access_printer(user, printer_id):
        raise HTTPException(403, "Printer access denied")
    if api_key is not None:
        check_printer_access(api_key, printer_id)


async def _printer(db, printer_id):
    printer = await db.get(Printer, printer_id)
    if not printer:
        raise HTTPException(404, "Printer not found")
    return printer


async def _plan(db, printer_id, schedule_id):
    plan = await db.scalar(
        select(DryingSchedule).where(
            DryingSchedule.id == schedule_id,
            DryingSchedule.printer_id == printer_id,
            DryingSchedule.deleted_at.is_(None),
        )
    )
    if not plan:
        raise HTTPException(404, "Drying schedule not found")
    return plan


async def _validate_enable(db, printer, data):
    if not data.enabled:
        return
    reason = scheduled_drying_block_reason(
        printer, printer_manager.get_status(printer.id), data.ams_id, data.temperature, datetime.now(timezone.utc)
    )
    reason = reason or await configuration_conflict(db, printer)
    if reason:
        raise HTTPException(409, {"code": reason})


@router.get("/{printer_id}/drying/schedules")
async def list_schedules(
    printer_id: int,
    user=RequirePermissionIfAuthEnabled(Permission.PRINTERS_READ),
    db: AsyncSession = Depends(get_db),
    api_key=Depends(resolve_optional_api_key),
):
    _access(printer_id, user, api_key)
    printer = await _printer(db, printer_id)
    plans = list(
        (
            await db.execute(
                select(DryingSchedule)
                .where(DryingSchedule.printer_id == printer_id, DryingSchedule.deleted_at.is_(None))
                .order_by(DryingSchedule.id)
            )
        ).scalars()
    )
    runs = list(
        (
            await db.execute(
                select(DryingScheduleRun)
                .where(DryingScheduleRun.printer_id == printer_id)
                .order_by(DryingScheduleRun.id.desc())
                .limit(30)
            )
        ).scalars()
    )
    state = printer_manager.get_status(printer_id)
    ids = {plan.ams_id for plan in plans}
    if state:
        ids.update(state.drying_telemetry.modules)
    capabilities = []
    for ams_id in sorted(ids):
        module = state.drying_telemetry.modules.get(ams_id, (None, ""))[0] if state else None
        capabilities.append(
            {
                "ams_id": ams_id,
                "module_type": module,
                "max_temperature": 65 if module == "n3f" else 85 if module == "n3s" else None,
                "reason": scheduled_drying_block_reason(printer, state, ams_id, 45, datetime.now(timezone.utc)),
            }
        )
    return {
        "schedules": [DryingScheduleResponse.model_validate(plan) for plan in plans],
        "runs": [DryingRunResponse.model_validate(run) for run in runs],
        "capabilities": capabilities,
    }


@router.post("/{printer_id}/drying/schedules", status_code=201, response_model=DryingScheduleResponse)
async def create_schedule(
    printer_id: int,
    data: DryingScheduleWrite,
    user=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
    api_key=Depends(resolve_optional_api_key),
):
    _access(printer_id, user, api_key)
    async with printer_operation(db, printer_id):
        printer = await _printer(db, printer_id)
        await _validate_enable(db, printer, data)
        plan = DryingSchedule(printer_id=printer_id, **data.model_dump())
        db.add(plan)
        await db.commit()
        return plan


@router.put("/{printer_id}/drying/schedules/{schedule_id}", response_model=DryingScheduleResponse)
async def update_schedule(
    printer_id: int,
    schedule_id: int,
    data: DryingScheduleWrite,
    user=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
    api_key=Depends(resolve_optional_api_key),
):
    _access(printer_id, user, api_key)
    async with printer_operation(db, printer_id):
        printer = await _printer(db, printer_id)
        plan = await _plan(db, printer_id, schedule_id)
        await _validate_enable(db, printer, data)
        for key, value in data.model_dump().items():
            setattr(plan, key, value)
        await db.commit()
        return plan


@router.delete("/{printer_id}/drying/schedules/{schedule_id}", status_code=204)
async def delete_schedule(
    printer_id: int,
    schedule_id: int,
    user=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
    api_key=Depends(resolve_optional_api_key),
):
    _access(printer_id, user, api_key)
    async with printer_operation(db, printer_id):
        plan = await _plan(db, printer_id, schedule_id)
        plan.enabled, plan.deleted_at = False, utc_naive(datetime.now(timezone.utc))
        await db.commit()


@router.post("/{printer_id}/drying/schedules/runs/{run_id}/resolve", response_model=DryingRunResponse)
async def resolve_run(
    printer_id: int,
    run_id: int,
    user=RequirePermissionIfAuthEnabled(Permission.PRINTERS_CONTROL),
    db: AsyncSession = Depends(get_db),
    api_key=Depends(resolve_optional_api_key),
):
    _access(printer_id, user, api_key)
    async with printer_operation(db, printer_id):
        printer = await _printer(db, printer_id)
        run = await db.get(DryingScheduleRun, run_id)
        if not run or run.printer_id != printer_id:
            raise HTTPException(404, "Drying run not found")
        if run.status != "uncertain" or run.active_printer_id is None:
            raise HTTPException(409, {"code": "run_not_uncertain"})
        now = datetime.now(timezone.utc)
        state = printer_manager.get_status(printer_id)
        reason = scheduled_drying_block_reason(printer, state, run.ams_id, 45, now)
        observation = state.drying_telemetry.units.get(run.ams_id) if state else None
        cutoff = max(run.claimed_at, run.publication_at or run.claimed_at).replace(tzinfo=timezone.utc).timestamp()
        if reason or not observation or observation.observed_at <= cutoff:
            raise HTTPException(409, {"code": reason or "telemetry_stale"})
        run.status, run.reason, run.active_printer_id = "resolved", "operator_resolved", None
        run.finished_at = utc_naive(now)
        await db.commit()
        return run
