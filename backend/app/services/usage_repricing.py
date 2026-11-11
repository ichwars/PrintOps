"""Reprice measured usage only when its original spool still exists."""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import or_, select

from backend.app.models.print_log import PrintLogEntry
from backend.app.models.spool import Spool
from backend.app.models.spool_usage_history import SpoolUsageHistory
from backend.app.services.inventory_mode import spoolman_owns_assignments
from backend.app.services.spoolman import get_spoolman_client
from backend.app.services.spoolman_costs import has_spoolman_actual_cost, nonnegative_finite_number, spoolman_usage_cost
from backend.app.utils.local_time import to_naive_utc

logger = logging.getLogger(__name__)
_COMPLETION_SLACK = timedelta(minutes=30)


def _charged_run(usage, candidates):
    recorded = to_naive_utc(usage.created_at)
    if recorded is None:
        return None
    started = [
        (to_naive_utc(run.started_at), run)
        for run in candidates
        if run.started_at and to_naive_utc(run.started_at) <= recorded
    ]
    if not started:
        return None
    newest = max(moment for moment, _ in started)
    matches = [run for moment, run in started if moment == newest]
    if len(matches) != 1:
        return None
    run = matches[0]
    ended = to_naive_utc(run.completed_at)
    return run if ended is None or recorded <= ended + _COMPLETION_SLACK else None


def _registered_at(spool: dict) -> datetime | None:
    try:
        return to_naive_utc(datetime.fromisoformat(spool["registered"]))
    except (KeyError, TypeError, ValueError):
        return None


async def _current_spoolman_rates(db, spool_ids: set[int]) -> dict[int, tuple[float | None, datetime | None]] | None:
    if not spool_ids or not await spoolman_owns_assignments(db):
        return {}
    client = await get_spoolman_client()
    if client is None:
        return None
    try:
        async with asyncio.timeout(5):
            spools = await client.get_all_spools(allow_archived=True)
    except Exception:
        logger.warning("Spoolman prices are unavailable during recalculation", exc_info=True)
        return None
    return {
        spool["id"]: (spoolman_usage_cost(spool, 1), _registered_at(spool))
        for spool in spools
        if isinstance(spool, dict) and type(spool.get("id")) is int and spool["id"] in spool_ids
    }


async def reprice_usage(db, archives, inherited_runs, default_rate, *, include_detached):
    archive_ids = {archive.id for archive in archives}
    scope = SpoolUsageHistory.archive_id.in_(archive_ids)
    run_scope = PrintLogEntry.archive_id.in_(archive_ids)
    if include_detached:
        scope = or_(scope, SpoolUsageHistory.archive_id.is_(None))
        run_scope = or_(run_scope, PrintLogEntry.archive_id.is_(None))
    rows = (
        await db.execute(
            select(SpoolUsageHistory, Spool.id, Spool.cost_per_kg)
            .outerjoin(Spool, SpoolUsageHistory.spool_id == Spool.id)
            .where(scope)
            .order_by(SpoolUsageHistory.id)
            .with_for_update(of=SpoolUsageHistory)
        )
    ).all()
    if not rows:
        return 0, set(), 0

    spoolman_rates = await _current_spoolman_rates(
        db, {row.spoolman_spool_id for row, _, _ in rows if row.spoolman_spool_id is not None}
    )
    unavailable = 0
    runs_by_source = defaultdict(list)
    first_runs = {}
    for run in await db.scalars(select(PrintLogEntry).where(run_scope).order_by(PrintLogEntry.id).with_for_update()):
        if run.archive_id is not None:
            first_runs.setdefault(run.archive_id, run)
        if run.archive_id is not None or run.printer_id is not None:
            runs_by_source[(run.archive_id, run.printer_id)].append(run)
    owners = {row.id: _charged_run(row, runs_by_source.get((row.archive_id, row.printer_id), ())) for row, _, _ in rows}
    source_owners = defaultdict(set)
    archives_with_missing_spools = set()
    for row, spool_id, _ in rows:
        if spool_id is None:
            archives_with_missing_spools.add(row.archive_id)
        run = owners[row.id]
        source_owners[row.archive_id].add(run.id if run is not None else None)
    following_archive = {
        run.id
        for archive in archives
        if (run := inherited_runs.get(archive.id)) is not None
        and run.status == "completed"
        and run.cost in (None, archive.cost)
        and archive.id not in archives_with_missing_spools
        and source_owners[archive.id] == {run.id}
        and run.filament_used_grams == archive.filament_used_grams
    }

    measured_archive_runs = {
        run.id: archive
        for archive in archives
        if has_spoolman_actual_cost(archive)
        and (run := first_runs.get(archive.id)) is not None
        and run.cost == archive.cost
    }
    updated = 0
    measured_runs = set()
    deltas = defaultdict(float)
    runs_to_update = {}
    for row, spool_id, own_rate in rows:
        run = owners[row.id]
        if run is None and (row.archive_id is None or row.spoolman_spool_id is not None or own_rate is None):
            continue
        # A legacy row may still identify its archive and explicit spool price.
        # It contributes to the archive estimate without changing a run's cost.
        measured_run = run if run is not None and run.id not in following_archive else None
        if measured_run is not None:
            measured_runs.add(measured_run.id)
        grams = nonnegative_finite_number(row.weight_used)
        if grams is None:
            continue
        if row.spoolman_spool_id is not None:
            if spoolman_rates is None:
                unavailable += 1
                continue
            if row.spoolman_spool_id not in spoolman_rates:
                continue
            rate, registered = spoolman_rates[row.spoolman_spool_id]
            if registered is not None and (row.created_at is None or to_naive_utc(row.created_at) < registered):
                continue
            cost = nonnegative_finite_number(grams * rate) if rate is not None else None
            if rate is not None and cost is None:
                continue
            fallback_cost = grams * default_rate / 1000
        elif spool_id is not None:
            if run is not None and run.id in measured_archive_runs:
                continue
            rate = default_rate if own_rate is None else nonnegative_finite_number(own_rate)
            if rate is None:
                continue
            priced = nonnegative_finite_number((grams / 1000) * rate)
            if priced is None:
                continue
            cost = round(priced, 2) if rate > 0 else None
            fallback_cost = 0.0
        else:
            continue
        if cost == row.cost:
            continue
        if measured_run is not None:
            previous = row.cost if row.cost is not None else fallback_cost
            current = cost if cost is not None else fallback_cost
            deltas[measured_run.id] += current - previous
            runs_to_update[measured_run.id] = measured_run
        row.cost = cost
        updated += 1
    for run_id, delta in deltas.items():
        run = runs_to_update[run_id]
        run.cost = round(max(0.0, (run.cost or 0.0) + delta), 2)
        archive = measured_archive_runs.get(run_id)
        if archive is not None:
            archive.cost = run.cost
    return updated, measured_runs, unavailable
