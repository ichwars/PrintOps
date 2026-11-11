"""Slot read-back callbacks cross the existing MQTT/event-loop bridge."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.printer_manager import PrinterManager


@pytest.mark.asyncio
async def test_the_manager_schedules_the_read_back_for_the_owning_printer():
    manager = PrinterManager()
    receiver = AsyncMock()
    manager.set_assignment_verified_callback(receiver)
    printer = MagicMock(id=7, ip_address="192.0.2.1", serial_number="TEST", access_code="dummy", model="X1C")
    scheduled = []
    with (
        patch("backend.app.services.printer_manager.BambuMQTTClient") as factory,
        patch("backend.app.services.printer_manager.asyncio.sleep", AsyncMock()),
        patch.object(manager, "_schedule_async", side_effect=scheduled.append),
    ):
        factory.return_value.state.connected = True
        await manager.connect_printer(printer)
        factory.return_value.on_assignment_verified(0, 1, True, {"kprofile_applied": False})
    assert len(scheduled) == 1
    await scheduled[0]
    receiver.assert_awaited_once_with(7, 0, 1, True, {"kprofile_applied": False})


@pytest.mark.asyncio
async def test_the_public_result_contains_only_the_display_fields():
    from backend.app.main import on_assignment_verified

    with (
        patch("backend.app.main.printer_manager.get_printer", return_value=MagicMock(name="printer")) as info,
        patch("backend.app.main.ws_manager.broadcast", AsyncMock()) as broadcast,
    ):
        info.return_value.name = "Printer B"
        await on_assignment_verified(8, 255, 1, False, {"kprofile_applied": False, "unexpected": "discard me"})
    broadcast.assert_awaited_once_with(
        {
            "type": "spool_assignment_verified",
            "printer_id": 8,
            "printer_name": "Printer B",
            "ams_id": 255,
            "tray_id": 1,
            "slot": "Ext 2",
            "verified": False,
            "kprofile_applied": False,
        }
    )
