"""Shared preheat filament defaults and persisted target-map parsing."""

import json
import logging

logger = logging.getLogger(__name__)
DEFAULT_PREHEAT_FILAMENT_TARGETS = {
    "PLA": 0,
    "PETG": 0,
    "PETG-CF": 40,
    "ABS": 45,
    "ASA": 45,
    "PA": 50,
    "PA-CF": 55,
    "PC": 50,
    "PC-FR": 50,
    "TPU": 0,
    "PVA": 0,
    "default": 0,
}


def parse_preheat_filament_targets(raw: str | None) -> dict[str, int]:
    if not raw:
        return dict(DEFAULT_PREHEAT_FILAMENT_TARGETS)
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("preheat_filament_targets unparseable, using defaults: %s", exc)
        return dict(DEFAULT_PREHEAT_FILAMENT_TARGETS)
    out = {}
    for key, value in parsed.items():
        try:
            out[str(key).upper()] = int(value)
        except (TypeError, ValueError):
            continue
    if "DEFAULT" not in out:
        out["DEFAULT"] = DEFAULT_PREHEAT_FILAMENT_TARGETS["default"]
    return out
