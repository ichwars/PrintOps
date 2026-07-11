from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from backend.app.core.text_normalization import (
    normalize_case_insensitive_key,
    normalize_tag_name_key,
)
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.customer import (
    Customer,
    CustomerAccount,
    CustomerAddress,
    CustomerContact,
    CustomerTag,
    CustomerTaxIdentifier,
)
from backend.app.models.number_sequence import NumberSequence
from backend.app.schemas.customer import (
    CustomerCreate,
    CustomerKind,
    CustomerStatus,
    CustomerUpdate,
)
from backend.app.services.number_sequence import reserve_number
from backend.app.services.order_errors import (
    DuplicateBusinessKeyError,
    ResourceInUseError,
    ResourceNotFoundError,
    VersionConflictError,
)

_CUSTOMER_LOAD_OPTIONS = (
    selectinload(Customer.accounts),
    selectinload(Customer.contacts),
    selectinload(Customer.addresses),
    selectinload(Customer.tax_identifiers),
    selectinload(Customer.tags),
)
_NESTED_FIELDS = {"accounts", "contacts", "addresses", "tax_identifiers", "tags"}
_SCALAR_FIELDS = {
    "kind",
    "display_name",
    "company_name",
    "first_name",
    "last_name",
    "status",
    "preferred_locale",
    "notes",
}


@dataclass(frozen=True, slots=True)
class CustomerPage:
    rows: list[tuple[Customer, CustomerAccount]]
    total: int
    limit: int
    offset: int


async def _load_customer(
    session: AsyncSession,
    customer_id: int,
    *,
    for_update: bool = False,
) -> Customer:
    statement = (
        select(Customer)
        .options(*_CUSTOMER_LOAD_OPTIONS)
        .where(Customer.id == customer_id)
    )
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    customer = result.scalar_one_or_none()
    if customer is None:
        raise ResourceNotFoundError(f"Customer {customer_id} was not found")
    return customer


async def get_customer(session: AsyncSession, customer_id: int) -> Customer:
    return await _load_customer(session, customer_id)


async def _validate_business_profiles(
    session: AsyncSession,
    profile_ids: list[int],
) -> None:
    ordered_profile_ids = sorted(set(profile_ids))
    dialect_name = session.get_bind().dialect.name
    locked_sequence_ids: dict[int, int | None] = {}

    if dialect_name == "sqlite":
        for profile_id in ordered_profile_ids:
            locked_sequence_ids[profile_id] = await session.scalar(
                update(NumberSequence)
                .where(
                    NumberSequence.business_profile_id == profile_id,
                    NumberSequence.key == "customer",
                )
                .values(updated_at=NumberSequence.updated_at)
                .returning(NumberSequence.id)
            )

    profile_statement = (
        select(BusinessProfile.id, BusinessProfile.is_active)
        .where(BusinessProfile.id.in_(ordered_profile_ids))
        .order_by(BusinessProfile.id)
    )
    if dialect_name != "sqlite":
        profile_statement = profile_statement.with_for_update()
    rows = (await session.execute(profile_statement)).all()
    profiles = dict(rows)

    for profile_id in ordered_profile_ids:
        if profile_id not in profiles:
            raise ResourceNotFoundError(f"Business profile {profile_id} was not found")
        if not profiles[profile_id]:
            raise ResourceInUseError(f"Business profile {profile_id} is inactive")

    if dialect_name != "sqlite":
        locked_sequence_ids = dict(
            (
                await session.execute(
                    select(NumberSequence.business_profile_id, NumberSequence.id)
                    .where(
                        NumberSequence.business_profile_id.in_(ordered_profile_ids),
                        NumberSequence.key == "customer",
                    )
                    .order_by(NumberSequence.business_profile_id)
                    .with_for_update()
                )
            ).all()
        )

    for profile_id in ordered_profile_ids:
        if locked_sequence_ids.get(profile_id) is None:
            raise ResourceNotFoundError(
                f"Number sequence not found for business profile {profile_id} and key 'customer'"
            )


async def _resolve_tags(session: AsyncSession, names: list[str]) -> list[CustomerTag]:
    if not names:
        return []

    keys = [normalize_tag_name_key(name) for name in names]
    existing_tags = (
        await session.scalars(
            select(CustomerTag).where(CustomerTag.name_key.in_(keys))
        )
    ).all()
    tags_by_key = {tag.name_key: tag for tag in existing_tags}

    for name in names:
        key = normalize_tag_name_key(name)
        if key in tags_by_key:
            continue

        tag = CustomerTag(name=name)
        try:
            async with session.begin_nested():
                session.add(tag)
                await session.flush([tag])
        except IntegrityError as exc:
            tag = await session.scalar(
                select(CustomerTag).where(CustomerTag.name_key == key)
            )
            if tag is None:
                raise exc
        tags_by_key[key] = tag

    return sorted(
        tags_by_key.values(),
        key=lambda tag: (tag.name_key, tag.name, tag.id or 0),
    )


