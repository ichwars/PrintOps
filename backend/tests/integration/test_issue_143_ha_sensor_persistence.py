"""Database coverage for bounded Home Assistant sensor state persistence (#143)."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from backend.app.models.printer import Printer
from backend.app.models.printer_ha_sensor import PrinterHASensor
from backend.app.services.ha_sensor_manager import HASensorManager

POSTGRES_TEST_URL = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
LAST_STATE_WIDTH = 64


def _sensors(printer_id: int) -> list[PrinterHASensor]:
    return [
        PrinterHASensor(
            printer_id=printer_id,
            name="Long text",
            entity_id="binary_sensor.issue_143_long",
            kind="binary",
            device_class="door",
            alert_state="on",
        ),
        PrinterHASensor(
            printer_id=printer_id,
            name="Temperature",
            entity_id="sensor.issue_143_temperature",
            kind="numeric",
            device_class="temperature",
            alert_above=35,
            block_print=True,
            failure_strategy="fail_closed",
            last_state="21.5",
        ),
        PrinterHASensor(
            printer_id=printer_id,
            name="Peer door",
            entity_id="binary_sensor.issue_143_peer",
            kind="binary",
            device_class="door",
            alert_state="on",
            last_state="off",
        ),
        PrinterHASensor(
            printer_id=printer_id,
            name="Long number",
            entity_id="sensor.issue_143_long_number",
            kind="numeric",
            device_class="temperature",
            alert_above=35,
        ),
    ]


async def _exercise_sensor_batch(db, printer_id: int) -> None:
    sensors = _sensors(printer_id)
    db.add_all(sensors)
    await db.commit()

    long_state = "x" * 500
    invalid_numeric_state = "calibrating-" + "z" * 200
    long_numeric_state = "0" * 100 + "42"
    manager = HASensorManager()
    await manager._apply(
        db,
        sensors,
        {
            sensors[0].entity_id: {"state": long_state},
            sensors[1].entity_id: {"state": invalid_numeric_state},
            sensors[2].entity_id: {"state": "on"},
            sensors[3].entity_id: {"state": long_numeric_state},
        },
    )

    db.expunge_all()
    stored = {
        sensor.name: sensor
        for sensor in (await db.execute(select(PrinterHASensor).where(PrinterHASensor.printer_id == printer_id)))
        .scalars()
        .all()
    }

    assert stored["Long text"].last_state == "x" * LAST_STATE_WIDTH
    assert manager.get_reading(sensors[0].id).state == long_state
    assert stored["Temperature"].last_state == "21.5"
    invalid_reading = manager.get_reading(sensors[1].id)
    assert invalid_reading.state == invalid_numeric_state
    assert invalid_reading.reachable is False
    assert stored["Peer door"].last_state == "on"
    assert stored["Peer door"].last_checked is not None
    assert stored["Long number"].last_state == "0" * LAST_STATE_WIDTH
    numeric_reading = manager.get_reading(sensors[3].id)
    assert numeric_reading.state == long_numeric_state
    assert numeric_reading.value == 42
    assert numeric_reading.alerting is True
    assert await manager.blocked_printers(db) == {printer_id: "Temperature (unavailable)"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sensor_batch_persists_safely_on_sqlite(db_session, printer_factory):
    printer = await printer_factory(serial_number="ISSUE143SQLITE")

    await _exercise_sensor_batch(db_session, printer.id)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(not POSTGRES_TEST_URL, reason="live PostgreSQL test URL not configured")
async def test_sensor_batch_persists_safely_on_postgresql():
    from backend.app.core import database

    assert database.settings.database_url == POSTGRES_TEST_URL
    await database.init_db()

    async with database.async_session() as db:
        printer = Printer(
            name="Issue 143 PostgreSQL",
            serial_number=f"ISSUE143-{uuid4().hex}",
            ip_address="192.0.2.143",
            access_code="issue143",
            model="X1C",
        )
        db.add(printer)
        await db.commit()
        await db.refresh(printer)
        printer_id = printer.id

        try:
            await _exercise_sensor_batch(db, printer_id)
        finally:
            await db.rollback()
            await db.execute(delete(PrinterHASensor).where(PrinterHASensor.printer_id == printer_id))
            await db.execute(delete(Printer).where(Printer.id == printer_id))
            await db.commit()
