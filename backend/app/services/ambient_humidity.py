"""Passive per-AMS humidity observations, independent of drying ownership."""

import time
from dataclasses import dataclass


def read_humidity(unit):
    for key in ("humidity_raw", "humidity"):
        try:
            if unit.get(key) is not None:
                return int(unit[key])
        except (TypeError, ValueError):
            pass
    return None


@dataclass(frozen=True)
class HumidityObservation:
    value: int | None
    observed_at: float | None
    sequence: int
    generation: object
    history: tuple[tuple[int, int | None, float | None], ...]


def observe_ams_humidity(state, explicit_units):
    """Record explicit sensor fields; cached merges must never refresh them."""
    observations = state.drying_telemetry.humidity
    for unit in explicit_units:
        if not isinstance(unit, dict) or not {"humidity_raw", "humidity"}.intersection(unit):
            continue
        try:
            ams_id = int(unit.get("id", -1))
        except (TypeError, ValueError):
            continue
        if ams_id < 0:
            continue
        explicit = {key: value for key, value in unit.items() if key in ("humidity_raw", "humidity")}
        valid = {
            key: value
            for key, value in explicit.items()
            if type(value) is int or isinstance(value, str) and value.isdigit()
        }
        value = read_humidity(valid)
        if value is not None and not 0 <= value <= 100:
            value = None
        previous = observations.get(ams_id)
        sequence = previous.sequence + 1 if previous else 1
        observed_at = time.monotonic() if value is not None else None
        history = previous.history if previous else ()
        observations[ams_id] = HumidityObservation(
            value,
            observed_at,
            sequence,
            state.drying_telemetry.humidity_generation,
            (history + ((sequence, value, observed_at),))[-256:],
        )


@dataclass
class HumidityStreak:
    since: float
    last_observation: float
    criteria: tuple


class AmbientHumidity:
    def __init__(self):
        self.streaks: dict[tuple[int, int], HumidityStreak] = {}
        self.samples: dict[tuple[int, int], tuple[object, int]] = {}

    def clear_printer(self, printer_id):
        self.streaks = {key: value for key, value in self.streaks.items() if key[0] != printer_id}
        self.samples = {key: value for key, value in self.samples.items() if key[0] != printer_id}

    def observe(self, printer_id, units, thresholds, fallback, resolve_threshold, minutes, now, max_gap, observations):
        seen = set()
        ready = set()
        for unit in units:
            ams_id = int(unit.get("id", 0))
            key = (printer_id, ams_id)
            seen.add(key)
            trays = unit.get("tray", []) or []
            threshold = resolve_threshold(trays, thresholds, fallback)
            sample = observations.get(ams_id)
            criteria = (
                threshold,
                tuple(sorted(str(tray.get("tray_type") or "") for tray in trays)),
                minutes,
                unit.get("module_type"),
                sample.generation if sample else None,
            )
            streak = self.streaks.get(key)
            if streak and streak.criteria != criteria:
                self.streaks.pop(key, None)
                streak = None
            if int(unit.get("dry_time") or 0) > 0 or unit.get("module_type") not in ("n3f", "n3s"):
                self.streaks.pop(key, None)
                continue
            token = (sample.generation, sample.sequence) if sample else None
            previous = self.samples.get(key)
            fresh = token is not None and previous != token
            if token:
                self.samples[key] = token
            if fresh:
                after = previous[1] if previous and previous[0] is sample.generation else 0
                readings = [reading for reading in sample.history if reading[0] > after]
                if not streak:
                    readings = readings[
                        -1:
                    ]  # Begin after disable/reconnect/criteria resets, never replay earlier data.
                if readings and readings[0][0] != after + 1:
                    streak = None  # Missing history cannot prove uninterrupted humidity.
                    self.streaks.pop(key, None)
                    readings = readings[-1:]
                for _, humidity, received_at in readings:
                    if humidity is None or received_at is None:
                        continue  # Invalid/missing sensor values are no observation.
                    if humidity <= threshold:
                        streak = None
                        self.streaks.pop(key, None)
                        continue
                    if not streak or received_at - streak.last_observation > max_gap:
                        streak = HumidityStreak(received_at, received_at, criteria)
                        self.streaks[key] = streak
                    streak.last_observation = received_at
            if streak and now - streak.last_observation > max_gap:
                self.streaks.pop(key, None)
                streak = None
            if (
                fresh
                and streak
                and sample.value is not None
                and sample.observed_at is not None
                and sample.observed_at - streak.since >= minutes * 60
            ):
                ready.add(ams_id)
        self.streaks = {key: value for key, value in self.streaks.items() if key[0] != printer_id or key in seen}
        self.samples = {key: value for key, value in self.samples.items() if key[0] != printer_id or key in seen}
        return ready
