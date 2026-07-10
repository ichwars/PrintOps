from decimal import Decimal

import pytest
from sqlalchemy import Numeric, String, inspect, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers, selectinload
from sqlalchemy.schema import CreateIndex

from backend.app.models.business_profile import (
    BusinessProfile,
    BusinessProfileAddress,
    BusinessProfileBankAccount,
    BusinessProfileTaxIdentifier,
)
from backend.app.models.customer import (
    Customer,
    CustomerAccount,
    CustomerAddress,
    CustomerContact,
    CustomerTag,
    CustomerTaxIdentifier,
    customer_tag_links,
)
from backend.app.models.number_sequence import NumberSequence

EXPECTED_ORDER_FOUNDATION_TABLES = {
    "business_profiles",
    "business_profile_addresses",
    "business_profile_tax_identifiers",
    "business_profile_bank_accounts",
    "number_sequences",
    "customers",
    "customer_accounts",
    "customer_contacts",
    "customer_addresses",
    "customer_tax_identifiers",
    "customer_tags",
    "customer_tag_links",
}

EXPECTED_CHECK_CONSTRAINTS = {
    "ck_business_profiles_country_code",
    "ck_business_profiles_currency",
    "ck_business_profiles_billing_mode",
    "ck_business_profile_address_kind",
    "ck_number_sequence_next_value",
    "ck_number_sequence_reset_policy",
    "ck_customers_kind",
    "ck_customers_status",
}

EXPECTED_UNIQUE_CONSTRAINTS = {
    "uq_business_profile_tax_identifier",
    "uq_number_sequence_profile_key",
    "uq_customer_account_profile_number",
    "uq_customer_account_customer_profile",
    "uq_customer_tax_identifier",
    "uq_customer_tag_name",
}


def _business_profile(name: str = "Primary issuer") -> BusinessProfile:
    return BusinessProfile(
        name=name,
        legal_name=f"{name} GmbH",
        country_code="DE",
        default_currency="EUR",
    )


def test_order_foundation_mappers_configure_with_explicit_ownership():
    configure_mappers()

    profile_relationship = BusinessProfile.__mapper__.relationships.get("number_sequences")
    assert profile_relationship is not None
    assert profile_relationship.back_populates == "business_profile"
    assert "delete-orphan" in profile_relationship.cascade

    tag_relationship = CustomerTag.__mapper__.relationships.get("customers")
    assert tag_relationship is not None
    assert tag_relationship.back_populates == "tags"


async def test_order_foundation_schema_contract(test_engine):
    def inspect_schema(sync_connection):
        inspector = inspect(sync_connection)
        table_names = set(inspector.get_table_names())
        check_names = {
            constraint["name"]
            for table_name in EXPECTED_ORDER_FOUNDATION_TABLES
            for constraint in inspector.get_check_constraints(table_name)
        }
        unique_names = {
            constraint["name"]
            for table_name in EXPECTED_ORDER_FOUNDATION_TABLES
            for constraint in inspector.get_unique_constraints(table_name)
        }
        foreign_keys = [
            foreign_key
            for table_name in EXPECTED_ORDER_FOUNDATION_TABLES
            for foreign_key in inspector.get_foreign_keys(table_name)
        ]
        return table_names, check_names, unique_names, foreign_keys

    async with test_engine.connect() as connection:
        table_names, check_names, unique_names, foreign_keys = await connection.run_sync(inspect_schema)

    assert table_names >= EXPECTED_ORDER_FOUNDATION_TABLES
    assert check_names >= EXPECTED_CHECK_CONSTRAINTS
    assert unique_names >= EXPECTED_UNIQUE_CONSTRAINTS
    assert len(foreign_keys) == 11
    assert all(foreign_key["options"].get("ondelete") == "CASCADE" for foreign_key in foreign_keys)

    discount_type = CustomerAccount.__table__.c.discount_percent.type
    currency_type = CustomerAccount.__table__.c.preferred_currency.type
    assert isinstance(discount_type, Numeric)
    assert (discount_type.precision, discount_type.scale) == (5, 2)
    assert isinstance(currency_type, String)
    assert currency_type.length == 3

    case_insensitive_indexes = [
        index for index in CustomerTag.__table__.indexes if index.name == "uq_customer_tag_name_ci"
    ]
    assert len(case_insensitive_indexes) == 1
    case_insensitive_index = case_insensitive_indexes[0]
    assert case_insensitive_index.unique
    for dialect in (sqlite.dialect(), postgresql.dialect()):
        compiled_index = str(CreateIndex(case_insensitive_index).compile(dialect=dialect)).lower()
        assert "unique index" in compiled_index
        assert "lower(name)" in compiled_index


