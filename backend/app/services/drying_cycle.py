"""Observe completed AMS drying cycles and changes to their physical contents."""

from dataclasses import dataclass, field
from datetime import datetime

from backend.app.services.ams_slot_presence import spool_present
from backend.app.utils.local_time import utcnow_naive
from backend.app.utils.tag_normalization import normalize_tag_uid, normalize_tray_uuid

DRIED_MIN_FRACTION = 0.5
RAN_TO_TERM_MINUTES = 5


@dataclass
class DryingCycle:
    observed_at: datetime
    peak_minutes: int
    start_seen: bool
    target_temp: int | None
    target_hours: int | None
    request: object | None = None
    last_tags: dict[int, tuple[str, str]] = field(default_factory=dict)
    excluded_slots: set[int] = field(default_factory=set)

    def observe_slots(self, unit: dict) -> None:
        for tray in unit.get("tray") or ():
            if not isinstance(tray, dict) or not str(tray.get("id", "")).isdigit():
                continue
            tray_id = int(tray["id"])
            if spool_present(tray) is False:
                self.excluded_slots.add(tray_id)
                continue
            uid = normalize_tag_uid(tray.get("tag_uid"))
            uuid = normalize_tray_uuid(tray.get("tray_uuid"))
            tags = (uid if uid.strip("0") else "", uuid if uuid.strip("0") else "")
            previous = self.last_tags.get(tray_id, ("", ""))
            if any(old and new and old != new for old, new in zip(previous, tags, strict=True)):
                self.excluded_slots.add(tray_id)
            self.last_tags[tray_id] = tuple(new or old for old, new in zip(previous, tags, strict=True))


@dataclass(frozen=True)
class DryingCycleEnd:
    ams_id: int
    first_observed_at: datetime
    ended_at: datetime
    excluded_slots: frozenset[int]
    target_temp: int | None
    hours: float | None


def completed_cycle(ams_id: int, cycle: DryingCycle, remaining: int) -> DryingCycleEnd | None:
    """Keep completed cycles and substantial partial cycles with observed progress."""
    requested = (cycle.target_hours or 0) * 60
    total = max(cycle.peak_minutes, requested)
    elapsed = max(0, total - remaining)
    if remaining > RAN_TO_TERM_MINUTES and (total <= 0 or elapsed < total * DRIED_MIN_FRACTION):
        return None
    hours = round(elapsed / 60, 1) if elapsed > 0 and (cycle.start_seen or requested) else None
    return DryingCycleEnd(
        ams_id,
        cycle.observed_at,
        utcnow_naive(),
        frozenset(cycle.excluded_slots),
        cycle.target_temp,
        hours,
    )
