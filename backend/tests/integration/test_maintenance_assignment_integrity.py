"""Maintenance assignments stay unique and keep history on upgrade."""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api.routes.maintenance import _get_or_create_maintenance_item
from backend.app.core.database import Base
from backend.app.core.printer_maintenance_migration import migrate_printer_maintenance
from backend.app.models.maintenance import MaintenanceHistory, MaintenanceType, PrinterMaintenance
from backend.app.models.printer import Printer

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_upgrade_keeps_the_latest_performed_row_and_all_history(test_engine, db_session, printer_factory):
    printer, other = await printer_factory(), await printer_factory()
    async with test_engine.begin() as conn:
        await conn.execute(text("DROP INDEX uq_printer_maintenance_printer_type"))

    maintenance = MaintenanceType(name="Check fixture", default_interval_hours=10)
    db_session.add(maintenance)
    await db_session.flush()
    earlier = PrinterMaintenance(
        printer_id=printer.id, maintenance_type_id=maintenance.id, last_performed_at=datetime(2026, 7, 1)
    )
    latest = PrinterMaintenance(
        printer_id=printer.id,
        maintenance_type_id=maintenance.id,
        last_performed_at=datetime(2026, 9, 1),
        custom_interval_type="days",
        custom_interval_hours=15,
    )
    never = PrinterMaintenance(printer_id=printer.id, maintenance_type_id=maintenance.id)
    separate = PrinterMaintenance(printer_id=other.id, maintenance_type_id=maintenance.id)
    db_session.add_all([earlier, latest, never, separate])
    await db_session.flush()
    db_session.add_all(
        [
            MaintenanceHistory(printer_maintenance_id=earlier.id, notes="Earlier"),
            MaintenanceHistory(printer_maintenance_id=latest.id, notes="Latest"),
        ]
    )
    await db_session.commit()

    async with test_engine.begin() as conn:
        await migrate_printer_maintenance(conn)
        await migrate_printer_maintenance(conn)

    item_ids = set(await db_session.scalars(select(PrinterMaintenance.id)))
    history = (
        await db_session.execute(select(MaintenanceHistory.printer_maintenance_id, MaintenanceHistory.notes))
    ).all()
    assert item_ids == {latest.id, separate.id}
    assert set(history) == {(latest.id, "Earlier"), (latest.id, "Latest")}


async def test_concurrent_assignment_creates_one_row(test_engine, tmp_path):
    engine = test_engine
    if test_engine.dialect.name == "sqlite":
        # In-memory SQLite fixtures share a connection. Use two actual
        # connections so the concurrent INSERTs exercise the database index.
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'maintenance.db'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as db:
            printer = Printer(name="P1S fixture", serial_number="F12-TEST", ip_address="192.0.2.1", access_code="test")
            task = MaintenanceType(name="Check fixture")
            db.add_all([printer, task])
            await db.commit()
            printer_id, task_id = printer.id, task.id

        async def add_assignment():
            async with maker() as db:
                item, created = await _get_or_create_maintenance_item(db, printer_id, task_id)
                await db.commit()
                return item.id, created

        results = await asyncio.gather(add_assignment(), add_assignment())
        assert results[0][0] == results[1][0]
        assert sorted(created for _, created in results) == [False, True]
    finally:
        if engine is not test_engine:
            await engine.dispose()
