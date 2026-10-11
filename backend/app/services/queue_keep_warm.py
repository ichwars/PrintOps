"""Opt-in bed holding only between verified compatible queued plates."""

import json
import logging
import math
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.drying_ownership import has_drying_reservation, printer_operation
from backend.app.services.preheat_chamber import derive_chamber_target, normalize_filament_type, observed_tray_materials
from backend.app.services.preheat_ownership import PreheatLease, preheat_ownership
from backend.app.utils.printer_models import normalize_printer_model
from backend.app.utils.threemf_tools import (
    extract_bed_temperature_from_3mf,
    extract_bed_type_from_3mf,
    extract_filament_usage_from_3mf,
)

logger = logging.getLogger(__name__)
_VERIFIED_BED_MODELS = frozenset({"X1C", "P2S"})


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _plate_signature(item, printer, state, targets) -> tuple | None:
    archive = getattr(item, "archive", None)
    source = archive or getattr(item, "library_file", None)
    if source is None or source.deleted_at is not None:
        return None
    if not isinstance(item.plate_id, int) or isinstance(item.plate_id, bool) or item.plate_id < 1:
        return None
    if item.gcode_injection or item.filament_overrides or item.variants:
        return None
    if archive:
        sliced_for = archive.sliced_for_model
    else:
        metadata = source.file_metadata
        if source.file_type != "3mf" or not isinstance(metadata, dict):
            return None
        sliced_for = metadata.get("sliced_for_model")
    if normalize_printer_model(sliced_for) != normalize_printer_model(printer.model):
        return None
    try:
        mapping = json.loads(item.ams_mapping or "null")
    except (ValueError, TypeError):
        return None
    if not isinstance(mapping, list) or not mapping:
        return None
    path = settings.base_dir / source.file_path
    if not path.is_file():
        return None
    bed = extract_bed_temperature_from_3mf(path, item.plate_id)
    bed_type = extract_bed_type_from_3mf(path, item.plate_id)
    if bed is None or not 40 <= bed <= 110 or not bed_type:
        return None
    usage = extract_filament_usage_from_3mf(path, item.plate_id)
    trays = observed_tray_materials(state.raw_data)
    used = []
    for filament in usage:
        amount = filament["used_g"]
        if not math.isfinite(amount) or amount < 0:
            return None
        if amount == 0:
            continue
        slot = filament["slot_id"]
        if slot < 1 or slot > len(mapping):
            return None
        mapped = mapping[slot - 1]
        material = normalize_filament_type(filament.get("type"))
        if (
            not isinstance(mapped, int)
            or isinstance(mapped, bool)
            or mapped < 0
            or (not getattr(item, "use_ams", True) and mapped < 254)
        ):
            return None
        if not material or trays.get(mapped) != material:
            return None
        used.append((slot, mapped, material))
    if not used:
        return None
    chamber = derive_chamber_target(state.raw_data, targets, [entry[1] for entry in used])
    explicit = getattr(item, "preheat_chamber_target_override", None)
    if explicit is not None:
        chamber = explicit
    if chamber <= 0:
        return None
    return bed, bed_type.strip().lower(), chamber, tuple(sorted(used))


def compatible_keep_warm_target(printer, previous, following, state, targets, held_target=None) -> int | None:
    """Return only a proven slicer target; refuse guessed compatibility."""
    if normalize_printer_model(printer.model) not in _VERIFIED_BED_MODELS:
        return None
    if state is None or not state.connected or state.state != "FINISH":
        return None
    if previous is None or previous.status != "completed" or following.status != "pending":
        return None
    if previous.printer_id != printer.id or following.printer_id != printer.id:
        return None
    if not previous.archive or previous.archive.status != "completed" or previous.auto_off_after:
        return None
    if not previous.archive.subtask_id or previous.archive.subtask_id != state.subtask_id:
        return None
    if previous.completed_at is None:
        return None
    elapsed = (datetime.now(timezone.utc) - _utc(previous.completed_at)).total_seconds()
    if not 0 <= elapsed <= 1800:
        return None
    if following.scheduled_time and _utc(following.scheduled_time) > datetime.now(timezone.utc):
        return None
    if any(
        (
            following.manual_start,
            following.filament_short,
            following.gcode_injection,
            following.filament_overrides,
            following.variants,
            following.preheat_override == "off",
        )
    ):
        return None
    prior = _plate_signature(previous, printer, state, targets)
    upcoming = _plate_signature(following, printer, state, targets)
    if prior is None or upcoming != prior:
        return None
    bed, _, chamber, _ = upcoming
    temps = state.temperatures or {}
    if temps.get("bed_target") not in (0, held_target):
        return None  # An existing manual/firmware heating session cannot be claimed.
    try:
        bed_now = float(temps.get("bed", 0) or 0)
        chamber_now = float(temps.get("chamber", 0) or 0)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(bed_now) or not math.isfinite(chamber_now):
        return None
    if bed_now < bed - 10 or chamber_now < chamber - 2:
        return None
    return bed


