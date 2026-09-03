"""Project deletion with retained warehouse production references."""

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.project import Project
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
    # Keep the existing project-tree behavior: children move to the old parent.
    await db.execute(update(Project).where(Project.parent_id == project_id).values(parent_id=project.parent_id))
    await db.delete(project)
    await db.commit()
