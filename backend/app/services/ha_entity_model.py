"""Entity catalog for Home Assistant MQTT device discovery.

Builds the payload of a ``{discovery_prefix}/device/{node_id}/config``
message (HA device discovery, >= 2023.7) from the topics the MQTT relay
already publishes. Pure functions — no I/O — so they are easy to test.

Entity set follows the Bambu Lab HA integration (ha-bambulab) so existing
dashboards feel familiar: one device per printer with state/progress/
temperatures/fans, plus event entities for print/error/filament events.
"""

from __future__ import annotations

from typing import Any

MANUFACTURER = "Bambu Lab"
ORIGIN_NAME = "PrintOps"
ORIGIN_URL = "https://github.com/ichwars/PrintOps"


def node_id_for_serial(serial: str) -> str:
    """HA object ids must be lowercase."""
    return f"printops_{serial.lower()}"


def printer_status_topic(topic_prefix: str, serial: str) -> str:
    return f"{topic_prefix}/printers/{serial}/status"


def _availability(topic_prefix: str, serial: str) -> list[dict[str, Any]]:
    """Available only while the relay is online AND the printer is connected."""
    return [
        {
            "topic": f"{topic_prefix}/status",
            "value_template": "{{ value_json.status }}",
        },
        {
            "topic": printer_status_topic(topic_prefix, serial),
            "value_template": "{{ value_json.connected }}",
            "payload": "True",
        },
    ]


def _sensor(
    topic_prefix: str,
    serial: str,
    key: str,
    name: str,
    *,
    value_template: str,
    icon: str | None = None,
    unit: str | None = None,
    device_class: str | None = None,
    state_class: str | None = None,
    entity_category: str | None = None,
    enabled_by_default: bool = True,
    json_attributes_template: str | None = None,
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "component": "sensor",
        "object_id": f"{node_id_for_serial(serial)}_{key}",
        "unique_id": f"{node_id_for_serial(serial)}_{key}",
        "name": name,
        "state_topic": printer_status_topic(topic_prefix, serial),
        "value_template": value_template,
        "availability": _availability(topic_prefix, serial),
        "enabled_by_default": enabled_by_default,
    }
    if icon:
        entity["icon"] = icon
    if unit:
        entity["unit_of_measurement"] = unit
    if device_class:
        entity["device_class"] = device_class
    if state_class:
        entity["state_class"] = state_class
    if entity_category:
        entity["entity_category"] = entity_category
    if json_attributes_template:
        entity["json_attributes_topic"] = printer_status_topic(topic_prefix, serial)
        entity["json_attributes_template"] = json_attributes_template
    return entity


def _binary_sensor(
    topic_prefix: str,
    serial: str,
    key: str,
    name: str,
    *,
    value_template: str,
    device_class: str | None = None,
    icon: str | None = None,
    payload_on: str = "True",
    payload_off: str = "False",
    enabled_by_default: bool = True,
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "component": "binary_sensor",
        "object_id": f"{node_id_for_serial(serial)}_{key}",
        "unique_id": f"{node_id_for_serial(serial)}_{key}",
        "name": name,
        "state_topic": printer_status_topic(topic_prefix, serial),
        "value_template": value_template,
        "payload_on": payload_on,
        "payload_off": payload_off,
        "availability": _availability(topic_prefix, serial),
        "enabled_by_default": enabled_by_default,
    }
    if device_class:
        entity["device_class"] = device_class
    if icon:
        entity["icon"] = icon
    return entity


def _event(
    topic_prefix: str,
    serial: str,
    key: str,
    name: str,
    *,
    state_topic: str,
    event_types: list[str],
    json_attributes_template: str | None = None,
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        "component": "event",
        "object_id": f"{node_id_for_serial(serial)}_{key}",
        "unique_id": f"{node_id_for_serial(serial)}_{key}",
        "name": name,
        "state_topic": f"{topic_prefix}/{state_topic}",
        "event_types": event_types,
        "availability": _availability(topic_prefix, serial),
    }
    if json_attributes_template:
        entity["json_attributes_topic"] = f"{topic_prefix}/{state_topic}"
        entity["json_attributes_template"] = json_attributes_template
    return entity


