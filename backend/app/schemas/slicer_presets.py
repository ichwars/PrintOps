"""Pydantic schemas for the unified slicer-presets endpoint.

The SliceModal lists imported, Orca Cloud, Bambu Cloud, and bundled presets.
Equivalent Bambu stock entries are listed once and their older references
resolve through stock_aliases.
"""

from typing import Literal

from pydantic import BaseModel, Field

from backend.app.schemas.slicer import PresetRef

CloudStatus = Literal["ok", "not_authenticated", "expired", "unreachable"]


class UnifiedPreset(BaseModel):
    """A single printer/process/filament preset with its source.

    The ``id`` shape varies by source:
      - cloud  → Bambu Cloud setting_id (e.g. ``"PFUS9ac902733670a9"``)
      - local  → stringified DB row id from ``local_presets``
      - standard → preset name as written in the bundled JSON (the slicer
                   resolves bundled profiles by name during inheritance walk)

    The frontend treats ``id`` as opaque; the slice dispatch path uses
    ``(source, id)`` to fetch / pass the preset content to the sidecar.

    ``filament_type`` and ``filament_colour`` are populated for the filament
    slot only — they let the SliceModal pre-pick a preset per plate slot in
    the multi-color flow by matching against the source 3MF's per-slot type
    and color. Populated when the underlying preset JSON exposes them; left
    as ``None`` on bundled profiles where colour is a runtime spool attribute.

    ``compatible_printers`` is the slicer's own list of printer-preset names a
    process / filament preset declares itself valid for. Populated for the
    local tier (stored at import time); left ``None`` for cloud (no per-preset
    detail is fetched — rate limits) and standard (the sidecar's bundled
    listing doesn't expose it). The SliceModal uses it to filter the
    process / filament dropdowns by the selected printer (#1325); when it is
    ``None`` the modal falls back to the user's uploaded Slicer Bundles, which
    map each printer to the presets it ships.
    """

    id: str
    name: str
    source: Literal["orca_cloud", "cloud", "local", "standard"]
    filament_type: str | None = None
    filament_colour: str | None = None
    compatible_printers: list[str] | None = None
    # Printer parent exposed for compatibility matching.
    printer_parent: str | None = None
    # Internal parent used to enrich filament metadata.
    inherits: str | None = Field(default=None, exclude=True)
    stock: bool = Field(default=False, exclude=True)


class UnifiedPresetsBySlot(BaseModel):
    """Three slots in the order Bambu Studio / OrcaSlicer use."""

    printer: list[UnifiedPreset] = []
    process: list[UnifiedPreset] = []
    filament: list[UnifiedPreset] = []


class UnifiedPresetsResponse(BaseModel):
    """Source tiers retain their presets except duplicate Bambu stock entries.

    Priority order: ``local > orca_cloud > cloud > standard``. The order
    drives auto-pick (first non-empty tier wins, name-lookup walks tiers
    in this order, filament scoring tiebreaks by per-tier bonus) and
    determines the visual rendering order of the SliceModal's optgroups,
    while same-named imports and Orca profiles remain available separately.

    ``cloud_status`` / ``orca_cloud_status`` let the frontend show a banner
    explaining why a cloud tier is empty when the user expected to see it
    (signed out / token expired / network down). Each tier has its own
    status because they can fail independently.
    """

    orca_cloud: UnifiedPresetsBySlot = UnifiedPresetsBySlot()
    cloud: UnifiedPresetsBySlot = UnifiedPresetsBySlot()
    local: UnifiedPresetsBySlot = UnifiedPresetsBySlot()
    standard: UnifiedPresetsBySlot = UnifiedPresetsBySlot()
    cloud_status: CloudStatus = "ok"
    orca_cloud_status: CloudStatus = "ok"
    stock_aliases: dict[str, PresetRef] = Field(default_factory=dict)


class LoadedSpoolPreset(BaseModel):
    preset_id: str
    preset_name: str
    preset_source: str
    tray_info_idx: str | None = None


class LoadedSpoolTray(BaseModel):
    ams_id: int
    tray_id: int
    tray_type: str | None = None
    tray_sub_brands: str | None = None
    tray_color: str | None = None
    tray_info_idx: str | None = None
    exists: bool | None = None
    state: int | None = None
    saved_preset: LoadedSpoolPreset | None = None


class LoadedSpoolUnit(BaseModel):
    id: int
    trays: list[LoadedSpoolTray]


class LoadedSpoolPrinter(BaseModel):
    id: int
    name: str
    model: str | None = None
    ams: list[LoadedSpoolUnit]
    external: list[LoadedSpoolTray]
    external_holders: int


class LoadedSpoolsResponse(BaseModel):
    printers: list[LoadedSpoolPrinter] = Field(default_factory=list)
