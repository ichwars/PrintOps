"""Background meter readings for power alerts and the MQTT energy topic."""

import asyncio
import logging
import math
from datetime import timedelta

from sqlalchemy import select

from backend.app.models.smart_plug import SmartPlug
from backend.app.services.mqtt_relay import mqtt_relay
from backend.app.services.notification_service import notification_service
from backend.app.services.smart_plug_selection import is_script_plug
from backend.app.utils.local_time import to_naive_utc, utcnow_naive

logger = logging.getLogger(__name__)
_POLL_SECONDS = 30


class SmartPlugTelemetry:
    def __init__(self):
        self._crossings: dict[int, tuple[str, float]] = {}

    async def run(self, manager):
        from backend.app.core import database

        while True:
            try:
                async with database.async_session() as db:
                    await self.poll(manager, db)
            except Exception:
                logger.warning("Smart plug meter check failed", exc_info=True)
            await asyncio.sleep(_POLL_SECONDS)

    async def poll(self, manager, db):
        relay = mqtt_relay.enabled and mqtt_relay.connected
        query = select(SmartPlug.id).where(SmartPlug.enabled.is_(True))
        if not relay:
            query = query.where(SmartPlug.power_alert_enabled.is_(True))
        ids = list(await db.scalars(query.order_by(SmartPlug.id)))
        active = set(ids)
        self._crossings = {key: crossing for key, crossing in self._crossings.items() if key in active}
        for plug_id in ids:
            plug = await db.get(SmartPlug, plug_id)
            if plug is None or not plug.enabled or is_script_plug(plug):
                continue
            try:
                reading = await self._read(manager, plug, db)
                if reading is None:
                    continue
                if relay:
                    await mqtt_relay.on_smart_plug_energy(
                        plug.id, plug.name, reading.get("power"), reading.get("today"), reading.get("total")
                    )
                await self._check_power(plug, reading.get("power"), db)
            except Exception:
                await db.rollback()
                logger.warning("Could not process meter readings for plug %s", plug_id, exc_info=True)

    async def _read(self, manager, plug, db):
        if plug.plug_type != "mqtt":
            service = await manager.get_service_for_plug(plug, db)
            return await service.get_energy(plug)
        subscriber = mqtt_relay.smart_plug_service
        data = subscriber.get_plug_data(plug.id)
        if data is None:
            return None
        cutoff = utcnow_naive() - timedelta(minutes=subscriber.REACHABLE_TIMEOUT_MINUTES)
        power_at = to_naive_utc(data.power_at)
        energy_at = to_naive_utc(data.energy_at)
        reading = {
            "power": data.power if power_at is not None and power_at >= cutoff else None,
            "today": data.energy if energy_at is not None and energy_at >= cutoff else None,
        }
        return reading if any(value is not None for value in reading.values()) else None

    async def _check_power(self, plug, power: float | None, db):
        if not plug.power_alert_enabled:
            self._crossings.pop(plug.id, None)
            return
        if power is None or not math.isfinite(power):
            return
        if plug.power_alert_high is not None and power > plug.power_alert_high:
            zone, threshold, direction = "High", plug.power_alert_high, "above"
        elif plug.power_alert_low is not None and power < plug.power_alert_low:
            zone, threshold, direction = "Low", plug.power_alert_low, "below"
        else:
            self._crossings.pop(plug.id, None)
            return
        if self._crossings.get(plug.id) == (zone, threshold):
            return
        plug.power_alert_last_triggered = utcnow_naive()
        await db.commit()
        self._crossings[plug.id] = (zone, threshold)
        await notification_service.on_printer_error(
            plug.printer_id,
            plug.name,
            f"Power {zone}",
            db,
            error_detail=f"Power consumption is {power:.1f} W, {direction} the threshold of {threshold:.1f} W",
        )