async def _reserve_available_number(
    session: AsyncSession,
    *,
    business_profile_id: int,
    effective_date: date,
) -> str:
    occupied_keys = await _normalized_number_keys(
        session,
        business_profile_id=business_profile_id,
    )
    for _attempt in range(len(occupied_keys) + 1):
        candidate = await reserve_number(
            session,
            business_profile_id=business_profile_id,
            key="customer",
            effective_date=effective_date,
        )
        if normalize_case_insensitive_key(candidate) not in occupied_keys:
            return candidate

    raise VersionConflictError(
        f"Could not reserve an available customer number for business profile {business_profile_id}"
    )


async def _assert_manual_number_available(
    session: AsyncSession,
    *,
    business_profile_id: int,
    number: str,
    exclude_account_id: int | None = None,
) -> None:
    if await _normalized_number_exists(
        session,
        business_profile_id=business_profile_id,
        number=number,
        exclude_account_id=exclude_account_id,
    ):
        raise DuplicateBusinessKeyError(
            "A customer account with this profile and number already exists"
        )


async def _normalized_number_exists(
    session: AsyncSession,
    *,
    business_profile_id: int,
    number: str,
    exclude_account_id: int | None = None,
) -> bool:
    """Compare visible numbers so legacy runtime-derived keys cannot hide collisions."""
    requested_key = normalize_case_insensitive_key(number)
    occupied_keys = await _normalized_number_keys(
        session,
        business_profile_id=business_profile_id,
        exclude_account_id=exclude_account_id,
    )
    return requested_key in occupied_keys


async def _normalized_number_keys(
    session: AsyncSession,
    *,
    business_profile_id: int,
    exclude_account_id: int | None = None,
) -> set[str]:
    statement = select(CustomerAccount.id, CustomerAccount.number).where(
        CustomerAccount.business_profile_id == business_profile_id
    )
    if exclude_account_id is not None:
        statement = statement.where(CustomerAccount.id != exclude_account_id)
    rows = (await session.execute(statement)).all()
    return {normalize_case_insensitive_key(row.number) for row in rows}


async def _new_accounts(
    session: AsyncSession,
    data: CustomerCreate,
    *,
    effective_date: date,
) -> list[CustomerAccount]:
    accounts: list[CustomerAccount] = []
    for account_data in data.accounts:
        values = account_data.model_dump()
        if values["number"] is None:
            values["number"] = await _reserve_available_number(
                session,
                business_profile_id=account_data.business_profile_id,
                effective_date=effective_date,
            )
        else:
            await _assert_manual_number_available(
                session,
                business_profile_id=account_data.business_profile_id,
                number=values["number"],
            )
        accounts.append(CustomerAccount(**values))
    return accounts


def _new_contacts(data: CustomerCreate) -> list[CustomerContact]:
    return [CustomerContact(**contact.model_dump()) for contact in data.contacts]


def _new_addresses(data: CustomerCreate) -> list[CustomerAddress]:
    return [CustomerAddress(**address.model_dump()) for address in data.addresses]


def _new_tax_identifiers(data: CustomerCreate) -> list[CustomerTaxIdentifier]:
    return [
        CustomerTaxIdentifier(**tax_identifier.model_dump())
        for tax_identifier in data.tax_identifiers
    ]


async def create_customer(
    session: AsyncSession,
    data: CustomerCreate,
    *,
    effective_date: date,
) -> Customer:
    await _validate_business_profiles(
        session,
        [account.business_profile_id for account in data.accounts],
    )
    tags = await _resolve_tags(session, data.tags)
    accounts = await _new_accounts(session, data, effective_date=effective_date)

    customer = Customer(**data.model_dump(include=_SCALAR_FIELDS))
    customer.accounts = accounts
    customer.contacts = _new_contacts(data)
    customer.addresses = _new_addresses(data)
    customer.tax_identifiers = _new_tax_identifiers(data)
    customer.tags = tags
    session.add(customer)
    await session.flush()
    return customer


