"""Polling endpoint for the in-memory slice-job dispatcher.

POST /library/files/{id}/slice and POST /archives/{id}/slice return a
job_id and a status_url pointing here. The frontend polls this until
status flips to `completed` or `failed`.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import require_ownership_permission, resolve_optional_api_key
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import resolve_row_visibility
from backend.app.models.api_key import APIKey
from backend.app.models.user import User
from backend.app.services.slice_dispatch import slice_dispatch

router = APIRouter(prefix="/slice-jobs", tags=["slice-jobs"])


@router.get("/{job_id}")
async def get_slice_job(
    job_id: int,
    auth_result: tuple[User | None, bool] = Depends(
        require_ownership_permission(
            Permission.LIBRARY_READ_ALL,
            Permission.LIBRARY_READ_OWN,
        )
    ),
    db: AsyncSession = DB_SESSION,
    api_key: APIKey | None = Depends(resolve_optional_api_key),
):
    visibility = await resolve_row_visibility(db, auth_result[0], api_key)
    job = slice_dispatch.get(job_id)
    if job is None or not visibility.can_access_owner(
        job.owner_id, Permission.LIBRARY_READ_ALL, Permission.LIBRARY_READ_OWN
    ):
        raise HTTPException(status_code=404, detail="Slice job not found or expired")
    body: dict = {
        "job_id": job.id,
        "status": job.status,
        "kind": job.kind,
        "source_id": job.source_id,
        "source_name": job.source_name,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        # Live progress fed by the sidecar's --pipe channel. Null when
        # the slicer hasn't emitted yet (early "Initializing" phase) or
        # the sidecar doesn't support progress (older versions).
        "progress": job.progress,
    }
    if job.status == "completed":
        body["result"] = job.result
    elif job.status == "failed":
        body["error_status"] = job.error_status
        body["error_detail"] = job.error_detail
    return body
