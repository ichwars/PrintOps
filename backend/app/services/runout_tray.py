"""Narrow a paused print's local slot only when nozzle wiring proves it."""

from __future__ import annotations

from backend.app.utils.tray_ids import TrayLayout, is_ams_ht_id, mapped_trays_with_slot


def nozzle_wiring(state) -> dict | None:
    """Which nozzle each AMS is wired to, for the runout hint; None with a
    Filament Track Switch fitted, where an AMS can feed either nozzle and the
    map can still hold an AMS's wiring from before it moved onto the switch."""
    if getattr(getattr(state, "fila_switch", None), "installed", False) is True:
        return None
    wiring = getattr(state, "ams_extruder_map", None)
    return wiring if isinstance(wiring, dict) else None


def _trays_on_extruder(
    raw_slot: int,
    ams_layout: list[tuple[int, bool]],
    active_extruder: int | None,
    ams_extruder_map: dict | None,
    tray_layout: TrayLayout,
) -> set[int] | None:
    """The global trays a local ``raw_slot`` can be on the AMS units wired to
    ``active_extruder`` (an AMS-HT's one tray for slot 0), or None when the
    wiring is unknown.

    An AMS on the Filament Track Switch has no entry in the map (it can feed
    either nozzle), so one without an entry makes the answer unknown too.
    """
    if active_extruder is None or not ams_extruder_map:
        return None
    trays: set[int] = set()
    for ams_id, is_ht in ams_layout:
        nozzle = ams_extruder_map.get(str(ams_id))
        if nozzle is None:
            return None
        if nozzle != active_extruder:
            continue
        if not is_ht or raw_slot == 0:
            trays.add(tray_layout.global_tray_id(ams_id, raw_slot))
    return trays


def resolve_expected_tray(
    raw_slot: int | None,
    ams_layout: list[tuple[int, bool]],
    mapping_raw: object,
    active_extruder: int | None = None,
    ams_extruder_map: dict | None = None,
    tray_layout: TrayLayout | None = None,
) -> int | None:
    """Globalise a raw firmware ``tray_tar``/``tray_pre`` value for the runout UI (#2587).

    The firmware reports the target/previous slot as a bare number whose meaning
    depends on the AMS layout (see ``PrinterState.tray_tar``). This mirrors the
    ``tray_now`` handling so the resolved ID lines up with what the AMS graphic
    already highlights via ``ams_id*4 + slot``.

    ``ams_layout`` is a list of ``(ams_id, is_ams_ht)`` for the connected units.

    - ``255``/``-1`` (none/idle) -> ``None``
    - ``254`` (external spool) -> ``254``
    - ``128``-``135`` (AMS-HT) -> already global, returned as-is
    - ``0``-``3`` local slot:
        * exactly one regular AMS -> ``ams_id*4 + slot``
        * several regular AMS -> resolved via the snow-encoded ``mapping`` field
          (each entry = ``ams_hw_id*256 + slot``; ``65535`` = unmapped), then
          narrowed to the AMS that feed ``active_extruder`` (``ams_extruder_map``,
          dual-nozzle printers), or ``None`` when it stays ambiguous (honest
          "can't determine")
        * no regular AMS -> ``None``
    - ``4``-``15`` -> already a global regular-AMS ID, returned as-is

    A printer with a rack AMS (``tray_layout``) reports the rack's raw slot 0-8.

    Returns ``None`` for anything it can't place, so the caller surfaces a
    "check the printer" message instead of pointing at the wrong slot.
    """
    if isinstance(raw_slot, bool) or not isinstance(raw_slot, int) or raw_slot in (255, -1):
        return None
    layout = tray_layout or TrayLayout()
    if layout.rack_units:
        rack_tray = layout.raw_slot_to_global(raw_slot)
        if rack_tray is not None:
            return rack_tray
        return raw_slot if is_ams_ht_id(raw_slot) or layout.is_external(raw_slot) else None
    if raw_slot == 254:
        return 254
    if is_ams_ht_id(raw_slot):
        return raw_slot
    if 0 <= raw_slot <= 3:
        regular = [ams_id for ams_id, is_ht in ams_layout if not is_ht]
        if len(regular) == 1:
            return layout.global_tray_id(regular[0], raw_slot)
        if len(regular) > 1:
            candidates = set(mapped_trays_with_slot(mapping_raw, raw_slot))
            if len(candidates) == 1:
                return candidates.pop()
            # The print paused on the active nozzle, so the slot is on an AMS
            # that feeds it.
            narrowed = _trays_on_extruder(raw_slot, ams_layout, active_extruder, ams_extruder_map, layout)
            if narrowed is None:
                return None
            if candidates:
                narrowed &= candidates
            return narrowed.pop() if len(narrowed) == 1 else None
        return None
    if 4 <= raw_slot <= 15:
        return raw_slot
    # 24-27 = A2L AMS-Lite (normalised unit 6) global tray ids, already resolved.
    if 24 <= raw_slot <= 27:
        return raw_slot
    return None
