"""Integration coverage for issuing business-profile CRUD and permissions."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import date
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api.routes import business_profiles as business_profile_routes
from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.database import Base
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.business_profile import BusinessProfile, BusinessProfileTaxIdentifier
from backend.app.models.customer import Customer, CustomerAccount
from backend.app.models.group import Group
from backend.app.models.number_sequence import NumberSequence
from backend.app.models.user import User
from backend.app.schemas.customer import CustomerCreate
from backend.app.services import business_profile as business_profile_service, customer as customer_service
from backend.app.services.order_errors import (
    DuplicateBusinessKeyError,
    ResourceInUseError,
    ResourceNotFoundError,
    VersionConflictError,
)

BASE_URL = "/api/v1/business-profiles"
DUPLICATE_MESSAGE = "A business profile with this name already exists"
TAX_DUPLICATE_MESSAGE = "A duplicate tax identifier already exists"
GENERIC_INTEGRITY_MESSAGE = "The business profile conflicts with existing data"
DEFAULT_CONFLICT_MESSAGE = "The default business profile changed concurrently; retry the request"
DELETE_REFERENCE_MESSAGE = "The business profile is referenced and cannot be deleted"
OPTION_FIELDS = {
    "id",
    "name",
    "country_code",
    "default_currency",
    "timezone",
    "default_locale",
    "billing_mode",
    "is_default",
    "is_active",
}


class FakeAsyncpgError(Exception):
    def __init__(self, message: str, *, constraint_name: str | None = None, sqlstate: str | None = None):
        super().__init__(message)
        self.constraint_name = constraint_name
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    ("constraint_name", "sqlstate", "operation_kind", "expected_type", "expected_message"),
    [
        (
            "uq_business_profiles_single_default",
            "23505",
            "write",
            VersionConflictError,
            DEFAULT_CONFLICT_MESSAGE,
        ),
        (
            "uq_business_profile_tax_identifier",
            "23505",
            "write",
            DuplicateBusinessKeyError,
            TAX_DUPLICATE_MESSAGE,
        ),
        (
            "business_profiles_name_key",
            "23505",
            "write",
            DuplicateBusinessKeyError,
            DUPLICATE_MESSAGE,
        ),
        (
            "customer_accounts_business_profile_id_fkey",
            "23503",
            "delete",
            ResourceInUseError,
            DELETE_REFERENCE_MESSAGE,
        ),
        (
            "uq_private_secret",
            "23505",
            "write",
            DuplicateBusinessKeyError,
            GENERIC_INTEGRITY_MESSAGE,
        ),
    ],
)
def test_asyncpg_integrity_metadata_maps_to_sanitized_domain_errors(
    constraint_name,
    sqlstate,
    operation_kind,
    expected_type,
    expected_message,
):
    original = RuntimeError("adapter wrapper")
    intermediate = RuntimeError("driver wrapper")
    driver_error = FakeAsyncpgError(
        "sensitive database detail",
        constraint_name=constraint_name,
        sqlstate=sqlstate,
    )
    original.__cause__ = intermediate
    intermediate.__context__ = driver_error
    driver_error.__cause__ = original

    classified = business_profile_routes._classify_integrity_error(
        IntegrityError("redacted statement", {}, original),
        operation_kind=operation_kind,
    )

    assert type(classified) is expected_type
    assert str(classified) == expected_message
    assert "sensitive database detail" not in str(classified)


@pytest.mark.parametrize(
    "driver_error",
    [
        FakeAsyncpgError("private check detail", sqlstate="23514"),
        FakeAsyncpgError("private not-null detail", sqlstate="23502"),
        RuntimeError("CHECK constraint failed: ck_business_profiles_billing_mode"),
        RuntimeError("NOT NULL constraint failed: business_profiles.legal_name"),
        RuntimeError("private table detail"),
    ],
)
def test_integrity_classification_does_not_mask_unknown_failures(driver_error):
    classified = business_profile_routes._classify_integrity_error(
        IntegrityError("redacted statement", {}, driver_error),
        operation_kind="write",
    )

    assert classified is None


@pytest.mark.asyncio
async def test_commit_write_rolls_back_and_reraises_unclassified_integrity_error():
    integrity_error = IntegrityError(
        "redacted statement",
        {},
        FakeAsyncpgError("private check detail", sqlstate="23514"),
    )

    class SessionProbe:
        rolled_back = False

        async def rollback(self):
            self.rolled_back = True

        async def commit(self):
            raise AssertionError("commit must not run")

    async def fail_with_integrity_error():
        raise integrity_error

    session = SessionProbe()
    with pytest.raises(IntegrityError) as captured:
        await business_profile_routes._commit_write(session, fail_with_integrity_error())

    assert captured.value is integrity_error
    assert session.rolled_back

PROFILE = {
    "name": "EU Operations",
    "legal_name": "Example Manufacturing GmbH",
    "trading_name": "Example Print",
    "country_code": "de",
    "default_currency": "eur",
    "timezone": "Europe/Berlin",
    "default_locale": "de-DE",
    "billing_mode": "hybrid",
    "is_active": True,
    "is_default": True,
    "addresses": [
        {
            "kind": "registered",
            "label": "Head office",
            "additional": None,
            "street": "Musterstrasse 1",
            "street_2": None,
            "postal_code": "10115",
            "city": "Berlin",
            "region": "Berlin",
            "country_code": "de",
            "is_default": True,
        }
    ],
    "tax_identifiers": [
        {
            "kind": "vat",
            "value": "DE123456789",
            "country_code": "de",
            "is_primary": True,
            "valid_from": None,
            "valid_until": None,
        }
    ],
    "bank_accounts": [
        {
            "label": "EUR account",
            "account_holder": "Example Manufacturing GmbH",
            "bank_name": "Example Bank",
            "country_code": "de",
            "currency": "eur",
            "iban": "DE02120300000000202051",
            "bic": "BYLADEM1001",
            "account_number": None,
            "routing_number": None,
            "is_default": True,
        }
    ],
}


def profile_payload(*, name: str = "EU Operations", is_default: bool = True) -> dict:
    payload = deepcopy(PROFILE)
    payload["name"] = name
    payload["legal_name"] = f"{name} GmbH"
    payload["is_default"] = is_default
    return payload


async def create_profile(
    client: AsyncClient,
    *,
    name: str = "EU Operations",
    is_default: bool = True,
) -> dict:
    response = await client.post(BASE_URL + "/", json=profile_payload(name=name, is_default=is_default))
    assert response.status_code == 201, response.text
    return response.json()


async def create_permission_user(db_session, *, username: str, permissions: list[str]) -> str:
    group = Group(name=f"{username}-permissions", permissions=permissions)
    user = User(username=username, password_hash="unused", role="user")
    user.groups.append(group)
    db_session.add_all([group, user])
    await db_session.flush()
    await db_session.commit()
    return create_access_token(data={"sub": username})


@pytest.mark.asyncio
async def test_create_normalizes_nested_codes_and_creates_customer_sequence(
    async_client: AsyncClient,
    db_session,
):
    payload = profile_payload(is_default=False)
    payload["name"] = "  EU Operations  "
    payload["tax_identifiers"][0]["kind"] = " VAT "

    response = await async_client.post(BASE_URL + "/", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "EU Operations"
    assert body["country_code"] == "DE"
    assert body["default_currency"] == "EUR"
    assert body["addresses"][0]["country_code"] == "DE"
    assert body["tax_identifiers"][0]["country_code"] == "DE"
    assert body["tax_identifiers"][0]["kind"] == "vat"
    assert body["bank_accounts"][0]["country_code"] == "DE"
    assert body["bank_accounts"][0]["currency"] == "EUR"
    assert body["is_default"] is True
    assert body["version"] == 1
    assert body["created_at"]
    assert body["updated_at"]
    assert all(isinstance(child["id"], int) for key in ("addresses", "tax_identifiers", "bank_accounts") for child in body[key])

    sequence = (
        await db_session.execute(
            select(NumberSequence).where(
                NumberSequence.business_profile_id == body["id"],
                NumberSequence.key == "customer",
            )
        )
    ).scalar_one()
    assert sequence.prefix == "CUST"
    assert sequence.pattern == "{PREFIX}-{#####}"
    assert sequence.next_value == 1
    assert sequence.reset_policy == "none"
    assert sequence.current_period is None


@pytest.mark.asyncio
async def test_default_switching_and_explicit_default_endpoint(async_client: AsyncClient):
    first = await create_profile(async_client, name="EU Operations", is_default=False)
    second = await create_profile(async_client, name="Nordic Operations", is_default=True)

    first_after_create = await async_client.get(f"{BASE_URL}/{first['id']}")
    assert first_after_create.status_code == 200
    assert first_after_create.json()["is_default"] is False
    assert first_after_create.json()["version"] == first["version"] + 1
    assert second["is_default"] is True

    stale_payload = profile_payload(name="EU Operations", is_default=True)
    stale_payload["version"] = first["version"]
    stale = await async_client.put(f"{BASE_URL}/{first['id']}", json=stale_payload)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"

    response = await async_client.post(f"{BASE_URL}/{first['id']}/default")

    assert response.status_code == 200, response.text
    assert response.json()["is_default"] is True
    assert response.json()["version"] == first_after_create.json()["version"] + 1
    second_after_switch = await async_client.get(f"{BASE_URL}/{second['id']}")
    assert second_after_switch.json()["is_default"] is False
    assert second_after_switch.json()["version"] == second["version"] + 1


@pytest.mark.asyncio
async def test_set_default_cas_rejects_competing_deactivation_and_rolls_back_default_clear(
    async_client: AsyncClient,
    test_engine,
):
    previous_default = await create_profile(async_client)
    target = await create_profile(async_client, name="Race Target", is_default=False)
    original_load = business_profile_service._load_business_profile
    competing_session = async_sessionmaker(test_engine, expire_on_commit=False)
    competed = False

    async def load_then_deactivate(session, profile_id, *, for_update=False):
        nonlocal competed
        profile = await original_load(session, profile_id, for_update=for_update)
        if not competed:
            competed = True
            async with competing_session() as competitor:
                result = await competitor.execute(
                    update(BusinessProfile)
                    .where(
                        BusinessProfile.id == profile_id,
                        BusinessProfile.version == target["version"],
                        BusinessProfile.is_active.is_(True),
                    )
                    .values(
                        is_active=False,
                        is_default=False,
                        version=BusinessProfile.version + 1,
                    )
                    .returning(BusinessProfile.id)
                    .execution_options(synchronize_session=False)
                )
                assert result.scalar_one() == profile_id
                await competitor.commit()
        return profile

    with patch.object(
        business_profile_service,
        "_load_business_profile",
        side_effect=load_then_deactivate,
    ):
        response = await async_client.post(f"{BASE_URL}/{target['id']}/default")

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "version_conflict"

    target_after_race = (await async_client.get(f"{BASE_URL}/{target['id']}")).json()
    assert target_after_race["is_active"] is False
    assert target_after_race["is_default"] is False
    assert target_after_race["version"] == target["version"] + 1

    default_after_race = (await async_client.get(f"{BASE_URL}/{previous_default['id']}")).json()
    assert default_after_race["is_default"] is True
    assert default_after_race["version"] == previous_default["version"]


@pytest.mark.asyncio
async def test_put_replaces_all_children_and_rejects_stale_version(async_client: AsyncClient):
    created = await create_profile(async_client)
    original_ids = {
        collection: {child["id"] for child in created[collection]}
        for collection in ("addresses", "tax_identifiers", "bank_accounts")
    }
    replacement = profile_payload()
    replacement["version"] = created["version"]
    replacement["addresses"] = [
        {
            **replacement["addresses"][0],
            "label": "Registered office",
            "street": "Neue Strasse 9",
            "postal_code": "10999",
        }
    ]
    replacement["tax_identifiers"] = [
        {
            **replacement["tax_identifiers"][0],
            "kind": "registration",
            "value": "HRB-12345",
        }
    ]
    replacement["bank_accounts"] = [
        {
            **replacement["bank_accounts"][0],
            "label": "Replacement account",
            "iban": None,
            "account_number": "0012345678",
        }
    ]

    response = await async_client.put(f"{BASE_URL}/{created['id']}", json=replacement)

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["version"] == created["version"] + 1
    assert updated["created_at"] == created["created_at"]
    assert updated["addresses"][0]["street"] == "Neue Strasse 9"
    assert updated["tax_identifiers"][0]["kind"] == "registration"
    assert updated["bank_accounts"][0]["account_number"] == "0012345678"
    for collection in original_ids:
        assert len(updated[collection]) == 1
        assert updated[collection][0]["id"] not in original_ids[collection]

    stale = await async_client.put(f"{BASE_URL}/{created['id']}", json=replacement)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"


@pytest.mark.asyncio
async def test_put_cas_rejects_database_version_advanced_outside_request(
    async_client: AsyncClient,
    test_engine,
):
    created = await create_profile(async_client)
    losing_payload = profile_payload()
    losing_payload["name"] = "Losing Update"
    losing_payload["version"] = created["version"]
    competing_session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with competing_session() as competitor:
        await competitor.execute(
            update(BusinessProfile)
            .where(BusinessProfile.id == created["id"])
            .values(
                name="Concurrent Winner",
                version=BusinessProfile.version + 1,
            )
        )
        await competitor.commit()

    response = await async_client.put(f"{BASE_URL}/{created['id']}", json=losing_payload)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "version_conflict"
    winner = await async_client.get(f"{BASE_URL}/{created['id']}")
    assert winner.status_code == 200
    assert winner.json()["name"] == "Concurrent Winner"
    assert winner.json()["version"] == created["version"] + 1
    assert winner.json()["addresses"][0]["street"] == created["addresses"][0]["street"]


@pytest.mark.asyncio
async def test_update_cannot_remove_the_usable_default(async_client: AsyncClient):
    created = await create_profile(async_client)

    for changes in ({"is_default": False}, {"is_active": False}):
        payload = profile_payload()
        payload.update(changes)
        payload["version"] = created["version"]
        response = await async_client.put(f"{BASE_URL}/{created['id']}", json=payload)

        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "resource_in_use"


@pytest.mark.asyncio
async def test_delete_invariants_and_owned_sequence_cascade(async_client: AsyncClient, db_session):
    default_profile = await create_profile(async_client, name="EU Operations")
    other_profile = await create_profile(async_client, name="UK Operations", is_default=False)

    blocked = await async_client.delete(f"{BASE_URL}/{default_profile['id']}")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "resource_in_use"

    deleted = await async_client.delete(f"{BASE_URL}/{other_profile['id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert await db_session.get(BusinessProfile, other_profile["id"]) is None
    sequence = (
        await db_session.execute(
            select(NumberSequence).where(NumberSequence.business_profile_id == other_profile["id"])
        )
    ).scalar_one_or_none()
    assert sequence is None


@pytest.mark.asyncio
async def test_delete_rejects_customer_account_reference(async_client: AsyncClient, db_session):
    await create_profile(async_client, name="EU Operations")
    referenced = await create_profile(async_client, name="Referenced Operations", is_default=False)
    customer = Customer(kind="company", display_name="Reference Customer")
    db_session.add(customer)
    await db_session.flush()
    db_session.add(
        CustomerAccount(
            customer_id=customer.id,
            business_profile_id=referenced["id"],
            number="CUST-00001",
            preferred_currency="EUR",
        )
    )
    await db_session.commit()

    response = await async_client.delete(f"{BASE_URL}/{referenced['id']}")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "resource_in_use"


@pytest.mark.asyncio
async def test_deactivation_rejects_customer_account_reference(async_client: AsyncClient, db_session):
    await create_profile(async_client, name="EU Operations")
    referenced = await create_profile(async_client, name="Referenced Operations", is_default=False)
    customer = Customer(kind="company", display_name="Reference Customer")
    db_session.add(customer)
    await db_session.flush()
    db_session.add(
        CustomerAccount(
            customer_id=customer.id,
            business_profile_id=referenced["id"],
            number="CUST-00001",
            preferred_currency="EUR",
        )
    )
    await db_session.commit()

    payload = profile_payload(name="Referenced Operations", is_default=False)
    payload["version"] = referenced["version"]
    payload["is_active"] = False
    response = await async_client.put(f"{BASE_URL}/{referenced['id']}", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "resource_in_use"


@pytest.mark.asyncio
async def test_sqlite_profile_deletion_and_customer_creation_do_not_orphan_accounts(tmp_path):
    database_path = (tmp_path / "profile-customer-race.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}", connect_args={"timeout": 2})

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as setup_session:
        profile = BusinessProfile(
            name="Race Operations",
            legal_name="Race Operations GmbH",
            country_code="DE",
            default_currency="EUR",
        )
        setup_session.add(profile)
        await setup_session.flush()
        setup_session.add(
            NumberSequence(
                business_profile_id=profile.id,
                key="customer",
                prefix="CUST",
                pattern="{PREFIX}-{#####}",
            )
        )
        await setup_session.commit()
        profile_id = profile.id

    customer_data = CustomerCreate.model_validate(
        {
            "kind": "company",
            "display_name": "Race Customer",
            "company_name": "Race Customer GmbH",
            "status": "active",
            "preferred_locale": "en",
            "accounts": [
                {
                    "business_profile_id": profile_id,
                    "number": "RACE-1",
                    "preferred_currency": "EUR",
                }
            ],
            "contacts": [],
            "addresses": [],
            "tax_identifiers": [],
            "tags": [],
        }
    )

    async def create_customer_after_delete_lock() -> None:
        async with session_factory() as customer_session:
            await customer_service.create_customer(
                customer_session,
                customer_data,
                effective_date=date(2026, 7, 11),
            )
            await customer_session.commit()

    profile_loaded = asyncio.Event()
    allow_delete = asyncio.Event()
    original_load = business_profile_service._load_business_profile

    async def load_then_pause(session, loaded_profile_id, *, for_update=False):
        loaded = await original_load(session, loaded_profile_id, for_update=for_update)
        profile_loaded.set()
        await allow_delete.wait()
        return loaded

    async def delete_profile() -> None:
        async with session_factory() as delete_session:
            await business_profile_service.delete_business_profile(delete_session, profile_id)
            await delete_session.commit()

    with patch.object(business_profile_service, "_load_business_profile", side_effect=load_then_pause):
        delete_task = asyncio.create_task(delete_profile())
        await asyncio.wait_for(profile_loaded.wait(), timeout=2)
        create_task = asyncio.create_task(create_customer_after_delete_lock())
        await asyncio.sleep(0.1)
        assert not create_task.done()
        allow_delete.set()
        await asyncio.wait_for(delete_task, timeout=2)

    with pytest.raises(ResourceNotFoundError):
        await asyncio.wait_for(create_task, timeout=2)
    async with session_factory() as verify_session:
        assert await verify_session.scalar(select(func.count(CustomerAccount.id))) == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_duplicate_name_has_stable_error_and_clean_transaction(async_client: AsyncClient):
    await create_profile(async_client)

    duplicate = await async_client.post(BASE_URL + "/", json=profile_payload())

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "duplicate_business_key",
        "message": DUPLICATE_MESSAGE,
    }
    follow_up = await async_client.post(BASE_URL + "/", json=profile_payload(name="Clean Transaction"))
    assert follow_up.status_code == 201, follow_up.text


@pytest.mark.asyncio
async def test_duplicate_tax_integrity_error_is_specific_and_transaction_recovers(async_client: AsyncClient):
    existing = await create_profile(async_client)
    request_payload = profile_payload(name="Tax Collision", is_default=False)

    async def insert_duplicate_tax_rows(session, _data):
        session.add_all(
            [
                BusinessProfileTaxIdentifier(
                    business_profile_id=existing["id"],
                    kind="registration",
                    value="DUPLICATE-REGISTRATION",
                ),
                BusinessProfileTaxIdentifier(
                    business_profile_id=existing["id"],
                    kind="registration",
                    value="DUPLICATE-REGISTRATION",
                ),
            ]
        )
        await session.flush()

    with patch.object(
        business_profile_service,
        "create_business_profile",
        side_effect=insert_duplicate_tax_rows,
    ):
        duplicate = await async_client.post(BASE_URL + "/", json=request_payload)

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "duplicate_business_key",
        "message": TAX_DUPLICATE_MESSAGE,
    }
    follow_up = await async_client.post(BASE_URL + "/", json=request_payload)
    assert follow_up.status_code == 201, follow_up.text


@pytest.mark.asyncio
async def test_default_uniqueness_integrity_error_requests_retry(async_client: AsyncClient):
    await create_profile(async_client)

    async def insert_competing_default(session, data):
        profile = BusinessProfile(
            name=data.name,
            legal_name=data.legal_name,
            trading_name=data.trading_name,
            country_code=data.country_code,
            default_currency=data.default_currency,
            timezone=data.timezone,
            default_locale=data.default_locale,
            billing_mode=data.billing_mode,
            is_active=True,
            is_default=True,
        )
        session.add(profile)
        await session.flush()
        return profile

    with patch.object(
        business_profile_service,
        "create_business_profile",
        side_effect=insert_competing_default,
    ):
        response = await async_client.post(
            BASE_URL + "/",
            json=profile_payload(name="Concurrent Default", is_default=True),
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "version_conflict"
    assert "retry" in response.json()["detail"]["message"].lower()


@pytest.mark.asyncio
async def test_children_are_returned_in_deterministic_id_order(async_client: AsyncClient):
    payload = profile_payload()
    payload["addresses"].append(
        {
            **payload["addresses"][0],
            "kind": "billing",
            "label": "UK billing",
            "street": "10 Market Street",
            "postal_code": "SW1A 1AA",
            "city": "London",
            "region": None,
            "country_code": "GB",
        }
    )
    payload["tax_identifiers"].append(
        {
            **payload["tax_identifiers"][0],
            "kind": "registration",
            "value": "HRB-12345",
            "country_code": "GB",
        }
    )
    payload["bank_accounts"].append(
        {
            **payload["bank_accounts"][0],
            "label": "USD account",
            "country_code": "US",
            "currency": "USD",
            "iban": None,
            "account_number": "000123456789",
        }
    )

    created = await async_client.post(BASE_URL + "/", json=payload)
    assert created.status_code == 201, created.text
    detail = await async_client.get(f"{BASE_URL}/{created.json()['id']}")
    assert detail.status_code == 200
    for collection in ("addresses", "tax_identifiers", "bank_accounts"):
        child_ids = [child["id"] for child in detail.json()[collection]]
        assert child_ids == sorted(child_ids)

    replacement = deepcopy(payload)
    replacement["version"] = detail.json()["version"]
    updated = await async_client.put(f"{BASE_URL}/{created.json()['id']}", json=replacement)
    assert updated.status_code == 200, updated.text
    updated_detail = await async_client.get(f"{BASE_URL}/{created.json()['id']}")
    for collection in ("addresses", "tax_identifiers", "bank_accounts"):
        child_ids = [child["id"] for child in updated_detail.json()[collection]]
        assert child_ids == sorted(child_ids)


def invalid_profile_cases() -> list[tuple[str, dict]]:
    cases: list[tuple[str, dict]] = []

    payload = profile_payload()
    payload["timezone"] = "Mars/Olympus"
    cases.append(("timezone", payload))

    payload = profile_payload()
    payload["country_code"] = "d"
    cases.append(("country", payload))

    payload = profile_payload()
    payload["default_currency"] = "EURO"
    cases.append(("currency", payload))

    payload = profile_payload()
    payload["country_code"] = "ZZ"
    cases.append(("unknown country", payload))

    payload = profile_payload()
    payload["default_currency"] = "FOO"
    cases.append(("unknown currency", payload))

    payload = profile_payload()
    payload["addresses"][0]["country_code"] = "d"
    cases.append(("address country", payload))

    payload = profile_payload()
    payload["addresses"][0]["country_code"] = "ZZ"
    cases.append(("unknown address country", payload))

    payload = profile_payload()
    payload["tax_identifiers"][0]["country_code"] = "d"
    cases.append(("tax country", payload))

    payload = profile_payload()
    payload["tax_identifiers"][0]["kind"] = "ß" * 17
    cases.append(("tax kind expands beyond database width", payload))

    payload = profile_payload()
    payload["tax_identifiers"][0]["country_code"] = "ZZ"
    cases.append(("unknown tax country", payload))

    payload = profile_payload()
    payload["bank_accounts"][0]["country_code"] = "d"
    cases.append(("bank country", payload))

    payload = profile_payload()
    payload["bank_accounts"][0]["country_code"] = "ZZ"
    cases.append(("unknown bank country", payload))

    payload = profile_payload()
    payload["bank_accounts"][0]["currency"] = "EURO"
    cases.append(("bank currency", payload))

    payload = profile_payload()
    payload["bank_accounts"][0]["currency"] = "FOO"
    cases.append(("unknown bank currency", payload))

    payload = profile_payload()
    payload["billing_mode"] = "manual"
    cases.append(("billing mode", payload))

    payload = profile_payload()
    payload["name"] = "   "
    cases.append(("blank profile name", payload))

    payload = profile_payload()
    payload["addresses"][0]["street"] = "   "
    cases.append(("blank address street", payload))

    payload = profile_payload()
    payload["tax_identifiers"].append(
        {
            **payload["tax_identifiers"][0],
            "kind": "VAT",
            "value": "DE987654321",
        }
    )
    cases.append(("case-insensitive duplicate primary tax kind", payload))

    payload = profile_payload()
    payload["tax_identifiers"][0].update({"kind": "VAT", "value": "de123456789", "is_primary": False})
    payload["tax_identifiers"].append(
        {
            **payload["tax_identifiers"][0],
            "kind": "vat",
            "value": "DE123456789",
        }
    )
    cases.append(("case-insensitive duplicate tax identifier", payload))

    payload = profile_payload()
    payload["tax_identifiers"][0].update({"kind": "\U00010570", "value": "A", "is_primary": True})
    payload["tax_identifiers"].append(
        {**payload["tax_identifiers"][0], "kind": "\U00010597", "value": "B"}
    )
    cases.append(("Unicode 15.1 duplicate primary tax kind", payload))

    payload = profile_payload()
    payload["addresses"].append(
        {
            **payload["addresses"][0],
            "street": "Second registered street 2",
        }
    )
    cases.append(("duplicate default address kind", payload))

    payload = profile_payload()
    payload["bank_accounts"].append(
        {
            **payload["bank_accounts"][0],
            "label": "Second EUR account",
            "iban": "DE75512108001245126199",
        }
    )
    cases.append(("duplicate default bank currency", payload))

    payload = profile_payload()
    payload["addresses"] = [{**payload["addresses"][0], "kind": "billing"}]
    cases.append(("missing registered address", payload))

    payload = profile_payload()
    payload["bank_accounts"][0]["iban"] = "  "
    payload["bank_accounts"][0]["account_number"] = None
    cases.append(("missing bank identifier", payload))

    payload = profile_payload()
    payload["tax_identifiers"][0]["valid_from"] = date(2026, 2, 1).isoformat()
    payload["tax_identifiers"][0]["valid_until"] = date(2026, 1, 31).isoformat()
    cases.append(("reversed tax validity", payload))

    return cases


@pytest.mark.asyncio
@pytest.mark.parametrize(("case_name", "payload"), invalid_profile_cases())
async def test_invalid_profile_payloads_return_422(
    async_client: AsyncClient,
    case_name: str,
    payload: dict,
):
    response = await async_client.post(BASE_URL + "/", json=payload)

    assert response.status_code == 422, f"{case_name}: {response.text}"


@pytest.mark.asyncio
async def test_put_version_zero_returns_422(async_client: AsyncClient):
    profile = await create_profile(async_client)
    payload = profile_payload()
    payload["version"] = 0

    response = await async_client.put(f"{BASE_URL}/{profile['id']}", json=payload)

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_optional_whitespace_is_normalized_to_none(async_client: AsyncClient):
    payload = profile_payload()
    payload["trading_name"] = "   "
    payload["addresses"][0].update(
        {
            "label": "   ",
            "additional": "   ",
            "street_2": "   ",
            "region": "   ",
        }
    )
    payload["tax_identifiers"][0]["country_code"] = "   "
    payload["bank_accounts"][0].update(
        {
            "bank_name": "   ",
            "country_code": "   ",
            "iban": "   ",
            "bic": "   ",
            "account_number": "  0012345678  ",
            "routing_number": "   ",
        }
    )

    response = await async_client.post(BASE_URL + "/", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["trading_name"] is None
    assert body["addresses"][0]["label"] is None
    assert body["addresses"][0]["additional"] is None
    assert body["addresses"][0]["street_2"] is None
    assert body["addresses"][0]["region"] is None
    assert body["tax_identifiers"][0]["country_code"] is None
    assert body["bank_accounts"][0]["bank_name"] is None
    assert body["bank_accounts"][0]["country_code"] is None
    assert body["bank_accounts"][0]["iban"] is None
    assert body["bank_accounts"][0]["bic"] is None
    assert body["bank_accounts"][0]["account_number"] == "0012345678"
    assert body["bank_accounts"][0]["routing_number"] is None


@pytest.mark.asyncio
async def test_list_detail_and_include_inactive(async_client: AsyncClient):
    active = await create_profile(async_client, name="EU Operations")
    inactive = await create_profile(async_client, name="Legacy Operations", is_default=False)
    update = profile_payload(name="Legacy Operations", is_default=False)
    update["is_active"] = False
    update["version"] = inactive["version"]
    response = await async_client.put(f"{BASE_URL}/{inactive['id']}", json=update)
    assert response.status_code == 200, response.text

    active_only = await async_client.get(BASE_URL + "/")
    including_inactive = await async_client.get(BASE_URL + "/?includeInactive=true")
    detail = await async_client.get(f"{BASE_URL}/{inactive['id']}")

    assert [item["id"] for item in active_only.json()] == [active["id"]]
    assert {item["id"] for item in including_inactive.json()} == {active["id"], inactive["id"]}
    assert detail.status_code == 200
    assert detail.json()["is_active"] is False
    assert detail.json()["addresses"]


@pytest.mark.asyncio
async def test_options_are_safe_and_static_route_wins(async_client: AsyncClient):
    profile = await create_profile(async_client)

    response = await async_client.get(BASE_URL + "/options")

    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            key: profile[key]
            for key in (
                "id",
                "name",
                "country_code",
                "default_currency",
                "timezone",
                "default_locale",
                "billing_mode",
                "is_default",
                "is_active",
            )
        }
    ]
    assert set(response.json()[0]) == OPTION_FIELDS
    assert not ({"addresses", "tax_identifiers", "bank_accounts"} & set(response.json()[0]))


@pytest.mark.asyncio
async def test_not_found_problem_details(async_client: AsyncClient):
    missing_update = profile_payload()
    missing_update["version"] = 1
    requests = (
        (async_client.get, f"{BASE_URL}/99999", {}),
        (async_client.put, f"{BASE_URL}/99999", {"json": missing_update}),
        (async_client.post, f"{BASE_URL}/99999/default", {}),
        (async_client.delete, f"{BASE_URL}/99999", {}),
    )
    for method, path, kwargs in requests:
        response = await method(path, **kwargs)
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"
        assert response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_full_profile_read_permission_gates_list_and_detail(async_client: AsyncClient, db_session):
    profile = await create_profile(async_client)
    operator_token = await create_permission_user(
        db_session,
        username="profile-operator",
        permissions=[Permission.CUSTOMERS_READ.value],
    )
    settings_reader_token = await create_permission_user(
        db_session,
        username="profile-settings-reader",
        permissions=[Permission.ORDER_SETTINGS_READ.value],
    )
    settings_manager_token = await create_permission_user(
        db_session,
        username="profile-settings-manager",
        permissions=[Permission.ORDER_SETTINGS_MANAGE.value],
    )
    operator_headers = {"Authorization": f"Bearer {operator_token}"}
    read_headers = {"Authorization": f"Bearer {settings_reader_token}"}
    manage_headers = {"Authorization": f"Bearer {settings_manager_token}"}

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        for path in (BASE_URL + "/", f"{BASE_URL}/{profile['id']}"):
            assert (await async_client.get(path, headers=operator_headers)).status_code == 403
            assert (await async_client.get(path, headers=manage_headers)).status_code == 403
            assert (await async_client.get(path, headers=read_headers)).status_code == 200


@pytest.mark.asyncio
async def test_manage_permission_gates_all_mutation_routes(async_client: AsyncClient, db_session):
    await create_profile(async_client, name="Default Operations")
    update_target = await create_profile(async_client, name="Update Target", is_default=False)
    delete_target = await create_profile(async_client, name="Delete Target", is_default=False)
    settings_reader_token = await create_permission_user(
        db_session,
        username="profile-mutation-reader",
        permissions=[Permission.ORDER_SETTINGS_READ.value],
    )
    settings_manager_token = await create_permission_user(
        db_session,
        username="profile-mutation-manager",
        permissions=[Permission.ORDER_SETTINGS_MANAGE.value],
    )
    read_headers = {"Authorization": f"Bearer {settings_reader_token}"}
    manage_headers = {"Authorization": f"Bearer {settings_manager_token}"}
    update_payload = profile_payload(name="Update Target", is_default=False)
    update_payload["version"] = update_target["version"]

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        denied_responses = (
            await async_client.post(
                BASE_URL + "/",
                headers=read_headers,
                json=profile_payload(name="Reader Cannot Create", is_default=False),
            ),
            await async_client.put(
                f"{BASE_URL}/{update_target['id']}",
                headers=read_headers,
                json=update_payload,
            ),
            await async_client.post(f"{BASE_URL}/{update_target['id']}/default", headers=read_headers),
            await async_client.delete(f"{BASE_URL}/{delete_target['id']}", headers=read_headers),
        )
        assert all(response.status_code == 403 for response in denied_responses)

        created = await async_client.post(
            BASE_URL + "/",
            headers=manage_headers,
            json=profile_payload(name="Manager Created", is_default=False),
        )
        updated = await async_client.put(
            f"{BASE_URL}/{update_target['id']}",
            headers=manage_headers,
            json=update_payload,
        )
        selected = await async_client.post(
            f"{BASE_URL}/{update_target['id']}/default",
            headers=manage_headers,
        )
        deleted = await async_client.delete(
            f"{BASE_URL}/{delete_target['id']}",
            headers=manage_headers,
        )

    assert created.status_code == 201, created.text
    assert updated.status_code == 200, updated.text
    assert selected.status_code == 200, selected.text
    assert deleted.status_code == 204, deleted.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "permission",
    (
        Permission.CUSTOMERS_READ,
        Permission.CALCULATIONS_READ,
        Permission.ORDERS_READ,
        Permission.COMMERCIAL_DOCUMENTS_READ,
    ),
)
async def test_options_accept_each_safe_read_permission(
    async_client: AsyncClient,
    db_session,
    permission: Permission,
):
    await create_profile(async_client)
    token = await create_permission_user(
        db_session,
        username=f"profile-options-{permission.name.lower()}",
        permissions=[permission.value],
    )

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        response = await async_client.get(
            BASE_URL + "/options",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200, response.text
    assert set(response.json()[0]) == OPTION_FIELDS


@pytest.mark.asyncio
async def test_api_keys_fail_closed_for_all_business_profile_routes(async_client: AsyncClient, db_session):
    default_profile = await create_profile(async_client)
    mutable_profile = await create_profile(async_client, name="Mutable Operations", is_default=False)
    full_key, key_hash, key_prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="business-profile-key",
            key_hash=key_hash,
            key_prefix=key_prefix,
            can_read_status=True,
            enabled=True,
        )
    )
    await db_session.commit()
    headers = {"X-API-Key": full_key}
    update_payload = profile_payload(name="Mutable Operations", is_default=False)
    update_payload["version"] = mutable_profile["version"]

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        responses = {
            "list": await async_client.get(BASE_URL + "/", headers=headers),
            "detail": await async_client.get(f"{BASE_URL}/{default_profile['id']}", headers=headers),
            "options": await async_client.get(BASE_URL + "/options", headers=headers),
            "create": await async_client.post(
                BASE_URL + "/",
                headers=headers,
                json=profile_payload(name="API Key Cannot Create", is_default=False),
            ),
            "update": await async_client.put(
                f"{BASE_URL}/{mutable_profile['id']}",
                headers=headers,
                json=update_payload,
            ),
            "set default": await async_client.post(
                f"{BASE_URL}/{mutable_profile['id']}/default",
                headers=headers,
            ),
            "delete": await async_client.delete(f"{BASE_URL}/{mutable_profile['id']}", headers=headers),
        }

    assert {name: response.status_code for name, response in responses.items()} == dict.fromkeys(responses, 403)
