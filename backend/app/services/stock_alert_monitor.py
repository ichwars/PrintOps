"""Periodic stock alerts from own SKU forecasts and reservation availability."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from time import monotonic

from sqlalchemy import select

from backend.app.models.notification import NotificationProvider
from backend.app.models.procurement import ProcurementOffer, Supplier
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.spool_usage_history import SpoolUsageHistory
from backend.app.services import stock_forecast as forecast
from backend.app.services.filament_sku_identity import canonical_sku_settings, sku_alias_ids
from backend.app.services.inventory_mode import spoolman_owns_assignments
from backend.app.services.notification_service import notification_service
from backend.app.services.spoolman import get_spoolman_client
from backend.app.services.stock_availability import _external_filament_reserved, _filament_reserved

logger = logging.getLogger(__name__)
STATE_KEY = "stock_alert_state"


def utc_now():
    return datetime.now(timezone.utc)


async def setting_value(db, key, default=None):
    value = await db.scalar(select(Settings.value).where(Settings.key == key))
    return value if value is not None else default


class StockAlertMonitor:
    def __init__(self):
        self._next_check = 0.0
        self._state: dict[str, dict] | None = None
        self._persisted = ""

    async def tick(self, db):
        now = monotonic()
        if now < self._next_check:
            return
        self._next_check = now + 3600
        try:
            wanted = {
                kind: bool(
                    await db.scalar(
                        select(NotificationProvider.id)
                        .where(NotificationProvider.enabled.is_(True), getattr(NotificationProvider, event).is_(True))
                        .limit(1)
                    )
                )
                for kind, event in (("reorder", "on_stock_reorder_alert"), ("break", "on_stock_break_alert"))
            }
            await self._load(db)
            if not any(wanted.values()):
                self._state.clear()
                await self._save(db)
                return
            external = await spoolman_owns_assignments(db)
            forecasts = await self._forecasts(db, external)
            if forecasts is None:
                return  # An outage is not recovery; retain notification history.
            active = set()
            for key, (result, spool) in forecasts.items():
                identity = json.dumps(["spoolman" if external else "internal", *key])
                kind = "break" if result.stock_break_alert else "reorder" if result.reorder_alert else None
                if result.snoozed or kind is None:
                    continue
                active.add(identity)
                previous = self._state.get(identity, {})
                events = {"reorder", "break"} if kind == "break" else {"reorder"}
                told = set(previous.get("events", [])) & events
                to_send = {event for event in events if wanted[event]} - told
                self._state[identity] = {"kind": kind, "events": sorted(told | to_send)}
                if not to_send:
                    continue
                material = " ".join(
                    part
                    for part in (
                        spool.material,
                        spool.subtype,
                        None if spool.color_name_is_synthesized else spool.color_name,
                    )
                    if part
                )
                args = {
                    "material": material,
                    "brand": spool.brand,
                    "stock_g": result.remaining_g,
                    "rate_g_day": result.daily_rate_g,
                    "days_left": result.days_remaining,
                    "db": db,
                }
                if "break" in to_send:
                    await notification_service.on_stock_break_alert(
                        **args, lead_time_days=result.effective_lead_time_days
                    )
                if "reorder" in to_send:
                    await notification_service.on_stock_reorder_alert(**args, skip_break_subscribers=kind == "break")
            self._state = {key: kind for key, kind in self._state.items() if key in active}
            await self._save(db)
        except Exception:
            logger.warning("Stock forecast notification check failed", exc_info=True)

    async def _load(self, db):
        if self._state is not None:
            return
        raw = await setting_value(db, STATE_KEY, "{}")
        try:
            state = json.loads(raw)
            self._state = {}
            if isinstance(state, dict):
                for key, value in state.items():
                    if isinstance(value, dict) and value.get("kind") in ("reorder", "break"):
                        events = value.get("events", [])
                        if isinstance(events, list):
                            self._state[key] = {
                                "kind": value["kind"],
                                "events": [event for event in events if event in ("reorder", "break")],
                            }
        except (TypeError, ValueError):
            self._state = {}
        self._persisted = json.dumps(self._state, sort_keys=True)

    async def _save(self, db):
        serialized = json.dumps(self._state, sort_keys=True)
        if serialized == self._persisted:
            return
        row = await db.scalar(select(Settings).where(Settings.key == STATE_KEY))
        if row is None:
            db.add(Settings(key=STATE_KEY, value=serialized))
        else:
            row.value = serialized
        await db.commit()
        self._persisted = serialized

    async def _forecasts(self, db, external):
        settings = {}
        for key, row in (await canonical_sku_settings(db)).items():
            aliases = await sku_alias_ids(db, row)
            offers = await db.scalars(
                select(ProcurementOffer.lead_time_days)
                .join(Supplier)
                .where(
                    ProcurementOffer.filament_sku_settings_id.in_(aliases),
                    ProcurementOffer.is_active.is_(True),
                    ProcurementOffer.is_preferred.is_(True),
                    Supplier.is_active.is_(True),
                )
            )
            settings[key] = forecast.SkuSettings(
                lead_time_days=max([row.lead_time_days or 0, *offers]),
                safety_margin_value=row.safety_margin_value,
                safety_margin_unit=row.safety_margin_unit,
                alerts_snoozed=bool(row.alerts_snoozed),
            )
        try:
            lead = max(0, int(await setting_value(db, "forecast_global_lead_time_days", "0")))
        except (TypeError, ValueError):
            lead = 0
        spools = []
        history = {}
        if external:
            from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool

            client = await get_spoolman_client()
            if client is None:
                return None
            try:
                async with asyncio.timeout(5):
                    raw_spools = await client.get_all_spools()
            except Exception as exc:
                logger.debug("Stock forecast skipped: Spoolman unavailable: %s", exc)
                return None
            for raw in raw_spools:
                if raw.get("archived"):
                    continue
                try:
                    spool = _map_spoolman_spool(raw)
                except ValueError:
                    continue
                spool["created_at"] = _created_at(spool.get("created_at"))
                spools.append(_stock_spool(spool, float(await _external_filament_reserved(db, str(spool["id"])))))
        else:
            rows = await db.scalars(select(Spool).where(Spool.archived_at.is_(None)))
            for spool in rows:
                spools.append(_stock_spool(spool, float(await _filament_reserved(db, spool.id))))
            records = await db.scalars(
                select(SpoolUsageHistory).order_by(SpoolUsageHistory.created_at.desc()).limit(5000)
            )
            for record in records:
                history.setdefault(record.spool_id, []).append(
                    forecast.UsageRecord(record.created_at, record.weight_used)
                )
        return forecast.forecast_all(spools, history, settings, lead, utc_now())


def _created_at(raw):
    if isinstance(raw, datetime):
        return raw
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _stock_spool(spool, reserved):
    def value(field, default=None):
        return spool.get(field, default) if isinstance(spool, dict) else getattr(spool, field, default)

    return forecast.StockSpool(
        id=value("id"),
        material=value("material"),
        subtype=value("subtype"),
        brand=value("brand"),
        color_name=value("color_name"),
        label_weight=value("label_weight"),
        weight_used=value("weight_used"),
        weight_used_baseline=value("weight_used_baseline") or 0,
        created_at=value("created_at"),
        color_name_is_synthesized=bool(value("color_name_is_synthesized", False)),
        reserved_g=reserved,
    )
