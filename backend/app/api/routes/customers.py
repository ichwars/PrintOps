from __future__ import annotations

from collections import deque
from collections.abc import Awaitable
from datetime import date
from typing import NoReturn, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.core.text_normalization import normalize_case_insensitive_key
from backend.app.models.customer import Customer, CustomerAccount
from backend.app.models.user import User
from backend.app.schemas.customer import (
    CustomerAccountResponse,
    CustomerAddressResponse,
    CustomerContactResponse,
    CustomerCreate,
    CustomerDetailResponse,
    CustomerKind,
    CustomerListItem,
    CustomerListResponse,
    CustomerStatus,
    CustomerTaxIdentifierResponse,
    CustomerUpdate,
    TaxDecisionRequest,
    TaxDecisionResponse,
    TaxOverrideRequest,
)
from backend.app.services import customer as customer_service
from backend.app.services.order_errors import (
    DuplicateBusinessKeyError,
    OrderDomainError,
    ResourceInUseError,
    ResourceNotFoundError,
    VersionConflictError,
)
from backend.app.services.tax_decision import (
    TAX_RULES_2026_1,
    TaxDecisionInput,
    TaxOverride,
    TaxOverrideActor,
    determine_tax,
    override_tax,
)

router = APIRouter(prefix="/customers", tags=["customers"])

_DUPLICATE_MESSAGE = "A customer account with this profile and number already exists"
_GENERIC_INTEGRITY_MESSAGE = "The customer conflicts with existing data"
_DELETE_REFERENCE_MESSAGE = "The customer is referenced and cannot be deleted"
_PROFILE_UNAVAILABLE_MESSAGE = "The selected business profile is no longer available"
_CUSTOMER_UNIQUE_CONSTRAINTS = {
    "uq_customer_account_profile_number",
    "uq_customer_account_customer_profile",
    "uq_customer_tax_identifier",
    "uq_customer_tag_name",
    "uq_customer_tag_name_key",
}
_T = TypeVar("_T")


def _raise_http_error(error: OrderDomainError) -> NoReturn:
    if isinstance(error, ResourceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
        code = "not_found"
    elif isinstance(error, VersionConflictError):
        status_code = status.HTTP_409_CONFLICT
        code = "version_conflict"
    elif isinstance(error, ResourceInUseError):
        status_code = status.HTTP_409_CONFLICT
        code = "resource_in_use"
    elif isinstance(error, DuplicateBusinessKeyError):
        status_code = status.HTTP_409_CONFLICT
        code = "duplicate_business_key"
    else:
        raise error

    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
    )


def _integrity_error_sources(error: IntegrityError) -> tuple[BaseException, ...]:
    pending = deque([error.orig])
    sources: list[BaseException] = []
    seen: set[int] = set()

    while pending and len(sources) < 16:
        source = pending.popleft()
        if source is None or id(source) in seen:
            continue
        seen.add(id(source))
        sources.append(source)
        pending.extend((getattr(source, "__cause__", None), getattr(source, "__context__", None)))

    return tuple(sources)


def _error_metadata(sources: tuple[BaseException, ...], *attribute_names: str) -> set[str]:
    values: set[str] = set()
    for source in sources:
        for metadata_source in (source, getattr(source, "diag", None)):
            if metadata_source is None:
                continue
            for attribute_name in attribute_names:
                value = getattr(metadata_source, attribute_name, None)
                if isinstance(value, str):
                    values.add(value.casefold())
    return values


def _classify_integrity_error(
    error: IntegrityError,
    *,
    operation_kind: str,
) -> OrderDomainError | None:
    sources = _integrity_error_sources(error)
    message = " ".join(str(source) for source in sources).casefold()
    constraint_names = _error_metadata(sources, "constraint_name")
    sql_states = _error_metadata(sources, "sqlstate", "pgcode")

    is_foreign_key_error = (
        "23503" in sql_states
        or any(name.endswith("_fkey") for name in constraint_names)
        or "foreign key constraint failed" in message
        or "violates foreign key constraint" in message
    )
    if is_foreign_key_error:
        if operation_kind == "delete":
            return ResourceInUseError(_DELETE_REFERENCE_MESSAGE)
        return ResourceInUseError(_PROFILE_UNAVAILABLE_MESSAGE)

    if "uq_customer_account_profile_number" in constraint_names or (
        "customer_accounts.business_profile_id" in message and "customer_accounts.number" in message
    ):
        return DuplicateBusinessKeyError(_DUPLICATE_MESSAGE)

    is_unique_error = (
        "23505" in sql_states
        or bool(constraint_names & _CUSTOMER_UNIQUE_CONSTRAINTS)
        or "unique constraint failed" in message
        or "duplicate key value violates unique constraint" in message
    )
    if is_unique_error:
        return DuplicateBusinessKeyError(_GENERIC_INTEGRITY_MESSAGE)
    return None


async def _commit_write(
    session: AsyncSession,
    operation: Awaitable[_T],
    *,
    operation_kind: str = "write",
) -> _T:
    try:
        result = await operation
        await session.commit()
        return result
    except IntegrityError as exc:
        await session.rollback()
        classified = _classify_integrity_error(exc, operation_kind=operation_kind)
        if classified is None:
            raise
        raise classified from exc
    except OrderDomainError:
        await session.rollback()
        raise


def _sorted_tag_names(customer: Customer) -> list[str]:
    return sorted(
        (tag.name for tag in customer.tags),
        key=lambda name: (normalize_case_insensitive_key(name), name),
    )


