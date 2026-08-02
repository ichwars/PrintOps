from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.core.websocket import ws_manager
from backend.app.models.small_part import SmallPart, SmallPartCategory, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.user import User
from backend.app.schemas.procurement import ProcurementOfferRead, SupplierRead
from backend.app.schemas.small_part import (
    SmallPartCategoryCreate,
    SmallPartCategoryRead,
    SmallPartCategoryUpdate,
    SmallPartCreate,
    SmallPartLedgerCreate,
    SmallPartLedgerRead,
    SmallPartListResponse,
    SmallPartOptionRead,
    SmallPartRead,
    SmallPartUnitCreate,
    SmallPartUnitRead,
    SmallPartUnitUpdate,
    SmallPartUpdate,
)
from backend.app.services import (
    procurement as procurement_service,
    small_parts as service,
    warehouse_number_sequence as warehouse_number_sequence_service,
)

router = APIRouter(prefix="/small-parts", tags=["small-parts"])

_MAX_GENERATED_SKU_ATTEMPTS = 1000
_MAX_CSV_IMPORT_BYTES = 2 * 1024 * 1024

_CSV_HEADERS = [
    "Artikelnummer",
    "Bezeichnung",
    "Kategorie",
    "Kategorie-ID",
    "Lagerort-ID",
    "Einheit",
    "Physisch",
    "Mindestbestand",
    "Einzelpreis",
    "Lieferant",
    "Beschreibung",
    "Suchbegriffe",
    "Standardgrund",
    "Aktiv",
]

_HEADER_ALIASES = {
    "artikelnummer": "sku",
    "sku": "sku",
    "bezeichnung": "name",
    "name": "name",
    "beschreibung": "description",
    "description": "description",
    "suchbegriffe": "search_terms",
    "search_terms": "search_terms",
    "kategorie": "category",
    "category": "category",
    "kategorie-id": "category_id",
    "kategorie_id": "category_id",
    "category_id": "category_id",
    "lagerort-id": "location_id",
    "lagerort_id": "location_id",
    "location_id": "location_id",
    "einheit": "unit_code",
    "unit": "unit_code",
    "unit_code": "unit_code",
    "physisch": "opening_quantity",
    "bestand": "opening_quantity",
    "opening_quantity": "opening_quantity",
    "mindestbestand": "minimum_stock",
    "minimum_stock": "minimum_stock",
    "einzelpreis": "unit_cost",
    "unit_cost": "unit_cost",
    "lieferant": "supplier_reference",
    "supplier_reference": "supplier_reference",
    "standardgrund": "default_consumption_reason",
    "default_consumption_reason": "default_consumption_reason",
    "aktiv": "is_active",
    "is_active": "is_active",
}


async def _load_part(db: AsyncSession, small_part_id: int) -> SmallPart:
    part = await db.scalar(
        select(SmallPart)
        .where(SmallPart.id == small_part_id)
        .options(selectinload(SmallPart.category), selectinload(SmallPart.unit), selectinload(SmallPart.location))
    )
    if part is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": "Material fehlt"})
    return part


def _offer_read(result: procurement_service.ProcurementOfferResult) -> ProcurementOfferRead:
    offer = result.offer
    return ProcurementOfferRead(
        **{column.name: getattr(offer, column.name) for column in offer.__table__.columns},
        supplier=SupplierRead.model_validate(result.supplier),
    )


async def _read_part(
    db: AsyncSession,
    part: SmallPart,
    preferred_offer: procurement_service.ProcurementOfferResult | None,
) -> SmallPartRead:
    balance = await service.get_balance(db, part.id)
    return SmallPartRead.model_validate(
        {
            "id": part.id,
            "sku": part.sku,
            "name": part.name,
            "description": part.description,
            "search_terms": part.search_terms,
            "category_id": part.category_id,
            "unit_code": part.unit_code,
            "location_id": part.location_id,
            "minimum_stock": part.minimum_stock,
            "unit_cost": part.unit_cost,
            "supplier_reference": part.supplier_reference,
            "default_consumption_reason": part.default_consumption_reason,
            "internal_notes": part.internal_notes,
            "is_active": part.is_active,
            "preferred_offer": _offer_read(preferred_offer) if preferred_offer is not None else None,
            "category": part.category,
            "unit": part.unit,
            "balance": {
                "physical": balance.physical,
                "reserved": balance.reserved,
                "available": balance.available,
                "is_low_stock": balance.available <= part.minimum_stock,
            },
            "created_at": part.created_at,
            "updated_at": part.updated_at,
        }
    )


