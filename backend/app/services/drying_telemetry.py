"""Explicit firmware observations used by scheduled drying, never cached guesses."""

import time
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DryingObservation:
    remaining_minutes: int | None
    observed_at: float
    module_type: str | None
    reasons_known: bool
    blocked: bool


@dataclass
class DryingTelemetry:
    idle_observed_at: float = 0
    firmware_observed_at: float = 0
    units: dict[int, DryingObservation] = field(default_factory=dict)
    modules: dict[int, tuple[str, str]] = field(default_factory=dict)


def invalidate_drying_availability(state) -> None:
    if state is not None:
        state.drying_telemetry.idle_observed_at = 0
        state.drying_telemetry.units.clear()


def observe_version_info(state, data: dict) -> None:
    modules = data.get("module")
    if not isinstance(modules, list):
        return
    previous = state.drying_telemetry.modules.copy()
    state.drying_telemetry.modules.clear()
    state.drying_telemetry.firmware_observed_at = 0
    for module in modules:
        if not isinstance(module, dict):
            continue
        name, version = module.get("name", ""), module.get("sw_ver")
        if name == "ota" and isinstance(version, str) and version:
            state.drying_telemetry.firmware_observed_at = time.time()
        if not isinstance(name, str) or "/" not in name or not isinstance(version, str):
            continue
        kind, identifier = name.split("/", 1)
        if kind in ("ams", "n3f", "n3s") and identifier.isdigit():
            state.drying_telemetry.modules[int(identifier)] = (kind, version)
    if previous != state.drying_telemetry.modules:
        state.drying_telemetry.units.clear()


def observe_printer_state(state, data: dict) -> None:
    if "gcode_state" in data:
        state.drying_telemetry.idle_observed_at = time.time()


def observe_ams_drying(client, explicit_units, merged_units) -> None:
    """Observe only units with an explicit dry_time, before cached merges can mask absence."""
    merged = {str(unit.get("id")): unit for unit in merged_units if isinstance(unit, dict)}
    for unit in explicit_units:
        if not isinstance(unit, dict) or "dry_time" not in unit:
            continue
        try:
            ams_id = int(unit.get("id", -1))
        except (TypeError, ValueError):
            continue
        if ams_id < 0:
            continue
        raw = unit["dry_time"]
        valid = (type(raw) is int and raw >= 0) or (isinstance(raw, str) and raw.isdigit())
        current = int(raw) if valid else None
        details = merged.get(str(ams_id), {})
        reasons = unit.get("dry_sf_reason")
        client.state.drying_telemetry.units[ams_id] = DryingObservation(
            current, time.time(), details.get("module_type"), isinstance(reasons, list), bool(reasons)
        )
        if current is None:
            continue
        previous = client._previous_dry_times.get(ams_id, 0)
        client._previous_dry_times[ams_id] = current
        if previous > 0 and current == 0:
            client._drying_targets.pop(ams_id, None)
            if client.on_drying_complete:
                client.on_drying_complete(ams_id)
