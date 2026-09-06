"""Shared business rule for a printer's primary smart plug (#140).

A printer may legitimately have several linked rows: its outlet, accessories,
Home Assistant scripts, or a read-only MQTT meter.  Consumers must not depend
on database row order when deciding which row represents printer power.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.smart_plug import SmartPlug

EnergyReader = Callable[[SmartPlug, AsyncSession | None], Awaitable[dict | None]]
logger = logging.getLogger(__name__)


def is_script_plug(plug: SmartPlug) -> bool:
    """Return whether *plug* is a runnable HA script rather than a switch."""
    entity_id = getattr(plug, "ha_entity_id", None)
    return bool(getattr(plug, "plug_type", None) == "homeassistant" and entity_id and entity_id.startswith("script."))


def can_be_switched(plug: SmartPlug) -> bool:
    """Match the device kinds accepted by the manual control path."""
    return not is_script_plug(plug) and getattr(plug, "plug_type", None) != "mqtt"


def reports_power(plug: SmartPlug) -> bool:
    """Whether configuration exposes a place to read current watts from."""
    plug_type = getattr(plug, "plug_type", None)
    if plug_type == "homeassistant":
        return bool(getattr(plug, "ha_power_entity", None))
    if plug_type == "mqtt":
        return bool(getattr(plug, "mqtt_power_topic", None) or getattr(plug, "mqtt_topic", None))
    if plug_type == "rest":
        return bool(getattr(plug, "rest_power_path", None))
    return True


def power_plug_rank(plug: SmartPlug) -> tuple[bool, bool, bool, bool, bool, int]:
    """Sort key for the row that represents the printer's power supply.

    Capability comes first so the card never offers an unusable switch.  The
    explicit printer-power relationship outranks display and metering details;
    an accessory must not become the printer outlet merely because it reports
    watts.  Nullable legacy flags rank behind explicit true values.  Lowest id
    is the final stable tiebreaker.
    """
    plug_id = getattr(plug, "id", None)
    return (
        not can_be_switched(plug),
        not bool(getattr(plug, "controls_printer_power", False)),
        not bool(getattr(plug, "enabled", False)),
        not bool(getattr(plug, "show_on_printer_card", False)),
        not reports_power(plug),
        plug_id if isinstance(plug_id, int) else 2**63 - 1,
    )


def _power_assignment(plug: SmartPlug) -> tuple[bool, bool, bool]:
    """The identity-bearing part of the rank, excluding presentation details."""
    return (
        can_be_switched(plug),
        bool(getattr(plug, "controls_printer_power", False)),
        bool(getattr(plug, "enabled", False)),
    )


def rank_power_plugs(plugs: Iterable[SmartPlug]) -> list[SmartPlug]:
    """Return linked plugs in deterministic primary-power order."""
    return sorted(plugs, key=power_plug_rank)


def pick_power_plug(plugs: Iterable[SmartPlug]) -> SmartPlug | None:
    """Return the best printer-power row, retaining single-row fallbacks."""
    return min(plugs, key=power_plug_rank, default=None)


async def plugs_for_printer(
    db: AsyncSession,
    printer_id: int | None,
) -> list[SmartPlug]:
    """Load one printer's plugs and apply the shared business ordering."""
    if printer_id is None:
        return []
    result = await db.execute(select(SmartPlug).where(SmartPlug.printer_id == printer_id).order_by(SmartPlug.id))
    return rank_power_plugs(result.scalars().all())


async def select_energy_reading(
    candidates: Sequence[SmartPlug],
    read_energy: EnergyReader,
    db: AsyncSession | None,
) -> tuple[SmartPlug, dict] | None:
    """Return the first ranked plug with a real lifetime counter.

    A power-only response is not consumption.  Fallback is limited to rows
    with the same printer-power assignment, so an accessory meter cannot be
    billed merely because the actual outlet has no lifetime counter.
    """
    ranked = rank_power_plugs(candidates)
    if not ranked:
        return None

    # Do not cross from the chosen printer-power relationship into an
    # accessory merely because the accessory has a meter. Multiple rows with
    # the same switchability/power/enabled role remain valid fallbacks for a
    # temporarily unavailable counter.
    assignment = _power_assignment(ranked[0])
    for plug in ranked:
        if _power_assignment(plug) != assignment:
            break
        energy = await read_energy(plug, db)
        if energy and energy.get("total") is not None:
            return plug, energy
    return None


async def read_printer_energy(
    db: AsyncSession,
    printer_id: int,
    read_energy: EnergyReader,
    *,
    log_prefix: str,
    context: str,
) -> tuple[SmartPlug, dict] | None:
    """Read the deterministically assigned printer meter with visible failures."""
    candidates = await plugs_for_printer(db, printer_id)
    if not candidates:
        logger.info("[%s] No smart plug for printer %s (%s)", log_prefix, printer_id, context)
        return None
    selected = await select_energy_reading(candidates, read_energy, db)
    if selected is None:
        logger.warning(
            "[%s] No assigned plug reports a lifetime counter for %s (linked: %s)",
            log_prefix,
            context,
            ", ".join(plug.name for plug in candidates),
        )
    return selected
