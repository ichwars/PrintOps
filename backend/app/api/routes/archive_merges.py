"""Preview and merge selected groups of duplicate archives."""

import logging
from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import OwnershipAccess, RequirePermissionIfAuthEnabled
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.websocket import ws_manager
from backend.app.models.user import User
from backend.app.services.archive_merge import count_groups, merge_selected, preview_groups

router = APIRouter()
logger = logging.getLogger(__name__)

ArchiveId = Annotated[int, Field(gt=0)]


class ArchiveMergeGroup(BaseModel):
    survivor_id: ArchiveId
    merged_ids: list[ArchiveId] = Field(min_length=1)


class ArchiveMergeRequest(BaseModel):
    groups: list[ArchiveMergeGroup] = Field(min_length=1, max_length=100)


@router.get("/merge-count")
async def count_archive_merge_groups(
    db: AsyncSession = DB_SESSION,
    user: User | None = RequirePermissionIfAuthEnabled(
        Permission.ARCHIVES_READ_ALL, Permission.ARCHIVES_UPDATE_ALL, Permission.ARCHIVES_DELETE_ALL
    ),
):
    return {"groups": await count_groups(db, OwnershipAccess(user, True))}


@router.get("/merge-preview")
async def preview_archive_merge(
    db: AsyncSession = DB_SESSION,
    user: User | None = RequirePermissionIfAuthEnabled(
        Permission.ARCHIVES_READ_ALL, Permission.ARCHIVES_UPDATE_ALL, Permission.ARCHIVES_DELETE_ALL
    ),
):
    return {"groups": await preview_groups(db, OwnershipAccess(user, True))}


@router.post("/merge")
async def merge_archives(
    body: ArchiveMergeRequest,
    db: AsyncSession = DB_SESSION,
    user: User | None = RequirePermissionIfAuthEnabled(
        Permission.ARCHIVES_READ_ALL, Permission.ARCHIVES_UPDATE_ALL, Permission.ARCHIVES_DELETE_ALL
    ),
):
    result = await merge_selected(db, body.groups, OwnershipAccess(user, True))
    for group in result["merged"]:
        try:
            await ws_manager.send_archive_updated({"id": group["survivor_id"]})
        except Exception:
            logger.warning("Could not broadcast merged archive %s", group["survivor_id"], exc_info=True)
    return result
