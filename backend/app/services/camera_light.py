"""Reference-count chamber lighting requested by camera viewers and captures."""

import asyncio
import logging
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from backend.app.models.printer import Printer
    from backend.app.services.bambu_mqtt import BambuMQTTClient

logger = logging.getLogger(__name__)
_EXPOSURE_SETTLE_SECONDS = 2.5
_DEFAULT_DELAY = 2.0
_SETTINGS_TTL = 15.0
CameraLightMode = Literal["off", "all", "selected"]
CAMERA_LIGHT_SETTINGS = ("camera_light_mode", "camera_light_delay")
_config_cache: tuple[object, float, CameraLightMode, float] | None = None


def normalized_mode(value: object) -> CameraLightMode:
    if value == "all":
        return "all"
    if value == "selected":
        return "selected"
    return "off"


def normalized_delay(value: object) -> float:
    try:
        delay = float(value) if isinstance(value, (int, float, str)) else _DEFAULT_DELAY
    except ValueError:
        return _DEFAULT_DELAY
    return min(5.0, max(0.0, delay)) if math.isfinite(delay) else _DEFAULT_DELAY


def invalidate_settings() -> None:
    global _config_cache
    _config_cache = None


async def _load_configuration() -> tuple[CameraLightMode, float]:
    from sqlalchemy import select

    from backend.app.core import database
    from backend.app.models.settings import Settings

    global _config_cache
    factory = database.async_session
    if _config_cache and _config_cache[0] is factory and monotonic() - _config_cache[1] < _SETTINGS_TTL:
        return _config_cache[2:]
    try:
        async with factory() as db:
            rows = await db.execute(select(Settings.key, Settings.value).where(Settings.key.in_(CAMERA_LIGHT_SETTINGS)))
            values = dict(rows.all())
    except Exception:
        logger.debug("Could not load automatic camera lighting settings", exc_info=True)
        return "off", _DEFAULT_DELAY
    mode = normalized_mode(values.get("camera_light_mode"))
    delay = normalized_delay(values.get("camera_light_delay"))
    _config_cache = (factory, monotonic(), mode, delay)
    return mode, delay


@dataclass
class _LightUse:
    holders: int = 0
    owner: "BambuMQTTClient | None" = None
    ready_at: float = 0.0
    manual_override: bool = False


_active_uses: dict[int, _LightUse] = {}


@asynccontextmanager
async def hold_camera_light(
    printer_id: int,
    *,
    illuminate_with: "BambuMQTTClient | None" = None,
    wait: bool = True,
    delay: float | None = None,
) -> AsyncIterator[None]:
    """Keep an automatically enabled light on until the last use leaves."""
    use = _active_uses.setdefault(printer_id, _LightUse())
    use.holders += 1
    try:
        if illuminate_with is not None and use.owner is None and not use.manual_override:
            status = illuminate_with.state
            if status and not status.chamber_light:
                try:
                    if illuminate_with.set_chamber_light(True):
                        use.owner = illuminate_with
                        use.ready_at = monotonic() + (delay if delay is not None else _EXPOSURE_SETTLE_SECONDS)
                except Exception:
                    logger.exception("Failed to enable chamber light for printer %s", printer_id)
        if wait and use.owner is not None and (remaining := use.ready_at - monotonic()) > 0:
            await asyncio.sleep(remaining)
        yield
    finally:
        use.holders -= 1
        if not use.holders:
            _active_uses.pop(printer_id, None)
            if use.owner is not None:
                try:
                    use.owner.set_chamber_light(False)
                except Exception:
                    logger.exception("Failed to restore chamber light for printer %s", printer_id)


def hand_back_camera_light(printer_id: int) -> None:
    """Leave the manual chamber-light setting in effect after the viewers leave."""
    use = _active_uses.get(printer_id)
    if use is not None:
        use.owner = None
        use.ready_at = 0.0
        use.manual_override = True


@asynccontextmanager
async def automatic_camera_light(printer: "Printer", *, wait: bool = False) -> AsyncIterator[None]:
    from backend.app.services.printer_manager import printer_manager

    mode, delay = await _load_configuration()
    enabled = mode == "all" or (mode == "selected" and getattr(printer, "camera_light_auto", False) is True)
    client = printer_manager.get_client(printer.id) if enabled else None
    async with hold_camera_light(printer.id, illuminate_with=client, wait=wait, delay=delay):
        yield
