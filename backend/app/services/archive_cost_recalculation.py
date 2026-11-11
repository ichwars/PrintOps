"""Reprice one archived print without summing the costs of its reprints."""

from sqlalchemy import and_, case, func, or_, select

from backend.app.models.archive import PrintArchive
from backend.app.models.filament import Filament
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.spool_usage_history import SpoolUsageHistory
from backend.app.services.archive_scope import whole_archive_conditions
from backend.app.services.print_cost_estimate import default_cost_per_kg, price_one_print
from backend.app.services.print_log_run import run_visibility_conditions
from backend.app.services.spoolman_costs import has_spoolman_actual_cost
from backend.app.services.usage_repricing import reprice_usage


def priced_usage_totals():
    return (
        func.sum(SpoolUsageHistory.cost),
        func.sum(case((SpoolUsageHistory.cost.is_not(None), SpoolUsageHistory.weight_used), else_=0.0)),
    )


async def one_print_cost(db, archive, previous_grams=None, pricing=None):
    grams = archive.filament_used_grams
    # Durable source provenance wins even after the current inventory mode
    # changes. Old built-in usage rows must not replace a Spoolman charge.
    if has_spoolman_actual_cost(archive):
        if previous_grams and grams and archive.cost is not None:
            return round(archive.cost * grams / previous_grams, 2)
        return archive.cost
    default = pricing["default"] if pricing is not None else await default_cost_per_kg(db)
    if pricing is None:
        usage_cost, tracked_grams = (
            await db.execute(
                select(*priced_usage_totals()).where(
                    SpoolUsageHistory.archive_id == archive.id, SpoolUsageHistory.spoolman_spool_id.is_(None)
                )
            )
        ).one()
    else:
        usage_cost, tracked_grams = pricing["usage"].get(archive.id, (None, 0))
    if usage_cost is not None and usage_cost > 0:
        if pricing is None:
            printed_grams, runs = (
                await db.execute(
                    select(func.sum(PrintLogEntry.filament_used_grams), func.count(PrintLogEntry.id)).where(
                        PrintLogEntry.archive_id == archive.id
                    )
                )
            ).one()
        else:
            printed_grams, runs = pricing["runs"].get(archive.id, (0, 0))
        return price_one_print(
            grams,
            float(usage_cost),
            float(tracked_grams or 0),
            float(printed_grams or 0),
            int(runs or 0),
            default,
            default,
        )
    # Usage detached from an archive cannot identify which same-named print incurred the cost.
    if not grams:
        return archive.cost
    rate = default
    if archive.filament_type:
        material = archive.filament_type.split(",")[0].strip()
        catalog = (
            pricing["catalog"].get(material)
            if pricing is not None
            else await db.scalar(select(Filament.cost_per_kg).where(Filament.type == material).limit(1))
        )
        if catalog is not None:
            rate = catalog
    return price_one_print(grams, None, 0, 0, 0, rate, default)


async def load_pricing_context(db):
    """Keep bulk repricing at a fixed query count as the archive grows."""
    default = await default_cost_per_kg(db)
    catalog = dict((await db.execute(select(Filament.type, Filament.cost_per_kg))).all())
    usage = (
        await db.execute(
            select(SpoolUsageHistory.archive_id, *priced_usage_totals())
            .where(SpoolUsageHistory.spoolman_spool_id.is_(None))
            .group_by(SpoolUsageHistory.archive_id)
        )
    ).all()
    runs = (
        await db.execute(
            select(
                PrintLogEntry.archive_id, func.sum(PrintLogEntry.filament_used_grams), func.count(PrintLogEntry.id)
            ).group_by(PrintLogEntry.archive_id)
        )
    ).all()
    return {
        "default": default,
        "catalog": catalog,
        "usage": {row[0]: (row[1], row[2]) for row in usage},
        "runs": {row[0]: (row[1], row[2]) for row in runs},
    }


async def projected_print_runs(db, access, archive_id=None):
    """The finished runs represented by archive metadata at this moment."""
    query = (
        select(PrintLogEntry)
        .join(PrintArchive, PrintArchive.id == PrintLogEntry.archive_id)
        .where(
            PrintArchive.status != "printing",
            or_(
                PrintLogEntry.printer_id.is_not_distinct_from(PrintArchive.printer_id),
                and_(PrintLogEntry.printer_id.is_(None), PrintArchive.started_at.is_(None)),
            ),
            or_(
                PrintArchive.started_at.is_(None),
                PrintLogEntry.started_at == PrintArchive.started_at,
            ),
            *run_visibility_conditions(access),
        )
        .order_by(PrintLogEntry.started_at.desc().nulls_last(), PrintLogEntry.id.desc())
    )
    if archive_id is not None:
        query = query.where(PrintArchive.id == archive_id).limit(1)
    entries = {}
    for run in await db.scalars(query):
        entries.setdefault(run.archive_id, run)
    return entries


def mirror_inherited_cost(run, previous_cost, new_cost):
    if run is not None and run.status == "completed" and run.cost in (None, previous_cost):
        run.cost = new_cost


async def recalculate_archive_costs(db, access):
    archives = list(
        await db.scalars(
            select(PrintArchive)
            .where(*whole_archive_conditions(access), PrintArchive.status != "printing")
            .order_by(PrintArchive.id)
            .with_for_update()
        )
    )
    previous_costs = {archive.id: archive.cost for archive in archives}
    runs = await projected_print_runs(db, access)
    repriced, measured_runs, unavailable = await reprice_usage(
        db,
        archives,
        runs,
        await default_cost_per_kg(db),
        include_detached=access.can_access_all and access.printer_ids is None,
    )
    pricing = await load_pricing_context(db)
    for archive in archives:
        cost = await one_print_cost(db, archive, pricing=pricing)
        if cost is not None and cost != archive.cost:
            run = runs.get(archive.id)
            if run is not None and run.id not in measured_runs:
                mirror_inherited_cost(run, archive.cost, cost)
            archive.cost = cost
    updated = sum(archive.cost != previous_costs[archive.id] for archive in archives)
    await db.commit()
    return {
        "message": f"Recalculated costs for {updated} archives",
        "updated": updated,
        "usage_repriced": repriced,
        "spoolman_unreachable": unavailable,
    }
