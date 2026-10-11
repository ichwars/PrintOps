"""Reconcile external SKU identities in the owned inventory background pass."""

import asyncio
import logging
from time import monotonic

from backend.app.services import spoolman
from backend.app.services.filament_sku_identity import canonical_sku_settings, ensure_sku, sku_key
from backend.app.services.inventory_mode import spoolman_owns_assignments

logger = logging.getLogger(__name__)


class SpoolmanSkuReconciler:
    def __init__(self):
        self._next_check = 0.0

    async def tick(self, db):
        now = monotonic()
        if now < self._next_check:
            return
        self._next_check = now + 300
        if not await spoolman_owns_assignments(db):
            return
        client = await spoolman.get_spoolman_client()
        if client is None:
            return
        try:
            async with asyncio.timeout(5):
                snapshot = await client.get_all_spools()
        except Exception as exc:
            logger.debug("External SKU reconciliation deferred: %s", exc)
            return
        from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool

        groups = {}
        for raw in snapshot:
            try:
                mapped = _map_spoolman_spool(raw)
                key = sku_key(mapped)
                if key[0]:
                    groups.setdefault(key, mapped)
            except (AttributeError, TypeError, ValueError):
                logger.debug("Ignoring malformed external spool during SKU reconciliation")
        known = await canonical_sku_settings(db)
        changed = False
        for key, mapped in groups.items():
            if key not in known or not known[key].material_number:
                known[key] = await ensure_sku(db, mapped)
                changed = True
        if changed:
            await db.commit()
