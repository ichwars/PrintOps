"""Native Spoolman weight resolution shared by inventory, scale and tracking."""

import math


def _weight(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def spoolman_net_weight(spool: dict) -> float | None:
    initial = _weight(spool.get("initial_weight"))
    if initial is not None and initial > 0:
        return initial
    filament = spool.get("filament")
    return _weight(filament.get("weight")) if isinstance(filament, dict) else None


def spoolman_tare(spool: dict) -> tuple[float, str]:
    filament = spool.get("filament") or {}
    vendor = filament.get("vendor") or {}
    for source, raw in (
        ("spool", spool.get("spool_weight")),
        ("filament", filament.get("spool_weight")),
        ("vendor", vendor.get("empty_spool_weight")),
    ):
        if (value := _weight(raw)) is not None:
            return value, source
    return 250.0, "fallback"


def spoolman_price_weight(spool: dict) -> float:
    net = spoolman_net_weight(spool)
    return net if net is not None and net > 0 else 1000.0
