from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value

from backend.app.models.business_profile import (
    BusinessProfile,
    BusinessProfileAddress,
    BusinessProfileBankAccount,
    BusinessProfileTaxIdentifier,
)
from backend.app.models.customer import CustomerAccount
from backend.app.models.number_sequence import NumberSequence
from backend.app.schemas.business_profile import BusinessProfileCreate, BusinessProfileUpdate
from backend.app.services.order_errors import ResourceInUseError, ResourceNotFoundError, VersionConflictError

_PROFILE_LOAD_OPTIONS = (
    selectinload(BusinessProfile.addresses),
    selectinload(BusinessProfile.tax_identifiers),
    selectinload(BusinessProfile.bank_accounts),
    selectinload(BusinessProfile.number_sequences),
)
_NESTED_FIELDS = {"addresses", "tax_identifiers", "bank_accounts"}


async def _lock_customer_sequence_for_sqlite(session: AsyncSession, profile_id: int) -> None:
    """Serialize profile lifecycle changes with SQLite customer creation."""
    if session.get_bind().dialect.name != "sqlite":
        return

    await session.execute(
        update(NumberSequence)
        .where(
            NumberSequence.business_profile_id == profile_id,
            NumberSequence.key == "customer",
        )
        .values(updated_at=NumberSequence.updated_at)
        .execution_options(synchronize_session=False)
    )


async def list_business_profiles(
    session: AsyncSession,
    *,
    include_inactive: bool = False,
) -> list[BusinessProfile]:
    statement = select(BusinessProfile).options(*_PROFILE_LOAD_OPTIONS).order_by(BusinessProfile.id)
    if not include_inactive:
        statement = statement.where(BusinessProfile.is_active.is_(True))
    result = await session.execute(statement)
    return list(result.scalars().unique().all())


async def _load_business_profile(
    session: AsyncSession,
    profile_id: int,
    *,
    for_update: bool = False,
) -> BusinessProfile:
    statement = select(BusinessProfile).options(*_PROFILE_LOAD_OPTIONS).where(BusinessProfile.id == profile_id)
    if for_update:
        statement = statement.with_for_update()
    result = await session.execute(statement)
    profile = result.scalar_one_or_none()
    if profile is None:
        raise ResourceNotFoundError(f"Business profile {profile_id} was not found")
    return profile


async def get_business_profile(session: AsyncSession, profile_id: int) -> BusinessProfile:
    return await _load_business_profile(session, profile_id)


