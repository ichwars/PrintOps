"""Project deletion with retained warehouse production references."""

from fastapi import HTTPException
from sqlalchemy import column, or_, select, table, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from backend.app.models.commerce import CustomerOrder, OfferAcceptance
from backend.app.models.project import (
    DEFAULT_PROJECT_PRIORITY,
    DEFAULT_PROJECT_STATUS,
    PROJECT_PRIORITIES,
    PROJECT_STATUSES,
    Project,
)
from backend.app.models.stock_reservation import StockReservation
from backend.app.models.warehouse_article import WarehouseArticle


async def delete_project(db: AsyncSession, project_id: int) -> None:
    # Article creation locks this same parent, including when SQLite foreign keys
    # are disabled. Check retained references before changing the project tree.
    await db.execute(update(Project).where(Project.id == project_id).values(id=Project.id))
    project = await db.get(Project, project_id, populate_existing=True)
    if project is None:
        raise HTTPException(404, "Project not found")
    if await db.scalar(select(WarehouseArticle.id).where(WarehouseArticle.project_id == project_id).limit(1)):
        raise HTTPException(409, "Project is referenced by a warehouse article; remove that reference before deletion")
    for reference in (CustomerOrder, OfferAcceptance, StockReservation):
        if await db.scalar(select(reference.id).where(reference.project_id == project_id).limit(1)):
            raise HTTPException(409, "Project is referenced by a customer order or stock reservation")
    # Keep the existing project-tree behavior: children move to the old parent.
    await db.execute(update(Project).where(Project.parent_id == project_id).values(parent_id=project.parent_id))
    await db.delete(project)
    await db.commit()


async def repair_project_choices(conn: AsyncConnection) -> None:
    """Normalize legacy priority and status values without touching timestamps."""
    projects = table("projects", column("priority"), column("status"))
    for field, allowed, fallback in (
        (projects.c.priority, PROJECT_PRIORITIES, DEFAULT_PROJECT_PRIORITY),
        (projects.c.status, PROJECT_STATUSES, DEFAULT_PROJECT_STATUS),
    ):
        await conn.execute(
            update(projects).where(or_(field.is_(None), field.not_in(allowed))).values({field: fallback})
        )