class QueueKeepWarm:
    def __init__(self, owner=None):
        self.owner = owner or preheat_ownership
        self.entries: dict[int, PreheatLease] = {}
        self.expired: dict[int, int] = {}

    @staticmethod
    def drying_reserved(scheduler, manager, printer_id) -> bool:
        if printer_id in scheduler._drying_in_progress:
            return True
        state = manager.get_status(printer_id)
        raw = getattr(state, "raw_data", None)
        if not isinstance(raw, dict):
            return True
        units = raw.get("ams", [])
        if isinstance(units, dict):
            units = units.get("ams", [])
        if not isinstance(units, list):
            return True
        try:
            return any(int(unit.get("dry_time") or 0) > 0 for unit in units)
        except (TypeError, ValueError, AttributeError):
            return True

    async def refresh(self, scheduler, db, items, dispatch_ids, interlocked, require_plate_clear, manager):
        enabled = await scheduler._get_bool_setting(db, "queue_keep_bed_warm", default=False)
        preheat = await scheduler._get_bool_setting(db, "preheat_enabled", default=False) if enabled else False
        gate = enabled and preheat and require_plate_clear
        heads = {}
        for item in items:
            if item.printer_id and item.printer_id not in heads:
                heads[item.printer_id] = item
        for pid, lease in list(self.entries.items()):
            head = heads.get(pid)
            if lease.expires_at <= time.time():
                self.expired[pid] = lease.item_id
            if lease.purpose != "keep_warm":
                self.entries.pop(pid)
                continue  # Dispatch adopted it; the ownership lifecycle owns cleanup now.
            superseded = head is not None and not self.owner.can_adopt(head)
            if superseded:
                self.expired[pid] = lease.item_id
            selected = head is not None and head.id == lease.item_id and head.id in dispatch_ids
            if (
                not gate
                or not head
                or head.id != lease.item_id
                or pid in interlocked
                or pid in self.expired
                or self.drying_reserved(scheduler, manager, pid)
            ):
                self.owner.rollback(lease)
                self.entries.pop(pid)
            elif selected:
                continue  # Retain the deadline/owner until the worker actually claims the row.
            elif self.owner.leases.get(pid) is not lease:
                self.entries.pop(pid)
        for pid, identity in list(self.expired.items()):
            if pid not in heads or heads[pid].id != identity:
                self.expired.pop(pid)
        if not gate:
            return
        minutes = max(1, min(30, await scheduler._get_int_setting(db, "queue_keep_warm_max_minutes", default=10)))
        targets = await scheduler._get_preheat_filament_targets(db)
        for pid, head in heads.items():
            if (
                pid in interlocked
                or pid in self.expired
                or head.id in dispatch_ids
                or self.drying_reserved(scheduler, manager, pid)
            ):
                continue
            if not manager.is_awaiting_plate_clear(pid) or not manager.is_connected(pid):
                if lease := self.entries.pop(pid, None):
                    self.owner.rollback(lease)
                continue
            printer = await scheduler._get_printer(db, pid)
            if printer is None:
                continue
            previous = (
                await db.execute(
                    select(PrintQueueItem)
                    .options(selectinload(PrintQueueItem.archive), selectinload(PrintQueueItem.variants))
                    .where(
                        PrintQueueItem.printer_id == pid,
                        PrintQueueItem.status.in_(["completed", "failed", "cancelled"]),
                    )
                    .order_by(PrintQueueItem.completed_at.desc().nulls_first(), PrintQueueItem.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            lease = self.entries.get(pid)
            target = compatible_keep_warm_target(
                printer,
                previous,
                head,
                manager.get_status(pid),
                targets,
                lease.targets.get("bed") if lease else None,
            )
            if target is None:
                if lease:
                    self.owner.rollback(lease)
                    self.entries.pop(pid)
                continue
            if lease:
                continue  # No repeated commands or deadline reseeding.
            async with printer_operation(db, pid):
                if (
                    await has_drying_reservation(db, pid)
                    or self.owner.blocks_power_off(pid)
                    or self.drying_reserved(scheduler, manager, pid)
                ):
                    continue
                client = manager.get_client(pid)
                if client is None:
                    continue
                lease = PreheatLease(self.owner, pid, head.id, manager, purpose="keep_warm")
                try:
                    lease.activate(minutes * 60)
                    if not lease.command(client, "bed", target):
                        self.owner.rollback(lease)
                        continue
                except Exception as exc:
                    logger.warning("Keep-warm skipped on printer %s: %s", pid, exc)
                    if self.owner.leases.get(pid) is lease:
                        self.owner.rollback(lease)
                    continue
                self.entries[pid] = lease
                await db.commit()
