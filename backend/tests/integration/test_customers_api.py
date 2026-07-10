"""Integration coverage for customer master-data CRUD and permissions."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api.routes import customers as customer_routes
from backend.app.core.auth import generate_api_key
from backend.app.core.database import Base
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.customer import Customer, CustomerAccount, CustomerTag
from backend.app.models.number_sequence import NumberSequence
from backend.app.schemas.customer import CustomerCreate
from backend.app.services import (
    customer as customer_service,
)
from backend.app.services.order_errors import DuplicateBusinessKeyError, ResourceInUseError
from backend.tests.integration.test_business_profiles_api import (
    create_permission_user,
    create_profile,
    profile_payload,
)

BASE_URL = "/api/v1/customers"
DUPLICATE_MESSAGE = "A customer account with this profile and number already exists"
GENERIC_INTEGRITY_MESSAGE = "The customer conflicts with existing data"
PROFILE_UNAVAILABLE_MESSAGE = "The selected business profile is no longer available"


class FakeAsyncpgError(Exception):
    def __init__(
        self,
        message: str,
        *,
        constraint_name: str | None = None,
        sqlstate: str | None = None,
    ):
        super().__init__(message)
        self.constraint_name = constraint_name
        self.sqlstate = sqlstate


def customer_payload(profile_id: int) -> dict:
    return {
        "kind": "company",
        "display_name": "Atelier Nord GmbH",
        "company_name": "Atelier Nord GmbH",
        "first_name": None,
        "last_name": None,
        "status": "active",
        "preferred_locale": "de-DE",
        "notes": "Priority customer",
        "accounts": [
            {
                "business_profile_id": profile_id,
                "number": None,
                "preferred_currency": "eur",
                "payment_term_days": 14,
                "delivery_terms": "DHL shipment",
                "discount_percent": "2.50",
                "is_active": True,
            }
        ],
        "contacts": [
            {
                "salutation": "Herr",
                "first_name": "Jonas",
                "last_name": "Berger",
                "role": "Purchasing",
                "email": "einkauf@example.test",
                "phone": "+49 30 123456",
                "is_primary": True,
                "include_on_documents": True,
            }
        ],
        "addresses": [
            {
                "kind": "billing",
                "label": "Head office",
                "additional": None,
                "street": "Zwickauer Strasse 18",
                "street_2": None,
                "postal_code": "09111",
                "city": "Chemnitz",
                "region": "Sachsen",
                "country_code": "de",
                "is_default": True,
            }
        ],
        "tax_identifiers": [
            {
                "kind": " VAT ",
                "value": "DE999999999",
                "country_code": "de",
                "validation_status": "unchecked",
            }
        ],
        "tags": [" B2B ", "priority", "b2b"],
    }


async def create_customer(
    client: AsyncClient,
    profile_id: int,
    *,
    payload: dict | None = None,
) -> dict:
    response = await client.post(
        BASE_URL + "/",
        json=payload if payload is not None else customer_payload(profile_id),
    )
    assert response.status_code == 201, response.text
    return response.json()


def person_payload(profile_id: int, *, display_name: str = "Ada Lovelace") -> dict:
    payload = customer_payload(profile_id)
    payload.update(
        {
            "kind": "person",
            "display_name": display_name,
            "company_name": None,
            "first_name": "Ada",
            "last_name": "Lovelace",
        }
    )
    return payload


@pytest.mark.asyncio
async def test_create_customer_auto_numbers_and_returns_normalized_aggregate(
    async_client: AsyncClient,
    db_session,
):
    profile = await create_profile(async_client)
    payload = customer_payload(profile["id"])
    payload["notes"] = "   "
    payload["contacts"][0]["salutation"] = "   "

    response = await async_client.post(BASE_URL + "/", json=payload)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["accounts"][0]["number"] == "CUST-00001"
    assert body["accounts"][0]["preferred_currency"] == "EUR"
    assert body["accounts"][0]["discount_percent"] == "2.50"
    assert body["addresses"][0]["country_code"] == "DE"
    assert body["tax_identifiers"][0]["kind"] == "vat"
    assert body["tags"] == ["B2B", "priority"]
    assert body["notes"] is None
    assert body["contacts"][0]["salutation"] is None
    assert body["version"] == 1
    assert body["created_at"]
    assert body["updated_at"]
    for collection in ("accounts", "contacts", "addresses", "tax_identifiers"):
        assert all(isinstance(child["id"], int) for child in body[collection])

    account = (
        await db_session.execute(
            select(CustomerAccount).where(CustomerAccount.customer_id == body["id"])
        )
    ).scalar_one()
    assert isinstance(account.discount_percent, Decimal)
    assert account.discount_percent == Decimal("2.50")


@pytest.mark.asyncio
async def test_discount_scale_is_exact_in_create_persistence_and_fresh_detail(
    async_client: AsyncClient,
    db_session,
):
    profile = await create_profile(async_client)
    invalid_payload = customer_payload(profile["id"])
    invalid_payload["accounts"][0]["discount_percent"] = "1.239"
    invalid = await async_client.post(BASE_URL + "/", json=invalid_payload)
    assert invalid.status_code == 422, invalid.text

    valid_payload = customer_payload(profile["id"])
    valid_payload["accounts"][0]["discount_percent"] = "2.000"
    created = await create_customer(async_client, profile["id"], payload=valid_payload)
    assert created["accounts"][0]["discount_percent"] == "2.00"

    persisted = (
        await db_session.execute(
            select(CustomerAccount).where(CustomerAccount.customer_id == created["id"])
        )
    ).scalar_one()
    assert persisted.discount_percent == Decimal("2.00")
    assert persisted.discount_percent.as_tuple().exponent == -2

    detail = await async_client.get(f"{BASE_URL}/{created['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["accounts"][0]["discount_percent"] == "2.00"
    assert detail.json() == created


@pytest.mark.asyncio
async def test_supplied_number_is_preserved(async_client: AsyncClient):
    profile = await create_profile(async_client)
    payload = customer_payload(profile["id"])
    payload["accounts"][0]["number"] = "  CLIENT-42  "

    created = await create_customer(async_client, profile["id"], payload=payload)

    assert created["accounts"][0]["number"] == "CLIENT-42"


@pytest.mark.asyncio
async def test_manual_number_does_not_block_following_automatic_numbers(
    async_client: AsyncClient,
    db_session,
):
    profile = await create_profile(async_client)
    manual_payload = customer_payload(profile["id"])
    manual_payload["accounts"][0]["number"] = "CUST-00001"
    await create_customer(async_client, profile["id"], payload=manual_payload)

    generated_numbers: list[str] = []
    for index in range(2):
        payload = customer_payload(profile["id"])
        payload["display_name"] = f"Automatic Customer {index}"
        payload["company_name"] = f"Automatic Customer {index} GmbH"
        created = await create_customer(async_client, profile["id"], payload=payload)
        generated_numbers.append(created["accounts"][0]["number"])

    assert generated_numbers == ["CUST-00002", "CUST-00003"]
    sequence = (
        await db_session.execute(
            select(NumberSequence).where(
                NumberSequence.business_profile_id == profile["id"],
                NumberSequence.key == "customer",
            )
        )
    ).scalar_one()
    await db_session.refresh(sequence)
    assert sequence.next_value == 4


@pytest.mark.asyncio
async def test_manual_and_automatic_writes_use_the_same_sequence_lock(
    tmp_path,
):
    database_path = (tmp_path / "manual-auto-lock.db").as_posix()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 2},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as setup_session:
        profile = BusinessProfile(
            name="Number Lock Probe",
            legal_name="Number Lock Probe GmbH",
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

    manual_payload = customer_payload(profile_id)
    manual_payload["accounts"][0]["number"] = "CUST-00001"
    automatic_payload = customer_payload(profile_id)
    automatic_payload["display_name"] = "Automatic Lock User"
    automatic_payload["company_name"] = "Automatic Lock User GmbH"

    async def create_automatic_customer() -> str:
        async with session_factory() as automatic_session:
            automatic = await customer_service.create_customer(
                automatic_session,
                CustomerCreate.model_validate(automatic_payload),
                effective_date=date(2026, 7, 10),
            )
            await automatic_session.commit()
            return automatic.accounts[0].number

    async with session_factory() as manual_session:
        await customer_service._validate_business_profiles(manual_session, [profile_id])
        automatic_create = asyncio.create_task(create_automatic_customer())
        await asyncio.sleep(0.1)
        was_blocked = not automatic_create.done()
        await customer_service.create_customer(
            manual_session,
            CustomerCreate.model_validate(manual_payload),
            effective_date=date(2026, 7, 10),
        )
        await manual_session.commit()
        automatic_number = await asyncio.wait_for(automatic_create, timeout=2)

    await engine.dispose()
    assert was_blocked
    assert automatic_number == "CUST-00002"


@pytest.mark.asyncio
async def test_numbers_are_unique_per_profile_and_customer_can_have_multiple_accounts(
    async_client: AsyncClient,
):
    first_profile = await create_profile(async_client)
    second_profile = await create_profile(
        async_client,
        name="Second Operations",
        is_default=False,
    )
    payload = customer_payload(first_profile["id"])
    payload["accounts"] = [
        {**payload["accounts"][0], "number": "SHARED-100"},
        {
            **payload["accounts"][0],
            "business_profile_id": second_profile["id"],
            "number": "SHARED-100",
            "preferred_currency": "usd",
        },
    ]

    created = await create_customer(async_client, first_profile["id"], payload=payload)

    assert [account["number"] for account in created["accounts"]] == ["SHARED-100", "SHARED-100"]
    assert [account["preferred_currency"] for account in created["accounts"]] == ["EUR", "USD"]

    duplicate_payload = customer_payload(first_profile["id"])
    duplicate_payload["display_name"] = "Duplicate Number"
    duplicate_payload["company_name"] = "Duplicate Number GmbH"
    duplicate_payload["accounts"][0]["number"] = "SHARED-100"
    duplicate = await async_client.post(BASE_URL + "/", json=duplicate_payload)

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "duplicate_business_key",
        "message": DUPLICATE_MESSAGE,
    }


@pytest.mark.asyncio
async def test_missing_inactive_and_duplicate_account_profiles_are_rejected(
    async_client: AsyncClient,
):
    active_profile = await create_profile(async_client)
    inactive_profile = await create_profile(
        async_client,
        name="Inactive Operations",
        is_default=False,
    )
    inactive_update = profile_payload(name="Inactive Operations", is_default=False)
    inactive_update["is_active"] = False
    inactive_update["version"] = inactive_profile["version"]
    response = await async_client.put(
        f"/api/v1/business-profiles/{inactive_profile['id']}",
        json=inactive_update,
    )
    assert response.status_code == 200, response.text

    missing_payload = customer_payload(99999)
    missing = await async_client.post(BASE_URL + "/", json=missing_payload)
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "not_found"

    inactive = await async_client.post(
        BASE_URL + "/",
        json=customer_payload(inactive_profile["id"]),
    )
    assert inactive.status_code == 409
    assert inactive.json()["detail"]["code"] == "resource_in_use"

    duplicate_payload = customer_payload(active_profile["id"])
    duplicate_payload["accounts"].append(deepcopy(duplicate_payload["accounts"][0]))
    duplicate = await async_client.post(BASE_URL + "/", json=duplicate_payload)
    assert duplicate.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("profile_change", ("disable", "delete"))
async def test_customer_profile_lock_blocks_stale_disable_or_delete(
    tmp_path,
    profile_change: str,
):
    database_path = (tmp_path / f"customer-profile-{profile_change}.db").as_posix()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 2},
    )

    @event.listens_for(engine.sync_engine, "connect")
    def configure_sqlite(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as setup_session:
        profile = BusinessProfile(
            name="Lock Probe",
            legal_name="Lock Probe GmbH",
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

    async def change_profile() -> None:
        async with session_factory() as competitor:
            statement = (
                update(BusinessProfile)
                .where(BusinessProfile.id == profile_id)
                .values(is_active=False)
                if profile_change == "disable"
                else delete(BusinessProfile).where(BusinessProfile.id == profile_id)
            )
            await competitor.execute(statement)
            await competitor.commit()

    async with session_factory() as customer_session:
        await customer_service._validate_business_profiles(customer_session, [profile_id])
        competing_change = asyncio.create_task(change_profile())
        await asyncio.sleep(0.1)
        was_blocked = not competing_change.done()
        await customer_session.rollback()
        await asyncio.wait_for(competing_change, timeout=2)

    await engine.dispose()
    assert was_blocked


@pytest.mark.asyncio
async def test_list_filters_searches_projects_profile_fields_and_paginates_distinctly(
    async_client: AsyncClient,
):
    selected_profile = await create_profile(async_client)
    other_profile = await create_profile(async_client, name="Other Operations", is_default=False)

    alpha_payload = customer_payload(selected_profile["id"])
    alpha_payload["display_name"] = "Alpha Studio"
    alpha_payload["company_name"] = "Alpha Studio GmbH"
    alpha_payload["accounts"][0].update(
        {
            "number": "ALPHA-900",
            "payment_term_days": 30,
            "delivery_terms": "DAP Berlin",
            "discount_percent": "4.25",
        }
    )
    alpha_payload["contacts"] = [
        {**alpha_payload["contacts"][0], "email": "match@example.test"},
        {
            **alpha_payload["contacts"][0],
            "email": "second-match@example.test",
            "is_primary": False,
        },
    ]
    alpha_payload["tags"] = ["Priority", "B2B"]
    alpha = await create_customer(async_client, selected_profile["id"], payload=alpha_payload)

    bravo_payload = person_payload(selected_profile["id"], display_name="bravo Person")
    bravo_payload["status"] = "inactive"
    bravo_payload["accounts"][0]["number"] = "BRAVO-200"
    bravo_payload["contacts"] = []
    bravo_payload["addresses"] = []
    bravo_payload["tax_identifiers"] = []
    bravo_payload["tags"] = []
    bravo = await create_customer(async_client, selected_profile["id"], payload=bravo_payload)

    outside_payload = customer_payload(other_profile["id"])
    outside_payload["display_name"] = "Outside Customer"
    outside_payload["company_name"] = "Outside Customer GmbH"
    await create_customer(async_client, other_profile["id"], payload=outside_payload)

    missing_profile_query = await async_client.get(BASE_URL + "/")
    assert missing_profile_query.status_code == 422

    page = await async_client.get(
        BASE_URL + "/",
        params={"business_profile_id": selected_profile["id"], "limit": 1, "offset": 0},
    )
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 2
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 0
    assert [item["id"] for item in page.json()["items"]] == [alpha["id"]]

    all_items = await async_client.get(
        BASE_URL + "/",
        params={"business_profile_id": selected_profile["id"], "limit": 200},
    )
    assert [item["id"] for item in all_items.json()["items"]] == [alpha["id"], bravo["id"]]
    alpha_item = all_items.json()["items"][0]
    assert alpha_item["business_profile_id"] == selected_profile["id"]
    assert alpha_item["account_number"] == "ALPHA-900"
    assert alpha_item["preferred_currency"] == "EUR"
    assert alpha_item["payment_term_days"] == 30
    assert alpha_item["delivery_terms"] == "DAP Berlin"
    assert alpha_item["discount_percent"] == "4.25"
    assert alpha_item["primary_contact_name"] == "Jonas Berger"
    assert alpha_item["primary_contact_email"] == "match@example.test"
    assert alpha_item["billing_city"] == "Chemnitz"
    assert alpha_item["billing_country_code"] == "DE"
    assert alpha_item["tags"] == ["B2B", "Priority"]

    for search in ("ALPHA STUDIO", "alpha-900", "MATCH@EXAMPLE.TEST"):
        response = await async_client.get(
            BASE_URL + "/",
            params={"business_profile_id": selected_profile["id"], "search": search},
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        assert [item["id"] for item in response.json()["items"]] == [alpha["id"]]

    filtered = await async_client.get(
        BASE_URL + "/",
        params={
            "business_profile_id": selected_profile["id"],
            "status": "inactive",
            "kind": "person",
        },
    )
    assert filtered.status_code == 200, filtered.text
    assert [item["id"] for item in filtered.json()["items"]] == [bravo["id"]]


@pytest.mark.asyncio
async def test_unicode_normalization_and_literal_wildcard_search_are_portable(
    async_client: AsyncClient,
    db_session,
):
    profile = await create_profile(async_client)
    unicode_payload = customer_payload(profile["id"])
    unicode_payload["display_name"] = "Straße Ärzte"
    unicode_payload["company_name"] = "Straße Ärzte GmbH"
    unicode_payload["contacts"][0]["email"] = "ärzte@example.test"
    unicode_payload["tags"] = ["Ärzte", "ärzte"]
    unicode_customer = await create_customer(
        async_client,
        profile["id"],
        payload=unicode_payload,
    )

    tag_reuse_payload = customer_payload(profile["id"])
    tag_reuse_payload["display_name"] = "Tag Reuse"
    tag_reuse_payload["company_name"] = "Tag Reuse GmbH"
    tag_reuse_payload["tags"] = ["ärzte"]
    await create_customer(async_client, profile["id"], payload=tag_reuse_payload)
    assert await db_session.scalar(select(func.count(CustomerTag.id))) == 1

    literal_payload = customer_payload(profile["id"])
    literal_payload["display_name"] = "Literal %_ Customer"
    literal_payload["company_name"] = "Literal %_ Customer GmbH"
    literal_payload["contacts"] = []
    literal_payload["addresses"] = []
    literal_payload["tax_identifiers"] = []
    literal_payload["tags"] = []
    literal_customer = await create_customer(
        async_client,
        profile["id"],
        payload=literal_payload,
    )

    for search in ("STRASSE", "ÄRZTE@EXAMPLE.TEST"):
        response = await async_client.get(
            BASE_URL + "/",
            params={"business_profile_id": profile["id"], "search": search},
        )
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()["items"]] == [unicode_customer["id"]]

    for wildcard in ("%", "_"):
        response = await async_client.get(
            BASE_URL + "/",
            params={"business_profile_id": profile["id"], "search": wildcard},
        )
        assert response.status_code == 200, response.text
        assert [item["id"] for item in response.json()["items"]] == [literal_customer["id"]]


@pytest.mark.asyncio
async def test_tag_normalized_key_utf8_byte_boundary_returns_422_before_persistence(
    async_client: AsyncClient,
    db_session,
):
    profile = await create_profile(async_client)
    accepted_name = "\ufdfa" * 15
    rejected_name = "\ufdfa" * 16
    accepted_payload = customer_payload(profile["id"])
    accepted_payload["tags"] = [accepted_name]

    accepted = await async_client.post(BASE_URL + "/", json=accepted_payload)

    assert accepted.status_code == 201, accepted.text
    tag = (await db_session.execute(select(CustomerTag))).scalar_one()
    assert len(tag.name_key.encode("utf-8")) == 495

    rejected_payload = customer_payload(profile["id"])
    rejected_payload["display_name"] = "Rejected Expanded Tag"
    rejected_payload["company_name"] = "Rejected Expanded Tag GmbH"
    rejected_payload["tags"] = [rejected_name]
    rejected = await async_client.post(BASE_URL + "/", json=rejected_payload)

    assert rejected.status_code == 422, rejected.text
    assert await db_session.scalar(select(func.count(CustomerTag.id))) == 1


@pytest.mark.asyncio
async def test_detail_returns_complete_sorted_nested_aggregate(async_client: AsyncClient):
    profile = await create_profile(async_client)
    payload = customer_payload(profile["id"])
    payload["contacts"].append(
        {
            **payload["contacts"][0],
            "first_name": "Mina",
            "last_name": "Schulz",
            "email": "mina@example.test",
            "is_primary": False,
        }
    )
    payload["addresses"].append(
        {
            **payload["addresses"][0],
            "kind": "delivery",
            "label": "Warehouse",
            "street": "Lagerweg 2",
        }
    )
    payload["tax_identifiers"].append(
        {
            **payload["tax_identifiers"][0],
            "kind": "registration",
            "value": "HRB-12345",
        }
    )
    payload["tags"] = ["zeta", "Alpha", "alpha", "Beta"]
    created = await create_customer(async_client, profile["id"], payload=payload)

    detail = await async_client.get(f"{BASE_URL}/{created['id']}")

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert set(body) == {
        "id",
        "kind",
        "display_name",
        "company_name",
        "first_name",
        "last_name",
        "status",
        "preferred_locale",
        "notes",
        "version",
        "created_at",
        "updated_at",
        "accounts",
        "contacts",
        "addresses",
        "tax_identifiers",
        "tags",
    }
    assert body["tags"] == ["Alpha", "Beta", "zeta"]
    for collection in ("accounts", "contacts", "addresses", "tax_identifiers"):
        ids = [child["id"] for child in body[collection]]
        assert ids == sorted(ids)


@pytest.mark.asyncio
async def test_put_replaces_nested_aggregate_and_rejects_sequential_stale_version(
    async_client: AsyncClient,
):
    profile = await create_profile(async_client)
    created = await create_customer(async_client, profile["id"])
    account_id = created["accounts"][0]["id"]
    old_ids = {
        collection: {child["id"] for child in created[collection]}
        for collection in ("contacts", "addresses", "tax_identifiers")
    }
    replacement = customer_payload(profile["id"])
    replacement["version"] = created["version"]
    replacement["display_name"] = "Atelier Nord Updated"
    replacement["company_name"] = "Atelier Nord Updated GmbH"
    replacement["accounts"][0]["number"] = created["accounts"][0]["number"]
    replacement["contacts"][0]["email"] = "updated@example.test"
    replacement["addresses"][0]["city"] = "Leipzig"
    replacement["tax_identifiers"][0]["value"] = "DE999999999"
    replacement["tags"] = ["Updated"]

    response = await async_client.put(f"{BASE_URL}/{created['id']}", json=replacement)

    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["version"] == created["version"] + 1
    assert updated["created_at"] == created["created_at"]
    assert updated["display_name"] == "Atelier Nord Updated"
    assert updated["accounts"][0]["number"] == created["accounts"][0]["number"]
    assert updated["accounts"][0]["id"] == account_id
    assert updated["contacts"][0]["email"] == "updated@example.test"
    assert updated["addresses"][0]["city"] == "Leipzig"
    assert updated["tags"] == ["Updated"]
    for collection, ids in old_ids.items():
        assert all(child["id"] not in ids for child in updated[collection])

    stale = await async_client.put(f"{BASE_URL}/{created['id']}", json=replacement)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "version_conflict"
    detail = await async_client.get(f"{BASE_URL}/{created['id']}")
    assert detail.json()["display_name"] == "Atelier Nord Updated"
    assert detail.json()["version"] == updated["version"]


@pytest.mark.asyncio
async def test_account_identity_tracks_business_profile_when_profiles_are_replaced(
    async_client: AsyncClient,
):
    first_profile = await create_profile(async_client)
    second_profile = await create_profile(
        async_client,
        name="Replacement Operations",
        is_default=False,
    )
    created = await create_customer(async_client, first_profile["id"])
    first_account_id = created["accounts"][0]["id"]

    same_profile = customer_payload(first_profile["id"])
    same_profile["version"] = created["version"]
    same_profile["accounts"][0]["number"] = "RENAMED-100"
    deleted_account_ids: list[int] = []

    def record_delete(_mapper, _connection, account):
        deleted_account_ids.append(account.id)

    event.listen(CustomerAccount, "after_delete", record_delete)
    try:
        renamed = await async_client.put(
            f"{BASE_URL}/{created['id']}",
            json=same_profile,
        )
    finally:
        event.remove(CustomerAccount, "after_delete", record_delete)
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["accounts"][0]["id"] == first_account_id
    assert renamed.json()["accounts"][0]["number"] == "RENAMED-100"
    assert deleted_account_ids == []

    new_profile = customer_payload(second_profile["id"])
    new_profile["version"] = renamed.json()["version"]
    new_profile["accounts"][0]["number"] = "SECOND-100"
    account_events: list[tuple[str, int, int]] = []

    def record_insert(_mapper, _connection, account):
        account_events.append(("insert", account.business_profile_id, account.id))

    def record_replaced_delete(_mapper, _connection, account):
        account_events.append(("delete", account.business_profile_id, account.id))

    event.listen(CustomerAccount, "after_insert", record_insert)
    event.listen(CustomerAccount, "after_delete", record_replaced_delete)
    try:
        replaced = await async_client.put(
            f"{BASE_URL}/{created['id']}",
            json=new_profile,
        )
    finally:
        event.remove(CustomerAccount, "after_insert", record_insert)
        event.remove(CustomerAccount, "after_delete", record_replaced_delete)
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["accounts"][0]["business_profile_id"] == second_profile["id"]
    assert replaced.json()["accounts"][0]["id"] != first_account_id
    assert account_events == [
        ("insert", second_profile["id"], replaced.json()["accounts"][0]["id"]),
        ("delete", first_profile["id"], first_account_id),
    ]


@pytest.mark.asyncio
async def test_conflicting_in_place_account_number_change_rolls_back(
    async_client: AsyncClient,
):
    profile = await create_profile(async_client)
    first_payload = customer_payload(profile["id"])
    first_payload["accounts"][0]["number"] = "LOCKED-100"
    await create_customer(async_client, profile["id"], payload=first_payload)

    second_payload = customer_payload(profile["id"])
    second_payload["display_name"] = "Second Number Owner"
    second_payload["company_name"] = "Second Number Owner GmbH"
    second_payload["accounts"][0]["number"] = "CHANGEABLE-200"
    second = await create_customer(async_client, profile["id"], payload=second_payload)

    conflicting_update = deepcopy(second_payload)
    conflicting_update["version"] = second["version"]
    conflicting_update["accounts"][0]["number"] = "LOCKED-100"
    conflict = await async_client.put(
        f"{BASE_URL}/{second['id']}",
        json=conflicting_update,
    )

    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "duplicate_business_key"
    unchanged = await async_client.get(f"{BASE_URL}/{second['id']}")
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["version"] == second["version"]
    assert unchanged.json()["accounts"][0]["id"] == second["accounts"][0]["id"]
    assert unchanged.json()["accounts"][0]["number"] == "CHANGEABLE-200"


@pytest.mark.asyncio
async def test_put_cas_rejects_competing_database_update(
    async_client: AsyncClient,
    test_engine,
):
    profile = await create_profile(async_client)
    created = await create_customer(async_client, profile["id"])
    losing_payload = customer_payload(profile["id"])
    losing_payload["version"] = created["version"]
    losing_payload["display_name"] = "Losing Update"
    losing_payload["company_name"] = "Losing Update GmbH"
    original_get = customer_service.get_customer
    competing_session = async_sessionmaker(test_engine, expire_on_commit=False)
    competed = False

    async def load_then_advance_version(session, customer_id):
        nonlocal competed
        customer = await original_get(session, customer_id)
        if not competed:
            competed = True
            async with competing_session() as competitor:
                await competitor.execute(
                    update(Customer)
                    .where(Customer.id == customer_id)
                    .values(
                        display_name="Concurrent Winner",
                        version=Customer.version + 1,
                    )
                )
                await competitor.commit()
        return customer

    with patch.object(customer_service, "get_customer", side_effect=load_then_advance_version):
        response = await async_client.put(
            f"{BASE_URL}/{created['id']}",
            json=losing_payload,
        )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "version_conflict"
    winner = await async_client.get(f"{BASE_URL}/{created['id']}")
    assert winner.json()["display_name"] == "Concurrent Winner"
    assert winner.json()["version"] == created["version"] + 1
    assert winner.json()["contacts"][0]["email"] == created["contacts"][0]["email"]


@pytest.mark.asyncio
async def test_delete_calls_deletability_guard_and_detail_becomes_not_found(
    async_client: AsyncClient,
):
    profile = await create_profile(async_client)
    created = await create_customer(async_client, profile["id"])

    with patch.object(
        customer_service,
        "_assert_customer_deletable",
        wraps=customer_service._assert_customer_deletable,
    ) as guard:
        response = await async_client.delete(f"{BASE_URL}/{created['id']}")

    assert response.status_code == 204
    assert response.content == b""
    guard.assert_called_once()
    detail = await async_client.get(f"{BASE_URL}/{created['id']}")
    assert detail.status_code == 404
    assert detail.json()["detail"]["code"] == "not_found"


def invalid_customer_cases(profile_id: int) -> list[tuple[str, dict]]:
    cases: list[tuple[str, dict]] = []

    payload = customer_payload(profile_id)
    payload["company_name"] = "   "
    cases.append(("company name", payload))

    payload = person_payload(profile_id)
    payload["first_name"] = "   "
    cases.append(("person first name", payload))

    payload = person_payload(profile_id)
    payload["last_name"] = None
    cases.append(("person last name", payload))

    payload = customer_payload(profile_id)
    payload["contacts"].append({**payload["contacts"][0], "email": "other@example.test"})
    cases.append(("multiple primary contacts", payload))

    payload = customer_payload(profile_id)
    payload["addresses"].append({**payload["addresses"][0], "street": "Other street 2"})
    cases.append(("multiple defaults per address kind", payload))

    payload = customer_payload(profile_id)
    payload["accounts"].append(deepcopy(payload["accounts"][0]))
    cases.append(("duplicate account profiles", payload))

    payload = customer_payload(profile_id)
    payload["accounts"][0]["preferred_currency"] = "FOO"
    cases.append(("unknown currency", payload))

    payload = customer_payload(profile_id)
    payload["accounts"][0]["discount_percent"] = "100.01"
    cases.append(("discount over one hundred", payload))

    payload = customer_payload(profile_id)
    payload["display_name"] = "   "
    cases.append(("blank display name", payload))

    payload = customer_payload(profile_id)
    payload["preferred_locale"] = "x"
    cases.append(("one-character locale", payload))

    payload = customer_payload(profile_id)
    payload["notes"] = "x" * 10001
    cases.append(("notes over ten thousand characters", payload))

    payload = customer_payload(profile_id)
    payload["addresses"][0]["street"] = "   "
    cases.append(("blank address street", payload))

    payload = customer_payload(profile_id)
    payload["addresses"][0]["country_code"] = "ZZ"
    cases.append(("unknown address country", payload))

    payload = customer_payload(profile_id)
    payload["tax_identifiers"][0]["kind"] = "   "
    cases.append(("blank tax kind", payload))

    payload = customer_payload(profile_id)
    payload["tax_identifiers"][0]["value"] = "   "
    cases.append(("blank tax value", payload))

    payload = customer_payload(profile_id)
    payload["tax_identifiers"][0]["country_code"] = "ZZ"
    cases.append(("unknown tax country", payload))

    payload = customer_payload(profile_id)
    payload["tax_identifiers"][0]["validation_status"] = "pending"
    cases.append(("unknown tax validation status", payload))

    payload = customer_payload(profile_id)
    payload["tax_identifiers"].append(
        {
            **payload["tax_identifiers"][0],
            "kind": "vat",
            "value": "de999999999",
        }
    )
    cases.append(("duplicate tax identifier", payload))

    payload = customer_payload(profile_id)
    payload["tags"] = ["   "]
    cases.append(("blank tag", payload))

    payload = customer_payload(profile_id)
    payload["tags"] = [f"tag-{index}" for index in range(51)]
    cases.append(("too many tags", payload))

    return cases


@pytest.mark.asyncio
async def test_invalid_customer_payloads_return_422(async_client: AsyncClient):
    profile = await create_profile(async_client)

    for case_name, payload in invalid_customer_cases(profile["id"]):
        response = await async_client.post(BASE_URL + "/", json=payload)
        assert response.status_code == 422, f"{case_name}: {response.text}"


@pytest.mark.asyncio
async def test_not_found_and_duplicate_errors_are_stable_and_transaction_recovers(
    async_client: AsyncClient,
):
    profile = await create_profile(async_client)
    update_payload = customer_payload(profile["id"])
    update_payload["version"] = 1

    for method, path, kwargs in (
        (async_client.get, f"{BASE_URL}/99999", {}),
        (async_client.put, f"{BASE_URL}/99999", {"json": update_payload}),
        (async_client.delete, f"{BASE_URL}/99999", {}),
    ):
        response = await method(path, **kwargs)
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "not_found"
        assert response.json()["detail"]["message"]

    first_payload = customer_payload(profile["id"])
    first_payload["accounts"][0]["number"] = "DUP-500"
    await create_customer(async_client, profile["id"], payload=first_payload)
    second_payload = customer_payload(profile["id"])
    second_payload["display_name"] = "Duplicate Customer"
    second_payload["company_name"] = "Duplicate Customer GmbH"
    second_payload["accounts"][0]["number"] = "DUP-500"

    duplicate = await async_client.post(BASE_URL + "/", json=second_payload)

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == {
        "code": "duplicate_business_key",
        "message": DUPLICATE_MESSAGE,
    }
    second_payload["accounts"][0]["number"] = "DUP-501"
    follow_up = await async_client.post(BASE_URL + "/", json=second_payload)
    assert follow_up.status_code == 201, follow_up.text


def test_asyncpg_integrity_metadata_maps_to_sanitized_duplicate_error():
    original = RuntimeError("adapter wrapper")
    driver_error = FakeAsyncpgError(
        "sensitive database detail",
        constraint_name="uq_customer_account_profile_number",
    )
    original.__cause__ = driver_error

    classified = customer_routes._classify_integrity_error(
        IntegrityError("redacted statement", {}, original),
        operation_kind="write",
    )

    assert type(classified) is DuplicateBusinessKeyError
    assert str(classified) == DUPLICATE_MESSAGE
    assert "sensitive database detail" not in str(classified)


@pytest.mark.parametrize(
    "driver_error",
    (
        FakeAsyncpgError(
            "sensitive foreign key detail",
            constraint_name="customer_accounts_business_profile_id_fkey",
            sqlstate="23503",
        ),
        RuntimeError("FOREIGN KEY constraint failed"),
    ),
)
def test_write_foreign_key_integrity_maps_to_profile_unavailable(driver_error):
    classified = customer_routes._classify_integrity_error(
        IntegrityError("redacted statement", {}, driver_error),
        operation_kind="write",
    )

    assert type(classified) is ResourceInUseError
    assert str(classified) == PROFILE_UNAVAILABLE_MESSAGE
    assert "sensitive" not in str(classified)


@pytest.mark.parametrize(
    ("driver_error", "expected_type", "expected_message"),
    (
        (
            FakeAsyncpgError("private unique detail", sqlstate="23505"),
            DuplicateBusinessKeyError,
            GENERIC_INTEGRITY_MESSAGE,
        ),
        (
            FakeAsyncpgError(
                "private known constraint detail",
                constraint_name="uq_customer_tag_name_key",
            ),
            DuplicateBusinessKeyError,
            GENERIC_INTEGRITY_MESSAGE,
        ),
        (
            RuntimeError("UNIQUE constraint failed: customer_tags.name_key"),
            DuplicateBusinessKeyError,
            GENERIC_INTEGRITY_MESSAGE,
        ),
        (
            RuntimeError("duplicate key value violates unique constraint customer_tags_name_key"),
            DuplicateBusinessKeyError,
            GENERIC_INTEGRITY_MESSAGE,
        ),
        (FakeAsyncpgError("private check detail", sqlstate="23514"), None, None),
        (FakeAsyncpgError("private not-null detail", sqlstate="23502"), None, None),
        (RuntimeError("CHECK constraint failed: ck_customers_status"), None, None),
        (RuntimeError("NOT NULL constraint failed: customers.display_name"), None, None),
        (RuntimeError("datatype mismatch"), None, None),
        (RuntimeError("private table secret"), None, None),
    ),
)
def test_integrity_classification_only_maps_unique_and_foreign_key_errors(
    driver_error,
    expected_type,
    expected_message,
):
    classified = customer_routes._classify_integrity_error(
        IntegrityError("redacted statement", {}, driver_error),
        operation_kind="write",
    )

    if expected_type is None:
        assert classified is None
    else:
        assert type(classified) is expected_type
        assert str(classified) == expected_message
        assert "private" not in str(classified)


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
        await customer_routes._commit_write(session, fail_with_integrity_error())

    assert captured.value is integrity_error
    assert session.rolled_back


@pytest.mark.asyncio
async def test_sequence_reservation_rolls_back_when_aggregate_write_fails(
    async_client: AsyncClient,
    db_session,
):
    profile = await create_profile(async_client)
    existing_payload = customer_payload(profile["id"])
    existing_payload["accounts"][0]["number"] = "CUST-00002"
    await create_customer(async_client, profile["id"], payload=existing_payload)
    original_reserve = customer_service._reserve_available_number

    async def reserve_then_collide(session, **kwargs):
        reserved = await original_reserve(session, **kwargs)
        assert reserved == "CUST-00001"
        return "CUST-00002"

    with patch.object(
        customer_service,
        "_reserve_available_number",
        side_effect=reserve_then_collide,
    ):
        failed = await async_client.post(BASE_URL + "/", json=customer_payload(profile["id"]))

    assert failed.status_code == 409, failed.text
    sequence = (
        await db_session.execute(
            select(NumberSequence).where(
                NumberSequence.business_profile_id == profile["id"],
                NumberSequence.key == "customer",
            )
        )
    ).scalar_one()
    await db_session.refresh(sequence)
    assert sequence.next_value == 1

    follow_up_payload = customer_payload(profile["id"])
    follow_up_payload["display_name"] = "Successful Follow-up"
    follow_up_payload["company_name"] = "Successful Follow-up GmbH"
    follow_up = await create_customer(async_client, profile["id"], payload=follow_up_payload)
    assert follow_up["accounts"][0]["number"] == "CUST-00001"


@pytest.mark.asyncio
async def test_customer_read_and_manage_permissions_gate_every_route(
    async_client: AsyncClient,
    db_session,
):
    profile = await create_profile(async_client)
    created = await create_customer(async_client, profile["id"])
    reader_token = await create_permission_user(
        db_session,
        username="customer-reader",
        permissions=[Permission.CUSTOMERS_READ.value],
    )
    manager_token = await create_permission_user(
        db_session,
        username="customer-manager",
        permissions=[Permission.CUSTOMERS_MANAGE.value],
    )
    unrelated_token = await create_permission_user(
        db_session,
        username="customer-unrelated",
        permissions=[Permission.ORDER_SETTINGS_READ.value],
    )
    reader_headers = {"Authorization": f"Bearer {reader_token}"}
    manager_headers = {"Authorization": f"Bearer {manager_token}"}
    unrelated_headers = {"Authorization": f"Bearer {unrelated_token}"}
    update_payload = customer_payload(profile["id"])
    update_payload["version"] = created["version"]
    update_payload["accounts"][0]["number"] = created["accounts"][0]["number"]

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        for path in (
            BASE_URL + f"/?business_profile_id={profile['id']}",
            f"{BASE_URL}/{created['id']}",
        ):
            assert (await async_client.get(path, headers=reader_headers)).status_code == 200
            assert (await async_client.get(path, headers=manager_headers)).status_code == 403
            assert (await async_client.get(path, headers=unrelated_headers)).status_code == 403

        denied_writes = (
            await async_client.post(
                BASE_URL + "/",
                headers=reader_headers,
                json=customer_payload(profile["id"]),
            ),
            await async_client.put(
                f"{BASE_URL}/{created['id']}",
                headers=reader_headers,
                json=update_payload,
            ),
            await async_client.delete(f"{BASE_URL}/{created['id']}", headers=reader_headers),
        )
        assert all(response.status_code == 403 for response in denied_writes)

        managed_payload = customer_payload(profile["id"])
        managed_payload["display_name"] = "Managed Customer"
        managed_payload["company_name"] = "Managed Customer GmbH"
        managed_payload["accounts"][0]["number"] = "MANAGED-1"
        managed = await async_client.post(
            BASE_URL + "/",
            headers=manager_headers,
            json=managed_payload,
        )
        updated = await async_client.put(
            f"{BASE_URL}/{created['id']}",
            headers=manager_headers,
            json=update_payload,
        )
        deleted = await async_client.delete(
            f"{BASE_URL}/{created['id']}",
            headers=manager_headers,
        )

    assert managed.status_code == 201, managed.text
    assert updated.status_code == 200, updated.text
    assert deleted.status_code == 204, deleted.text


@pytest.mark.asyncio
async def test_api_keys_fail_closed_for_every_customer_route(
    async_client: AsyncClient,
    db_session,
):
    profile = await create_profile(async_client)
    created = await create_customer(async_client, profile["id"])
    full_key, key_hash, key_prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="customer-key",
            key_hash=key_hash,
            key_prefix=key_prefix,
            can_read_status=True,
            enabled=True,
        )
    )
    await db_session.commit()
    headers = {"X-API-Key": full_key}
    update_payload = customer_payload(profile["id"])
    update_payload["version"] = created["version"]
    update_payload["accounts"][0]["number"] = created["accounts"][0]["number"]

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        responses = (
            await async_client.get(
                BASE_URL + f"/?business_profile_id={profile['id']}",
                headers=headers,
            ),
            await async_client.get(f"{BASE_URL}/{created['id']}", headers=headers),
            await async_client.post(
                BASE_URL + "/",
                headers=headers,
                json=customer_payload(profile["id"]),
            ),
            await async_client.put(
                f"{BASE_URL}/{created['id']}",
                headers=headers,
                json=update_payload,
            ),
            await async_client.delete(f"{BASE_URL}/{created['id']}", headers=headers),
        )

    assert all(response.status_code == 403 for response in responses)
