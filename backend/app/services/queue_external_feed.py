"""Reconcile AMS use against the plate being dispatched, retaining nozzle routing."""

from pathlib import Path

from backend.app.services.filament_requirements import extract_filament_requirements
from backend.app.services.queue_filament_mapping import _might_be_dual_nozzle

_EXTERNAL_TRAY_ID_MIN = 254


def _consumed_mapping_entries(mapping: list | None, required: list[dict] | None) -> list | None:
    """The ``mapping`` entries for the slots this plate actually prints.

    ``required`` comes from ``extract_filament_requirements``, which drops any
    filament with ``used_g <= 0`` — so a slot_id present there is one the plate
    consumes, and one absent from it is padding. That distinction is why this
    decision lives here and not in the MQTT command builder: a ``-1`` in the
    mapping means either "this plate does not print filament N" or "we never
    worked out which tray", and only the plate's own filament list separates
    them. The builder sees both as the same byte, which is how a plate whose one
    printed filament sat on the external spool went out as `use_ams=true` with a
    mapping of nothing but -1 and stalled at preheat until the firmware gave up
    with 07FF_8012 (#3087).

    Returns None whenever the two cannot be lined up — no mapping, no parsed
    requirements, or a requirement the mapping is too short to cover — so every
    caller falls back to existing behaviour rather than acting on a guess.
    """
    if not isinstance(mapping, list) or not mapping or not required:
        return None
    entries = []
    for filament in required:
        slot_id = filament.get("slot_id")
        if not isinstance(slot_id, int) or not 1 <= slot_id <= len(mapping):
            # The mapping and the requirements disagree about how many filaments
            # the file has. They came from different reads, so judge nothing.
            return None
        entries.append(mapping[slot_id - 1])
    return entries or None


def _is_external_tray(tray_id) -> bool:
    """True for an explicit external-spool selection (254/255), not for an
    unresolved slot and not for an AMS tray."""
    if tray_id is None:
        return False
    try:
        return int(tray_id) >= _EXTERNAL_TRAY_ID_MIN
    except (TypeError, ValueError):
        return False


def plate_uses_external_feed(printer_model, status, mapping, file_path: Path | None, plate_id: int) -> bool:
    if not mapping or file_path is None or not any(_is_external_tray(tray) for tray in mapping):
        return False
    if _might_be_dual_nozzle(printer_model, status):
        return False
    required = extract_filament_requirements(file_path, plate_id=plate_id)
    consumed = _consumed_mapping_entries(mapping, required)
    return bool(consumed) and all(_is_external_tray(tray) for tray in consumed)


def external_feed_options(printer_model, status, mapping, file_path, plate_id, stored_use_ams) -> dict:
    external_only = plate_uses_external_feed(printer_model, status, mapping, file_path, plate_id)
    return {"use_ams": False if external_only else stored_use_ams, "plate_uses_only_external": external_only}
