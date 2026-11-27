"""Tests for HA MQTT device discovery (mqtt_discovery + ha_entity_model)."""

from unittest.mock import MagicMock

import pytest

from backend.app.services.ha_entity_model import ams_device_config, node_id_for_serial, printer_device_config
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


# --- AMS sub-devices -----------------------------------------------------------


AMS_UNIT = {
    "id": 1,
    "humidity": 12,
    "temp": 31.5,
    "dry_time": 45,
    "dry_status": 2,
    "serial_number": "AMS01",
    "sw_ver": "01.02.00",
    "is_ams_ht": False,
    "module_type": "AMS",
    "trays": [
        {
            "id": 0,
            "type": "PLA",
            "color": "#FF0000",
            "remain": 80,
            "brand": "Bambu PLA Basic",
            "name": "A00-Y2",
            "exists": True,
            "state": 11,
        },
        {"id": 1, "type": None, "color": None, "remain": 0, "brand": None, "name": None, "exists": False, "state": 9},
    ],
}


def test_ams_device_config_structure():
    cfg = ams_device_config(
        topic_prefix="printops",
        printer_serial="00M09ABC",
        printer_name="X1C",
        unit=AMS_UNIT,
    )
    device = cfg["device"]
    assert device["identifiers"] == ["printops_00m09abc_ams_1"]
    assert device["name"] == "X1C AMS 1"
    assert device["via_device"] == "printops_00m09abc"
    assert device["model"] == "AMS"
    assert device["sw_version"] == "01.02.00"

    humidity = next(e for e in cfg["entities"] if e["object_id"].endswith("_ams_1_humidity"))
    assert humidity["unit_of_measurement"] == "%"
    assert "value_json.ams[0].humidity" in humidity["value_template"]

    slot = next(e for e in cfg["entities"] if e["object_id"].endswith("_ams_1_slot_0"))
    assert slot["name"] == "Slot 1"
    assert "value_json.ams[0].trays[0].type or 'empty'" in slot["value_template"]
    assert "json_attributes_template" in slot


def test_sync_ams_units_announces_and_retracts(discovery):
    relay = make_relay()
    discovery.configure({"ha_discovery_enabled": True}, relay)
    discovery.announce_printer(serial="00M09ABC", name="X1C")
    relay._publish.reset_mock()

    discovery.sync_ams_units(printer_serial="00M09ABC", printer_name="X1C", units=[AMS_UNIT])
    assert relay._publish.call_count == 1
    topic, payload = relay._publish.call_args.args[:2]
    assert topic == "homeassistant/device/printops_00m09abc_ams_1/config"
    assert payload["device"]["name"] == "X1C AMS 1"

    # Same unit again: no change. A removed unit: retracted.
    relay._publish.reset_mock()
    discovery.sync_ams_units(printer_serial="00M09ABC", printer_name="X1C", units=[AMS_UNIT])
    relay._publish.assert_not_called()
    discovery.sync_ams_units(printer_serial="00M09ABC", printer_name="X1C", units=[])
    assert relay._publish.call_count == 1
    assert relay._publish.call_args.args[1] == ""
    assert "printops_00m09abc_ams_1" not in discovery._devices


def test_remove_printer_retracts_ams_devices(discovery):
    relay = make_relay()
    discovery.configure({"ha_discovery_enabled": True}, relay)
    discovery.announce_printer(serial="00M09ABC", name="X1C")
    discovery.sync_ams_units(printer_serial="00M09ABC", printer_name="X1C", units=[AMS_UNIT])
    relay._publish.reset_mock()

    assert discovery.remove_printer("00M09ABC") is True
    assert relay._publish.call_count == 2
    topics = {call.args[0] for call in relay._publish.call_args_list}
    assert "homeassistant/device/printops_00m09abc/config" in topics
    assert "homeassistant/device/printops_00m09abc_ams_1/config" in topics
    assert discovery._devices == {}


def test_relay_status_payload_includes_ams():
    """The relay status topic carries the AMS summary discovery templates read."""
    from types import SimpleNamespace

    from backend.app.services.mqtt_relay import MQTTRelayService

    relay = MQTTRelayService()
    relay.enabled = True
    relay.connected = True
    relay.topic_prefix = "printops"
    relay.client = MagicMock()

    captured = {}

    def fake_publish(topic, payload, retain=False):
        captured["topic"] = topic
        captured["payload"] = payload
        return True

    relay._publish = fake_publish

    state = SimpleNamespace(
        raw_data={},
        connected=True,
        state="RUNNING",
        progress=10.0,
        remaining_time=5,
        layer_num=1,
        total_layers=10,
        current_print="x",
        subtask_name="y",
        gcode_file="z.3mf",
        temperatures={"nozzle": 200},
        wifi_signal=-50,
        chamber_light=True,
        speed_level=2,
        cooling_fan_speed=30,
        big_fan1_speed=40,
        big_fan2_speed=50,
        heatbreak_fan_speed=60,
    )
    import asyncio

    asyncio.run(relay.on_printer_status(1, state, "X1C", "00M09ABC"))
    assert captured["topic"] == "printops/printers/00M09ABC/status"
    assert "ams" in captured["payload"]
    assert isinstance(captured["payload"]["ams"], list)
