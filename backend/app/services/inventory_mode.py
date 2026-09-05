"""Inventory-mode decisions shared by assignment readers and writers."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.settings import Settings

logger = logging.getLogger(__name__)


async def spoolman_owns_assignments(db: AsyncSession) -> bool:
    """Return whether the Spoolman assignment ledger is currently active."""
    try:
        result = await db.execute(select(Settings.value).where(Settings.key == "spoolman_enabled"))
        value = result.scalar_one_or_none()
        return bool(value) and value.lower() == "true"
    except Exception as exc:  # noqa: BLE001 - mode probes fail closed to built-in inventory
        logger.debug("Could not read inventory mode; using built-in inventory: %s", exc)
        return False
