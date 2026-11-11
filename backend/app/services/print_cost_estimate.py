"""Common cost rules for a single print and the configured fallback rate."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession


def plate_scoped_run_estimate(archive, path, plate_id=None):
    """Scope fallback grams and proportional cost to this run's plate."""
    from backend.app.services.spoolman_costs import nonnegative_finite_number, positive_finite_number
    from backend.app.utils.threemf_tools import extract_filament_usage_from_3mf

    whole = positive_finite_number(archive.filament_used_grams)
    cost = nonnegative_finite_number(archive.cost)
    if getattr(archive, "plate_estimates", None):
        from backend.app.services.archive_plate_estimates import archive_run_estimate

        _, grams = archive_run_estimate(archive, plate_id)
        estimate_cost = round(cost * grams / whole, 2) if cost is not None and grams and whole else None
        return grams, estimate_cost
    selected = plate_id if plate_id is not None else archive.plate_id
    if selected is None or path is None:
        return whole, cost
    usage = extract_filament_usage_from_3mf(path, selected)
    grams = sum(positive_finite_number(row.get("used_g")) or 0 for row in usage)
    if grams <= 0:
        return whole, cost
    # Archives parsed for one plate carry that plate's grams; other files
    # carry whole-file totals. The stored grams are the matching cost basis.
    estimate_cost = round(cost * grams / whole, 2) if cost is not None and whole else None
    return round(grams, 2), estimate_cost


async def default_cost_per_kg(db: AsyncSession) -> float:
    """The default filament price per kg, as the Settings page shows it: 25
    when it was never saved."""
    from backend.app.api.routes.settings import get_setting

    raw = await get_setting(db, "default_filament_cost")
    try:
        from backend.app.services.spoolman_costs import nonnegative_finite_number

        parsed = nonnegative_finite_number(raw)
        return parsed if parsed is not None else 25.0
    except (TypeError, ValueError):
        return 25.0


async def estimate_filament_cost(db: AsyncSession, grams: float | None, filament_type: str | None) -> float | None:
    """Price the amount in a 3MF at its first material's configured rate."""
    from sqlalchemy import select

    from backend.app.models.filament import Filament
    from backend.app.services.spoolman_costs import nonnegative_finite_number, positive_finite_number

    weight = positive_finite_number(grams)
    if weight is None or not filament_type:
        return None
    primary = filament_type.split(",", 1)[0].strip()
    rate = await db.scalar(select(Filament.cost_per_kg).where(Filament.type == primary).order_by(Filament.id).limit(1))
    rate = nonnegative_finite_number(rate)
    if rate is None:
        rate = await default_cost_per_kg(db)
    return nonnegative_finite_number(round((weight / 1000) * rate, 2))


def price_one_print(
    grams: float | None,
    usage_cost: float | None,
    tracked_grams: float,
    printed_grams: float,
    runs: int,
    fallback_cost_per_kg: float,
    default_cost_per_kg: float,
) -> float | None:
    """Cost of one print of ``grams``, the figure an archive carries (#1378).

    ``usage_cost`` / ``tracked_grams`` are the priced spool usage recorded
    against the archive, over every run of it; ``printed_grams`` / ``runs`` are
    those runs' grams and count from Print History. The spools tracked
    ``tracked_grams`` of ``printed_grams``: one print gets that share at their
    average price per gram and the rest at the default rate (#1344). Without
    priced usage, everything is priced at ``fallback_cost_per_kg``.
    """
    if usage_cost and usage_cost > 0 and tracked_grams > 0:
        if not grams:
            # No figure for one print: an average run's usage is the best one.
            cost = usage_cost / max(1, runs)
        else:
            expected = printed_grams if printed_grams > 0 else grams
            covered = grams * min(1.0, tracked_grams / expected)
            cost = covered * (usage_cost / tracked_grams) + (grams - covered) / 1000.0 * default_cost_per_kg
    elif grams:
        cost = grams / 1000.0 * fallback_cost_per_kg
    else:
        return None
    return float(Decimal(str(cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
