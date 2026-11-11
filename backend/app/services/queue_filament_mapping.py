"""Revalidate queue mappings on the selected printer and hold missing filaments."""

import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import allowed_printer_ids_for_user, is_auth_enabled
from backend.app.core.config import settings
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.user import User
from backend.app.services.notification_service import notification_service
from backend.app.services.queue_dispatch_state import edited_since_loaded
from backend.app.services.queue_item_printer import drop_printer_resolved
from backend.app.utils.printer_models import is_dual_nozzle_model

logger = logging.getLogger(__name__)
_UNMATCHED_HOLD_PREFIX = "Needs "
_EXTERNAL_TRAY_ID_MIN = 254
_SHORT_HOLD_RECHECK_SECONDS = 120


def _is_unmatched_hold_reason(reason: str | None) -> bool:
    return bool(reason) and reason.startswith(_UNMATCHED_HOLD_PREFIX)


def _mapping_is_all_unresolved(mapping: list | None) -> bool:
    """Return True for a non-empty mapping made only of unresolved slots."""
    if not isinstance(mapping, list) or not mapping:
        return False
    return all(slot is None or (isinstance(slot, int) and slot < 0) for slot in mapping)


def _is_tray_id(value: object) -> bool:
    """True when ``value`` can be read as a global tray ID.

    ``bool`` is a subclass of ``int``, so a hand-written API payload carrying
    ``true`` would otherwise be read as tray 1 and judged — or dispatched —
    against whatever happens to be loaded there.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _unresolved_required(required: list[dict], mapping: list) -> list[dict]:
    """The requirements in ``required`` that ``mapping`` gives no tray (#2799).

    Only slots the plate prints are judged: a ``-1`` anywhere else is padding
    for a filament this plate does not use. A slot past the end of the mapping
    is unresolved too.
    """
    unresolved = []
    for req in required:
        slot_id = req.get("slot_id") or 0
        if slot_id <= 0:
            continue
        tray = mapping[slot_id - 1] if slot_id <= len(mapping) else None
        if not _is_tray_id(tray) or tray < 0:
            unresolved.append(req)
    return unresolved


def _describe_filament(entry: dict, nozzle_key: str) -> str:
    """One-line "PETG #000000 (left nozzle)" for an error message (#2771).

    Shared by the required and loaded sides, which name their extruder
    differently: a 3MF requirement carries ``nozzle_id``, a loaded tray carries
    ``extruder_id``. Both are MQTT extruder ids — 0 is the right/main nozzle,
    1 the left/deputy — and both are absent on single-nozzle printers, where
    naming a nozzle would be noise.
    """
    parts = [(entry.get("type") or "filament").upper()]
    if entry.get("color"):
        parts.append(str(entry["color"]))
    nozzle = entry.get(nozzle_key)
    if nozzle == 0:
        parts.append("(right nozzle)")
    elif nozzle == 1:
        parts.append("(left nozzle)")
    return " ".join(parts)


def _might_be_dual_nozzle(printer_model: str | None, status) -> bool:
    """Whether this printer could have two extruders, judged generously.

    On a dual-nozzle printer ``use_ams`` is nozzle routing rather than an
    AMS on/off flag — H2D Pro firmware reads it as an extruder index — which is
    why the MQTT command builder skips its own use_ams reconcile there. Anything
    that might be dual-nozzle therefore keeps whatever ``use_ams`` it arrived
    with, external spools or not.

    Deliberately over-eager: a wrong "yes" only means this printer keeps the
    behaviour it has always had, while a wrong "no" would rewrite a field that
    steers which nozzle prints. The model name is the first answer (it is what
    the command builder falls back to as well), then the same live evidence the
    dispatcher's extruder annotation uses — a second nozzle reporting a
    diameter, a populated ``ams_extruder_map``, or more than one external feed,
    since a single-nozzle printer has exactly one.
    """
    if is_dual_nozzle_model(printer_model):
        return True
    nozzles = getattr(status, "nozzles", None) or []
    if len(nozzles) > 1 and getattr(nozzles[1], "nozzle_diameter", ""):
        return True
    raw = getattr(status, "raw_data", None) or {}
    if raw.get("ams_extruder_map"):
        return True
    vt_trays = raw.get("vt_tray") or []
    return isinstance(vt_trays, list) and len(vt_trays) > 1


def _int_or(value, default: int) -> int:
    """``int(value)``, or ``default`` when the field is missing or junk.

    AMS telemetry types its ids inconsistently — `"0"` in one firmware, `0` in
    the next — and a tray id that fails to parse must not take the whole
    derivation down with it.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _forced_override_requirements(item: PrintQueueItem) -> list[dict]:
    """The item's force_color_match overrides as filament requirements (#3280).

    What ``_build_override_direct_mapping`` matches when the 3MF cannot be
    read, so the checks after it judge the same list.
    """
    try:
        overrides = json.loads(item.filament_overrides) if item.filament_overrides else []
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(overrides, list):
        return []
    return [
        {
            "slot_id": o.get("slot_id"),
            "type": o.get("type", ""),
            "color": o.get("color", ""),
            "tray_info_idx": o.get("tray_info_idx", ""),
            "force_color_match": True,
        }
        for o in overrides
        if isinstance(o, dict) and o.get("force_color_match") and isinstance(o.get("slot_id"), int)
    ]


async def creator_printer_ids(db: AsyncSession, user_id: int | None) -> set[int] | None:
    """An automatic move stays within the active creator's current grants."""
    if not await is_auth_enabled(db):
        return None
    user = await db.get(User, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        return set()
    return allowed_printer_ids_for_user(user)


def filament_constraints(candidate) -> tuple[list[str] | None, list[dict] | None]:
    required_types = None
    overrides = None
    if candidate.required_filament_types:
        try:
            required_types = json.loads(candidate.required_filament_types)
        except json.JSONDecodeError:
            pass
    if candidate.filament_overrides:
        try:
            overrides = json.loads(candidate.filament_overrides)
        except json.JSONDecodeError:
            pass
    if overrides:
        override_types = sorted({o["type"] for o in overrides if "type" in o})
        if override_types:
            required_types = sorted(set(required_types or []) | set(override_types))
    return required_types, overrides


class QueueFilamentMapping:
    """Mapping checks shared by dispatch and the explicit start preflight."""

    async def _ensure_ams_mapping(self, db: AsyncSession, printer_id: int, item: PrintQueueItem) -> str | None:
        """Ensure the queue item carries a usable AMS mapping before dispatch.

        Recomputes from live printer status when the stored mapping is missing OR
        unresolved (all -1). A stored all-[-1] mapping is a bug artifact — a
        frontend status-load race can serialize [-1] before the printer's AMS
        trays are known (#2589) — and must not be trusted: downstream it would be
        silently downgraded to external-spool mode and print against an empty
        feed. A resolved mapping is re-checked against the target printer's
        live trays before it is trusted (#2799) and recomputed when it does not
        fit. When it does fit, its resolved slots are kept as they are and only
        the slots the plate prints that are still unresolved are matched again;
        all of it is left alone when the user has acknowledged it with "Print
        Anyway".

        When recompute cannot resolve it either (no compatible tray loaded), the
        bogus [-1] is cleared to None so it is not later mistaken for an explicit
        external selection. On a printer that reported loaded trays,
        ``_block_on_unmatched_filament`` holds the item rather than let it go out
        mapping-less; where it cannot judge, the print command keeps use_ams=True
        and the firmware surfaces a clear AMS-mapping error instead of silently
        printing to the empty external feed.

        """
        stored_mapping: list | None = None
        if item.ams_mapping:
            try:
                stored_mapping = json.loads(item.ams_mapping)
            except (json.JSONDecodeError, TypeError):
                stored_mapping = None

        # Present and resolved. Global tray IDs only mean something relative to
        # the printer they were resolved against, so "resolved" is not the same
        # as "resolved *here*" — check the mapping still fits the printer that
        # is about to run this item before trusting it (#2799). "Print anyway"
        # is the user overriding exactly this judgement, so it short-circuits.
        if item.ams_mapping and not _mapping_is_all_unresolved(stored_mapping):
            if item.skip_filament_check:
                return None
            conflict = await self._stored_mapping_conflict(db, printer_id, item, stored_mapping)
            if conflict is None:
                # It fits, but a slot the plate prints may still be empty: the
                # spool was missing when it was mapped, and has perhaps been
                # loaded since. Nothing else would ever look at that slot again,
                # so a job held for it would be held again on every Start.
                filled = await self._fill_unresolved_slots(db, printer_id, item, stored_mapping)
                if filled is not None:
                    item.ams_mapping = json.dumps(filled)
                    logger.info(
                        "Queue item %s: filled unresolved slots of %s on printer %s: %s",
                        item.id,
                        stored_mapping,
                        printer_id,
                        filled,
                    )
                    await db.commit()
                return None
            logger.warning(
                "Queue item %s: stored ams_mapping %s does not fit printer %s (%s) — recomputing",
                item.id,
                stored_mapping,
                printer_id,
                conflict,
            )
            # Drop it before recomputing so a failed recompute cannot fall back
            # to the mapping we just rejected.
            item.ams_mapping = None
            stored_mapping = None
            await db.commit()

        computed_mapping = await self._compute_ams_mapping_for_printer(db, printer_id, item)
        if computed_mapping and not _mapping_is_all_unresolved(computed_mapping):
            item.ams_mapping = json.dumps(computed_mapping)
            logger.info(
                "Queue item %s: Computed AMS mapping for printer %s: %s",
                item.id,
                printer_id,
                computed_mapping,
            )
            await db.commit()
            return None

        external_only = await self._external_spool_only_mapping(db, printer_id, item)
        if external_only is not None:
            item.ams_mapping = json.dumps(external_only)
            await db.commit()
            return None

        if _mapping_is_all_unresolved(stored_mapping):
            logger.warning(
                "Queue item %s: stored ams_mapping %s is unresolved and could not be recomputed "
                "from live status on printer %s; clearing it so dispatch does not treat it as external",
                item.id,
                stored_mapping,
                printer_id,
            )
            item.ams_mapping = None
            await db.commit()

        return None

    async def _fill_unresolved_slots(
        self,
        db: AsyncSession,
        printer_id: int,
        item: PrintQueueItem,
        stored_mapping: list | None,
    ) -> list | None:
        """``stored_mapping`` with its unresolved required slots matched on live trays (#2799).

        Every resolved entry is kept, so a tray the user picked by hand stays
        picked. Only the plate's unresolved slots are matched, and only against
        trays the mapping does not already use: the matcher never gives two
        slots one tray, and filling a gap with a tray the user assigned to
        another slot would print that slot's filament twice.

        Returns None when there is nothing to fill or nothing could be filled.
        """
        if not isinstance(stored_mapping, list) or not stored_mapping:
            return None
        required = await self._get_filament_requirements(db, item)
        if not required:
            return None
        self._apply_filament_overrides(item, required)
        gaps = {req["slot_id"] for req in _unresolved_required(required, stored_mapping)}
        if not gaps:
            return None

        reserved = {t for t in stored_mapping if _is_tray_id(t) and t >= 0}
        computed = await self._compute_ams_mapping_for_printer(
            db, printer_id, item, only_slots=gaps, reserved_trays=reserved
        )
        if not computed:
            return None

        merged = list(stored_mapping) + [-1] * max(0, len(computed) - len(stored_mapping))
        filled = False
        for slot_id in gaps:
            tray = computed[slot_id - 1] if slot_id <= len(computed) else None
            if _is_tray_id(tray) and tray >= 0:
                merged[slot_id - 1] = tray
                filled = True
        return merged if filled else None

    async def missing_filament_for_start(self, db: AsyncSession, item: PrintQueueItem) -> list[str] | None:
        """What a staged item would be held for if it were started now (#2799).

        The Start button asks this before releasing an item, so that a job whose
        filament is still not loaded offers "Print Anyway" instead of being
        released, held again by the scheduler and leaving no way past the hold.
        It reaches the same answer the dispatch path would: a stored mapping
        that fits is kept and only its gaps are matched again, and one that
        does not fit (or is missing) is replaced by a fresh match.

        Returns the missing filaments, described the way the queue row
        describes them, or None when nothing is missing or there is not enough
        evidence to say: no printer yet (a model-based item picks one at
        dispatch), no status, no trays reported, or no readable 3MF.
        """
        if item.skip_filament_check or not item.printer_id:
            return None
        status = self._filament_printer_status(item.printer_id)
        if status is None or not self._build_loaded_filaments(status):
            return None

        # Called from a request, not from a pass: drop whatever the last pass
        # memoised so this reads the file as it is now. A pass running at the
        # same time only loses its cache.
        self._filament_req_memo.clear()

        mapping: list | None = None
        if item.ams_mapping:
            try:
                mapping = json.loads(item.ams_mapping)
            except (json.JSONDecodeError, TypeError):
                mapping = None
        if not isinstance(mapping, list) or _mapping_is_all_unresolved(mapping):
            mapping = None
        if mapping is not None:
            if await self._stored_mapping_conflict(db, item.printer_id, item, mapping) is None:
                mapping = await self._fill_unresolved_slots(db, item.printer_id, item, mapping) or mapping
            else:
                mapping = None
        if mapping is None:
            mapping = await self._compute_ams_mapping_for_printer(db, item.printer_id, item) or []

        required = await self._get_filament_requirements(db, item)
        if required:
            self._apply_filament_overrides(item, required)
        else:
            # The same fallback the hold uses, or Start would release a job the
            # next pass holds again (#3280).
            required = _forced_override_requirements(item)
            if not required:
                return None
        missing = _unresolved_required(required, mapping)
        return [_describe_filament(req, "nozzle_id") for req in missing] or None

    async def _stored_mapping_conflict(
        self,
        db: AsyncSession,
        printer_id: int,
        item: PrintQueueItem,
        stored_mapping: list | None,
    ) -> str | None:
        """Describe why ``stored_mapping`` cannot be trusted on ``printer_id`` (#2799).

        A mapping is a list of global tray IDs, and those are only meaningful
        relative to the printer they were resolved against — the same rule
        ``print_queue`` documents for tray identity. Two ways a stored mapping
        arrives at a printer it was not resolved for:

        * the print dialog stamps one mapping onto every selected printer, so a
          mapping computed against the first printer is dispatched verbatim to
          the rest, whose AMS slot order differs;
        * a spool is moved between queueing and dispatch.

        Both end the same way: the slot index still resolves, so nothing looks
        wrong, and the printer obeys it — an explicit ``ams_mapping`` bypasses
        the firmware's own type check, so a PETG slot happily prints in ASA.

        Returns a short reason when the mapping names a tray this printer does
        not have loaded, points a slot at a tray holding a different filament
        type, or points it at an external spool this printer reports empty while
        its AMS holds that slot's filament (#3239). Returns None when the
        mapping fits, and — deliberately — whenever we lack the evidence to
        judge, so a recompute only ever follows a positive finding.

        An unresolved (``-1``) required slot is NOT a conflict: it says the
        matcher had nothing, not that the mapping belongs to another printer,
        and destroying a partially hand-resolved mapping over it would lose the
        slots the user did resolve. ``_fill_unresolved_slots`` matches those
        slots again on their own, and ``_block_on_unmatched_filament`` holds the
        item when that finds nothing.
        """
        if not isinstance(stored_mapping, list) or not stored_mapping:
            return None

        status = self._filament_printer_status(printer_id)
        if status is None:
            return None

        loaded = self._build_loaded_filaments(status)
        if not loaded:
            # Nothing reported yet (reconnect, first push pending). Saying
            # "tray not loaded" here would recompute against an AMS we cannot
            # see, which is how #2589 produced a bogus all-[-1] in the first
            # place.
            return None
        by_tray = {f["global_tray_id"]: f for f in loaded}

        # Cheap pass first, on live status alone: every tray the mapping names
        # has to exist here. This catches a foreign mapping without opening the
        # 3MF, which is worth doing because the parse below is neither cached
        # nor free.
        for index, tray in enumerate(stored_mapping):
            if not _is_tray_id(tray) or tray < 0:
                continue
            if tray in by_tray:
                continue
            if tray >= 254:
                # An external feed we have not heard about is absence of
                # evidence about *that slot* — the rest of the mapping is still
                # worth judging, so skip it rather than abandoning the pass.
                continue
            return f"slot {index + 1} points at tray {tray}, which this printer does not have loaded"

        # Only now is the 3MF worth opening: the type check needs to know what
        # each slot actually asked for. The external spool is checked the same
        # way as an AMS tray — `_build_loaded_filaments` reports its type, and
        # two printers with different filament in the external feed is the same
        # failure this method exists to catch.
        required = await self._get_filament_requirements(db, item)
        if not required:
            return None
        self._apply_filament_overrides(item, required)

        # External feeds the printer reports and reports as empty. That is
        # evidence, unlike an external feed it says nothing about (#3239).
        empty_external: set[int] = set()
        vt_trays = status.raw_data.get("vt_tray") if isinstance(status.raw_data, dict) else None
        for vt in vt_trays if isinstance(vt_trays, list) else []:
            if isinstance(vt, dict) and not vt.get("tray_type"):
                try:
                    empty_external.add(int(vt.get("id", 254)))
                except (TypeError, ValueError):
                    continue

        for req in required:
            slot_id = req.get("slot_id") or 0
            if slot_id <= 0:
                continue
            if slot_id > len(stored_mapping):
                return f"slot {slot_id} is not covered by the mapping"

            tray = stored_mapping[slot_id - 1]
            if not _is_tray_id(tray) or tray < 0:
                continue

            loaded_tray = by_tray.get(tray)
            if loaded_tray is None:
                # A mapping made for a printer that feeds this slot from its
                # external spool, sent to one whose external spool is empty and
                # whose AMS holds the filament (#3239). Only then: an external
                # spool can be loaded without its filament set, and on a printer
                # with nothing else to offer that job printed before. The colour
                # has to match too: with only another colour in the AMS, the
                # printer asking for the spool beats printing in that colour.
                want = self._canonical_filament_type(req.get("type") or "")
                if tray >= 254 and tray in empty_external and want:
                    ams_tray = next(
                        (
                            f
                            for f in loaded
                            if not f.get("is_external")
                            and self._canonical_filament_type(f.get("type")) == want
                            and self._colors_are_similar(f.get("color"), req.get("color"))
                        ),
                        None,
                    )
                    if ams_tray is not None:
                        return (
                            f"slot {slot_id} points at the external spool, which is empty, "
                            f"while tray {ams_tray['global_tray_id']} holds {ams_tray.get('type')}"
                        )
                continue

            want = self._canonical_filament_type(req.get("type") or "")
            have = self._canonical_filament_type(loaded_tray.get("type") or "")
            if want and have and want != have:
                return f"slot {slot_id} needs {req.get('type')} but tray {tray} holds {loaded_tray.get('type')}"

            # A forced slot fits only a tray the matcher would give it (#3280).
            if req.get("force_color_match"):
                want_idx = req.get("tray_info_idx") or ""
                have_idx = loaded_tray.get("tray_info_idx") or ""
                if self._normalize_color_for_compare(req.get("color")) != self._normalize_color_for_compare(
                    loaded_tray.get("color")
                ) or (want_idx and have_idx and want_idx != have_idx):
                    return (
                        f"slot {slot_id} is forced to {req.get('type')} {req.get('color')} "
                        f"but tray {tray} holds {loaded_tray.get('type')} {loaded_tray.get('color')}"
                    )

        return None

    def _apply_filament_overrides(self, item: PrintQueueItem, filament_reqs: list[dict]) -> None:
        """Rewrite ``filament_reqs`` in place with the item's per-slot overrides.

        Extracted from ``_compute_ams_mapping_for_printer`` so the unmappable
        diagnosis (#2771) describes the filament the matcher actually looked
        for, not the one the 3MF was sliced with — naming the pre-override
        filament in a user-facing error would send the user to load the wrong
        spool.
        """
        if not item.filament_overrides:
            return
        try:
            overrides = json.loads(item.filament_overrides)
            override_map = {o["slot_id"]: o for o in overrides}
            for req in filament_reqs:
                if req["slot_id"] in override_map:
                    override = override_map[req["slot_id"]]
                    req["type"] = override["type"]
                    req["color"] = override["color"]
                    # A manual/preference override SWAPS the slot's filament, so the
                    # 3MF's original tray_info_idx now points at the old spool and must
                    # be cleared — matching then falls back to type+colour. A
                    # force_color_match override is not a swap: it carries the 3MF's
                    # intended variant (Basic GFA00 / Matte GFA01 / Silk GFA06), so keep
                    # it here too, letting the matcher pin the correct variant slot on a
                    # printer holding two same-colour spools of different variants (#2650).
                    # A spool that names no variant still counts; one naming another
                    # variant does not, as in `_get_missing_force_color_slots` (#3280).
                    req["tray_info_idx"] = (
                        override.get("tray_info_idx", "") if override.get("force_color_match") else ""
                    )
                    # The matcher satisfies a forced slot only the way
                    # `_get_missing_force_color_slots` does, never by a similar
                    # colour or the type alone (#3280).
                    req["force_color_match"] = bool(override.get("force_color_match"))
                    logger.debug(
                        "Queue item %s: Override slot %d -> %s %s",
                        item.id,
                        req["slot_id"],
                        override["type"],
                        override["color"],
                    )
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to apply filament overrides for queue item %s: %s", item.id, e)

    async def _block_on_unmatched_filament(
        self,
        db: AsyncSession,
        item: PrintQueueItem,
        release_assignment: bool = False,
    ) -> bool:
        """Promote to manual_start when a slot the plate prints has no tray (#2799).

        The matcher leaves a requirement it cannot satisfy at ``-1`` and dispatch
        goes ahead, letting the printer choose — which is how a job prints in the
        wrong material without anyone being asked. Holding is the same answer the
        deficit gate already gives for "the spool is too light", so it reuses the
        same promote-and-notify machinery.

        Keyed off unresolved slots in the *computed* mapping intersected with the
        plate's own requirement list. Intersecting is what makes ``-1`` safe to
        read: on its own it also pads slots this plate does not print, so the
        array alone would hold perfectly good jobs. Reading the mapping rather
        than the printer's loaded filament types also inherits the matcher's
        per-nozzle restriction for free — a dual-nozzle printer carrying the
        filament on the other nozzle's AMS has it "loaded" but unusable, and a
        type-only scan would wave that through.

        A mapping that resolved *nothing* is the same finding arriving as an
        absence. ``_ensure_ams_mapping`` clears a rejected mapping its recompute
        could not replace, and dispatch then goes out as ``use_ams`` with no
        table at all — several megabytes uploaded for an 0700_8012 rejection.
        That is held too, but only once live status positively reports loaded
        trays: #2589's mapping is bogus precisely because the AMS was not known
        yet, and its empty loaded list is that ignorance rather than a miss.

        ``release_assignment`` is for the model-based path, which commits its
        printer choice before the gates run. Holding an "any P2S" job would
        otherwise pin it to the one P2S that could not run it.

        Returns True when this dispatch attempt was blocked.
        """
        if item.skip_filament_check or not item.printer_id:
            return False

        mapping: list | None = None
        if item.ams_mapping:
            try:
                mapping = json.loads(item.ams_mapping)
            except (json.JSONDecodeError, TypeError):
                return False
            if not isinstance(mapping, list):
                return False

        unmatched = await self._unmatched_requirements(db, item, item.printer_id, mapping)
        if not unmatched:
            # No cleanup needed here: once start is pressed the item is no
            # longer staged, and whichever exit runs next overwrites the reason
            # (`hold_item` on the fixed-printer branch, the assignment on the
            # model-based one), as does dispatch.
            return False

        wanted = ", ".join(_describe_filament(r, "nozzle_id") for r in unmatched)
        held_by = item.printer_id
        item.manual_start = True
        # Human-readable: this renders on the queue row.
        item.waiting_reason = f"{_UNMATCHED_HOLD_PREFIX}{wanted}"
        if release_assignment:
            # "Any P2S" means any, so the job returns to the pool rather than
            # waiting on the printer that could not take it. The mapping goes
            # with the assignment: its tray IDs were resolved against the
            # printer being released and mean nothing on the next one (#2799),
            # and keeping them would hold the job again even on a printer that
            # has the filament, since an unresolved slot is deliberately not a
            # conflict worth recomputing over.
            item.printer_id = None
            drop_printer_resolved(item)
        await db.commit()

        job_name = await self._get_job_name(db, item)
        printer = await self._get_printer(db, held_by)
        logger.info(
            "Queue item %s blocked — printer %s has nothing loaded for %s; promoted to manual_start",
            item.id,
            held_by,
            wanted,
        )
        try:
            await notification_service.on_queue_job_waiting(
                job_name=job_name,
                target_model=(printer.model if printer else "") or "",
                waiting_reason=f"needs {wanted}",
                db=db,
                # Released to the pool: no printer holds it any more.
                printer_id=None if release_assignment else held_by,
            )
        except Exception as e:
            logger.debug("filament_missing notification failed for item %s: %s", item.id, e)
        return True

    async def _external_spool_only_mapping(
        self, db: AsyncSession, printer_id: int, item: PrintQueueItem
    ) -> list[int] | None:
        """Every filament on the external spool, for a printer that has nothing else (#3239).

        A printer without an AMS prints from its external spool, and an external
        spool whose filament was never set reports no type, so the matcher has
        nothing to match. Sent without a mapping, the print goes out with the AMS
        on and the firmware rejects it with 0700_8012. A stored ``[254]`` used
        to carry such a job through; a job placed by model or location no longer
        keeps one, and one queued that way never had one.

        Only on a positive report: the printer has said it has no AMS, it has a
        single external feed (a dual-nozzle printer's feeds steer nozzles, which
        is not ours to pick), and no feed has a filament set — with one set, the
        matcher has already given its answer. Not for a job that asked for its
        colours to be matched strictly: a spool without a filament set has no
        colour to check. Returns None otherwise.
        """
        if item.filament_overrides:
            try:
                overrides = json.loads(item.filament_overrides)
            except (json.JSONDecodeError, TypeError):
                return None
            if not isinstance(overrides, list) or any(
                isinstance(o, dict) and o.get("force_color_match") for o in overrides
            ):
                return None
        status = self._filament_printer_status(printer_id)
        if status is None or not isinstance(status.raw_data, dict):
            return None
        ams_units = status.raw_data.get("ams")
        if not isinstance(ams_units, list) or ams_units:
            return None
        vt_trays = status.raw_data.get("vt_tray")
        if not isinstance(vt_trays, list) or len(vt_trays) != 1 or not isinstance(vt_trays[0], dict):
            return None
        if self._build_loaded_filaments(status):
            return None
        printer = await self._get_printer(db, printer_id)
        if _might_be_dual_nozzle(printer.model if printer else None, status):
            return None
        external = _int_or(vt_trays[0].get("id"), _EXTERNAL_TRAY_ID_MIN)
        if external < _EXTERNAL_TRAY_ID_MIN:
            return None

        required = await self._get_filament_requirements(db, item)
        slot_ids = [r.get("slot_id") for r in required or []]
        slot_ids = [s for s in slot_ids if isinstance(s, int) and s > 0]
        if not slot_ids:
            return None
        mapping = [-1] * max(slot_ids)
        for slot_id in slot_ids:
            mapping[slot_id - 1] = external
        return mapping

    async def _unmatched_requirements(
        self, db: AsyncSession, item: PrintQueueItem, printer_id: int, mapping: list | None
    ) -> list[dict]:
        """The requirements ``mapping`` leaves without a tray on ``printer_id`` (#2799).

        ``None`` is a mapping that resolved nothing. Only a printer that reported
        loaded trays makes that a finding — see ``_block_on_unmatched_filament``
        on why an empty list is not one.
        """
        if mapping is None:
            status = self._filament_printer_status(printer_id)
            if status is None or not self._build_loaded_filaments(status):
                return []
            # Every required slot reads unresolved against an empty mapping.
            mapping = []

        required = await self._get_filament_requirements(db, item)
        if required:
            self._apply_filament_overrides(item, required)
        else:
            # An unreadable 3MF still has its forced colours to go by: they are
            # what the mapping was built from (#3280).
            required = _forced_override_requirements(item)
        return _unresolved_required(required, mapping) if required else []

    async def _unmatched_on(self, db: AsyncSession, item: PrintQueueItem, printer_id: int) -> list[str]:
        """What ``item`` would be held for on ``printer_id``, as the queue row names it.

        Asks the matcher and the unmatched-filament hold, but changes nothing.
        Choosing a printer for an "any model" job only checked that each type
        and forced colour was loaded somewhere, which a dual-nozzle printer with
        the spool on the other nozzle, or one spool asked for twice, passes. The
        hold then gave the printer back, and the next pass chose it again.

        Empty when the hold would let the item through, including "Print
        Anyway" and a match that fails: the printer is then chosen as before.
        """
        if item.skip_filament_check:
            return []
        key = (item.id, item.archive_id, item.library_file_id, item.plate_id, item.filament_overrides, printer_id)
        if key in self._unmatched_memo:
            return list(self._unmatched_memo[key])
        try:
            mapping = await self._compute_ams_mapping_for_printer(db, printer_id, item)
            unmatched = await self._unmatched_requirements(db, item, printer_id, mapping)
        except Exception as e:
            logger.warning("Filament match check failed for item %s on printer %s: %s", item.id, printer_id, e)
            return []
        described = [_describe_filament(req, "nozzle_id") for req in unmatched]
        self._unmatched_memo[key] = described
        return list(described)

    async def _get_filament_requirements(self, db: AsyncSession, item: PrintQueueItem) -> list[dict] | None:
        """Resolve the queue item's source 3MF and parse the per-slot
        filament requirements out of it. Thin DB-resolver wrapper around
        ``filament_requirements.extract_filament_requirements`` so the VP
        queue-mode write path (#1188) can reuse the same parser at upload
        time.
        """
        from backend.app.services.filament_requirements import extract_filament_requirements

        # Callers rewrite these dicts in place via `_apply_filament_overrides`,
        # so every caller gets its own copy — a shared list would leak one
        # item's overrides into the next item that happens to print the same
        # plate.
        memo_key = (item.archive_id, item.library_file_id, item.plate_id)
        if memo_key in self._filament_req_memo:
            cached = self._filament_req_memo[memo_key]
            return [dict(r) for r in cached] if cached else None

        file_path: Path | None = None
        if item.archive_id:
            result = await db.execute(select(PrintArchive).where(PrintArchive.id == item.archive_id))
            archive = result.scalar_one_or_none()
            if archive:
                file_path = settings.base_dir / archive.file_path
        elif item.library_file_id:
            result = await db.execute(LibraryFile.active().where(LibraryFile.id == item.library_file_id))
            library_file = result.scalar_one_or_none()
            if library_file:
                lib_path = Path(library_file.file_path)
                file_path = lib_path if lib_path.is_absolute() else settings.base_dir / library_file.file_path

        if not file_path or not file_path.exists():
            self._filament_req_memo[memo_key] = None
            return None

        filaments = extract_filament_requirements(file_path, plate_id=item.plate_id)
        self._filament_req_memo[memo_key] = filaments or None
        return [dict(r) for r in filaments] if filaments else None

    async def _release_short_model_hold(
        self,
        db: AsyncSession,
        item: PrintQueueItem,
        unavailable: set[int],
        require_plate_clear: bool,
    ) -> bool:
        """Free an "any model" job held for low filament once a printer can run it (#3137).

        The deficit gate holds a model-based job on the printer the matcher
        gave it, because "Print Anyway" needs a printer to print on. When
        another idle printer of the job's model has the filament, the job is
        moved to that printer and its hold lifted, and the fixed-printer
        branch dispatches it in this same pass, through the same checks a
        held job meets when the user presses Start. It is moved rather than
        put back in the pool because the model-based branch would pick again
        without requiring the amounts on record (below), and could pick a
        different printer. Only the deficit gate sets ``filament_short``, so a
        job held for any other reason stays held.

        The printer it is held on is left out: a spool loaded there is started
        with Start, as before, rather than while someone may still be loading
        the next one. Each job is checked at most every
        ``_SHORT_HOLD_RECHECK_SECONDS``, as every check matches its filament
        on each idle printer again.

        Cross-model jobs (#671) stay held: checking a variant writes its file
        onto the item, which would leave a job that is not moved holding
        another variant's file for the printer it waits on.

        A printer qualifies only on a positive finding: every slot the plate
        prints mapped to a spool whose remaining amount is on record and
        enough. A printer whose spools Bambuddy does not track is not one.

        Returns True when the job was moved. A check that fails keeps the hold
        rather than stopping the queue pass.
        """
        if not item.filament_short or item.skip_filament_check or item.printer_id is None:
            return False
        if not item.target_model or item.variants:
            return False
        now = time.monotonic()
        if now - self._short_hold_checked_at.get(item.id, float("-inf")) < _SHORT_HOLD_RECHECK_SECONDS:
            return False
        self._short_hold_checked_at[item.id] = now

        try:
            candidates = self._queue_model_candidates(item)
            if not candidates:
                return False
            effective_types, filament_overrides = filament_constraints(candidates[0])

            async def is_short(pid: int) -> bool:
                return await self._filament_short_on(db, item, pid, require_known=True)

            match_id, _ = await self._find_idle_printer_for_model(
                db,
                item.target_model,
                unavailable | {item.printer_id},
                effective_types,
                item.target_location,
                filament_overrides=filament_overrides,
                require_plate_clear=require_plate_clear,
                allowed_printer_ids=await creator_printer_ids(db, item.created_by_id),
                unmatched_on=lambda pid: self._unmatched_on(db, item, pid),
                is_short=is_short,
            )
            # Every idle printer short comes back as the first of them.
            if match_id is None or await is_short(match_id):
                return False
        except Exception as e:
            logger.warning("Queue item %s: looking for another printer failed: %s", item.id, e)
            return False

        if await edited_since_loaded(db, item):
            return False

        logger.info(
            "Queue item %s: printer %s has the filament it was short of on printer %s — moving it there",
            item.id,
            match_id,
            item.printer_id,
        )
        self._short_hold_checked_at.pop(item.id, None)
        item.printer_id = match_id
        # Resolved against the printer it leaves (#3239).
        drop_printer_resolved(item)
        item.manual_start = False
        item.filament_short = False
        item.waiting_reason = None
        await db.commit()

        try:
            printer = await self._get_printer(db, match_id)
            await notification_service.on_queue_job_assigned(
                job_name=await self._get_job_name(db, item),
                printer_id=match_id,
                printer_name=printer.name if printer else "Unknown",
                target_model=item.target_model,
                db=db,
            )
        except Exception as e:
            logger.debug("Assignment notification failed for item %s: %s", item.id, e)
        return True

    async def _filament_shortfall(
        self,
        db: AsyncSession,
        item: PrintQueueItem,
        printer_id: int,
        compute_deficit,
        *,
        require_known: bool = False,
    ) -> bool:
        """Would ``item`` be held for a filament deficit on ``printer_id`` (#3137)?

        Asks what ``_block_on_filament_deficit`` would answer once the item is
        assigned there, with the mapping the item would get there, but changes
        nothing. The model-based matcher uses it to prefer a printer whose
        spools can finish the job.

        False whenever the gate would let the item through: "Print Anyway",
        no mapping, or a check that fails. With ``require_known`` all three of
        those, and any printed slot whose remaining amount is unknown, count
        as short instead: releasing a held job starts it with nobody asked, so
        it needs the amount on record, not merely nothing against it.
        """
        if item.skip_filament_check:
            return False
        try:
            mapping = await self._compute_ams_mapping_for_printer(db, printer_id, item)
            if not mapping:
                return require_known
            if require_known and not await self._get_filament_requirements(db, item):
                return True
            deficit = await compute_deficit(
                db, item, printer_id=printer_id, ams_mapping=mapping, require_known=require_known, source_item=item
            )
        except Exception as e:
            logger.warning("Filament deficit check failed for item %s on printer %s: %s", item.id, printer_id, e)
            return require_known
        return bool(deficit)

    def _reset_filament_pass(self, items) -> None:
        self._filament_req_memo.clear()
        self._unmatched_memo.clear()
        pending_ids = {item.id for item in items}
        self._short_hold_checked_at = {
            item_id: at for item_id, at in self._short_hold_checked_at.items() if item_id in pending_ids
        }

    def _candidate_filament_checks(self, db, item, candidate):
        # Candidate checks must not dirty the persistent queue row.
        check_item = SimpleNamespace(
            **{column.key: getattr(item, column.key) for column in PrintQueueItem.__table__.columns},
            library_file=item.library_file,
            archive=item.archive,
        )
        self._resolve_variant(check_item, candidate)

        async def unmatched_on(printer_id):
            return await self._unmatched_on(db, check_item, printer_id)

        async def is_short(printer_id):
            return await self._filament_short_on(db, check_item, printer_id)

        return unmatched_on, is_short

    async def _waiting_for_manual_start(self, db, item, unavailable, require_plate_clear) -> bool:
        if not item.manual_start:
            return False
        if item.filament_short and await self._release_short_model_hold(db, item, unavailable, require_plate_clear):
            return False
        if item.waiting_reason and not _is_unmatched_hold_reason(item.waiting_reason):
            item.waiting_reason = None
            await db.commit()
        return True
