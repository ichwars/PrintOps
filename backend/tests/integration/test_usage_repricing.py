from datetime import datetime, timedelta

from sqlalchemy import select

from backend.app.models.print_log import PrintLogEntry
from backend.app.models.spool import Spool
from backend.app.models.spool_usage_history import SpoolUsageHistory


async def test_recalculate_uses_each_prints_current_spool_price(
    async_client, db_session, printer_factory, archive_factory
):
    first, second = await printer_factory(), await printer_factory()
    start = datetime(2026, 11, 1, 10)
    archive = await archive_factory(
        first.id,
        cost=2.0,
        filament_used_grams=100,
        started_at=start,
        completed_at=start + timedelta(minutes=10),
        with_run=False,
    )
    first_spool = Spool(material="PLA", cost_per_kg=30)
    second_spool = Spool(material="PLA", cost_per_kg=40)
    db_session.add_all([first_spool, second_spool])
    await db_session.flush()
    rows = []
    runs = []
    for printer, spool, grams, cost in [(first, first_spool, 100, 2.0), (second, second_spool, 30, 0.6)]:
        run = PrintLogEntry(
            archive_id=archive.id,
            printer_id=printer.id,
            status="completed",
            started_at=start,
            completed_at=start + timedelta(minutes=10),
            filament_used_grams=grams,
            cost=cost,
        )
        usage = SpoolUsageHistory(
            archive_id=archive.id,
            printer_id=printer.id,
            spool_id=spool.id,
            weight_used=grams,
            cost=cost,
            created_at=start + timedelta(minutes=11),
        )
        runs.append(run)
        rows.append(usage)
    db_session.add_all([*runs, *rows])
    await db_session.commit()

    response = await async_client.post("/api/v1/archives/recalculate-costs")
    assert response.status_code == 200, response.text
    assert response.json()["usage_repriced"] == 2
    assert list(await db_session.scalars(select(PrintLogEntry.cost).order_by(PrintLogEntry.id))) == [3.0, 1.2]
    assert list(await db_session.scalars(select(SpoolUsageHistory.cost).order_by(SpoolUsageHistory.id))) == [3.0, 1.2]
    again = await async_client.post("/api/v1/archives/recalculate-costs")
    assert again.json()["usage_repriced"] == again.json()["updated"] == 0


async def test_spoolman_recalculation_uses_its_price_and_preserves_unreachable_records(
    async_client, db_session, printer_factory, archive_factory, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from backend.app.models.settings import Settings
    from backend.app.services import usage_repricing

    printer = await printer_factory()
    start = datetime(2026, 11, 1, 10)
    archive = await archive_factory(
        printer.id,
        cost=2.0,
        filament_used_grams=100,
        started_at=start,
        completed_at=start + timedelta(minutes=10),
        extra_data={"cost_source": "spoolman"},
    )
    db_session.add_all(
        [
            Settings(key="spoolman_enabled", value="true"),
            SpoolUsageHistory(
                archive_id=archive.id,
                printer_id=printer.id,
                spoolman_spool_id=7,
                weight_used=100,
                cost=2.0,
                created_at=start + timedelta(minutes=11),
            ),
        ]
    )
    await db_session.commit()

    monkeypatch.setattr(usage_repricing, "get_spoolman_client", AsyncMock(return_value=None))
    response = await async_client.post("/api/v1/archives/recalculate-costs")
    assert response.json()["spoolman_unreachable"] == 1
    assert await db_session.scalar(select(SpoolUsageHistory.cost)) == 2.0

    remote = {"id": 7, "price": 15, "initial_weight": 500}
    client = SimpleNamespace(get_all_spools=AsyncMock(return_value=[remote]))
    monkeypatch.setattr(usage_repricing, "get_spoolman_client", AsyncMock(return_value=client))
    response = await async_client.post("/api/v1/archives/recalculate-costs")
    assert response.status_code == 200, response.text
    assert response.json()["usage_repriced"] == response.json()["updated"] == 1
    assert await db_session.scalar(select(SpoolUsageHistory.cost)) == 3.0
    assert await db_session.scalar(select(PrintLogEntry.cost)) == 3.0
    await db_session.refresh(archive)
    assert archive.cost == 3.0
