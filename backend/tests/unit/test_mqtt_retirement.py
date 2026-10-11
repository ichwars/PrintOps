"""A wedged external MQTT thread must not stop request serving or shutdown."""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from backend.app.services.bambu_mqtt import BambuMQTTClient
from backend.app.services.mqtt_relay import MQTTRelayService
from backend.app.services.mqtt_smart_plug import MQTTSmartPlugService


class WedgedBroker:
    def __init__(self):
        self.released = threading.Event()
        self.disconnected = threading.Event()
        self.stopped = threading.Event()
        self.on_connect = lambda *_: None
        self.on_disconnect = lambda *_: None
        self.on_subscribe = lambda *_: None
        self.on_message = lambda *_: None

    def publish(self, *_args, **_kwargs):
        pass

    def disconnect(self):
        self.disconnected.set()

    def loop_stop(self):
        self.released.wait(timeout=3)
        self.stopped.set()


@pytest.mark.parametrize("operation", ["reset", "disconnect"])
def test_printer_retirement_returns_before_old_network_thread_stops(operation):
    broker = WedgedBroker()
    client = BambuMQTTClient("192.0.2.10", "TEST-PRINTER", "12345678")
    client._client = broker
    client.state.connected = True
    client.on_state_change = MagicMock()
    try:
        if operation == "reset":
            client._hard_reset_client()
        else:
            client.disconnect()
        assert not broker.stopped.is_set(), "retirement waited for the MQTT network thread"
        assert client._client is None
        assert broker.on_message is None, "retired telemetry can mutate the replacement session"
        assert broker.on_connect is None
        assert broker.on_disconnect is None
        assert broker.on_subscribe is None
        assert broker.disconnected.wait(timeout=1)
        if operation == "disconnect":
            assert client.state.connected is False
            client.on_state_change.assert_not_called()
    finally:
        broker.released.set()
        broker.stopped.wait(timeout=1)


@pytest.mark.asyncio
@pytest.mark.parametrize("service_type", [MQTTRelayService, MQTTSmartPlugService])
async def test_broker_service_retirement_keeps_the_event_loop_available(service_type):
    broker = WedgedBroker()
    service = service_type()
    service.client = broker
    service.connected = True
    heartbeat = asyncio.Event()

    async def tick():
        await asyncio.sleep(0)
        heartbeat.set()

    beat = asyncio.create_task(tick())
    try:
        await service.disconnect()
        assert not broker.stopped.is_set(), "shutdown joined the stuck network thread"
        await asyncio.wait_for(heartbeat.wait(), timeout=1)
        assert service.client is None
        assert service.connected is False
        assert broker.on_message is None
        assert broker.disconnected.wait(timeout=1)
    finally:
        broker.released.set()
        broker.stopped.wait(timeout=1)
        await beat


def test_explicit_disconnect_timeout_still_allows_the_disconnect_callback():
    broker = WedgedBroker()
    client = BambuMQTTClient("192.0.2.10", "TEST-PRINTER", "12345678")
    broker.on_disconnect = client._on_disconnect
    client._client = broker

    def acknowledge_disconnect():
        broker.disconnected.set()
        if broker.on_disconnect is not None:
            broker.on_disconnect(broker, None)

    broker.disconnect = acknowledge_disconnect
    try:
        client.disconnect(timeout=1)
        assert client._disconnection_event.is_set()
        assert not broker.stopped.is_set()
    finally:
        broker.released.set()
        broker.stopped.wait(timeout=1)
