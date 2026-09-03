"""Explicit, version-checked master-data adoption. No upstream writes."""

import hashlib
import json
from datetime import date

from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.customer import Customer, CustomerAddress, CustomerContact, CustomerTaxIdentifier
from backend.app.models.lexware import LexwareConnection, LexwareResource
from backend.app.schemas.customer import CustomerCreate, CustomerUpdate
from backend.app.schemas.lexware import LexwareImportRequest, LexwarePreviewRequest
from backend.app.services import customer as customer_service
from backend.app.services.lexware_client import LexwareError
from backend.app.services.lexware_connections import lock_connection
from backend.app.services.lexware_mapping import (
    ARTICLE_FIELDS,
    CONTACT_FIELDS,
    article_source,
    contact_source,
    customer_data,
    customer_preview_data,
)
from backend.app.services.order_errors import DuplicateBusinessKeyError


def snapshot_hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


async def resource_for(db: AsyncSession, connection_id: int, resource_id: int) -> LexwareResource:
    resource = await db.scalar(
        select(LexwareResource)
        .where(
            LexwareResource.id == resource_id,
            LexwareResource.connection_id == connection_id,
        )
        .execution_options(populate_existing=True)
    )
    if resource is None:
        raise LexwareError("Lexware resource not found", 404)
    return resource


async def _target(db: AsyncSession, resource: LexwareResource, request: LexwarePreviewRequest):
    if resource.kind == "contacts":
        if request.article_id:
            raise LexwareError("Customer import cannot target an article", 422)
        target_id = request.customer_id or resource.customer_id
        if resource.customer_id and target_id != resource.customer_id:
            raise LexwareError("This contact is already linked to another customer", 409)
        return await customer_service.get_customer(db, target_id) if target_id else None
    from backend.app.models.warehouse_article import WarehouseArticle

    if request.customer_id:
        raise LexwareError("Article import cannot target a customer", 422)
    target_id = request.article_id or resource.article_id
    if resource.article_id and target_id != resource.article_id:
        raise LexwareError("This article is already linked to another local article", 409)
    target = await db.get(WarehouseArticle, target_id, populate_existing=True) if target_id else None
    if target_id and target is None:
        raise LexwareError("Local article not found", 404)
    return target


async def preview(db: AsyncSession, connection_id: int, request: LexwarePreviewRequest) -> dict:
    connection = await db.get(LexwareConnection, connection_id)
    if connection is None:
        raise LexwareError("Lexware connection not found", 404)
    resource = await resource_for(db, connection_id, request.resource_id)
    target = await _target(db, resource, request)
    fields = CONTACT_FIELDS if resource.kind == "contacts" else ARTICLE_FIELDS
    source = contact_source(resource.payload) if resource.kind == "contacts" else article_source(resource.payload)
    current, affected = {}, []
    if target and resource.kind == "contacts":
        if connection.business_profile_id not in {account.business_profile_id for account in target.accounts}:
            raise LexwareError("Customer does not belong to this business profile", 409)
        current = customer_preview_data(target, connection.business_profile_id)
        profile_ids = [account.business_profile_id for account in target.accounts]
        affected = [
            {"id": row.id, "name": row.name}
            for row in (await db.scalars(select(BusinessProfile).where(BusinessProfile.id.in_(profile_ids)))).all()
        ]
    elif target:
        current = {
            field: str(getattr(target, field)) if field in {"sale_price", "tax_rate"} else getattr(target, field)
            for field in fields
        }
        current.update(unit_code=target.unit_code, kind=target.kind, stock_source=target.stock_source)
    warnings = []
    if resource.payload.get("archived"):
        warnings.append("Archived Lexware records cannot be imported")
    if len(affected) > 1:
        warnings.append("Changes affect the shared customer identity in every listed business profile")
    if resource.kind == "articles":
        warnings.append("Confirm the local article kind and unit; inventory is never imported from Lexware")
    changes = [
        {"field": field, "current": current.get(field), "incoming": source.get(field)}
        for field in sorted(fields)
        if current.get(field) != source.get(field) and (field != "customer_number" or source.get(field) is not None)
    ]
    return {
        "resource_id": resource.id,
        "version_hash": resource.version_hash,
        "local_version": target.version if target else None,
        "customer_id": target.id if target and resource.kind == "contacts" else None,
        "article_id": target.id if target and resource.kind == "articles" else None,
        "source": source,
        "current": current,
        "changes": changes,
        "affected_profiles": affected,
        "warnings": warnings,
    }


async def apply_import(db: AsyncSession, connection_id: int, request: LexwareImportRequest) -> dict:
    connection = await lock_connection(db, connection_id)
    if not connection.encrypted_api_key:
        raise LexwareError("Reconnect Lexware before importing cached data", 409)
    profile = await db.get(BusinessProfile, connection.business_profile_id)
    if profile is None or not profile.is_active:
        raise LexwareError("Business profile is inactive", 409)
    resource = await resource_for(db, connection_id, request.resource_id)
    if resource.version_hash != request.version_hash:
        raise LexwareError("External data changed; refresh the preview", 409)
    signature = snapshot_hash(request.model_dump(mode="json"))
    if resource.imported_baseline.get("request_signature") == signature:
        return {"customer_id": resource.customer_id, "article_id": resource.article_id, "unchanged": True}
    if resource.payload.get("archived"):
        raise LexwareError("Archived Lexware records cannot be imported", 409)
    allowed = CONTACT_FIELDS if resource.kind == "contacts" else ARTICLE_FIELDS
    fields = set(request.fields)
    if not fields <= allowed:
        raise LexwareError("Import contains unsupported fields", 422)
    target = await _target(db, resource, request)
    if (target.version if target else None) != request.local_version:
        raise LexwareError("Local data changed; refresh the preview", 409)
    if resource.kind == "contacts":
        target = await _import_customer(db, profile, resource, request, target, fields)
        resource.customer_id = target.id
    else:
        target = await _import_article(db, resource, request, target, fields)
        resource.article_id = target.id
    resource.imported_hash = resource.version_hash
    resource.imported_baseline = {
        "request_signature": signature,
        "fields": sorted(fields),
        "local_version": target.version,
    }
    await db.flush()
    return {"customer_id": resource.customer_id, "article_id": resource.article_id, "unchanged": False}