async def list_customers(
    session: AsyncSession,
    *,
    business_profile_id: int,
    search: str | None = None,
    status: CustomerStatus | None = None,
    kind: CustomerKind | None = None,
    limit: int = 50,
    offset: int = 0,
) -> CustomerPage:
    filters = [CustomerAccount.business_profile_id == business_profile_id]
    if status is not None:
        filters.append(Customer.status == status)
    if kind is not None:
        filters.append(Customer.kind == kind)
    if search is not None and (normalized_search := search.strip()):
        search_key = normalize_case_insensitive_key(normalized_search)
        matching_contact = exists().where(
            CustomerContact.customer_id == Customer.id,
            CustomerContact.email_key.contains(search_key, autoescape=True),
        )
        filters.append(
            or_(
                Customer.display_name_key.contains(search_key, autoescape=True),
                CustomerAccount.number_key.contains(search_key, autoescape=True),
                matching_contact,
            )
        )

    total = await session.scalar(
        select(func.count(func.distinct(Customer.id)))
        .select_from(Customer)
        .join(CustomerAccount, CustomerAccount.customer_id == Customer.id)
        .where(*filters)
    )
    result = await session.execute(
        select(Customer, CustomerAccount)
        .join(CustomerAccount, CustomerAccount.customer_id == Customer.id)
        .options(*_CUSTOMER_LOAD_OPTIONS)
        .where(*filters)
        .order_by(Customer.display_name_key, Customer.id)
        .limit(limit)
        .offset(offset)
    )
    rows = [(row.Customer, row.CustomerAccount) for row in result.unique().all()]
    return CustomerPage(
        rows=rows,
        total=total or 0,
        limit=limit,
        offset=offset,
    )


async def update_customer(
    session: AsyncSession,
    customer_id: int,
    data: CustomerUpdate,
    *,
    effective_date: date,
) -> Customer:
    # The profile validation acquires SQLite's write lock. Run it before the
    # first customer read so the transaction cannot hold a stale read snapshot
    # when it later mutates customer and account rows.
    await _validate_business_profiles(
        session,
        [account.business_profile_id for account in data.accounts],
    )
    customer = await get_customer(session, customer_id)

    scalar_values = data.model_dump(include=_SCALAR_FIELDS)
    scalar_values["display_name_key"] = normalize_case_insensitive_key(data.display_name)
    cas_result = await session.execute(
        update(Customer)
        .where(
            Customer.id == customer_id,
            Customer.version == data.version,
        )
        .values(**scalar_values, version=Customer.version + 1)
        .returning(Customer.version, Customer.updated_at)
        .execution_options(synchronize_session=False)
    )
    cas_row = cas_result.one_or_none()
    if cas_row is None:
        raise VersionConflictError(
            f"Customer {customer_id} changed concurrently; reload it and retry"
        )

    for field, value in scalar_values.items():
        set_committed_value(customer, field, value)
    set_committed_value(customer, "version", cas_row.version)
    set_committed_value(customer, "updated_at", cas_row.updated_at)

    tags = await _resolve_tags(session, data.tags)
    new_contacts = _new_contacts(data)
    new_addresses = _new_addresses(data)
    new_tax_identifiers = _new_tax_identifiers(data)

    old_contacts = list(customer.contacts)
    old_addresses = list(customer.addresses)
    old_tax_identifiers = list(customer.tax_identifiers)

    existing_accounts = {
        account.business_profile_id: account
        for account in customer.accounts
    }
    requested_profile_ids: set[int] = set()
    for account_data in data.accounts:
        requested_profile_ids.add(account_data.business_profile_id)
        values = account_data.model_dump()
        existing_account = existing_accounts.get(account_data.business_profile_id)
        if values["number"] is None:
            values["number"] = await _reserve_available_number(
                session,
                business_profile_id=account_data.business_profile_id,
                effective_date=effective_date,
            )
        else:
            await _assert_manual_number_available(
                session,
                business_profile_id=account_data.business_profile_id,
                number=values["number"],
                exclude_account_id=existing_account.id if existing_account is not None else None,
            )

        if existing_account is None:
            customer.accounts.append(CustomerAccount(**values))
            continue
        for field, value in values.items():
            setattr(existing_account, field, value)
    await session.flush()

    for profile_id, account in existing_accounts.items():
        if profile_id not in requested_profile_ids:
            customer.accounts.remove(account)
    await session.flush()

    for tax_identifier in old_tax_identifiers:
        tax_identifier.value = f"__replace__{uuid4().hex}"
    await session.flush()

    customer.contacts.extend(new_contacts)
    customer.addresses.extend(new_addresses)
    customer.tax_identifiers.extend(new_tax_identifiers)
    customer.tags = tags
    await session.flush()

    for contact in old_contacts:
        customer.contacts.remove(contact)
    for address in old_addresses:
        customer.addresses.remove(address)
    for tax_identifier in old_tax_identifiers:
        customer.tax_identifiers.remove(tax_identifier)
    await session.flush()
    await session.refresh(customer, attribute_names=["updated_at"])
    return customer


def _assert_customer_deletable(customer: Customer) -> None:
    # Commercial references are introduced by later foundation tasks.
    _ = customer


async def delete_customer(session: AsyncSession, customer_id: int) -> None:
    customer = await _load_customer(session, customer_id, for_update=True)
    _assert_customer_deletable(customer)
    await session.delete(customer)
    await session.flush()