async def _read_single_part(db: AsyncSession, part: SmallPart) -> SmallPartRead:
    preferred_offers = await procurement_service.preferred_offers_for_materials(db, [part.id])
    return await _read_part(db, part, preferred_offers.get(part.id))


def _conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail={"code": "conflict", "message": message})


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    stripped = text.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def _decimal_csv(value: Decimal | str | int | float | None, places: int | None = None) -> str:
    if value is None:
        number = Decimal("0")
    elif isinstance(value, Decimal):
        number = value
    else:
        number = Decimal(str(value))
    if places is not None:
        number = number.quantize(Decimal(1).scaleb(-places))
    return str(number)


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _parse_decimal(value: str | None, *, default: Decimal | None = None) -> Decimal | None:
    raw = (value or "").strip()
    if not raw:
        return default
    cleaned = (
        raw.replace("\ufeff", "")
        .replace("€", "")
        .replace("netto", "")
        .replace("Stück", "")
        .replace("Stk.", "")
        .replace("stk.", "")
        .replace("pcs", "")
        .strip()
    )
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Ungültige Zahl: {raw}") from None


def _parse_int(value: str | None) -> int | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        number = int(raw)
    except ValueError:
        raise ValueError(f"Ungültige ID: {raw}") from None
    return number if number > 0 else None


def _parse_bool(value: str | None, *, default: bool = True) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "ja", "yes", "y", "aktiv", "active"}:
        return True
    if raw in {"0", "false", "nein", "no", "n", "inaktiv", "inactive"}:
        return False
    raise ValueError(f"Ungültiger Aktiv-Wert: {value}")


def _read_csv_rows(raw: bytes) -> list[dict[str, str]]:
    text = raw.decode("utf-8-sig")
    sample = text[:4096]
    delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV enthält keine Kopfzeile")
    rows: list[dict[str, str]] = []
    for row in reader:
        normalized: dict[str, str] = {}
        for key, value in row.items():
            if key is None:
                continue
            alias = _HEADER_ALIASES.get(_normalize_header(key))
            if alias:
                normalized[alias] = (value or "").strip()
        if any(value.strip() for value in normalized.values()):
            rows.append(normalized)
    return rows


