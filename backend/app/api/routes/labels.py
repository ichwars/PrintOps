"""Spool label printing routes (#809).

Two endpoints, one per inventory backend:

- ``POST /inventory/labels``  — local-DB spools
- ``POST /spoolman/labels``   — Spoolman-backed spools

Both accept ``{spool_ids: [int], template: str}`` and return a PDF stream.
The QR code on each label deep-links to ``/inventory?spool=<id>`` so a phone
scan jumps straight back into PrintOps at that spool's row.
"""

from __future__ import annotations

import asyncio
import io
import logging
import zipfile
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.routes import label_templates, spool_label_scan
from backend.app.api.routes._spoolman_helpers import _map_spoolman_spool
from backend.app.api.routes.settings import get_setting
from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.models.small_part import SmallPart
from backend.app.models.spool import Spool
from backend.app.models.user import User
from backend.app.schemas.label_template import SheetLayoutSpec
from backend.app.services.filament_sku_identity import resolve_material_numbers
from backend.app.services.label_renderer import (
    DEFAULT_LABEL_FIELDS,
    LabelData,
    LabelField,
    LabelLayout,
    TemplateName,
    get_sheet_capacity,
    pdf_to_pngs,
    render_label_preview_pdf,
    render_labels,
    validate_start_position,
)
from backend.app.services.spoolman import get_spoolman_client
from backend.app.utils.http import build_content_disposition

logger = logging.getLogger(__name__)

router = APIRouter(tags=["labels"])

router.include_router(label_templates.router)
router.include_router(spool_label_scan.router)

# Cap how many labels can be requested in one go. Sane upper bound for the
# largest realistic batch (an Avery sheet at 30/page × ~10 pages).
MAX_LABELS_PER_REQUEST = 500
MAX_PNG_SHEET_PAGES_X_DPI = 15_000


class LabelRenderOptions(BaseModel):
    template: TemplateName | Literal["custom"]
    layout: SheetLayoutSpec | None = None
    # Black-and-white thermal printers: drop the colour swatch (prints as a
    # muddy grey block) and widen the text column instead (#1870).
    monochrome: bool = False
    fields: list[LabelField] | None = Field(default=None, max_length=12)
    format: Literal["pdf", "png"] = "pdf"
    dpi: Literal[203, 300, 600] = 300
    start_position: int = Field(default=1, ge=1, strict=True)

    @model_validator(mode="after")
    def valid_sheet_position(self):
        if (self.template == "custom") != (self.layout is not None):
            raise ValueError("A layout is required only for a custom sheet")
        validate_start_position(self.resolved_layout(), self.start_position)
        return self

    def resolved_layout(self) -> LabelLayout:
        if self.layout is not None:
            return self.layout.to_layout()
        return self.template


class LabelRequest(LabelRenderOptions):
    spool_ids: list[int] = Field(..., min_length=1, max_length=MAX_LABELS_PER_REQUEST)


class SmallPartLabelRequest(LabelRenderOptions):
    small_part_ids: list[int] = Field(..., min_length=1, max_length=MAX_LABELS_PER_REQUEST)


def _split_extra_colors(raw: str | None) -> list[str] | None:
    """Parse ``Spool.extra_colors`` (comma-separated hex tokens) into a list."""
    if not raw:
        return None
    parts = [p.strip().lstrip("#") for p in raw.split(",") if p.strip()]
    return parts or None


async def _resolve_deeplink_base(request: Request, db: AsyncSession) -> str:
    """Where the QR codes should point. Prefers `external_url` when set so a
    phone scan reaches the user's public PrintOps URL rather than an internal
    address; falls back to the request's own scheme+host when no setting is
    configured.
    """
    external = (await get_setting(db, "external_url") or "").strip().rstrip("/")
    if external:
        return external
    return f"{request.url.scheme}://{request.url.netloc}"


def _spool_to_label_data(spool: Spool, deeplink_base: str, *, material_number: str | None = None) -> LabelData:
    name = spool.color_name or spool.slicer_filament_name or f"{spool.brand or ''} {spool.material}".strip()
    return LabelData(
        spool_id=spool.id,
        name=name or spool.material,
        material=spool.material,
        brand=spool.brand,
        subtype=spool.subtype,
        rgba=spool.rgba,
        extra_colors=_split_extra_colors(spool.extra_colors),
        storage_location=getattr(spool, "storage_location", None),
        deeplink_url=f"{deeplink_base}/inventory?spool={spool.id}&source=inventory",
        material_number=material_number,
        nozzle_temp_min=spool.nozzle_temp_min,
        nozzle_temp_max=spool.nozzle_temp_max,
        label_weight=spool.label_weight,
        note=spool.note,
        added=spool.created_at.date() if spool.created_at else None,
    )


