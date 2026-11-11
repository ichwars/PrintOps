"""Routing and teardown of stale printer MQTT sessions."""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient


def _wait_for_retirement(serial: str) -> None:
    for thread in threading.enumerate():
        if thread.name == f"mqtt-retire-{serial}":
            thread.join(timeout=5)
            assert not thread.is_alive(), "MQTT retirement did not finish"


class TestForceReconnectRouting:
    """#1136 — force_reconnect_stale_session routes between hard-reset (full
    paho-client teardown, wipes the QoS 1 queue) and socket-close (the legacy
    behaviour, safe to call from paho's own network thread). The routing
    decision is based on whether an asyncio loop is running: hard-reset
    requires loop_stop() which would deadlock if called from inside the
    network thread itself."""

    @pytest.fixture
    def mqtt_client(self):
        client = BambuMQTTClient(
            ip_address="192.168.1.100",
            serial_number="TEST_HARD_RESET",
            access_code="12345678",
        )
        client.state.connected = True
        client._client = MagicMock()
        return client

    def test_routing_falls_back_to_socket_close_without_running_loop(self, mqtt_client):
        """Sync caller → no asyncio loop → socket-close path (legacy behaviour
        preserved for paho-thread callers like zombie detection)."""
        mqtt_client.force_reconnect_stale_session("test")
        mqtt_client._client.socket().close.assert_called()
        # Old client is NOT torn down on this path; same-instance reconnect
        # via paho's auto-reconnect handles it.
        assert mqtt_client._client is not None

    def test_routing_uses_hard_reset_when_loop_is_running(self, mqtt_client):
        """Async caller → loop available → hard-reset path wipes the queue."""
        original = mqtt_client._client
        # Stub connect() so the rebuild doesn't open a real socket.
        mqtt_client.connect = lambda loop=None: None

        async def _trigger():
            mqtt_client.force_reconnect_stale_session("test")

        asyncio.run(_trigger())
        _wait_for_retirement(mqtt_client.serial_number)
        original.disconnect.assert_called()
        original.loop_stop.assert_called()
        # connect() stub didn't repopulate _client, so it's None — the contract
        # in production is that connect() builds a fresh mqtt.Client here.
        assert mqtt_client._client is None

    def test_marks_state_disconnected_and_broadcasts(self, mqtt_client):
        """Both routing paths must broadcast the disconnected state once."""
        broadcasts: list[bool] = []
        mqtt_client.on_state_change = lambda s: broadcasts.append(s.connected)
        mqtt_client.force_reconnect_stale_session("test")
        assert mqtt_client.state.connected is False
        assert mqtt_client._stale_reconnecting is True
        assert broadcasts == [False]


class TestHardResetClientDirect:
    """Lower-level coverage of `_hard_reset_client` itself — the helper called
    by the routing layer when a full paho-client teardown is safe. These tests
    drive the helper directly so they don't depend on the routing decision."""

    @pytest.fixture
    def mqtt_client(self):
        client = BambuMQTTClient(
            ip_address="192.168.1.100",
            serial_number="TEST_HARD_DIRECT",
            access_code="12345678",
        )
        client.state.connected = True
        client._client = MagicMock()
        # Stub connect() so the rebuild doesn't open a real socket.
        client.connect = lambda loop=None: None
        return client

    def test_disconnects_and_stops_old_client(self, mqtt_client):
        """Old paho client must receive DISCONNECT (broker drops session) +
        loop_stop (network thread exits, taking its QoS 1 queue with it)."""
        original = mqtt_client._client
        mqtt_client._hard_reset_client()
        _wait_for_retirement(mqtt_client.serial_number)
        original.disconnect.assert_called()
        original.loop_stop.assert_called()

    def test_clears_client_reference(self, mqtt_client):
        """Old reference must go to None so subsequent code can't accidentally
        publish through the dying client."""
        mqtt_client._hard_reset_client()
        assert mqtt_client._client is None

    def test_swallows_disconnect_exception(self, mqtt_client):
        """A failing disconnect() (e.g. paho already in error state) must not
        propagate through async dispatch callers, and a single broken client
        could brick every future dispatch."""
        original = mqtt_client._client
        original.disconnect.side_effect = RuntimeError("boom")
        # No exception escapes the call (test would fail if it did).
        mqtt_client._hard_reset_client()
        _wait_for_retirement(mqtt_client.serial_number)
        # loop_stop is still attempted after the disconnect failure.
        original.loop_stop.assert_called()
        assert mqtt_client._client is None
