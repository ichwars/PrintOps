"""Low-filament notifications use the active assignment ledger and stock weight."""

import asyncio
import logging
import math
from time import monotonic

from sqlalchemy import select

from backend.app.models.notification import NotificationProvider
from backend.app.models.printer import Printer
from backend.app.models.spool import Spool
from backend.app.models.spool_assignment import SpoolAssignment
from backend.app.models.spoolman_slot_assignment import SpoolmanSlotAssignment
from backend.app.services.filament_low_state import FilamentLowState, provider_identity, spool_identity
from backend.app.services.inventory_mode import spoolman_owns_assignments
from backend.app.services.notification_service import notification_service
from backend.app.services.spool_assignment_notifications import (
    _global_tray_from_assignment,
    _slot_label_from_global_tray,
)
from backend.app.services.spoolman import get_spoolman_client
from backend.app.services.stock_alert_monitor import setting_value

logger = logging.getLogger(__name__)


def _threshold(raw, fallback=20):
    try:
        value = float(raw)
        return value if math.isfinite(value) and 0 < value <= 100 else fallback
    except (TypeError, ValueError):
        return fallback


class FilamentLowMonitor:
    def __init__(self):
        self._next_check = 0.0
        self._state = FilamentLowState()

    async def tick(self, db):
        now = monotonic()
        if now < self._next_check:
            return
        self._next_check = now + 30
        try:
            providers = list(
                await db.scalars(
                    select(NotificationProvider).where(
                        NotificationProvider.enabled.is_(True), NotificationProvider.on_filament_low.is_(True)
                    )
                )
            )
            if not providers:
                return
            await self._state.load(db)
            threshold = _threshold(await setting_value(db, "low_stock_threshold", "20"))
            external = await spoolman_owns_assignments(db)
            slots = await self._slots(db, external, providers)
            if slots is None:
                return  # Outage preserves dedup; it is not a successful empty snapshot.
            monitored = select(Printer.id).where(Printer.is_active.is_(True))
            if not any(provider.printer_id is None for provider in providers):
                monitored = monitored.where(Printer.id.in_({provider.printer_id for provider in providers}))
            observed_printers = set(await db.scalars(monitored))
            mode = "spoolman" if external else "internal"
            active = set()
            for assignment, printer, spool in slots:

                def value(field, default=None, spool=spool):
                    return spool.get(field, default) if isinstance(spool, dict) else getattr(spool, field, default)

                key = (mode, printer.id, assignment.ams_id, assignment.tray_id, value("id"))
                label_weight = value("label_weight") or 0
                if not math.isfinite(label_weight) or label_weight <= 0:
                    active.add(key)  # Unusable weight is not evidence of recovery.
                    continue
                remaining = max(0, label_weight - (value("weight_used") or 0))
                percent = min(100, remaining / label_weight * 100)
                if percent >= _threshold(value("low_stock_threshold_pct"), threshold):
                    continue
                active.add(key)
                eligible = {
                    provider.id: provider_identity(provider)
                    for provider in providers
                    if provider.printer_id in (None, printer.id)
                }
                current = self._state.providers_for(key, eligible, spool_identity(spool))
                targets = {pid for pid in eligible if not current[pid]["delivered"]}
                if not targets:
                    continue
                slot = _slot_label_from_global_tray(_global_tray_from_assignment(assignment.ams_id, assignment.tray_id))
                outcomes = await notification_service.on_filament_low(
                    printer_id=printer.id,
                    printer_name=printer.name,
                    slot=slot,
                    remaining_percent=int(percent),
                    db=db,
                    color=value("color_name"),
                    provider_ids=targets,
                    skip_digest_provider_ids={pid for pid in targets if current[pid]["digest"]},
                )
                for pid in targets:
                    delivery = (outcomes or {}).get(pid)
                    if delivery:
                        current[pid]["delivered"] = delivery.status == "delivered"
                        current[pid]["digest"] |= delivery.digest_queued
            self._state.reconcile(mode, observed_printers, active)
            await self._state.save(db)
        except Exception:
            logger.warning("Low-filament notification check failed", exc_info=True)

    async def _slots(self, db, external, providers):
        table = SpoolmanSlotAssignment if external else SpoolAssignment
        query = select(table, Printer).join(Printer, Printer.id == table.printer_id).where(Printer.is_active.is_(True))
        if not any(provider.printer_id is None for provider in providers):
            query = query.where(table.printer_id.in_({provider.printer_id for provider in providers}))
        rows = (await db.execute(query)).all()
        if not rows:
            return []  # Especially in external mode: no inventory HTTP without assignments.
        if external:
            from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool

            client = await get_spoolman_client()
            if client is None:
                return None
            try:
                async with asyncio.timeout(5):
                    raw_spools = await client.get_all_spools()
            except Exception as exc:
                logger.debug("Low-filament check skipped: Spoolman unavailable: %s", exc)
                return None
            spools = {}
            for raw in raw_spools:
                if raw.get("archived"):
                    continue
                try:
                    mapped = _map_spoolman_spool(raw)
                    spools[mapped["id"]] = mapped
                except ValueError:
                    continue
            return [
                (assignment, printer, spools[assignment.spoolman_spool_id])
                for assignment, printer in rows
                if assignment.spoolman_spool_id in spools
            ]
        spools = {
            spool.id: spool
            for spool in await db.scalars(
                select(Spool).where(
                    Spool.id.in_({assignment.spool_id for assignment, _ in rows}), Spool.archived_at.is_(None)
                )
            )
        }
        return [
            (assignment, printer, spools[assignment.spool_id])
            for assignment, printer in rows
            if assignment.spool_id in spools
        ]
