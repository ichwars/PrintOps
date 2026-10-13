"""Passive per-AMS humidity observations, independent of drying ownership."""

from dataclasses import dataclass


def read_humidity(unit):
    for key in ("humidity_raw", "humidity"):
        try:
            if unit.get(key) is not None:
                return int(unit[key])
        except (TypeError, ValueError):
            pass
    return None


@dataclass
class HumidityStreak:
    since: float
    last_observation: float
    criteria: tuple


class AmbientHumidity:
    def __init__(self):
        self.streaks: dict[tuple[int, int], HumidityStreak] = {}

    def clear_printer(self, printer_id):
        self.streaks = {key: value for key, value in self.streaks.items() if key[0] != printer_id}

    def observe(self, printer_id, units, thresholds, fallback, resolve_threshold, minutes, now, max_gap):
        seen = set()
        ready = set()
        for unit in units:
            ams_id = int(unit.get("id", 0))
            key = (printer_id, ams_id)
            seen.add(key)
            trays = unit.get("tray", []) or []
            threshold = resolve_threshold(trays, thresholds, fallback)
            criteria = (
                threshold,
                tuple(sorted(str(tray.get("tray_type") or "") for tray in trays)),
                minutes,
                unit.get("module_type"),
            )
            streak = self.streaks.get(key)
            if streak and (streak.criteria != criteria or now - streak.last_observation > max_gap):
                self.streaks.pop(key, None)
                streak = None
            if int(unit.get("dry_time") or 0) > 0 or unit.get("module_type") not in ("n3f", "n3s"):
                self.streaks.pop(key, None)
                continue
            humidity = read_humidity(unit)
            if humidity is None:
                continue  # No observation: do not refresh or interpret as a low reading.
            if humidity <= threshold:
                self.streaks.pop(key, None)
                continue
            if not streak:
                streak = HumidityStreak(now, now, criteria)
                self.streaks[key] = streak
            streak.last_observation = now
            if now - streak.since >= minutes * 60:
                ready.add(ams_id)
        self.streaks = {key: value for key, value in self.streaks.items() if key[0] != printer_id or key in seen}
        return ready
