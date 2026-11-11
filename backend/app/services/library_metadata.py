"""Folder metadata edits stay within internal storage boundaries."""

from fastapi import HTTPException
from sqlalchemy import select

from backend.app.models.library import LibraryFolder


async def metadata_folder_id(db, file, folder_id):
    target = None
    if folder_id != 0:
        target = (await db.execute(select(LibraryFolder).where(LibraryFolder.id == folder_id))).scalar_one_or_none()
        if target is None:
            raise HTTPException(status_code=404, detail="Folder not found")
    target_id = target.id if target is not None else None
    if target_id != file.folder_id and (file.is_external or (target is not None and target.is_external)):
        raise HTTPException(status_code=400, detail="Use POST /api/v1/library/files/move for external folders")
    return target_id
