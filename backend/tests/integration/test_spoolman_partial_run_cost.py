"""Failed-run prices follow actual successful charges, without repricing the file."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.models.active_print_spoolman import ActivePrintSpoolman
from backend.app.models.spool_usage_history import SpoolUsageHistory
from backend.app.services.spoolman_tracking import cleanup_tracking

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("price,layer,expected", [(20.0, 50, 1.0), (None, 50, 1.25), (20.0, 0, None)])
async def test_partial_cost_uses_only_charged_grams(
    test_engine, db_session, printer_factory, archive_factory, price, layer, expected
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, cost=2.5, with_run=False)
    db_session.add(
        ActivePrintSpoolman(
            printer_id=printer.id,
            archive_id=archive.id,
            filament_usage=[{"slot_id": 1, "used_g": 100.0}],
            ams_trays={"0": {"tray_uuid": "A" * 32}},
            slot_to_tray=[0],
        )
    )
    await db_session.commit()
    spool = {"id": 7, "price": price, "initial_weight": 1000, "filament": {"weight": 1000}}
    client = SimpleNamespace(find_spool_by_tag=AsyncMock(return_value=spool), use_spool=AsyncMock())
    state = SimpleNamespace(layer_num=layer, total_layers=100, raw_data={})
    maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    with (
        patch("backend.app.services.spoolman_tracking.async_session", maker),
        patch(
            "backend.app.services.spoolman_tracking._get_spoolman_client_with_fallback", AsyncMock(return_value=client)
        ),
        patch("backend.app.services.spoolman_tracking._get_printer_serial", AsyncMock(return_value="serial")),
        patch("backend.app.services.printer_manager.printer_manager.get_status", return_value=state),
    ):
        assert await cleanup_tracking(printer.id, archive.id, db_session, status="cancelled") == expected
        assert await cleanup_tracking(printer.id, archive.id, db_session, status="cancelled") is None
    if layer:
        client.use_spool.assert_awaited_once_with(7, 50.0)
        usage = await db_session.scalar(select(SpoolUsageHistory))
        assert (usage.spoolman_spool_id, usage.spool_id, usage.weight_used, usage.status) == (
            7,
            None,
            50.0,
            "cancelled",
        )
    else:
        client.use_spool.assert_not_awaited()
    assert archive.cost == 2.5
    assert (await db_session.execute(select(ActivePrintSpoolman))).scalar_one_or_none() is None


async def test_backup_split_never_charges_an_unfed_slicer_slot(
    test_engine, db_session, printer_factory, archive_factory
):
    from backend.app.services.spoolman_tracking import report_usage

    printer = await printer_factory()
    archive = await archive_factory(printer.id, cost=2.0, with_run=False)
    db_session.add(
        ActivePrintSpoolman(
            printer_id=printer.id,
            archive_id=archive.id,
            filament_usage=[{"slot_id": 1, "used_g": 100.0}, {"slot_id": 2, "used_g": 900.0}],
            ams_trays={"0": {"tray_uuid": "A" * 32}, "1": {"tray_uuid": "B" * 32}},
            slot_to_tray=[0, -1],
        )
    )
    await db_session.commit()
    spools = {"A" * 32: {"id": 7}, "B" * 32: {"id": 8}}
    client = SimpleNamespace(find_spool_by_tag=AsyncMock(side_effect=lambda tag: spools[tag]), use_spool=AsyncMock())
    state = SimpleNamespace(layer_num=100, total_layers=100, tray_change_log=[(0, 0), (1, 50)], raw_data={})
    maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    with (
        patch("backend.app.services.spoolman_tracking.async_session", maker),
        patch(
            "backend.app.services.spoolman_tracking._get_spoolman_client_with_fallback", AsyncMock(return_value=client)
        ),
        patch("backend.app.services.spoolman_tracking._get_printer_serial", AsyncMock(return_value="serial")),
        patch("backend.app.services.printer_manager.printer_manager.get_status", return_value=state),
    ):
        await report_usage(printer.id, archive.id)
    assert [call.args for call in client.use_spool.await_args_list] == [(7, 50.0), (8, 50.0)]
