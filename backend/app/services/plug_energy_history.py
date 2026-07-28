"""Derive daily energy values from lifetime smart-plug counters."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.smart_plug_energy_snapshot import SmartPlugEnergySnapshot
from backend.app.utils.local_time import local_day_start, to_naive_utc

logger = logging.getLogger(__name__)


async def _counter_at(
    db: AsyncSession,
    plug_id: int,
    boundary: datetime,
    *,
    fallback_after: tuple[datetime, float] | None = None,
) -> float | None:
    """Return a lifetime counter derived at the exact day boundary."""
    boundary_utc = to_naive_utc(boundary)
    before_result = await db.execute(
        select(SmartPlugEnergySnapshot.recorded_at, SmartPlugEnergySnapshot.lifetime_kwh)
        .where(
            SmartPlugEnergySnapshot.plug_id == plug_id,
            SmartPlugEnergySnapshot.recorded_at <= boundary_utc,
        )
        .order_by(SmartPlugEnergySnapshot.recorded_at.desc())
        .limit(1)
    )
    before = before_result.one_or_none()
    if before is not None and before.recorded_at == boundary_utc:
        return before.lifetime_kwh

    after_result = await db.execute(
        select(SmartPlugEnergySnapshot.recorded_at, SmartPlugEnergySnapshot.lifetime_kwh)
        .where(
            SmartPlugEnergySnapshot.plug_id == plug_id,
            SmartPlugEnergySnapshot.recorded_at >= boundary_utc,
        )
        .order_by(SmartPlugEnergySnapshot.recorded_at.asc())
        .limit(1)
    )
    after = after_result.one_or_none()
    if after is None and fallback_after is not None and fallback_after[0] >= boundary_utc:
        after = fallback_after
    if before is None or after is None:
        return None

    before_at, before_kwh = before
    after_at, after_kwh = after
    if after_kwh < before_kwh or after_at <= before_at:
        return None
    span_seconds = (after_at - before_at).total_seconds()
    if span_seconds <= 0:
        return None
    boundary_offset = (boundary_utc - before_at).total_seconds()
    return before_kwh + (after_kwh - before_kwh) * (boundary_offset / span_seconds)


async def derive_today_yesterday(
    db: AsyncSession,
    plug_id: int,
    live_total_kwh: float,
    *,
    now_utc: datetime | None = None,
) -> tuple[float | None, float | None]:
    """Return today/yesterday kWh from a cumulative lifetime counter."""
    now = now_utc or datetime.now(timezone.utc)
    now_counter = (to_naive_utc(now), live_total_kwh)
    midnight_today = local_day_start(now)
    midnight_yesterday = local_day_start(now, days_ago=1)

    base_today = await _counter_at(db, plug_id, midnight_today, fallback_after=now_counter)
    if base_today is None:
        return None, None

    today: float | None = live_total_kwh - base_today
    if today < 0:
        logger.info(
            "Plug %s: lifetime counter went backwards (%.3f < %.3f); reporting no daily value",
            plug_id,
            live_total_kwh,
            base_today,
        )
        today = None

    base_yesterday = await _counter_at(db, plug_id, midnight_yesterday)
    if base_yesterday is None:
        return today, None

    yesterday: float | None = base_today - base_yesterday
    if yesterday < 0:
        yesterday = None

    return today, yesterday


async def fill_derived_energy(db: AsyncSession, plug_id: int, energy: dict) -> dict:
    """Fill missing today/yesterday values when a lifetime total is available."""
    total = energy.get("total")
    if total is None:
        return energy
    if energy.get("today") is not None and energy.get("yesterday") is not None:
        return energy

    today, yesterday = await derive_today_yesterday(db, plug_id, float(total))
    if energy.get("today") is None and today is not None:
        energy["today"] = round(today, 3)
    if energy.get("yesterday") is None and yesterday is not None:
        energy["yesterday"] = round(yesterday, 3)
    return energy