def _spoolman_dict_to_label_data(s: dict, deeplink_base: str, *, material_number: str | None = None) -> LabelData:
    """Reuse the same native Spoolman values and identity as the inventory."""
    mapped = _map_spoolman_spool(s)
    multi_colors = (s.get("filament") or {}).get("multi_color_hexes")
    extra_colors = _split_extra_colors(multi_colors) if isinstance(multi_colors, str) else None
    if isinstance(multi_colors, list):
        extra_colors = [str(color).strip().lstrip("#") for color in multi_colors if str(color).strip()] or None
    added = None
    registered = mapped.get("created_at")
    if isinstance(registered, str):
        try:
            added = datetime.fromisoformat(registered).date()
        except ValueError:
            pass
    return LabelData(
        spool_id=mapped["id"],
        name=mapped.get("slicer_filament_name") or mapped["material"] or "Spool",
        material=mapped["material"],
        brand=mapped["brand"],
        subtype=mapped["subtype"],
        rgba=mapped["rgba"],
        extra_colors=extra_colors,
        storage_location=mapped.get("storage_location"),
        deeplink_url=f"{deeplink_base}/inventory?spool={mapped['id']}&source=spoolman",
        material_number=material_number,
        label_weight=mapped["label_weight"],
        note=mapped.get("note"),
        nozzle_temp_min=mapped.get("nozzle_temp_min"),
        nozzle_temp_max=mapped.get("nozzle_temp_max"),
        added=added,
    )


def _small_part_to_label_data(part: SmallPart, deeplink_base: str) -> LabelData:
    category = part.category.name if part.category else "Material"
    storage_location = getattr(part.location, "name", None)
    return LabelData(
        spool_id=part.id,
        name=part.name,
        material=category,
        brand=part.sku,
        subtype=part.unit.label if part.unit else part.unit_code,
        rgba=None,
        extra_colors=None,
        storage_location=storage_location,
        deeplink_url=f"{deeplink_base}/warehouse/parts?part={part.id}",
        material_number=part.sku,
    )


def _stream_pdf(pdf: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={
            "Content-Disposition": build_content_disposition(filename, disposition="inline"),
            "Content-Length": str(len(pdf)),
            # PDFs are deterministic per request; tell the browser not to cache
            # so re-printing after edits picks up the new data.
            "Cache-Control": "no-store",
        },
    )


def _validate_png_sheet_size(body: LabelRenderOptions, label_count: int, request: Request) -> None:
    if body.format != "png" or request.url.path.endswith("/preview"):
        return
    capacity = get_sheet_capacity(body.resolved_layout())
    if capacity is None:
        return
    pages = (label_count + body.start_position + capacity - 2) // capacity
    limit = MAX_PNG_SHEET_PAGES_X_DPI // body.dpi
    if pages > limit:
        raise HTTPException(422, f"PNG export allows up to {limit} sheet pages at {body.dpi} dpi")


async def _label_response(
    body: LabelRenderOptions, data_list: list[LabelData], request: Request, prefix: str
) -> StreamingResponse:
    fields = DEFAULT_LABEL_FIELDS if body.fields is None else frozenset(body.fields)
    preview = request.url.path.endswith("/preview")
    layout = body.resolved_layout()

    def render():
        if preview:
            pdf = render_label_preview_pdf(layout, data_list[0], monochrome=body.monochrome, fields=fields)
            return pdf_to_pngs(pdf, body.dpi)[0], "image/png", f"{prefix}-preview.png"
        pdf = render_labels(
            layout, data_list, monochrome=body.monochrome, start_position=body.start_position, fields=fields
        )
        if body.format == "pdf":
            return pdf, "application/pdf", f"{prefix}-{body.template}.pdf"
        pngs = pdf_to_pngs(pdf, body.dpi)
        if len(pngs) == 1:
            return pngs[0], "image/png", f"{prefix}-{body.template}.png"
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            for index, png in enumerate(pngs, 1):
                archive.writestr(f"label-{index}.png", png)
        return output.getvalue(), "application/zip", f"{prefix}-{body.template}.zip"

    try:
        payload, media_type, filename = await asyncio.to_thread(render)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=media_type,
        headers={
            "Content-Disposition": build_content_disposition(
                filename, disposition="inline" if media_type == "application/pdf" else "attachment"
            ),
            "Content-Length": str(len(payload)),
            "Cache-Control": "no-store",
        },
    )