def printer_device_config(
    *,
    topic_prefix: str,
    serial: str,
    name: str,
    model: str | None = None,
    firmware: str | None = None,
    external_url: str | None = None,
) -> dict[str, Any]:
    """Full device discovery payload for one printer."""
    temps = "value_json.temperatures"
    entities: list[dict[str, Any]] = [
        _sensor(
            topic_prefix,
            serial,
            "state",
            "State",
            value_template="{{ (value_json.state or 'unknown') | lower }}",
            icon="mdi:printer-3d",
        ),
        _sensor(
            topic_prefix,
            serial,
            "stage",
            "Stage",
            value_template="{{ value_json.subtask_name or '' }}",
            icon="mdi:list-status",
        ),
        _sensor(
            topic_prefix,
            serial,
            "progress",
            "Progress",
            value_template="{{ value_json.progress }}",
            unit="%",
            icon="mdi:progress-clock",
        ),
        _sensor(
            topic_prefix,
            serial,
            "remaining_time",
            "Remaining time",
            value_template="{{ value_json.remaining_time }}",
            unit="min",
            device_class="duration",
            icon="mdi:timer-outline",
        ),
        _sensor(
            topic_prefix,
            serial,
            "current_print",
            "Current print",
            value_template="{{ value_json.subtask_name or value_json.gcode_file or '' }}",
            icon="mdi:file-document-outline",
        ),
        _sensor(
            topic_prefix,
            serial,
            "layer",
            "Layer",
            value_template="{{ value_json.layer_num }}",
            icon="mdi:layers",
            json_attributes_template="{{ {'total_layers': value_json.total_layers} | tojson }}",
        ),
        _sensor(
            topic_prefix,
            serial,
            "nozzle_temp",
            "Nozzle temperature",
            value_template=f"{{{{ {temps}.nozzle }}}}",
            unit="°C",
            device_class="temperature",
            state_class="measurement",
        ),
        _sensor(
            topic_prefix,
            serial,
            "nozzle_target",
            "Nozzle target",
            value_template=f"{{{{ {temps}.nozzle_target }}}}",
            unit="°C",
            device_class="temperature",
            state_class="measurement",
        ),
        _sensor(
            topic_prefix,
            serial,
            "bed_temp",
            "Bed temperature",
            value_template=f"{{{{ {temps}.bed }}}}",
            unit="°C",
            device_class="temperature",
            state_class="measurement",
        ),
        _sensor(
            topic_prefix,
            serial,
            "bed_target",
            "Bed target",
            value_template=f"{{{{ {temps}.bed_target }}}}",
            unit="°C",
            device_class="temperature",
            state_class="measurement",
        ),
        _sensor(
            topic_prefix,
            serial,
            "chamber_temp",
            "Chamber temperature",
            value_template=f"{{{{ {temps}.chamber }}}}",
            unit="°C",
            device_class="temperature",
            state_class="measurement",
        ),
        _sensor(
            topic_prefix,
            serial,
            "wifi_signal",
            "WiFi signal",
            value_template="{{ value_json.wifi_signal }}",
            unit="dBm",
            device_class="signal_strength",
            state_class="measurement",
            entity_category="diagnostic",
            enabled_by_default=False,
        ),
        _sensor(
            topic_prefix,
            serial,
            "cooling_fan",
            "Cooling fan",
            value_template="{{ value_json.cooling_fan_speed }}",
            unit="%",
            icon="mdi:fan",
        ),
        _sensor(
            topic_prefix,
            serial,
            "aux_fan",
            "Auxiliary fan",
            value_template="{{ value_json.big_fan1_speed }}",
            unit="%",
            icon="mdi:fan",
            enabled_by_default=False,
        ),
        _sensor(
            topic_prefix,
            serial,
            "chamber_fan",
            "Chamber fan",
            value_template="{{ value_json.big_fan2_speed }}",
            unit="%",
            icon="mdi:fan",
            enabled_by_default=False,
        ),
        _sensor(
            topic_prefix,
            serial,
            "heatbreak_fan",
            "Heatbreak fan",
            value_template="{{ value_json.heatbreak_fan_speed }}",
            unit="%",
            icon="mdi:fan",
            enabled_by_default=False,
        ),
        _binary_sensor(
            topic_prefix,
            serial,
            "online",
            "Online",
            value_template="{{ value_json.connected }}",
            device_class="connectivity",
        ),
        _binary_sensor(
            topic_prefix,
            serial,
            "chamber_light",
            "Chamber light",
            value_template="{{ value_json.chamber_light }}",
            device_class="light",
        ),
        _event(
            topic_prefix,
            serial,
            "print_started",
            "Print started",
            state_topic=f"printers/{serial}/print/started",
            event_types=["started"],
            json_attributes_template="{{ {'filename': value_json.gcode_file, 'subtask_name': value_json.subtask_name} | tojson }}",
        ),
        _event(
            topic_prefix,
            serial,
            "print_completed",
            "Print completed",
            state_topic=f"printers/{serial}/print/completed",
            event_types=["completed"],
        ),
        _event(
            topic_prefix,
            serial,
            "print_failed",
            "Print failed",
            state_topic=f"printers/{serial}/print/failed",
            event_types=["failed"],
        ),
        _event(
            topic_prefix,
            serial,
            "printer_error",
            "Printer error",
            state_topic=f"printers/{serial}/error",
            event_types=["error"],
        ),
        _event(
            topic_prefix,
            serial,
            "filament_low",
            "Filament low",
            state_topic=f"printers/{serial}/filament/low",
            event_types=["low"],
        ),
    ]
    device: dict[str, Any] = {
        "identifiers": [node_id_for_serial(serial)],
        "name": name,
        "manufacturer": MANUFACTURER,
        "serial_number": serial,
    }
    if model:
        device["model"] = model
    if firmware:
        device["sw_version"] = firmware
    if external_url:
        device["configuration_url"] = external_url
    return {
        "device": device,
        "entities": entities,
        "origin": {"name": ORIGIN_NAME, "url": ORIGIN_URL},
    }
