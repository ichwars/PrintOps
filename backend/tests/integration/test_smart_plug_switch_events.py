"""Scheduled power changes run the corresponding enabled Home Assistant scripts."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.core import database
from backend.app.services import smart_plug_manager as plug_module
from backend.app.services.mqtt_relay import mqtt_relay


async def test_schedules_run_power_scripts_once_for_multiple_plugs(
    db_session, test_engine, printer_factory, smart_plug_factory, monkeypatch
):
    printer = await printer_factory()
    other = await printer_factory()
    schedules = {
        "printer_id": printer.id,
        "schedule_enabled": True,
        "schedule_on_time": "13:00",
        "schedule_off_time": "14:00",
    }
    first = await smart_plug_factory(name="Power 1", **schedules)
    second = await smart_plug_factory(name="Power 2", **schedules)
    accessory = await smart_plug_factory(name="Accessory", controls_printer_power=False, **schedules)
    on_script = await smart_plug_factory(
        printer_id=printer.id, plug_type="homeassistant", ha_entity_id="script.power_on", auto_off=False
    )
    off_script = await smart_plug_factory(
        printer_id=printer.id, plug_type="homeassistant", ha_entity_id="script.power_off", auto_on=False
    )
    await smart_plug_factory(
        printer_id=printer.id, plug_type="homeassistant", ha_entity_id="script.disabled", enabled=False
    )
    await smart_plug_factory(printer_id=other.id, plug_type="homeassistant", ha_entity_id="script.other")
    assert first.controls_printer_power and second.controls_printer_power

    monkeypatch.setattr(database, "async_session", async_sessionmaker(test_engine, expire_on_commit=False))
    clock = Mock()
    clock.now.return_value = datetime(2026, 11, 9, 13)
    monkeypatch.setattr(plug_module, "datetime", clock)
    monkeypatch.setattr(plug_module.printer_manager, "is_print_active", lambda _: False)
    monkeypatch.setattr(plug_module.printer_manager, "mark_printer_offline", Mock())
    monkeypatch.setattr(plug_module.printer_manager, "get_status", lambda _: None)
    manager = plug_module.SmartPlugManager()
    service = SimpleNamespace(turn_on=AsyncMock(return_value=True), turn_off=AsyncMock(return_value=True))
    monkeypatch.setattr(manager, "get_service_for_plug", AsyncMock(return_value=service))
    monkeypatch.setattr(mqtt_relay, "enabled", True)
    monkeypatch.setattr(mqtt_relay, "connected", True)
    publish = AsyncMock()
    monkeypatch.setattr(mqtt_relay, "on_smart_plug_state", publish)

    await manager._check_schedules()
    await manager._check_schedules()
    assert sorted(call.args[0].id for call in service.turn_on.await_args_list) == sorted(
        [first.id, second.id, accessory.id, on_script.id]
    )
    clock.now.return_value = datetime(2026, 11, 9, 14)
    await manager._check_schedules()
    assert sorted(call.args[0].id for call in service.turn_off.await_args_list) == sorted(
        [first.id, second.id, accessory.id]
    )
    assert service.turn_on.await_args.args[0].id == off_script.id
    assert [(call.kwargs["state"], call.kwargs["printer_name"]) for call in publish.await_args_list] == [
        *[("on", printer.name)] * 3,
        *[("off", printer.name)] * 3,
    ]


async def test_background_meter_reports_fresh_readings_and_alerts_once_per_crossing(
    db_session, printer_factory, smart_plug_factory, monkeypatch
):
    from datetime import timedelta, timezone

    from backend.app.services.mqtt_smart_plug import SmartPlugMQTTData
    from backend.app.services.notification_service import notification_service

    printer = await printer_factory()
    plug = await smart_plug_factory(
        name="Metered outlet",
        printer_id=printer.id,
        power_alert_enabled=True,
        power_alert_high=100,
        power_alert_low=20,
    )
    wireless = await smart_plug_factory(
        plug_type="mqtt", name="Wireless meter", power_alert_enabled=True, power_alert_high=100
    )
    now = datetime.now(timezone.utc)
    data = SmartPlugMQTTData(
        plug_id=wireless.id,
        power=200,
        energy=1.2,
        power_at=now - timedelta(minutes=10),
        energy_at=now,
        last_seen=now,
    )
    monkeypatch.setattr(mqtt_relay.smart_plug_service, "get_plug_data", lambda _: data)
    monkeypatch.setattr(mqtt_relay, "enabled", True)
    monkeypatch.setattr(mqtt_relay, "connected", True)
    publish, notify = AsyncMock(), AsyncMock()
    monkeypatch.setattr(mqtt_relay, "on_smart_plug_energy", publish)
    monkeypatch.setattr(notification_service, "on_printer_error", notify)
    energy = AsyncMock(side_effect=[{"power": power, "today": 0.8} for power in (121, 135, None, 13, 50, 127)])
    manager = plug_module.SmartPlugManager()
    monkeypatch.setattr(manager, "get_service_for_plug", AsyncMock(return_value=SimpleNamespace(get_energy=energy)))

    for _ in range(6):
        await manager._telemetry.poll(manager, db_session)
    assert energy.await_count == 6
    assert [call.args[2] for call in notify.await_args_list] == ["Power High", "Power Low", "Power High"]
    assert all(call.args[:2] == (printer.id, plug.name) for call in notify.await_args_list)
    await db_session.refresh(plug)
    assert plug.power_alert_last_triggered is not None
    assert [call.args[2:] for call in publish.await_args_list if call.args[0] == wireless.id] == [(None, 1.2, None)] * 6