@router.post("/inventory/labels/preview")
@router.post("/inventory/labels")
async def render_local_inventory_labels(
    body: LabelRequest,
    request: Request,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> StreamingResponse:
    """Render labels for spools in the local inventory."""
    _validate_png_sheet_size(body, len(set(body.spool_ids)), request)
    result = await db.execute(select(Spool).where(Spool.id.in_(body.spool_ids)))
    spools = list(result.scalars().all())

    found_ids = {s.id for s in spools}
    missing = [sid for sid in body.spool_ids if sid not in found_ids]
    if missing:
        raise HTTPException(404, f"Spool(s) not found: {missing}")

    # Preserve caller's order so an Avery sheet print matches the on-screen list.
    ordered = sorted(spools, key=lambda s: body.spool_ids.index(s.id))

    deeplink_base = await _resolve_deeplink_base(request, db)
    material_numbers = await resolve_material_numbers(db, ordered)
    data_list = [_spool_to_label_data(s, deeplink_base, material_number=material_numbers[s.id]) for s in ordered]

    return await _label_response(body, data_list, request, "printops-labels")


@router.post("/small-parts/labels/preview")
@router.post("/small-parts/labels")
async def render_small_part_labels(
    body: SmallPartLabelRequest,
    request: Request,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> StreamingResponse:
    """Render labels for stocked material in the small-parts warehouse."""
    _validate_png_sheet_size(body, len(set(body.small_part_ids)), request)
    result = await db.execute(
        select(SmallPart)
        .where(SmallPart.id.in_(body.small_part_ids))
        .options(selectinload(SmallPart.category), selectinload(SmallPart.unit), selectinload(SmallPart.location))
    )
    parts = list(result.scalars().all())

    found_ids = {part.id for part in parts}
    missing = [part_id for part_id in body.small_part_ids if part_id not in found_ids]
    if missing:
        raise HTTPException(404, f"Material(s) not found: {missing}")

    ordered = sorted(parts, key=lambda part: body.small_part_ids.index(part.id))

    deeplink_base = await _resolve_deeplink_base(request, db)
    data_list = [_small_part_to_label_data(part, deeplink_base) for part in ordered]

    return await _label_response(body, data_list, request, "printops-material-labels")


@router.post("/spoolman/labels/preview")
@router.post("/spoolman/labels")
async def render_spoolman_labels(
    body: LabelRequest,
    request: Request,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> StreamingResponse:
    """Render labels for spools tracked in Spoolman.

    Fetch active and archived spools once, then select the requested IDs.
    This avoids one remote request per label and supports archived selections.
    """
    _validate_png_sheet_size(body, len(body.spool_ids), request)
    spoolman_on = (await get_setting(db, "spoolman_enabled") or "").lower() == "true"
    if not spoolman_on:
        raise HTTPException(400, "Spoolman integration is not enabled")

    client = await get_spoolman_client()
    if client is None or not client.is_connected:
        raise HTTPException(503, "Spoolman not reachable")

    try:
        all_spools = await client.get_all_spools(allow_archived=True)
    except Exception as exc:
        logger.warning("Spoolman fetch failed during label render: %s", exc)
        raise HTTPException(502, "Failed to fetch spools from Spoolman") from exc

    by_id = {int(s.get("id", 0)): s for s in all_spools if s.get("id") is not None}
    missing = [sid for sid in body.spool_ids if sid not in by_id]
    if missing:
        raise HTTPException(404, f"Spool(s) not found in Spoolman: {missing}")

    deeplink_base = await _resolve_deeplink_base(request, db)
    material_numbers = await resolve_material_numbers(db, [_map_spoolman_spool(by_id[sid]) for sid in body.spool_ids])
    data_list = [
        _spoolman_dict_to_label_data(by_id[sid], deeplink_base, material_number=material_numbers[sid])
        for sid in body.spool_ids
    ]

    return await _label_response(body, data_list, request, "printops-labels-spoolman")
