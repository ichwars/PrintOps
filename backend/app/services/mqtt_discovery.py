"""Home Assistant MQTT device discovery on top of the MQTT relay.

When enabled, publishes one retained ``{discovery_prefix}/device/{node_id}/config``
message per printer so Home Assistant creates the device and its entities
automatically — no YAML. Devices are re-announced on broker reconnect and when
HA sends its birth message; they are removed (empty retained payload) when
discovery is turned off, prefixes change, the printer is deleted, or on clean
shutdown. If the broker is unreachable, removals are queued and executed once
the broker is reachable again (including after a restart).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from backend.app.services.ha_entity_model import (
    ams_device_config,
    ams_node_id,
    node_id_for_serial,
    printer_device_config,
)

if TYPE_CHECKING:
    from backend.app.services.mqtt_relay import MQTTRelayService

logger = logging.getLogger(__name__)

DEFAULT_DISCOVERY_PREFIX = "homeassistant"


def validate_discovery_prefix(prefix: str | None, topic_prefix: str | None) -> str | None:
    """Return an error message, or None when the prefix is valid."""
    p = (prefix or "").strip().strip("/")
    t = (topic_prefix or "").strip().strip("/")
    if not p:
        return "Discovery prefix must not be empty."
    if "+" in p or "#" in p:
        return "Discovery prefix must not contain MQTT wildcards (+ or #)."
    if p == t:
        return "The discovery prefix must differ from the topic prefix."
    return None


class MQTTDiscoveryService:
    """Publishes and retracts HA device discovery messages via the relay."""

    def __init__(self) -> None:
        self.enabled = False
        self.discovery_prefix = DEFAULT_DISCOVERY_PREFIX
        self.topic_prefix = "printops"
        self._relay: MQTTRelayService | None = None
        self._devices: dict[str, dict[str, Any]] = {}  # node_id -> config payload
        self._pending_removals: set[str] = set()  # node_ids to remove once broker is reachable
        self._lock = threading.Lock()

    # --- configuration -----------------------------------------------------

    def configure(self, settings: dict, relay: MQTTRelayService) -> str | None:
        """Apply settings. Returns a validation error or None."""
        self._relay = relay
        self.topic_prefix = relay.topic_prefix
        prefix = (settings.get("ha_discovery_prefix") or DEFAULT_DISCOVERY_PREFIX).strip().strip("/")
        error = validate_discovery_prefix(prefix, relay.topic_prefix)
        self.discovery_prefix = prefix or DEFAULT_DISCOVERY_PREFIX
        self.enabled = bool(settings.get("ha_discovery_enabled")) and relay.enabled and error is None
        if settings.get("ha_discovery_enabled") and error is not None:
            logger.warning("HA discovery disabled: %s", error)
        return error

    # --- topics ------------------------------------------------------------

    def config_topic(self, node_id: str) -> str:
        return f"{self.discovery_prefix}/device/{node_id}/config"

    @property
    def birth_topic(self) -> str:
        return f"{self.discovery_prefix}/status"

    # --- publishing --------------------------------------------------------

    def _publish(self, topic: str, payload: Any, retain: bool = True) -> bool:
        if self._relay is None:
            return False
        return self._relay._publish(topic, payload, retain=retain)

    def _publish_config(self, node_id: str, payload: dict[str, Any] | str) -> bool:
        return self._publish(self.config_topic(node_id), payload, retain=True)

    # --- announce / remove ---------------------------------------------------

    def announce_printer(
        self,
        *,
        serial: str,
        name: str,
        model: str | None = None,
        firmware: str | None = None,
        external_url: str | None = None,
    ) -> bool:
        """Announce (or refresh) one printer device."""
        if not self.enabled:
            return False
        node_id = node_id_for_serial(serial)
        payload = printer_device_config(
            topic_prefix=self.topic_prefix,
            serial=serial,
            name=name,
            model=model,
            firmware=firmware,
            external_url=external_url,
        )
        with self._lock:
            self._devices[node_id] = payload
            self._pending_removals.discard(node_id)
        ok = self._publish_config(node_id, payload)
        if ok:
            logger.debug("Announced HA device %s", node_id)
        return ok

    def remove_printer(self, serial: str) -> bool:
        """Remove one printer device and its AMS sub-devices (empty retained config)."""
        node_id = node_id_for_serial(serial)
        with self._lock:
            ams_nodes = [n for n in self._devices if n.startswith(f"{node_id}_ams_")]
            for n in [node_id, *ams_nodes]:
                self._devices.pop(n, None)
            if not self.enabled or self._relay is None or not self._relay.connected:
                self._pending_removals.update({node_id, *ams_nodes})
                return False
            self._pending_removals.difference_update({node_id, *ams_nodes})
        for n in [node_id, *ams_nodes]:
            self._publish_config(n, "")
        return True

    def clear_all(self) -> None:
        """Remove all announced devices (discovery off, prefix change, shutdown)."""
        with self._lock:
            node_ids = list(self._devices)
            self._devices.clear()
            if self._relay is None or not self._relay.connected:
                self._pending_removals.update(node_ids)
                return
        for node_id in node_ids:
            self._publish_config(node_id, "")

    def reannounce_all(self) -> None:
        """Re-publish all known device configs (broker reconnect, HA birth message)."""
        if not self.enabled:
            return
        with self._lock:
            devices = dict(self._devices)
            self._pending_removals.clear()
        for node_id, payload in devices.items():
            self._publish_config(node_id, payload)

    # --- broker lifecycle ----------------------------------------------------

    def on_broker_connect(self) -> None:
        """Called by the relay after the broker connection is established."""
        if not self.enabled or self._relay is None or self._relay.client is None:
            return
        client = self._relay.client
        client.subscribe(self.birth_topic)
        self.reannounce_all()
        self._flush_pending_removals()

    def _flush_pending_removals(self) -> None:
        with self._lock:
            pending = list(self._pending_removals)
            self._pending_removals.clear()
        for node_id in pending:
            self._publish_config(node_id, "")

    def handle_message(self, topic: str, payload: str) -> None:
        """Re-announce when HA announces itself (birth message)."""
        if topic == self.birth_topic and payload.strip() == "online":
            logger.debug("HA birth message received, re-announcing devices")
            self.reannounce_all()

    def on_shutdown(self) -> None:
        """Clear all devices on clean shutdown."""
        self.clear_all()

    def announce_ams_unit(
        self,
        *,
        printer_serial: str,
        printer_name: str,
        unit: dict,
    ) -> bool:
        """Announce (or refresh) one AMS sub-device of a printer."""
        if not self.enabled:
            return False
        node_id = ams_node_id(printer_serial, unit["id"])
        payload = ams_device_config(
            topic_prefix=self.topic_prefix,
            printer_serial=printer_serial,
            printer_name=printer_name,
            unit=unit,
        )
        with self._lock:
            self._devices[node_id] = payload
            self._pending_removals.discard(node_id)
        return self._publish_config(node_id, payload)

    def sync_ams_units(
        self,
        *,
        printer_serial: str,
        printer_name: str,
        units: list[dict],
    ) -> None:
        """Announce new AMS units and retract removed ones."""
        if not self.enabled:
            return
        prefix = f"{node_id_for_serial(printer_serial)}_ams_"
        current = {ams_node_id(printer_serial, unit["id"]): unit for unit in units}
        with self._lock:
            announced = {n: p for n, p in self._devices.items() if n.startswith(prefix)}
        for node_id, unit in current.items():
            if node_id not in announced:
                self.announce_ams_unit(
                    printer_serial=printer_serial,
                    printer_name=printer_name,
                    unit=unit,
                )
        for node_id in announced:
            if node_id not in current:
                with self._lock:
                    self._devices.pop(node_id, None)
                self._publish_config(node_id, "")


mqtt_discovery = MQTTDiscoveryService()


async def maybe_announce_printer(printer_info: Any, state: Any = None) -> None:
    """Announce a printer and its AMS units to HA discovery once per process.

    Called from the printer status callback; does nothing unless discovery is
    enabled and the printer has not been announced yet.
    """
    if not mqtt_discovery.enabled:
        return
    node_id = node_id_for_serial(printer_info.serial_number)
    if node_id in mqtt_discovery._devices:
        # Printer already announced; still keep AMS sub-devices in sync.
        mqtt_discovery.sync_ams_units(
            printer_serial=printer_info.serial_number,
            printer_name=printer_info.name,
            units=_build_ams_units(printer_info, state),
        )
        return
    external_url = None
    try:
        from backend.app.api.routes.settings import get_setting
        from backend.app.core.database import async_session

        async with async_session() as db:
            external_url = await get_setting(db, "external_url") or None
    except Exception:
        logger.debug("Could not read external_url for HA discovery", exc_info=True)
    mqtt_discovery.announce_printer(
        serial=printer_info.serial_number,
        name=printer_info.name,
        model=getattr(printer_info, "model", None),
        firmware=getattr(printer_info, "firmware_version", None),
        external_url=external_url,
    )
    # Keep AMS sub-devices in sync with what the printer reports.
    mqtt_discovery.sync_ams_units(
        printer_serial=printer_info.serial_number,
        printer_name=printer_info.name,
        units=_build_ams_units(printer_info, state),
    )


def _build_ams_units(printer_info: Any, state: Any) -> list[dict]:
    """Build the relay-format AMS payload dicts from the printer state."""
    if state is None:
        return []
    try:
        from backend.app.services.printer_status_ams import build_ams_units

        units, _ = build_ams_units(
            getattr(state, "raw_data", None) or {},
            state,
            {},
            getattr(printer_info, "model", None),
        )
    except Exception:
        logger.debug("Could not build AMS units for HA discovery", exc_info=True)
        return []
    return [
        {
            "id": unit.id,
            "humidity": unit.humidity,
            "temp": unit.temp,
            "dry_time": unit.dry_time,
            "dry_status": unit.dry_status,
            "serial_number": unit.serial_number,
            "sw_ver": unit.sw_ver,
            "is_ams_ht": unit.is_ams_ht,
            "module_type": unit.module_type,
            "trays": [
                {
                    "id": tray.id,
                    "type": tray.tray_type,
                    "color": tray.tray_color,
                    "remain": tray.remain,
                    "brand": tray.tray_sub_brands,
                    "name": tray.tray_id_name,
                    "exists": tray.exists,
                    "state": tray.state,
                }
                for tray in unit.tray
            ],
        }
        for unit in units
    ]
