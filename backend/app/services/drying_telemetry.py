"""Explicit firmware observations used by scheduled drying, never cached guesses."""

import time
from dataclasses import dataclass, field

from backend.app.services.ambient_humidity import HumidityObservation, observe_ams_humidity
from backend.app.services.drying_cycle import DryingCycle, completed_cycle
from backend.app.utils.local_time import utcnow_naive


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
    humidity: dict[int, HumidityObservation] = field(default_factory=dict)
    humidity_generation: object = field(default_factory=object)
    countdown_changes: dict[int, tuple[int, int | None, float]] = field(default_factory=dict)
    parked_countdowns: set[int] = field(default_factory=set)
    cycles: dict[int, DryingCycle] = field(default_factory=dict)


def invalidate_drying_availability(state) -> None:
    if state is not None:
        state.drying_telemetry.idle_observed_at = 0
        state.drying_telemetry.units.clear()
        state.drying_telemetry.countdown_changes.clear()
        state.drying_telemetry.parked_countdowns.clear()


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
        state.drying_telemetry.countdown_changes.clear()
        state.drying_telemetry.parked_countdowns.clear()
        for ams_id, identity in previous.items():
            if state.drying_telemetry.modules.get(ams_id) != identity:
                state.drying_telemetry.cycles.pop(ams_id, None)
        state.drying_telemetry.humidity.clear()
        state.drying_telemetry.humidity_generation = object()


def observe_printer_state(state, data: dict) -> None:
    if "gcode_state" in data:
        state.drying_telemetry.idle_observed_at = time.time()


def observe_ams_drying(client, explicit_units, merged_units) -> None:
    """Observe only units with an explicit dry_time, before cached merges can mask absence."""
    observe_ams_humidity(client.state, explicit_units)
    merged = {str(unit.get("id")): unit for unit in merged_units if isinstance(unit, dict)}
    telemetry = client.state.drying_telemetry
    for ams_id, cycle in telemetry.cycles.items():
        cycle.observe_slots(merged.get(str(ams_id), {}))
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
        _observe_countdown(client.state.drying_telemetry, ams_id, current, unit)
        details = merged.get(str(ams_id), {})
        reasons = unit.get("dry_sf_reason")
        prior_observation = telemetry.units.get(ams_id)
        telemetry.units[ams_id] = DryingObservation(
            current, time.time(), details.get("module_type"), isinstance(reasons, list), bool(reasons)
        )
        if current is None:
            continue
        previous = client._previous_dry_times.get(ams_id, 0)
        client._previous_dry_times[ams_id] = current
        if current > 0:
            cycle = telemetry.cycles.get(ams_id)
            request = client._drying_targets.get(ams_id)
            if cycle is None or (request is not None and cycle.request is not request and current > previous):
                target = request or {}
                cycle = telemetry.cycles[ams_id] = DryingCycle(
                    utcnow_naive(),
                    current,
                    prior_observation is not None and prior_observation.remaining_minutes == 0,
                    target.get("temp"),
                    target.get("duration_hours"),
                    request,
                )
                cycle.observe_slots(details)
            cycle.peak_minutes = max(current, cycle.peak_minutes)
        if previous > 0 and current == 0:
            client._drying_targets.pop(ams_id, None)
            if client.on_drying_complete:
                client.on_drying_complete(ams_id)
            cycle = telemetry.cycles.pop(ams_id, None)
            if cycle is not None and client.on_drying_cycle_end:
                record = completed_cycle(ams_id, cycle, previous)
                if record is not None:
                    client.on_drying_cycle_end(record)


def _observe_countdown(telemetry: DryingTelemetry, ams_id: int, remaining: int | None, explicit: dict) -> None:
    """Recognize a parked timer only from repeated fresh inactive-phase reports.

    A stale positive counter or a long heating phase must keep the queue hold.
    Two inactive reports with the same timer at least 150 seconds apart are
    evidence of a parked display; progress, phase changes and lifecycle resets
    withdraw that evidence. Cached merges never count as fresh observations.
    """
    if remaining is None or remaining == 0:
        telemetry.countdown_changes.pop(ams_id, None)
        telemetry.parked_countdowns.discard(ams_id)
        return
    phase = explicit.get("dry_status")
    if type(phase) is not int:
        try:
            phase = (int(str(explicit["info"]), 16) >> 4) & 0xF if "info" in explicit else None
        except (TypeError, ValueError):
            phase = None
    previous = telemetry.countdown_changes.get(ams_id)
    now = time.monotonic()
    if previous is None or previous[0] != remaining:
        telemetry.countdown_changes[ams_id] = (remaining, phase, now)
        telemetry.parked_countdowns.discard(ams_id)
    elif phase is not None:
        if phase != previous[1]:
            telemetry.countdown_changes[ams_id] = (remaining, phase, now)
            telemetry.parked_countdowns.discard(ams_id)
        elif phase == 0 and now - previous[2] >= 150:
            telemetry.parked_countdowns.add(ams_id)
        elif phase != 0:
            telemetry.parked_countdowns.discard(ams_id)