async def get_default_business_profile(session: AsyncSession) -> BusinessProfile:
    result = await session.execute(
        select(BusinessProfile)
        .options(*_PROFILE_LOAD_OPTIONS)
        .where(BusinessProfile.is_default.is_(True), BusinessProfile.is_active.is_(True))
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise ResourceNotFoundError("No active default business profile was found")
    return profile


async def _clear_other_defaults(session: AsyncSession, *, keep_profile_id: int | None = None) -> None:
    statement = update(BusinessProfile).where(BusinessProfile.is_default.is_(True))
    if keep_profile_id is not None:
        statement = statement.where(BusinessProfile.id != keep_profile_id)
    await session.execute(
        statement.values(
            is_default=False,
            version=BusinessProfile.version + 1,
        ).execution_options(synchronize_session=False)
    )


def _new_addresses(data: BusinessProfileCreate) -> list[BusinessProfileAddress]:
    return [BusinessProfileAddress(**address.model_dump()) for address in data.addresses]


def _new_tax_identifiers(data: BusinessProfileCreate) -> list[BusinessProfileTaxIdentifier]:
    return [BusinessProfileTaxIdentifier(**tax_id.model_dump()) for tax_id in data.tax_identifiers]


def _new_bank_accounts(data: BusinessProfileCreate) -> list[BusinessProfileBankAccount]:
    return [BusinessProfileBankAccount(**account.model_dump()) for account in data.bank_accounts]


async def create_business_profile(
    session: AsyncSession,
    data: BusinessProfileCreate,
) -> BusinessProfile:
    existing_profile_id = await session.scalar(select(BusinessProfile.id).limit(1))
    should_be_default = existing_profile_id is None or data.is_default
    if should_be_default and not data.is_active:
        raise ResourceInUseError("The default business profile must be active")
    if should_be_default:
        await _clear_other_defaults(session)

    values = data.model_dump(exclude=_NESTED_FIELDS)
    values["is_default"] = should_be_default
    profile = BusinessProfile(**values)
    profile.addresses = _new_addresses(data)
    profile.tax_identifiers = _new_tax_identifiers(data)
    profile.bank_accounts = _new_bank_accounts(data)
    session.add(profile)
    await session.flush()

    session.add_all(
        [
            NumberSequence(
                business_profile_id=profile.id,
                key="customer",
                prefix="CUST",
                pattern="{PREFIX}-{#####}",
                next_value=1,
                reset_policy="none",
                current_period=None,
            ),
            NumberSequence(
                business_profile_id=profile.id,
                key="offer",
                prefix="ANG",
                pattern="{PREFIX}-{YYYY}-{#####}",
                next_value=1,
                reset_policy="yearly",
                current_period=None,
            ),
            NumberSequence(
                business_profile_id=profile.id,
                key="order",
                prefix="AUF",
                pattern="{PREFIX}-{YYYY}-{#####}",
                next_value=1,
                reset_policy="yearly",
                current_period=None,
            ),
        ]
    )
    await session.flush()
    return profile


async def update_business_profile(
    session: AsyncSession,
    profile_id: int,
    data: BusinessProfileUpdate,
) -> BusinessProfile:
    # SQLite must enter its write transaction before the first read. Otherwise
    # a concurrent writer can invalidate the deferred read snapshot and turn
    # the later lock upgrade into SQLITE_BUSY_SNAPSHOT.
    await _lock_customer_sequence_for_sqlite(session, profile_id)
    profile = await _load_business_profile(
        session,
        profile_id,
        for_update=session.get_bind().dialect.name != "sqlite",
    )
    if profile.is_active and not data.is_active:
        customer_account_id = await session.scalar(
            select(CustomerAccount.id).where(CustomerAccount.business_profile_id == profile_id).limit(1)
        )
        if customer_account_id is not None:
            raise ResourceInUseError("The business profile is referenced by a customer account")
    if profile.is_default and (not data.is_default or not data.is_active):
        raise ResourceInUseError("The active default business profile cannot be disabled or unset")
    if data.is_default and not data.is_active:
        raise ResourceInUseError("The default business profile must be active")

    cas_result = await session.execute(
        update(BusinessProfile)
        .where(
            BusinessProfile.id == profile_id,
            BusinessProfile.version == data.version,
        )
        .values(version=BusinessProfile.version + 1)
        .returning(BusinessProfile.id)
        .execution_options(synchronize_session=False)
    )
    if cas_result.scalar_one_or_none() is None:
        raise VersionConflictError(f"Business profile {profile_id} changed concurrently; reload it and retry")
    set_committed_value(profile, "version", data.version + 1)

    if data.is_default:
        await _clear_other_defaults(session, keep_profile_id=profile.id)

    old_addresses = list(profile.addresses)
    old_tax_identifiers = list(profile.tax_identifiers)
    old_bank_accounts = list(profile.bank_accounts)

    values = data.model_dump(exclude=_NESTED_FIELDS | {"version"})
    for field, value in values.items():
        setattr(profile, field, value)

    # Keep the old rows present until replacements are inserted so replacement
    # child IDs remain distinct on SQLite. Move old tax keys aside first to
    # avoid colliding with an unchanged (kind, value) replacement.
    for tax_id in old_tax_identifiers:
        tax_id.value = f"__replace__{uuid4().hex}"
    await session.flush()

    profile.addresses.extend(_new_addresses(data))
    profile.tax_identifiers.extend(_new_tax_identifiers(data))
    profile.bank_accounts.extend(_new_bank_accounts(data))
    await session.flush()

    for address in old_addresses:
        profile.addresses.remove(address)
    for tax_id in old_tax_identifiers:
        profile.tax_identifiers.remove(tax_id)
    for account in old_bank_accounts:
        profile.bank_accounts.remove(account)
    await session.flush()
    await session.refresh(profile, attribute_names=["updated_at"])
    return profile


async def set_default_business_profile(session: AsyncSession, profile_id: int) -> BusinessProfile:
    await _lock_customer_sequence_for_sqlite(session, profile_id)
    profile = await _load_business_profile(
        session,
        profile_id,
        for_update=session.get_bind().dialect.name != "sqlite",
    )
    observed_version = profile.version
    if not profile.is_active:
        raise ResourceInUseError("An inactive business profile cannot be the default")

    await _clear_other_defaults(session, keep_profile_id=profile.id)
    cas_result = await session.execute(
        update(BusinessProfile)
        .where(
            BusinessProfile.id == profile.id,
            BusinessProfile.version == observed_version,
            BusinessProfile.is_active.is_(True),
        )
        .values(
            is_default=True,
            version=BusinessProfile.version + 1,
        )
        .returning(BusinessProfile.id)
        .execution_options(synchronize_session=False)
    )
    if cas_result.scalar_one_or_none() is None:
        raise VersionConflictError(f"Business profile {profile_id} changed concurrently; reload it and retry")

    set_committed_value(profile, "is_default", True)
    set_committed_value(profile, "version", observed_version + 1)
    await session.flush()
    await session.refresh(profile, attribute_names=["updated_at"])
    return profile


async def delete_business_profile(session: AsyncSession, profile_id: int) -> None:
    await _lock_customer_sequence_for_sqlite(session, profile_id)
    profile = await _load_business_profile(
        session,
        profile_id,
        for_update=session.get_bind().dialect.name != "sqlite",
    )
    if profile.is_default:
        raise ResourceInUseError("The default business profile cannot be deleted")

    customer_account_id = await session.scalar(
        select(CustomerAccount.id).where(CustomerAccount.business_profile_id == profile_id).limit(1)
    )
    if customer_account_id is not None:
        raise ResourceInUseError("The business profile is referenced by a customer account")

    await session.delete(profile)
    await session.flush()
