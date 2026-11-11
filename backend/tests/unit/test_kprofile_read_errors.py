"""A missing/refused read is distinct from a successfully read empty table."""

import asyncio
from unittest.mock import MagicMock

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient, KProfileReadError, NozzleInfo


@pytest.fixture
def client():
    client = BambuMQTTClient(ip_address="192.0.2.1", serial_number="TEST", access_code="test")
    client.state.connected = True
    client._client = MagicMock()
    return client


@pytest.mark.asyncio
async def test_timeout_retries_then_raises_instead_of_a_fictitious_empty_table(client):
    with pytest.raises(KProfileReadError):
        await client.get_kprofiles(timeout=0.001, max_retries=2)
    assert client._client.publish.call_count == 2
    assert client._pending_kprofile_requests == {}


@pytest.mark.asyncio
async def test_not_connected_does_not_publish(client):
    client.state.connected = False
    with pytest.raises(KProfileReadError):
        await client.get_kprofiles(timeout=0.001)
    client._client.publish.assert_not_called()


@pytest.mark.asyncio
async def test_successful_empty_table_is_not_an_error(client):
    task = asyncio.create_task(client.get_kprofiles(timeout=0.1, max_retries=1))
    await asyncio.sleep(0)
    seq = str(client._sequence_id)
    client._handle_kprofile_response({"sequence_id": seq, "nozzle_diameter": "0.4", "filaments": []})
    assert await task == []


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{"result": "fail", "filaments": []}, {"result": "success"}])
async def test_a_refusal_or_missing_table_never_becomes_an_empty_table(client, response):
    task = asyncio.create_task(client.get_kprofiles(timeout=0.01, max_retries=1))
    await asyncio.sleep(0)
    client._handle_kprofile_response({"sequence_id": str(client._sequence_id), "nozzle_diameter": "0.4", **response})
    with pytest.raises(KProfileReadError):
        await task


@pytest.mark.parametrize(
    "command", ["extrusion_cali_get", "extrusion_cali_set", "extrusion_cali_sel", "extrusion_cali_del"]
)
def test_command_nozzle_echo_is_not_physical_hardware_status(client, command):
    client.state.nozzles = [NozzleInfo(nozzle_type="HS00", nozzle_diameter="0.4")]
    client._process_message({"print": {"command": command, "nozzle_diameter": "0.8", "nozzle_type": "HH01"}})
    assert (client.state.nozzles[0].nozzle_type, client.state.nozzles[0].nozzle_diameter) == ("HS00", "0.4")
