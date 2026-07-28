from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.models.smart_plug import SmartPlug
from backend.app.models.smart_plug_energy_snapshot import SmartPlugEnergySnapshot
from backend.app.services.plug_energy_history import derive_today_yesterday, fill_derived_energy
from backend.app.utils.local_time import local_day_start, to_naive_utc

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def berlin(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")


async def _plug(db) -> SmartPlug:
    plug = SmartPlug(
        name="Shelly",
        plug_type="rest",
        rest_energy_total_path="aenergy.total",
        rest_energy_total_multiplier=0.001,
    )
    db.add(plug)
    await db.commit()
    await db.refresh(plug)
    return plug


async def _snapshot(db, plug_id: int, when: datetime, kwh: float) -> None:
    db.add(
        SmartPlugEnergySnapshot(
            plug_id=plug_id,
            recorded_at=to_naive_utc(when),
            lifetime_kwh=kwh,
        )
    )
    await db.commit()


async def test_derives_today_and_yesterday_from_lifetime_counter(db_session):
    plug = await _plug(db_session)
    now = datetime.now(timezone.utc)

    await _snapshot(db_session, plug.id, local_day_start(now, days_ago=1), 100.0)
    await _snapshot(db_session, plug.id, local_day_start(now), 102.0)

    today, yesterday = await derive_today_yesterday(db_session, plug.id, live_total_kwh=103.5)

    assert today == pytest.approx(1.5)
    assert yesterday == pytest.approx(2.0)


async def test_yesterday_is_empty_until_two_midnights_exist(db_session):
    plug = await _plug(db_session)
    now = datetime.now(timezone.utc)
    await _snapshot(db_session, plug.id, local_day_start(now), 102.0)

    today, yesterday = await derive_today_yesterday(db_session, plug.id, live_total_kwh=103.5)

    assert today == pytest.approx(1.5)
    assert yesterday is None


async def test_derives_midnight_baseline_from_adjacent_snapshots(db_session):
    plug = await _plug(db_session)
    now = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
    midnight_today = local_day_start(now)

    await _snapshot(db_session, plug.id, local_day_start(now, days_ago=1), 100.0)
    await _snapshot(db_session, plug.id, midnight_today - timedelta(hours=1), 101.0)
    await _snapshot(db_session, plug.id, midnight_today + timedelta(minutes=5), 102.0)

    today, yesterday = await derive_today_yesterday(db_session, plug.id, live_total_kwh=104.0, now_utc=now)

    assert today == pytest.approx(2.0769, rel=1e-3)
    assert yesterday == pytest.approx(1.9231, rel=1e-3)


async def test_nothing_derivable_before_first_midnight_baseline(db_session):
    plug = await _plug(db_session)
    now = datetime.now(timezone.utc)
    await _snapshot(db_session, plug.id, now - timedelta(minutes=30), 102.0)

    today, yesterday = await derive_today_yesterday(db_session, plug.id, live_total_kwh=103.5)

    assert today is None
    assert yesterday is None


async def test_counter_reset_reports_blank_instead_of_negative(db_session):
    plug = await _plug(db_session)
    now = datetime.now(timezone.utc)
    await _snapshot(db_session, plug.id, local_day_start(now, days_ago=1), 100.0)
    await _snapshot(db_session, plug.id, local_day_start(now), 102.0)

    today, _yesterday = await derive_today_yesterday(db_session, plug.id, live_total_kwh=0.4)

    assert today is None


async def test_snapshots_from_other_plugs_are_not_borrowed(db_session):
    plug = await _plug(db_session)
    other = SmartPlug(name="Other", plug_type="rest")
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    now = datetime.now(timezone.utc)
    await _snapshot(db_session, other.id, local_day_start(now), 50.0)

    today, yesterday = await derive_today_yesterday(db_session, plug.id, live_total_kwh=103.5)

    assert today is None
    assert yesterday is None


async def test_fill_derived_energy_fills_lifetime_only_values(db_session):
    plug = await _plug(db_session)
    now = datetime.now(timezone.utc)
    await _snapshot(db_session, plug.id, local_day_start(now, days_ago=1), 100.0)
    await _snapshot(db_session, plug.id, local_day_start(now), 102.0)

    energy = await fill_derived_energy(db_session, plug.id, {"power": 84.0, "total": 103.5})

    assert energy["today"] == pytest.approx(1.5)
    assert energy["yesterday"] == pytest.approx(2.0)
    assert energy["total"] == 103.5


async def test_fill_derived_energy_never_overwrites_reported_daily_values(db_session):
    plug = await _plug(db_session)
    now = datetime.now(timezone.utc)
    await _snapshot(db_session, plug.id, local_day_start(now, days_ago=1), 100.0)
    await _snapshot(db_session, plug.id, local_day_start(now), 102.0)

    energy = await fill_derived_energy(db_session, plug.id, {"today": 9.9, "yesterday": 8.8, "total": 103.5})

    assert energy["today"] == 9.9
    assert energy["yesterday"] == 8.8


async def test_fill_derived_energy_without_lifetime_counter_is_left_alone(db_session):
    plug = await _plug(db_session)

    energy = await fill_derived_energy(db_session, plug.id, {"power": 84.0, "today": 1.2})

    assert energy == {"power": 84.0, "today": 1.2}
