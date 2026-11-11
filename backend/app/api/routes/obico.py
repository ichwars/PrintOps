"""API routes for Obico AI failure detection."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import OwnershipAccess, RequirePermissionIfAuthEnabled, require_permission_with_key
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.core.row_visibility import resolve_row_visibility
from backend.app.models.user import User
from backend.app.services.obico_detection import obico_detection_service, pop_frame
from backend.app.services.secret_fields import SECRET_PLACEHOLDER, secret_is_set

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/obico", tags=["obico"])


class TestConnectionRequest(BaseModel):
    url: str | None = None
    token: str | None = None


@router.get("/status")
async def get_status(
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SETTINGS_READ),
):
    """Scheduler status, per-printer classification, and recent detection history."""
    settings = await obico_detection_service._load_settings()
    status = obico_detection_service.get_status(settings["sensitivity"])
    return {
        **status,
        "enabled": settings["enabled"],
        "ml_url": settings["ml_url"],
        "sensitivity": settings["sensitivity"],
        "action": settings["action"],
        "poll_interval": settings["poll_interval"],
        "external_url_configured": bool(settings["external_url"]),
    }


@router.get("/printer-status")
async def get_printer_status(
    db: AsyncSession = DB_SESSION,
    access: OwnershipAccess = Depends(require_permission_with_key(Permission.PRINTERS_READ)),
):
    """Return live card states without exposing Obico configuration."""
    settings = await obico_detection_service._load_settings()
    enabled_printers = settings["enabled_printers"]
    visibility = await resolve_row_visibility(db, access.user, access.api_key)
    scope = visibility.printer_ids
    can_see_error = visibility.has_permission(Permission.SETTINGS_READ)
    per_printer = obico_detection_service.get_per_printer()
    if scope is not None:
        per_printer = {printer_id: entry for printer_id, entry in per_printer.items() if printer_id in scope}
        enabled_printers = scope if enabled_printers is None else scope.intersection(enabled_printers)
    if not can_see_error:
        per_printer = {printer_id: {**entry, "error": None} for printer_id, entry in per_printer.items()}
    return {
        "enabled": settings["enabled"],
        "monitored_printers": sorted(enabled_printers) if enabled_printers is not None else None,
        "per_printer": per_printer,
        "last_error": obico_detection_service._last_error if can_see_error and scope is None else None,
    }


@router.post("/test-connection")
async def test_connection(
    req: TestConnectionRequest,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SETTINGS_UPDATE),
):
    """Ping an explicit configuration, or the saved one when values are omitted."""
    url = req.url
    token = req.token
    if url is None or token is None or token == SECRET_PLACEHOLDER:
        settings = await obico_detection_service._load_settings()
        saved_url = settings.get("ml_url") or ""
        saved_token = settings.get("ml_token") or ""
        if url is None:
            url = saved_url
        if token is None or token == SECRET_PLACEHOLDER:
            if token == SECRET_PLACEHOLDER and not secret_is_set(saved_token):
                raise HTTPException(400, "Enter the token because none is saved")
            if secret_is_set(saved_token) and url.rstrip("/") != saved_url.rstrip("/"):
                raise HTTPException(400, "Enter the token again because the URL changed")
            token = saved_token if secret_is_set(saved_token) else ""
    if not url:
        return {"ok": False, "status_code": None, "body": None, "error": "URL is empty", "auth_ok": None}
    return await obico_detection_service.test_connection(url, token)


@router.get("/cached-frame/{nonce}")
async def cached_frame(nonce: str):
    """Serve a pre-captured JPEG to the Obico ML API.

    The detection loop captures a snapshot locally (where we control the timeout),
    stashes the bytes under a one-shot random nonce, then hands this URL to Obico's
    ML API. Obico's hardcoded 5s read timeout never races our snapshot pipeline.

    Unauthenticated: the unguessable 32-byte nonce is single-use and expires in
    seconds, so exposing this path doesn't widen the camera access surface.
    """
    data = await pop_frame(nonce)
    if data is None:
        raise HTTPException(status_code=404, detail="Frame not found or expired")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )
