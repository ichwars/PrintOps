"""Tests for HA MQTT device discovery (mqtt_discovery + ha_entity_model)."""

from unittest.mock import MagicMock

import pytest

from backend.app.services.ha_entity_model import node_id_for_serial, printer_device_config
from backend.app.services.mqtt_discovery import (
    MQTTDiscoveryService,
    validate_discovery_prefix,
)


def make_relay(connected=True):
    relay = MagicMock()
    relay.enabled = True
    relay.connected = connected
    relay.topic_prefix = "printops"
    relay.client = MagicMock()
    relay._publish = MagicMock(return_value=True)
    return relay


@pytest.fixture
def discovery():
    svc = MQTTDiscoveryService()
    yield svc
    svc._devices.clear()
    svc._pending_removals.clear()


# --- prefix validation -------------------------------------------------------


@pytest.mark.parametrize(
    ("prefix", "topic", "ok"),
    [
        ("homeassistant", "printops", True),
        ("homeassistant/", "printops", True),
        ("homeassistant", "homeassistant", False),
        ("ha+", "printops", False),
        ("ha/#", "printops", False),
        ("", "printops", False),
    ],
)
def test_validate_prefix(prefix, topic, ok):
    assert (validate_discovery_prefix(prefix, topic) is None) == ok


# --- entity model ------------------------------------------------------------


def test_printer_device_config_structure():
    cfg = printer_device_config(
        topic_prefix="printops",
        serial="00M09ABC",
        name="X1C",
        model="BL-P001",
        firmware="01.09.00.00",
        external_url="http://printops.local:8080",
    )
    device = cfg["device"]
    assert device["identifiers"] == ["printops_00m09abc"]
    assert device["manufacturer"] == "Bambu Lab"
    assert device["model"] == "BL-P001"
    assert device["sw_version"] == "01.09.00.00"
    assert device["configuration_url"] == "http://printops.local:8080"
    assert cfg["origin"]["name"] == "PrintOps"

    entities = cfg["entities"]
    components = {e["component"] for e in entities}
    assert {"sensor", "binary_sensor", "event"} <= components

    state = next(e for e in entities if e["object_id"].endswith("_state"))
    assert state["state_topic"] == "printops/printers/00M09ABC/status"
    assert "value_json.state" in state["value_template"]
    assert len(state["availability"]) == 2  # relay online + printer connected

    temp = next(e for e in entities if e["object_id"].endswith("_nozzle_temp"))
    assert temp["device_class"] == "temperature"
    assert temp["unit_of_measurement"] == "°C"

    events = [e for e in entities if e["component"] == "event"]
    event_topics = {e["state_topic"] for e in events}
    assert "printops/printers/00M09ABC/print/started" in event_topics
    assert "printops/printers/00M09ABC/filament/low" in event_topics


def test_node_id_lowercase():
    assert node_id_for_serial("ABC123") == "printops_abc123"


# --- service behavior --------------------------------------------------------


def test_configure_enables_only_with_relay(discovery):
    relay = make_relay()
    assert discovery.configure({"ha_discovery_enabled": True, "ha_discovery_prefix": "homeassistant"}, relay) is None
    assert discovery.enabled is True
    relay.enabled = False
    discovery.configure({"ha_discovery_enabled": True}, relay)
    assert discovery.enabled is False


def test_configure_rejects_prefix_equal_topic(discovery):
    relay = make_relay()
    err = discovery.configure({"ha_discovery_enabled": True, "ha_discovery_prefix": "printops"}, relay)
    assert err is not None
    assert discovery.enabled is False


def test_announce_publishes_retained_config(discovery):
    relay = make_relay()
    discovery.configure({"ha_discovery_enabled": True, "ha_discovery_prefix": "homeassistant"}, relay)
    ok = discovery.announce_printer(serial="00M09ABC", name="X1C", model="BL-P001", firmware="1.0")
    assert ok is True
    relay._publish.assert_called_once()
    topic, payload = relay._publish.call_args.args[:2]
    assert topic == "homeassistant/device/printops_00m09abc/config"
    assert relay._publish.call_args.kwargs.get("retain") is True
    assert payload["device"]["name"] == "X1C"
    assert "printops_00m09abc_state" in [e["object_id"] for e in payload["entities"]]


def test_announce_noop_when_disabled(discovery):
    relay = make_relay()
    discovery.configure({"ha_discovery_enabled": False}, relay)
    assert discovery.announce_printer(serial="S", name="P") is False
    relay._publish.assert_not_called()


def test_remove_printer_publishes_empty_payload(discovery):
    relay = make_relay()
    discovery.configure({"ha_discovery_enabled": True}, relay)
    discovery.announce_printer(serial="00M09ABC", name="X1C")
    relay._publish.reset_mock()
    assert discovery.remove_printer("00M09ABC") is True
    topic, payload = relay._publish.call_args.args[:2]
    assert topic == "homeassistant/device/printops_00m09abc/config"
    assert payload == ""
    assert "printops_00m09abc" not in discovery._devices


def test_remove_queues_when_broker_down(discovery):
    relay = make_relay(connected=False)
    discovery.configure({"ha_discovery_enabled": True}, relay)
    discovery._devices["printops_x"] = {"device": {}}
    assert discovery.remove_printer("X") is False
    assert "printops_x" in discovery._pending_removals


def test_reannounce_on_birth_message(discovery):
    relay = make_relay()
    discovery.configure({"ha_discovery_enabled": True}, relay)
    discovery.announce_printer(serial="00M09ABC", name="X1C")
    relay._publish.reset_mock()
    discovery.handle_message("homeassistant/status", "online")
    relay._publish.assert_called_once()
    assert relay._publish.call_args.args[0] == "homeassistant/device/printops_00m09abc/config"
    relay._publish.reset_mock()
    discovery.handle_message("homeassistant/status", "offline")
    relay._publish.assert_not_called()


def test_on_broker_connect_subscribes_and_reannounces(discovery):
    relay = make_relay()
    discovery.configure({"ha_discovery_enabled": True}, relay)
    discovery.announce_printer(serial="00M09ABC", name="X1C")
    relay._publish.reset_mock()
    discovery.on_broker_connect()
    relay.client.subscribe.assert_called_once_with("homeassistant/status")
    relay._publish.assert_called_once()


def test_clear_all_retracts_every_device(discovery):
    relay = make_relay()
    discovery.configure({"ha_discovery_enabled": True}, relay)
    discovery.announce_printer(serial="AAA", name="A")
    discovery.announce_printer(serial="BBB", name="B")
    relay._publish.reset_mock()
    discovery.clear_all()
    assert relay._publish.call_count == 2
    for call in relay._publish.call_args_list:
        assert call.args[1] == ""
        assert call.kwargs.get("retain") is True
    assert discovery._devices == {}
