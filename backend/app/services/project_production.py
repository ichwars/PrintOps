from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.archive import PrintArchive
from backend.app.models.location import Location
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.project_production import ProjectProductionOutput, ProjectProductionReceipt
from backend.app.schemas.project import ProjectProductionDestination
from backend.app.schemas.warehouse_article import WarehouseMovementCreate
from backend.app.services.warehouse_articles import WarehouseError, load_article
from backend.app.services.warehouse_stock import post_movement

PIECE_UNITS = {"C62", "H87"}


async def validate_production_article(db: AsyncSession, article_id: int) -> None:
    article = await load_article(db, article_id, lock=True)
    if not (
        article.is_active
        and article.kind == "finished"
        and article.stock_source == "own"
        and article.unit_code in PIECE_UNITS
    ):
        raise WarehouseError(
            "invalid_production_article", "Wähle ein aktives Fertigprodukt mit eigenem Bestand in Stück.", 422
        )


async def save_destination(
    db: AsyncSession, project_id: int, destination: ProjectProductionDestination
) -> ProjectProductionOutput:
    output = await db.get(ProjectProductionOutput, project_id)
    if output and (output.article_id, output.location_id) == (destination.article_id, destination.location_id):
        return output
    if (
        output
        and await db.scalar(
            select(ProjectProductionReceipt.ledger_entry_id)
            .where(ProjectProductionReceipt.project_id == project_id)
            .limit(1)
        )
        is not None
    ):
        raise WarehouseError("production_destination_booked", "Das Lagerziel ist nach der ersten Buchung festgelegt.")
    await validate_production_article(db, destination.article_id)
    await db.execute(
        update(Location).where(Location.id == destination.location_id).values(updated_at=Location.updated_at)
    )
    if await db.get(Location, destination.location_id) is None:
        raise WarehouseError("invalid_location", "Lagerort nicht gefunden", 422)
    if output is None:
        output = ProjectProductionOutput(project_id=project_id)
        db.add(output)
    output.article_id = destination.article_id
    output.location_id = destination.location_id
    return output


async def book_confirmed_output(db: AsyncSession, output: ProjectProductionOutput, *, actor_id: int | None) -> None:
    # Lock the runs even if an older archive was moved to another project. The
    # run's own project snapshot takes precedence over its archive assignment.
    run_ids = list(
        await db.scalars(
            select(PrintLogEntry.id)
            .outerjoin(PrintArchive, PrintArchive.id == PrintLogEntry.archive_id)
            .where(
                func.coalesce(PrintLogEntry.project_id, PrintArchive.project_id) == output.project_id,
                PrintLogEntry.status == "completed",
            )
            .order_by(PrintLogEntry.id)
            .with_for_update(of=PrintLogEntry)
        )
    )
    if not run_ids:
        return
    pending = (
        await db.execute(
            select(PrintLogEntry.id, PrintLogEntry.good_quantity)
            .outerjoin(ProjectProductionReceipt, ProjectProductionReceipt.run_id == PrintLogEntry.id)
            .where(PrintLogEntry.id.in_(run_ids), ProjectProductionReceipt.ledger_entry_id.is_(None))
            .order_by(PrintLogEntry.id)
        )
    ).all()
    if any(run.good_quantity is None for run in pending):
        raise WarehouseError(
            "production_outcome_unconfirmed", "Bestätige die Gutteile der fertigen Druckläufe vor dem Projektabschluss."
        )
    good_runs = [run for run in pending if run.good_quantity]
    if not good_runs:
        return
    await validate_production_article(db, output.article_id)
    for run in good_runs:
        # The unique run-to-receipt link and the ledger entry are committed
        # together. Independent warehouse actions use their own command keys.
        entry = await post_movement(
            db,
            output.article_id,
            WarehouseMovementCreate(
                entry_kind="receipt",
                location_id=output.location_id,
                quantity=Decimal(run.good_quantity),
                reason=f"Nachproduktion · Projekt #{output.project_id} · Drucklauf #{run.id}",
                idempotency_key=f"project-production-{uuid4().hex}",
            ),
            actor_id=actor_id,
        )
        db.add(ProjectProductionReceipt(ledger_entry_id=entry.id, project_id=output.project_id, run_id=run.id))