def _serialize_customer(customer: Customer) -> CustomerDetailResponse:
    return CustomerDetailResponse(
        id=customer.id,
        kind=customer.kind,
        display_name=customer.display_name,
        company_name=customer.company_name,
        first_name=customer.first_name,
        last_name=customer.last_name,
        status=customer.status,
        preferred_locale=customer.preferred_locale,
        notes=customer.notes,
        version=customer.version,
        created_at=customer.created_at,
        updated_at=customer.updated_at,
        accounts=[
            CustomerAccountResponse.model_validate(account)
            for account in sorted(customer.accounts, key=lambda child: child.id)
        ],
        contacts=[
            CustomerContactResponse.model_validate(contact)
            for contact in sorted(customer.contacts, key=lambda child: child.id)
        ],
        addresses=[
            CustomerAddressResponse.model_validate(address)
            for address in sorted(customer.addresses, key=lambda child: child.id)
        ],
        tax_identifiers=[
            CustomerTaxIdentifierResponse.model_validate(tax_identifier)
            for tax_identifier in sorted(customer.tax_identifiers, key=lambda child: child.id)
        ],
        tags=_sorted_tag_names(customer),
    )


def _serialize_list_item(customer: Customer, account: CustomerAccount) -> CustomerListItem:
    primary_contact = next(
        (contact for contact in customer.contacts if contact.is_primary),
        None,
    )
    primary_contact_name = None
    if primary_contact is not None:
        name_parts = [primary_contact.first_name, primary_contact.last_name]
        primary_contact_name = " ".join(part for part in name_parts if part) or None

    billing_address = next(
        (address for address in customer.addresses if address.kind == "billing" and address.is_default),
        None,
    )
    return CustomerListItem(
        id=customer.id,
        business_profile_id=account.business_profile_id,
        account_number=account.number,
        preferred_currency=account.preferred_currency,
        payment_term_days=account.payment_term_days,
        delivery_terms=account.delivery_terms,
        discount_percent=account.discount_percent,
        account_is_active=account.is_active,
        display_name=customer.display_name,
        company_name=customer.company_name,
        first_name=customer.first_name,
        last_name=customer.last_name,
        kind=customer.kind,
        status=customer.status,
        preferred_locale=customer.preferred_locale,
        primary_contact_name=primary_contact_name,
        primary_contact_email=primary_contact.email if primary_contact is not None else None,
        billing_city=billing_address.city if billing_address is not None else None,
        billing_country_code=(billing_address.country_code if billing_address is not None else None),
        tags=_sorted_tag_names(customer),
        version=customer.version,
    )


@router.get("/", response_model=CustomerListResponse)
async def list_customers(
    business_profile_id: int = Query(gt=0),
    search: str | None = Query(default=None),
    customer_status: CustomerStatus | None = Query(default=None, alias="status"),
    customer_kind: CustomerKind | None = Query(default=None, alias="kind"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CUSTOMERS_READ),
) -> CustomerListResponse:
    page = await customer_service.list_customers(
        db,
        business_profile_id=business_profile_id,
        search=search,
        status=customer_status,
        kind=customer_kind,
        limit=limit,
        offset=offset,
    )
    return CustomerListResponse(
        items=[_serialize_list_item(customer, account) for customer, account in page.rows],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/", response_model=CustomerDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CUSTOMERS_MANAGE),
) -> CustomerDetailResponse:
    try:
        customer = await _commit_write(
            db,
            customer_service.create_customer(db, data, effective_date=date.today()),
        )
    except OrderDomainError as exc:
        _raise_http_error(exc)
    return _serialize_customer(customer)


@router.post("/tax-decisions/preview", response_model=TaxDecisionResponse)
async def preview_tax_decision(
    data: TaxDecisionRequest,
    _: User | None = RequirePermissionIfAuthEnabled(Permission.COMMERCIAL_DOCUMENTS_DRAFT),
) -> TaxDecisionResponse:
    decision = determine_tax(
        TaxDecisionInput(**data.model_dump()),
        TAX_RULES_2026_1,
    )
    return TaxDecisionResponse.model_validate(decision)


@router.post("/tax-decisions/override", response_model=TaxDecisionResponse)
async def create_tax_override(
    data: TaxOverrideRequest,
    user: User | None = RequirePermissionIfAuthEnabled(
        Permission.COMMERCIAL_DOCUMENTS_TAX_OVERRIDE
    ),
) -> TaxDecisionResponse:
    decision = determine_tax(
        TaxDecisionInput(**data.facts.model_dump()),
        TAX_RULES_2026_1,
    )
    overridden = override_tax(
        decision,
        TaxOverride(**data.override.model_dump()),
        TaxOverrideActor(user_id=user.id if user is not None else 0, can_override=True),
    )
    return TaxDecisionResponse.model_validate(overridden)


@router.get("/{customer_id}", response_model=CustomerDetailResponse)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CUSTOMERS_READ),
) -> CustomerDetailResponse:
    try:
        customer = await customer_service.get_customer(db, customer_id)
    except OrderDomainError as exc:
        _raise_http_error(exc)
    return _serialize_customer(customer)


@router.put("/{customer_id}", response_model=CustomerDetailResponse)
async def update_customer(
    customer_id: int,
    data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CUSTOMERS_MANAGE),
) -> CustomerDetailResponse:
    try:
        customer = await _commit_write(
            db,
            customer_service.update_customer(
                db,
                customer_id,
                data,
                effective_date=date.today(),
            ),
        )
    except OrderDomainError as exc:
        _raise_http_error(exc)
    return _serialize_customer(customer)


@router.delete(
    "/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.CUSTOMERS_MANAGE),
) -> Response:
    try:
        await _commit_write(
            db,
            customer_service.delete_customer(db, customer_id),
            operation_kind="delete",
        )
    except OrderDomainError as exc:
        _raise_http_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
