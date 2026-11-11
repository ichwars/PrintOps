"""Shared label sheet templates for inventory and material labels."""

import re

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import DB_SESSION
from backend.app.core.permissions import Permission
from backend.app.models.label_template import LabelTemplate
from backend.app.models.user import User
from backend.app.schemas.label_template import LabelTemplateResponse, LabelTemplateWrite

router = APIRouter(prefix="/label-templates", tags=["labels"])


@router.get("/", response_model=list[LabelTemplateResponse])
async def list_label_templates(
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    rows = list(await db.scalars(select(LabelTemplate)))

    def natural_name(row):
        return [int(part) if index % 2 else part for index, part in enumerate(re.split(r"(\d+)", row.name_key))]

    return sorted(rows, key=natural_name)


async def _save(db: AsyncSession, row: LabelTemplate, body: LabelTemplateWrite):
    row.name = body.name
    row.name_key = body.name.casefold()
    row.layout = body.layout.model_dump()
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "A label template with that name already exists") from exc
    await db.refresh(row)
    return row


@router.post("/", response_model=LabelTemplateResponse, status_code=201)
async def create_label_template(
    body: LabelTemplateWrite,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    row = LabelTemplate()
    db.add(row)
    return await _save(db, row, body)


@router.put("/{template_id}", response_model=LabelTemplateResponse)
async def update_label_template(
    template_id: int,
    body: LabelTemplateWrite,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    row = await db.get(LabelTemplate, template_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Label template not found")
    return await _save(db, row, body)


@router.delete("/{template_id}")
async def delete_label_template(
    template_id: int,
    db: AsyncSession = DB_SESSION,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    row = await db.get(LabelTemplate, template_id, with_for_update=True)
    if row is None:
        raise HTTPException(404, "Label template not found")
    await db.delete(row)
    await db.commit()
    return {"status": "deleted"}
