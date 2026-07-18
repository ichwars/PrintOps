from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

DENSITY_BY_MATERIAL = {
    "PLA": Decimal("1.24"),
    "PETG": Decimal("1.27"),
    "ABS": Decimal("1.04"),
    "ASA": Decimal("1.07"),
    "TPU": Decimal("1.21"),
    "PA": Decimal("1.14"),
    "PC": Decimal("1.20"),
}


@dataclass(frozen=True)
class BoundsMm:
    width: Decimal
    depth: Decimal
    height: Decimal


@dataclass(frozen=True)
class PlateGeometry:
    object_count: int
    triangle_count: int
    volume_cm3: Decimal
    bounds_mm: BoundsMm


@dataclass(frozen=True)
class EstimatorSettings:
    density_g_cm3: Decimal | None
    infill_percent: Decimal
    layer_height_mm: Decimal
    nozzle_mm: Decimal
    speed_mm_s: Decimal
    wall_lines: int


@dataclass(frozen=True)
class EstimateResult:
    material_grams: Decimal | None
    print_hours: Decimal | None
    warnings: tuple[str, ...]


def _clamp(value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
    return max(minimum, min(maximum, value))


def _normalize_material(value: str) -> str:
    return value.strip().upper().split("-")[0]


def _travel_seconds(bounds: BoundsMm, layer_height: Decimal) -> Decimal:
    if bounds.height <= 0 or layer_height <= 0:
        return Decimal("0")
    layers = bounds.height / layer_height
    return layers * (bounds.width + bounds.depth) / Decimal("180")


def estimate_plate(geometry: PlateGeometry, settings: EstimatorSettings, material_type: str) -> EstimateResult:
    if geometry.volume_cm3 <= 0:
        return EstimateResult(None, None, ("Model volume unavailable",))
    density = settings.density_g_cm3 or DENSITY_BY_MATERIAL.get(_normalize_material(material_type), Decimal("1.24"))
    infill = _clamp(settings.infill_percent / Decimal("100"), Decimal("0"), Decimal("1"))
    solid_share = min(Decimal("0.92"), Decimal("0.18") + Decimal(settings.wall_lines) * Decimal("0.055"))
    effective_cm3 = geometry.volume_cm3 * _clamp(
        solid_share + (Decimal("1") - solid_share) * infill,
        Decimal("0.18"),
        Decimal("1"),
    )
    grams = (effective_cm3 * density * Decimal("1.06")).quantize(Decimal("0.1"))
    flow = settings.nozzle_mm * Decimal("1.12") * settings.layer_height_mm * settings.speed_mm_s * Decimal("0.58")
    if flow <= 0:
        return EstimateResult(grams, None, ("Geometry estimate", "Invalid flow settings"))
    seconds = effective_cm3 * Decimal("1000") / flow + _travel_seconds(geometry.bounds_mm, settings.layer_height_mm)
    return EstimateResult(
        grams,
        (seconds / Decimal("3600")).quantize(Decimal("0.01")),
        ("Geometry estimate",),
    )