async def _import_customer(db, profile, resource, request, target, fields):
    source = contact_source(resource.payload)
    if not (resource.payload.get("roles") or {}).get("customer"):
        # Lexware may represent a role with an empty object. Presence is decisive.
        if "customer" not in (resource.payload.get("roles") or {}):
            raise LexwareError("This Lexware contact is not a customer", 422)
    if target:
        if profile.id not in {account.business_profile_id for account in target.accounts}:
            raise LexwareError("Customer does not belong to this business profile", 409)
        data = customer_data(target)
    else:
        if "identity" not in fields:
            raise LexwareError("Select identity when creating a customer", 422)
        data = {
            "preferred_locale": profile.default_locale,
            "accounts": [{"business_profile_id": profile.id, "preferred_currency": profile.default_currency}],
        }
    for field in fields:
        if field == "identity":
            data.update(source[field])
        elif field == "customer_number":
            if source[field] is None:
                raise LexwareError("The Lexware contact has no customer number to import", 422)
            account_data = next(account for account in data["accounts"] if account["business_profile_id"] == profile.id)
            account_data["number"] = source[field]
        else:
            data[field] = source[field]
    try:
        if target:
            validated = CustomerUpdate(**data, version=request.local_version)
            await customer_service._validate_business_profiles(
                db, [account.business_profile_id for account in target.accounts]
            )
            if "customer_number" in fields:
                account = next(account for account in target.accounts if account.business_profile_id == profile.id)
                number = next(
                    account.number for account in validated.accounts if account.business_profile_id == profile.id
                )
                await customer_service._assert_manual_number_available(
                    db, business_profile_id=profile.id, number=number, exclude_account_id=account.id
                )
            values = (
                validated.model_dump(include={"kind", "display_name", "company_name", "first_name", "last_name"})
                if "identity" in fields
                else {}
            )
            # Only selected collections are replaced. The normal full customer
            # editor rewrites child rows; using it here would change untouched IDs
            # and document preferences even for an identity-only import.
            changed = await db.scalar(
                update(Customer)
                .where(
                    Customer.id == target.id,
                    Customer.version == request.local_version,
                )
                .values(**values, version=Customer.version + 1)
                .returning(Customer.version)
                .execution_options(synchronize_session=False)
            )
            if changed is None:
                raise LexwareError("Local customer changed; refresh the preview", 409)
            for field, value in values.items():
                setattr(target, field, value)
            set_committed_value(target, "version", changed)
            if "customer_number" in fields:
                account.number = number
            for field, model in (
                ("addresses", CustomerAddress),
                ("contacts", CustomerContact),
                ("tax_identifiers", CustomerTaxIdentifier),
            ):
                if field in fields:
                    setattr(target, field, [])
                    await db.flush()
                    setattr(target, field, [model(**item.model_dump()) for item in getattr(validated, field)])
            await db.flush()
            return target
        return await customer_service.create_customer(db, CustomerCreate(**data), effective_date=date.today())
    except DuplicateBusinessKeyError:
        raise LexwareError(
            "This customer number is already assigned in the selected business profile",
            409,
            code="customer_number_conflict",
        ) from None
    except ValidationError:
        raise LexwareError("Contact data is incomplete or incompatible with the selected local fields", 422) from None


async def _import_article(db, resource, request, target, fields):
    from backend.app.schemas.warehouse_article import WarehouseArticleCreate, WarehouseArticleUpdate
    from backend.app.services.warehouse_articles import create_article, update_article

    source = article_source(resource.payload)
    if source["external_type"] not in {"PRODUCT", "SERVICE"}:
        raise LexwareError("Lexware article type is unsupported", 422)
    values = {field: source[field] for field in fields}
    try:
        if target:
            if (target.kind == "service") != (source["external_type"] == "SERVICE"):
                raise LexwareError("Local and external article types differ", 409)
            if request.confirmed_unit_code != target.unit_code:
                raise LexwareError("Confirm the external and local unit mapping before updating this article", 422)
            return await update_article(db, target.id, WarehouseArticleUpdate(**values, version=request.local_version))
        options = request.article_options or {}
        allowed_options = {
            "sku",
            "kind",
            "unit_code",
            "stock_source",
            "small_part_id",
            "project_id",
            "calculation_revision_id",
        }
        if set(options) - allowed_options or not {"sku", "kind", "unit_code", "stock_source"} <= set(options):
            raise LexwareError("Confirm article number, kind, unit and stock source", 422)
        if "name" not in fields or (options["kind"] == "service") != (source["external_type"] == "SERVICE"):
            raise LexwareError("Article name and compatible type are required", 422)
        return await create_article(db, WarehouseArticleCreate(**options, **values))
    except ValidationError:
        raise LexwareError("Article fields or unit mapping are invalid", 422) from None
