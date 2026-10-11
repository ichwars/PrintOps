"""Normalize only explicit calibration diameter and reported flow values."""

import math


def diameter(value) -> str | None:
    """Normalize an explicit finite nozzle diameter, without inventing one."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
        return f"{number:g}" if math.isfinite(number) and 0 < number <= 2 else None
    except (TypeError, ValueError):
        return None


def flow_type(value) -> str | None:
    """Only HS/HH report flow; legacy material names do not report Standard."""
    if not isinstance(value, str):
        return None
    prefix = value.strip().upper()[:2]
    return prefix if prefix in {"HS", "HH"} else None