async def test_order_foundation_aggregate_can_be_committed(db_session):
    profile = _business_profile()
    profile.addresses.append(
        BusinessProfileAddress(
            kind="registered",
            street="Werkstrasse 1",
            postal_code="10115",
            city="Berlin",
            country_code="DE",
            is_default=True,
        )
    )
    profile.tax_identifiers.append(
        BusinessProfileTaxIdentifier(
            kind="vat",
            value="DE123456789",
            country_code="DE",
            is_primary=True,
        )
    )
    profile.bank_accounts.append(
        BusinessProfileBankAccount(
            label="Operating account",
            account_holder="Primary issuer GmbH",
            currency="EUR",
            iban="DE02120300000000202051",
            is_default=True,
        )
    )
    profile.number_sequences.append(NumberSequence(key="invoice", prefix="INV"))
    db_session.add(profile)
    await db_session.flush()

    customer = Customer(
        kind="company",
        display_name="Atelier Nord GmbH",
        company_name="Atelier Nord GmbH",
        accounts=[
            CustomerAccount(
                business_profile_id=profile.id,
                number="CUST-00001",
                preferred_currency="EUR",
                payment_term_days=14,
                delivery_terms="DHL shipment",
                discount_percent=Decimal("2.00"),
            )
        ],
        contacts=[
            CustomerContact(
                first_name="Jonas",
                last_name="Berger",
                email="einkauf@example.test",
                is_primary=True,
                include_on_documents=True,
            )
        ],
        addresses=[
            CustomerAddress(
                kind="billing",
                street="Zwickauer Strasse 18",
                postal_code="09111",
                city="Chemnitz",
                country_code="DE",
                is_default=True,
            )
        ],
        tax_identifiers=[
            CustomerTaxIdentifier(
                kind="vat",
                value="DE999999999",
                country_code="DE",
            )
        ],
        tags=[CustomerTag(name="B2B")],
    )
    db_session.add(customer)
    await db_session.commit()
    db_session.expire_all()

    stored_profile = (await db_session.scalars(select(BusinessProfile))).one()
    stored_customer = (await db_session.scalars(select(Customer))).one()

    assert len(stored_profile.addresses) == 1
    assert len(stored_profile.tax_identifiers) == 1
    assert len(stored_profile.bank_accounts) == 1
    assert [sequence.key for sequence in stored_profile.number_sequences] == ["invoice"]
    assert stored_customer.accounts[0].discount_percent == Decimal("2.00")
    assert stored_customer.contacts[0].is_primary
    assert stored_customer.addresses[0].is_default
    assert stored_customer.tax_identifiers[0].validation_status == "unchecked"
    assert [tag.name for tag in stored_customer.tags] == ["B2B"]


async def test_deleting_business_profile_deletes_owned_number_sequences(db_session):
    profile = _business_profile()
    db_session.add(profile)
    await db_session.flush()
    sequence = NumberSequence(business_profile_id=profile.id, key="invoice")
    db_session.add(sequence)
    await db_session.commit()

    await db_session.delete(profile)
    await db_session.commit()

    remaining_sequence_ids = (await db_session.scalars(select(NumberSequence.id))).all()
    assert remaining_sequence_ids == []


async def test_customer_tag_names_are_case_insensitively_unique(db_session):
    db_session.add(CustomerTag(name="B2B"))
    await db_session.commit()

    db_session.add(CustomerTag(name="b2b"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_customer_tag_prevents_retagging_after_pk_reuse(db_session):
    tag = CustomerTag(name="B2B")
    customer = Customer(
        kind="company",
        display_name="Atelier Nord GmbH",
        company_name="Atelier Nord GmbH",
        tags=[tag],
    )
    db_session.add(customer)
    await db_session.commit()
    customer_id = customer.id
    tag_id = tag.id

    await db_session.delete(tag)
    await db_session.commit()
    db_session.add(CustomerTag(id=tag_id, name="Replacement"))
    await db_session.commit()
    db_session.expire_all()

    stored_customer = (
        await db_session.scalars(
            select(Customer).where(Customer.id == customer_id).options(selectinload(Customer.tags))
        )
    ).one()
    linked_tag_ids = (
        await db_session.scalars(
            select(customer_tag_links.c.tag_id).where(customer_tag_links.c.customer_id == customer_id)
        )
    ).all()

    assert stored_customer.tags == []
    assert linked_tag_ids == []
