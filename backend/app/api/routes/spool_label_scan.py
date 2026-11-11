"""Resolve spool labels without navigating to or requesting their URLs."""

import re
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.routes.settings import get_setting
from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.models.user import User

router = APIRouter()
InventorySource = Literal["inventory", "spoolman"]


class ScannedLabel(BaseModel):
    payload: str = Field(min_length=1, max_length=2048)


class ResolvedSpoolLabel(BaseModel):
    spool_id: int
    source: InventorySource


def _positive_id(value: str) -> int | None:
    if not re.fullmatch(r"[0-9]{1,10}", value):
        return None
    spool_id = int(value)
    return spool_id if 0 < spool_id <= 2**31 - 1 else None


def _origin_and_path(value: str) -> tuple[tuple[str, str, int] | None, str, str] | None:
    try:
        parsed = urlsplit(value)
        if parsed.fragment or parsed.username is not None or parsed.password is not None:
            return None
        if not parsed.scheme and not parsed.netloc and parsed.path.startswith("/"):
            return None, parsed.path, parsed.query
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return (parsed.scheme, parsed.hostname, port), parsed.path.rstrip("/"), parsed.query
    except ValueError:
        return None


def _spool_label(
    payload: str, request_url: str, external_url: str, spoolman_url: str, source: InventorySource
) -> tuple[int, InventorySource] | None:
    if source == "spoolman" and (tag := re.fullmatch(r"web\+spoolman:s-([0-9]{1,10})", payload, re.IGNORECASE)):
        spool_id = _positive_id(tag[1])
        return (spool_id, "spoolman") if spool_id else None
    parsed = _origin_and_path(payload)
    if parsed is None:
        return None
    origin, path, query = parsed
    printops_locations = {(None, "/inventory")}
    if current := _origin_and_path(request_url):
        printops_locations.add((current[0], "/inventory"))
    if external := _origin_and_path(external_url):
        printops_locations.add((external[0], f"{external[1]}/inventory"))
    if (origin, path) in printops_locations:
        params = parse_qs(query, keep_blank_values=True)
        spool_ids = params.get("spool", [])
        sources = params.get("source", [source])
        if len(spool_ids) == 1 and sources == [source] and (spool_id := _positive_id(spool_ids[0])):
            return spool_id, source

    if source == "spoolman" and (remote := _origin_and_path(spoolman_url)) and remote[0] == origin:
        match = re.fullmatch(re.escape(remote[1]) + r"/spool/show/([0-9]{1,10})", path)
        if match and not query and (spool_id := _positive_id(match[1])):
            return spool_id, "spoolman"
    return None


@router.post("/inventory/labels/resolve-spool", response_model=ResolvedSpoolLabel)
async def resolve_spool_label(
    body: ScannedLabel,
    request: Request,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    source: InventorySource = (
        "spoolman" if (await get_setting(db, "spoolman_enabled") or "").lower() == "true" else "inventory"
    )
    external_url = (await get_setting(db, "external_url") or "").strip()
    spoolman_url = (await get_setting(db, "spoolman_url") or "").strip() if source == "spoolman" else ""
    label = _spool_label(body.payload.strip(), str(request.url), external_url, spoolman_url, source)
    if label is None:
        raise HTTPException(422, "This is not a spool label for the active inventory")
    spool_id, label_source = label
    return ResolvedSpoolLabel(spool_id=spool_id, source=label_source)
