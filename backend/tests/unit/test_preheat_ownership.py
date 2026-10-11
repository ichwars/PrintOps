"""Owned heater rollback must preserve manual and actual printer sessions."""

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.app.services.heater_commands import set_heater_temperature
from backend.app.services.preheat_ownership import PreheatLease, PreheatOwnership


@pytest.fixture
async def owned(tmp_path):
    owner = PreheatOwnership(tmp_path)
    owner.poll_seconds = 0.001
    state = SimpleNamespace(state="IDLE", connected=True, temperatures={"bed_target": 0, "chamber_target": 0})
    client = MagicMock(state=state)
    client._heater_command_revisions = {}
    client.send_gcode.return_value = True
    client.set_bed_temperature.side_effect = lambda target: set_heater_temperature(client, "bed", target)
    client.set_chamber_temperature.side_effect = lambda target: set_heater_temperature(client, "chamber", target)
    manager = MagicMock()
    manager.get_status.return_value = state
    manager.get_client.return_value = client
    lease = PreheatLease(owner, 7, 42, manager)
    lease.activate(600)
    owner.item_status = AsyncMock(return_value="pending")
    ctx = SimpleNamespace(owner=owner, lease=lease, state=state, client=client, manager=manager)
    yield ctx
    for item in list(owner.leases.values()):
        if item.monitor:
            item.monitor.cancel()
            await item.monitor


@pytest.mark.asyncio
async def test_owned_bed_and_chamber_stop_and_durable_record_clears(owned):
    owned.lease.command(owned.client, "bed", 60)
    owned.lease.command(owned.client, "chamber", 50)
    assert owned.owner.blocks_power_off(7)
    assert owned.owner.rollback(owned.lease)
    assert [c.args for c in owned.client.send_gcode.call_args_list] == [
        ("M140 S60",),
        ("M141 S50",),
        ("M140 S0",),
        ("M141 S0",),
    ]
    assert not owned.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_status_read_started_before_publish_cannot_treat_stale_pending_as_reversion(owned):
    queried, resume, returned, confirmed = (asyncio.Event() for _ in range(4))
    reads = 0

    async def read_status(lease):
        nonlocal reads
        reads += 1
        if reads == 1:
            queried.set()
            await resume.wait()
            returned.set()
            return "pending"
        await confirmed.wait()
        return "printing"

    owned.owner.item_status.side_effect = read_status
    owned.lease.command(owned.client, "bed", 60)
    await asyncio.wait_for(queried.wait(), 1)
    # CAS/publish completes while the old pending read is still in flight.
    owned.lease.dispatched()
    resume.set()
    await asyncio.wait_for(returned.wait(), 1)
    assert owned.owner.blocks_power_off(7)
    owned.client.set_bed_temperature.assert_called_once_with(60)
    owned.state.state = "RUNNING"
    confirmed.set()
    await asyncio.wait_for(owned.lease.monitor, 1)
    assert not owned.owner.blocks_power_off(7)
    owned.client.set_bed_temperature.assert_called_once_with(60)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [60, 75])
async def test_manual_command_even_same_target_supersedes_owned_bed(owned, target):
    owned.lease.command(owned.client, "bed", 60)
    owned.client.set_bed_temperature(target)
    assert owned.owner.rollback(owned.lease)
    assert owned.client.set_bed_temperature.call_count == 2
    assert owned.state.temperatures["bed_target"] == target


@pytest.mark.asyncio
async def test_telemetry_changed_one_target_only_stops_other_owned_heater(owned):
    owned.lease.command(owned.client, "bed", 60)
    owned.lease.command(owned.client, "chamber", 50)
    owned.state.temperatures["bed_target"] = 80
    assert owned.owner.rollback(owned.lease)
    assert owned.client.set_bed_temperature.call_count == 1
    owned.client.set_chamber_temperature.assert_called_with(0)


@pytest.mark.asyncio
async def test_already_hot_manual_session_never_claimed(owned):
    owned.state.temperatures["bed_target"] = 60
    assert owned.lease.command(owned.client, "bed", 60)
    assert owned.owner.rollback(owned.lease)
    owned.client.set_bed_temperature.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["PREPARE", "SLICING", "RUNNING", "PAUSE"])
async def test_confirmed_print_hands_off_without_zero_command(owned, state):
    owned.lease.command(owned.client, "bed", 60)
    owned.state.state = state
    assert owned.owner.rollback(owned.lease)
    owned.client.set_bed_temperature.assert_called_once_with(60)
    assert not owned.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_print_begins_between_heater_rollbacks_preserves_chamber(owned):
    owned.lease.command(owned.client, "bed", 60)
    owned.lease.command(owned.client, "chamber", 50)

    def bed_off(target):
        assert target == 0
        owned.state.state = "PREPARE"
        return True

    owned.client.set_bed_temperature.side_effect = bed_off
    assert not owned.owner.rollback(owned.lease)
    owned.client.set_chamber_temperature.assert_called_once_with(50)
    assert owned.owner.rollback(owned.lease)  # Next observation hands off to firmware.


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [None, "UNKNOWN", "OFFLINE"])
async def test_unknown_state_preserves_journal_and_blocks_power_off(owned, state):
    owned.lease.command(owned.client, "bed", 60)
    owned.state.state = state
    assert not owned.owner.rollback(owned.lease)
    assert owned.owner.blocks_power_off(7)
    owned.client.set_bed_temperature.assert_called_once_with(60)


@pytest.mark.asyncio
async def test_disconnected_or_refused_shutdown_retries_without_losing_ownership(owned):
    owned.lease.command(owned.client, "bed", 60)
    owned.state.connected = False
    assert not owned.owner.rollback(owned.lease)
    owned.state.connected = True
    owned.client.set_bed_temperature.return_value = False
    owned.client.set_bed_temperature.side_effect = None
    assert not owned.owner.rollback(owned.lease)
    assert owned.owner.blocks_power_off(7)
    owned.client.set_bed_temperature.return_value = True
    assert owned.owner.rollback(owned.lease)


@pytest.mark.asyncio
async def test_publish_keeps_ownership_until_real_start(owned):
    owned.lease.command(owned.client, "bed", 60)
    owned.lease.dispatched()
    assert owned.owner.blocks_power_off(7)
    assert owned.lease.expires_at <= time.time() + 300
    owned.owner.poll_seconds = 0.001
    owned.state.state = "RUNNING"
    await asyncio.wait_for(owned.lease.monitor, 1)
    owned.client.set_bed_temperature.assert_called_once_with(60)
    assert not owned.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_expired_unacknowledged_dispatch_stops_owned_heat(owned):
    owned.lease.command(owned.client, "bed", 60)
    owned.lease.dispatched()
    owned.owner.item_status.return_value = "printing"
    owned.owner.poll_seconds = 0.001
    owned.lease.expires_at = 0
    await asyncio.wait_for(owned.lease.monitor, 1)
    owned.client.set_bed_temperature.assert_called_with(0)
    assert not owned.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_cancelled_or_ended_queue_stops_heat(owned):
    owned.lease.command(owned.client, "bed", 60)
    owned.owner.item_status.return_value = "cancelled"
    owned.owner.poll_seconds = 0.001
    await asyncio.wait_for(owned.lease.monitor, 1)
    owned.client.set_bed_temperature.assert_called_with(0)


@pytest.mark.asyncio
async def test_shutdown_rolls_back_owned_idle_heaters(owned):
    owned.lease.command(owned.client, "bed", 60)
    owned.owner.stop()
    owned.client.set_bed_temperature.assert_called_with(0)
    assert not owned.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_restart_retains_matching_targets_until_unambiguous_resolution(owned):
    owned.lease.command(owned.client, "bed", 60)
    recovered = PreheatOwnership(owned.owner.directory)
    await recovered.recover(owned.manager)
    assert recovered.blocks_power_off(7)
    owned.client.set_bed_temperature.assert_called_once_with(60)
    owned.state.temperatures["bed_target"] = 0
    assert recovered.rollback(recovered.leases[7])
    assert not recovered.blocks_power_off(7)
    owned.owner.stop()


@pytest.mark.asyncio
async def test_reconnected_mqtt_client_cannot_stop_new_heating_session(owned):
    owned.lease.command(owned.client, "bed", 60)
    replacement = MagicMock(state=owned.state)
    owned.manager.get_client.return_value = replacement
    assert not owned.owner.rollback(owned.lease)
    replacement.set_bed_temperature.assert_not_called()
    assert owned.owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_invalid_restart_record_blocks_power_off(tmp_path):
    owner = PreheatOwnership(tmp_path)
    (tmp_path / "7.json").write_text(json.dumps({"printer_id": 7, "targets": {"nozzle": 200}}))
    await owner.recover(MagicMock())
    assert owner.blocks_power_off(7)


@pytest.mark.asyncio
async def test_journal_write_failure_prevents_heater_command(owned):
    owned.owner.save = MagicMock(side_effect=OSError("disk unavailable"))
    with pytest.raises(OSError):
        owned.lease.command(owned.client, "bed", 60)
    owned.client.set_bed_temperature.assert_not_called()


@pytest.mark.asyncio
async def test_power_off_in_progress_prevents_acquiring_new_heaters(owned):
    other = PreheatLease(owned.owner, 8, 43, owned.manager)
    with owned.owner.power_off_window(8), pytest.raises(RuntimeError):
        other.activate(60)
    assert not owned.owner.blocks_power_off(8)


@pytest.mark.asyncio
async def test_lagged_zero_telemetry_still_repeats_safe_off_for_live_owner(owned):
    owned.lease.command(owned.client, "bed", 60)
    owned.state.temperatures["bed_target"] = 0
    assert owned.owner.rollback(owned.lease)
    owned.client.set_bed_temperature.assert_called_with(0)
