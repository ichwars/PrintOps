"""Validate reparenting while concurrent writers cannot alter the folder tree."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.library import LibraryFolder

_sqlite_folder_move_lock = asyncio.Lock()


@asynccontextmanager
async def lock_folder_tree_for_move(db: AsyncSession, folder_id: int, *, reparenting: bool):
    if not reparenting:
        yield
        return
    if db.get_bind().dialect.name == "postgresql":
        await db.execute(text("LOCK TABLE library_folders IN SHARE ROW EXCLUSIVE MODE"))
        yield
        return

    # The application lock also covers deployments using a shared SQLite
    # connection. The write lock covers separate connections and processes.
    async with _sqlite_folder_move_lock:
        await db.execute(
            text("UPDATE library_folders SET parent_id = parent_id WHERE id = :folder_id"), {"folder_id": folder_id}
        )
        try:
            yield
        except BaseException:
            await db.rollback()
            raise


async def validate_folder_move(db: AsyncSession, folder: LibraryFolder, parent_id: int | None) -> None:
    if folder.parent_id == parent_id:
        return
    if folder.is_external:
        raise HTTPException(400, "External folders cannot be moved")
    if parent_id is None:
        return

    branch = (
        select(LibraryFolder.id, LibraryFolder.parent_id, LibraryFolder.is_external)
        .where(LibraryFolder.id == parent_id)
        .cte(recursive=True)
    )
    # UNION is intentional: a pre-existing cycle must not hang the query.
    branch = branch.union(
        select(LibraryFolder.id, LibraryFolder.parent_id, LibraryFolder.is_external).join(
            branch, LibraryFolder.id == branch.c.parent_id
        )
    )
    ancestors = (await db.execute(select(branch))).all()
    if not ancestors:
        raise HTTPException(404, "Parent folder not found")
    if folder.id == parent_id:
        raise HTTPException(400, "Folder cannot be its own parent")
    if any(row.id == folder.id for row in ancestors):
        raise HTTPException(400, "Cannot move folder into its own subtree")
    if any(row.is_external for row in ancestors):
        raise HTTPException(400, "Cannot move a folder into an external folder")
    if not any(row.parent_id is None for row in ancestors):
        raise HTTPException(409, "Destination folder tree has no root")
