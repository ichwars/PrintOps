"""Spoolman price semantics and durable archive-cost provenance."""

from __future__ import annotations

import math

SPOOLMAN_COST_SOURCE_KEY = "cost_source"
SPOOLMAN_COST_SOURCE = "spoolman"


def positive_finite_number(value) -> float | None:
    """Return a positive finite float while rejecting bools and invalid input."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def nonnegative_finite_number(value) -> float | None:
    """Return a finite float greater than or equal to zero."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def spoolman_usage_cost(spool: dict | None, grams_used) -> float | None:
    """Price consumed grams using Spoolman's full-spool price and net weight."""
    grams = positive_finite_number(grams_used)
    if not isinstance(spool, dict) or grams is None:
        return None
    filament = spool.get("filament")
    if not isinstance(filament, dict):
        return None

    price = positive_finite_number(spool.get("price"))
    if price is None:
        price = positive_finite_number(filament.get("price"))
    weight = positive_finite_number(filament.get("weight"))
    if price is None or weight is None:
        return None

    cost = grams * (price / weight)
    return cost if math.isfinite(cost) else None


def resolve_print_log_cost(
    spoolman_run_cost: float | None,
    usage_results: list[dict],
    status: str,
    archive_cost: float | None,
) -> float | None:
    """Choose this run's measured cost before falling back to the archive estimate."""
    measured_cost = nonnegative_finite_number(spoolman_run_cost)
    if measured_cost is not None:
        return measured_cost
    usage_cost = sum(positive_finite_number(result.get("cost")) or 0.0 for result in usage_results)
    finite_usage_cost = positive_finite_number(usage_cost)
    if finite_usage_cost is not None:
        return finite_usage_cost
    return nonnegative_finite_number(archive_cost) if status == "completed" else None


def has_spoolman_actual_cost(archive) -> bool:
    """Return whether an archive cost was measured from charged Spoolman spools."""
    extra_data = getattr(archive, "extra_data", None)
    return isinstance(extra_data, dict) and extra_data.get(SPOOLMAN_COST_SOURCE_KEY) == SPOOLMAN_COST_SOURCE


def mark_spoolman_actual_cost(archive) -> bool:
    """Persist the Spoolman cost source without discarding other archive metadata."""
    if has_spoolman_actual_cost(archive):
        return False
    extra_data = getattr(archive, "extra_data", None)
    archive.extra_data = {
        **(extra_data if isinstance(extra_data, dict) else {}),
        SPOOLMAN_COST_SOURCE_KEY: SPOOLMAN_COST_SOURCE,
    }
    return True