async def _read_csv_upload(file: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_CSV_IMPORT_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={"code": "csv_import_too_large", "message": "CSV-Datei ist zu groß"},
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _small_part_import_context(db: AsyncSession):
    categories = list(await db.scalars(select(SmallPartCategory)))
    units = list(await db.scalars(select(SmallPartUnit)))
    existing = list(await db.scalars(select(SmallPart)))
    return {
        "categories_by_name": {category.name.strip().casefold(): category for category in categories},
        "categories_by_id": {category.id: category for category in categories},
        "units_by_code": {unit.code.upper(): unit for unit in units},
        "units_by_label": {unit.label.strip().casefold(): unit for unit in units},
        "existing_by_sku": {part.sku.strip().casefold(): part for part in existing},
        "default_unit": next((unit for unit in units if unit.code == "C62"), units[0] if units else None),
    }


def _small_part_payload_from_csv(row: dict[str, str], context: dict) -> tuple[dict, Decimal, bool, list[str]]:
    warnings: list[str] = []
    sku = row.get("sku", "").strip()
    name = row.get("name", "").strip()
    if not name:
        raise ValueError("Bezeichnung fehlt")

    raw_unit = row.get("unit_code", "").strip()
    unit = None
    if raw_unit:
        unit = context["units_by_code"].get(raw_unit.upper()) or context["units_by_label"].get(raw_unit.casefold())
    if unit is None:
        unit = context["default_unit"]
    if unit is None:
        raise ValueError("Keine Materialeinheit vorhanden")

    category_id = _parse_int(row.get("category_id"))
    category_name = row.get("category", "").strip()
    if category_id is None and category_name:
        category = context["categories_by_name"].get(category_name.casefold())
        if category is not None:
            category_id = category.id
        else:
            warnings.append(f"Kategorie nicht gefunden: {category_name}")
    elif category_id is not None and category_id not in context["categories_by_id"]:
        raise ValueError(f"Kategorie-ID nicht gefunden: {category_id}")

    minimum_stock = _parse_decimal(row.get("minimum_stock"), default=Decimal("0"))
    unit_cost = _parse_decimal(row.get("unit_cost"), default=Decimal("0"))
    opening_quantity = _parse_decimal(row.get("opening_quantity"), default=Decimal("0"))
    if minimum_stock is None or minimum_stock < 0:
        raise ValueError("Mindestbestand darf nicht negativ sein")
    if unit_cost is None or unit_cost < 0:
        raise ValueError("Einzelpreis darf nicht negativ sein")
    if opening_quantity is None or opening_quantity < 0:
        raise ValueError("Anfangsbestand darf nicht negativ sein")

    payload = {
        "sku": sku,
        "name": name,
        "description": row.get("description") or None,
        "search_terms": row.get("search_terms") or None,
        "category_id": category_id,
        "unit_code": unit.code,
        "location_id": _parse_int(row.get("location_id")),
        "minimum_stock": minimum_stock,
        "unit_cost": unit_cost,
        "supplier_reference": row.get("supplier_reference") or None,
        "default_consumption_reason": row.get("default_consumption_reason") or "Produktion",
        "is_active": _parse_bool(row.get("is_active"), default=True),
    }
    return payload, opening_quantity, "opening_quantity" in row, warnings


async def _small_part_csv_operations(db: AsyncSession, raw: bytes) -> tuple[dict, list[dict]]:
    rows = _read_csv_rows(raw)
    context = await _small_part_import_context(db)
    preview_rows = []
    operations: list[dict] = []
    valid = errors = skipped = 0
    warnings: list[str] = []
    seen_skus: set[str] = set()
    for index, row in enumerate(rows, start=2):
        try:
            payload, stock_quantity, stock_quantity_provided, row_warnings = _small_part_payload_from_csv(row, context)
            sku_key = payload["sku"].strip().casefold()
            action = "update" if sku_key and sku_key in context["existing_by_sku"] else "create"
            existing = context["existing_by_sku"].get(sku_key) if action == "update" else None
            if sku_key and sku_key in seen_skus:
                raise ValueError("Artikelnummer kommt mehrfach in der CSV vor")
            if sku_key:
                seen_skus.add(sku_key)

            if action == "update":
                model = SmallPartUpdate(**payload)
            else:
                model = SmallPartCreate(**payload, opening_quantity=stock_quantity)

            valid += 1
            warnings.extend(row_warnings)
            preview_rows.append(
                {
                    "row_number": index,
                    "status": "valid",
                    "action": action,
                    "sku": payload["sku"],
                    "name": payload["name"],
                    "unit_code": payload["unit_code"],
                    "opening_quantity": _decimal_csv(stock_quantity),
                    "reason": None,
                    "warnings": row_warnings,
                }
            )
            operations.append(
                {
                    "row_number": index,
                    "action": action,
                    "model": model,
                    "payload": payload,
                    "existing": existing,
                    "stock_quantity": stock_quantity,
                    "stock_quantity_provided": stock_quantity_provided,
                }
            )
        except (ValueError, ValidationError) as exc:
            errors += 1
            preview_rows.append(
                {
                    "row_number": index,
                    "status": "error",
                    "action": None,
                    "sku": row.get("sku", ""),
                    "name": row.get("name", ""),
                    "unit_code": row.get("unit_code", ""),
                    "opening_quantity": row.get("opening_quantity", ""),
                    "reason": str(exc),
                    "warnings": [],
                }
            )
    if not preview_rows:
        skipped += 1
    return {
        "rows": preview_rows,
        "valid_count": valid,
        "error_count": errors,
        "skipped_count": skipped,
        "warnings": warnings,
    }, operations


async def _preview_small_part_csv(db: AsyncSession, raw: bytes) -> dict:
    preview, _ = await _small_part_csv_operations(db, raw)
    return preview


@router.get("/search", response_model=list[SmallPartOptionRead])
async def search_small_part_options(
    q: str = "",
    limit: int = Query(30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> list[SmallPartOptionRead]:
    matches = await service.search_small_parts(db, query=q, active_only=True, limit=limit)
    return [
        SmallPartOptionRead(
            id=item.part.id,
            sku=item.part.sku,
            name=item.part.name,
            unit_code=item.part.unit_code,
            unit_cost=item.part.unit_cost,
            available=item.available,
        )
        for item in matches
    ]


@router.get("/settings/categories", response_model=list[SmallPartCategoryRead])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    return list(await db.scalars(select(SmallPartCategory).order_by(SmallPartCategory.name)))


@router.post("/settings/categories", response_model=SmallPartCategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: SmallPartCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE),
):
    category = SmallPartCategory(name=data.name, name_key=data.name.strip().casefold(), is_active=data.is_active)
    db.add(category)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Kategorie ist bereits vorhanden") from exc
    await db.refresh(category)
    return category


@router.patch("/settings/categories/{category_id}", response_model=SmallPartCategoryRead)
async def update_category(
    category_id: int,
    data: SmallPartCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    category = await db.get(SmallPartCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes:
        category.name_key = changes["name"].strip().casefold()
    for field, value in changes.items():
        setattr(category, field, value)
    await db.commit()
    await db.refresh(category)
    return category


@router.delete("/settings/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_DELETE),
):
    category = await db.get(SmallPartCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")
    if await db.scalar(select(func.count(SmallPart.id)).where(SmallPart.category_id == category_id)):
        raise _conflict("Kategorie wird noch verwendet")
    await db.delete(category)
    await db.commit()


@router.get("/settings/units", response_model=list[SmallPartUnitRead])
async def list_units(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    return list(await db.scalars(select(SmallPartUnit).order_by(SmallPartUnit.label)))


@router.post("/settings/units", response_model=SmallPartUnitRead, status_code=status.HTTP_201_CREATED)
async def create_unit(
    data: SmallPartUnitCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE),
):
    unit = SmallPartUnit(**data.model_dump())
    db.add(unit)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise _conflict("Einheit ist bereits vorhanden") from exc
    await db.refresh(unit)
    return unit


@router.patch("/settings/units/{unit_code}", response_model=SmallPartUnitRead)
async def update_unit(
    unit_code: str,
    data: SmallPartUnitUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
):
    unit = await db.get(SmallPartUnit, unit_code.upper())
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unit not found")
    referenced = await db.scalar(select(func.count(SmallPart.id)).where(SmallPart.unit_code == unit.code))
    changes = data.model_dump(exclude_unset=True)
    if referenced and "decimal_places" in changes and changes["decimal_places"] != unit.decimal_places:
        raise _conflict("Nach Verwendung kann die Genauigkeit nicht mehr geändert werden")
    for field, value in changes.items():
        setattr(unit, field, value)
    await db.commit()
    await db.refresh(unit)
    return unit


@router.delete("/settings/units/{unit_code}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_unit(
    unit_code: str,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_DELETE),
):
    unit = await db.get(SmallPartUnit, unit_code.upper())
    if unit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unit not found")
    if await db.scalar(select(func.count(SmallPart.id)).where(SmallPart.unit_code == unit.code)):
        raise _conflict("Einheit wird noch verwendet")
    await db.delete(unit)
    await db.commit()


@router.get("/export")
async def export_small_parts_csv(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    parts = list(
        (
            await db.scalars(
                select(SmallPart)
                .options(
                    selectinload(SmallPart.category), selectinload(SmallPart.unit), selectinload(SmallPart.location)
                )
                .order_by(SmallPart.is_active.desc(), func.lower(SmallPart.name), SmallPart.id)
            )
        ).unique()
    )
    preferred_offers = await procurement_service.preferred_offers_for_materials(db, [part.id for part in parts])
    reads = [await _read_part(db, part, preferred_offers.get(part.id)) for part in parts]

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(_CSV_HEADERS)
    for part in reads:
        writer.writerow(
            [
                _csv_cell(part.sku),
                _csv_cell(part.name),
                _csv_cell(part.category.name if part.category else ""),
                _csv_cell(part.category_id),
                _csv_cell(part.location_id),
                _csv_cell(part.unit_code),
                _decimal_csv(part.balance.physical, places=part.unit.decimal_places),
                _decimal_csv(part.minimum_stock, places=part.unit.decimal_places),
                _decimal_csv(part.unit_cost, places=2),
                _csv_cell(
                    part.supplier_reference or part.preferred_offer.supplier.name
                    if part.preferred_offer
                    else part.supplier_reference
                ),
                _csv_cell(part.description),
                _csv_cell(part.search_terms),
                _csv_cell(part.default_consumption_reason),
                "ja" if part.is_active else "nein",
            ]
        )
    data = "\ufeff" + output.getvalue()
    filename = f"printops-material-{datetime.now(timezone.utc).date().isoformat()}.csv"
    return StreamingResponse(
        io.BytesIO(data.encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/import")
async def import_small_parts_csv(
    dry_run: bool = False,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE),
):
    raw = await _read_csv_upload(file)
    preview, operations = await _small_part_csv_operations(db, raw)
    if dry_run:
        return preview
    if preview["error_count"]:
        return {
            "created": 0,
            "updated": 0,
            "skipped": preview["skipped_count"],
            "errors": preview["error_count"],
            "error_rows": [row for row in preview["rows"] if row["status"] == "error"],
        }
    if any(operation["action"] == "update" for operation in operations) and user is not None:
        if not user.has_all_permissions(Permission.INVENTORY_UPDATE.value):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permissions: {Permission.INVENTORY_UPDATE.value}",
            )

    created = updated = skipped = errors = 0
    error_rows = []
    import_run_id = uuid4().hex
    current_operation: dict | None = None
    try:
        for current_operation in operations:
            if current_operation["action"] == "update":
                existing = current_operation["existing"]
                await service.update_small_part(db, existing, current_operation["model"])
                if current_operation["stock_quantity_provided"]:
                    balance = await service.get_balance(db, existing.id)
                    delta = Decimal(current_operation["stock_quantity"]) - balance.physical
                    if delta:
                        await service.append_ledger_entry(
                            db,
                            small_part_id=existing.id,
                            entry_kind="correction",
                            physical_delta=delta,
                            reserved_delta=Decimal("0"),
                            reason="CSV-Import",
                            idempotency_key=f"material-csv-import:{import_run_id}:{existing.id}",
                        )
                updated += 1
            else:
                data: SmallPartCreate = current_operation["model"]
                payload = data.model_dump(exclude={"opening_quantity"})
                generate_sku = not payload.get("sku")
                attempts = _MAX_GENERATED_SKU_ATTEMPTS if generate_sku else 1
                part: SmallPart | None = None
                for _ in range(attempts):
                    if generate_sku:
                        payload["sku"] = await warehouse_number_sequence_service.reserve_number(db, key="material")
                        existing_id = await db.scalar(select(SmallPart.id).where(SmallPart.sku == payload["sku"]))
                        if existing_id is not None:
                            continue
                    part = SmallPart(**payload)
                    db.add(part)
                    await db.flush()
                    break
                if part is None:
                    raise _conflict("Keine freie Artikelnummer im Nummernkreis gefunden")
                if data.opening_quantity > 0:
                    await service.append_ledger_entry(
                        db,
                        small_part_id=part.id,
                        entry_kind="opening",
                        physical_delta=data.opening_quantity,
                        reserved_delta=Decimal("0"),
                        reason="Anfangsbestand",
                        idempotency_key=f"material-opening:{part.id}",
                    )
                created += 1
        await db.commit()
    except Exception as exc:
        await db.rollback()
        errors = 1
        created = updated = 0
        operation = current_operation or {}
        payload = operation.get("payload", {})
        error_rows.append(
            {
                "row_number": operation.get("row_number"),
                "reason": str(exc),
                "sku": payload.get("sku", ""),
                "name": payload.get("name", ""),
            }
        )
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors, "error_rows": error_rows}


@router.get("", response_model=SmallPartListResponse)
async def list_small_parts(
    q: str = "",
    active: bool | None = None,
    low_stock: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> SmallPartListResponse:
    matches = await service.search_small_parts(db, query=q, active_only=active is True, limit=10000)
    if active is not None:
        matches = [item for item in matches if item.part.is_active is active]
    preferred_offers = await procurement_service.preferred_offers_for_materials(db, [item.part.id for item in matches])
    reads = [await _read_part(db, item.part, preferred_offers.get(item.part.id)) for item in matches]
    if low_stock:
        reads = [item for item in reads if item.balance.is_low_stock]
    total = len(reads)
    return SmallPartListResponse(items=reads[offset : offset + limit], total=total, limit=limit, offset=offset)


@router.post("", response_model=SmallPartRead, status_code=status.HTTP_201_CREATED)
async def create_small_part(
    data: SmallPartCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE),
) -> SmallPartRead:
    payload = data.model_dump(exclude={"opening_quantity"})
    generate_sku = not payload.get("sku")
    attempts = _MAX_GENERATED_SKU_ATTEMPTS if generate_sku else 1
    last_integrity_error: IntegrityError | None = None

    for _ in range(attempts):
        if generate_sku:
            payload["sku"] = await warehouse_number_sequence_service.reserve_number(db, key="material")
            existing_id = await db.scalar(select(SmallPart.id).where(SmallPart.sku == payload["sku"]))
            if existing_id is not None:
                continue

        part = SmallPart(**payload)
        try:
            async with db.begin_nested():
                db.add(part)
                await db.flush()
                if data.opening_quantity > 0:
                    await service.append_ledger_entry(
                        db,
                        small_part_id=part.id,
                        entry_kind="opening",
                        physical_delta=data.opening_quantity,
                        reserved_delta=Decimal("0"),
                        reason="Anfangsbestand",
                        idempotency_key=f"material-opening:{part.id}",
                    )
            await db.commit()
            return await _read_single_part(db, await _load_part(db, part.id))
        except IntegrityError as exc:
            last_integrity_error = exc
            if not generate_sku:
                await db.rollback()
                raise _conflict("Artikelnummer ist bereits vorhanden oder ein Katalogwert fehlt") from exc
        except Exception:
            await db.rollback()
            raise

    await db.rollback()
    raise _conflict("Keine freie Artikelnummer im Nummernkreis gefunden") from last_integrity_error


@router.get("/{small_part_id}", response_model=SmallPartRead)
async def get_small_part(
    small_part_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
) -> SmallPartRead:
    return await _read_single_part(db, await _load_part(db, small_part_id))


@router.patch("/{small_part_id}", response_model=SmallPartRead)
async def update_small_part(
    small_part_id: int,
    data: SmallPartUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
) -> SmallPartRead:
    part = await _load_part(db, small_part_id)
    try:
        await service.update_small_part(db, part, data)
        await db.commit()
    except (service.SmallPartUnitChangeNotAllowed, IntegrityError) as exc:
        await db.rollback()
        message = (
            str(exc)
            if isinstance(exc, service.SmallPartUnitChangeNotAllowed)
            else "Artikelnummer ist bereits vorhanden"
        )
        raise _conflict(message) from exc
    return await _read_single_part(db, await _load_part(db, small_part_id))


@router.get("/{small_part_id}/ledger", response_model=list[SmallPartLedgerRead])
async def list_small_part_ledger(
    small_part_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ),
):
    await _load_part(db, small_part_id)
    return list(
        await db.scalars(
            select(SmallPartLedgerEntry)
            .where(SmallPartLedgerEntry.small_part_id == small_part_id)
            .order_by(SmallPartLedgerEntry.created_at.desc(), SmallPartLedgerEntry.id.desc())
        )
    )


@router.post("/{small_part_id}/ledger", response_model=SmallPartLedgerRead, status_code=status.HTTP_201_CREATED)
async def add_small_part_stock(
    small_part_id: int,
    data: SmallPartLedgerCreate,
    db: AsyncSession = Depends(get_db),
    user: User | None = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE),
) -> SmallPartLedgerRead:
    try:
        entry = await service.append_ledger_entry(
            db,
            small_part_id=small_part_id,
            entry_kind=data.entry_kind,
            physical_delta=data.quantity,
            reserved_delta=Decimal("0"),
            reason=data.reason,
            idempotency_key=data.idempotency_key,
            actor_id=user.id if user else None,
        )
        await db.commit()
    except service.SmallPartNotFound as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "not_found", "message": str(exc)}) from exc
    except service.InsufficientSmallPartStock as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "insufficient_stock", "message": str(exc)},
        ) from exc
    except service.SmallPartIdempotencyConflict as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "idempotency_conflict", "message": str(exc)},
        ) from exc
    await db.refresh(entry)
    await ws_manager.broadcast({"type": "inventory_changed", "resource": "small_part", "id": small_part_id})
    return SmallPartLedgerRead.model_validate(entry)
