"""Cloud manual heater intent must supersede queue rollback before any await."""

import asyncio
import json
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from backend.app.api.routes import printers_controls
from backend.app.services.bambu_cloud import BambuCloudError
from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.preheat_ownership import PreheatLease, PreheatOwnership


@pytest.fixture
async def manual_heat(tmp_path, monkeypatch):
    owner = PreheatOwnership(tmp_path)
    owner.poll_seconds = 60
    client = BambuMQTTClient("192.0.2.1", "cloud-manual-test", "test-only", model="H2D")
    client.state.connected = True
    client.state.state = "IDLE"
    client.state.developer_mode = False
    client.state.temperatures = {"bed_target": 0, "chamber_target": 0}
    commands = []

    def publish(topic, payload, qos):
        commands.append(json.loads(payload)["print"]["param"])

    client._client = SimpleNamespace(publish=publish)
    manager = SimpleNamespace(get_status=lambda _: client.state, get_client=lambda _: client)
    monkeypatch.setattr(printers_controls, "printer_manager", manager)
    lease = PreheatLease(owner, 7, 42, manager)
    lease.activate(600)
    owner.item_status = AsyncMock(return_value="pending")
    lease.command(client, "bed", 60)
    lease.command(client, "chamber", 50)
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(id=7, model="H2D", serial_number="test")
    yield SimpleNamespace(owner=owner, client=client, lease=lease, db=db, commands=commands)
    if lease.monitor:
        lease.monitor.cancel()
        with suppress(asyncio.CancelledError):
            await lease.monitor


@pytest.mark.asyncio
@pytest.mark.parametrize("heater,target", [("bed", 60), ("bed", 75), ("chamber", 50), ("chamber", 55)])
@pytest.mark.parametrize("delivery", ["success", "uncertain", "cancelled"])
@pytest.mark.parametrize("await_stage", ["configuration", "publish"])
async def test_cloud_manual_heater_never_rolled_back_even_during_uncertain_await(
    manual_heat, monkeypatch, heater, target, delivery, await_stage
):
    """Missing manual supersession emits an unintended zero for that heater."""
    context = manual_heat
    cloud_commands = []

    async def cloud_publish(serial, payload):
        cloud_commands.append(payload)
        if await_stage == "publish":
            assert context.owner.rollback(context.lease)
        if delivery == "uncertain":
            raise BambuCloudError("reply lost after manual publication")
        if delivery == "cancelled":
            raise asyncio.CancelledError

    cloud = SimpleNamespace(is_authenticated=True, publish_mqtt_command=cloud_publish, close=AsyncMock())

    async def configure(db, user):
        if await_stage == "configuration":
            assert context.owner.rollback(context.lease)
        return cloud

    monkeypatch.setattr(printers_controls, "build_authenticated_cloud", configure)
    route = getattr(printers_controls, f"set_{heater}_temperature")
    kwargs = {"current_user": SimpleNamespace(id=1), "cloud_owner": None, "db": context.db}
    if delivery == "success":
        result = await route(7, target, **kwargs)
        assert result["control_channel"] == "cloud"
    elif delivery == "uncertain":
        with pytest.raises(HTTPException) as raised:
            await route(7, target, **kwargs)
        assert raised.value.status_code == 502
    else:
        with pytest.raises(asyncio.CancelledError):
            await route(7, target, **kwargs)

    other_off = "M141 S0" if heater == "bed" else "M140 S0"
    assert context.commands == ["M140 S60", "M141 S50", other_off]
    command = "M140" if heater == "bed" else "M141"
    assert cloud_commands == [{"print": {"command": "gcode_line", "param": f"{command} S{target}", "sequence_id": "0"}}]


@pytest.mark.asyncio
@pytest.mark.parametrize("control", ["nozzle", "fan"])
async def test_cloud_nonheater_control_keeps_owned_bed_and_chamber_rollback(manual_heat, monkeypatch, control):
    context = manual_heat

    async def configure(db, user):
        assert context.owner.rollback(context.lease)
        return SimpleNamespace(is_authenticated=True, publish_mqtt_command=AsyncMock(), close=AsyncMock())

    monkeypatch.setattr(printers_controls, "build_authenticated_cloud", configure)
    kwargs = {"current_user": SimpleNamespace(id=1), "cloud_owner": None, "db": context.db}
    if control == "nozzle":
        result = await printers_controls.set_nozzle_temperature(7, 200, nozzle=0, **kwargs)
    else:
        result = await printers_controls.set_fan_speed(7, fan="chamber", speed=50, **kwargs)
    assert result["control_channel"] == "cloud"
    assert context.commands == ["M140 S60", "M141 S50", "M140 S0", "M141 S0"]


@pytest.mark.asyncio
async def test_manual_airduct_keeps_owned_heater_rollback(manual_heat):
    context = manual_heat
    airduct = []

    def publish(topic, payload, qos):
        data = json.loads(payload)["print"]
        if data["command"] == "gcode_line":
            context.commands.append(data["param"])
        else:
            airduct.append(data)

    context.client._client = SimpleNamespace(publish=publish)
    result = await printers_controls.set_airduct_mode(7, mode="cooling", _=None, db=context.db)
    assert result["success"]
    assert airduct
    assert context.owner.rollback(context.lease)
    assert context.commands == ["M140 S60", "M141 S50", "M140 S0", "M141 S0"]


@pytest.mark.asyncio
@pytest.mark.parametrize("heater,target", [("bed", 60), ("chamber", 50)])
async def test_local_manual_same_target_keeps_existing_protection(manual_heat, heater, target):
    context = manual_heat
    context.client.state.developer_mode = True
    route = getattr(printers_controls, f"set_{heater}_temperature")
    result = await route(7, target, current_user=SimpleNamespace(id=1), cloud_owner=None, db=context.db)
    assert result["control_channel"] == "local"
    assert context.owner.rollback(context.lease)
    command = "M140" if heater == "bed" else "M141"
    other_off = "M141 S0" if heater == "bed" else "M140 S0"
    assert context.commands == ["M140 S60", "M141 S50", f"{command} S{target}", other_off]
