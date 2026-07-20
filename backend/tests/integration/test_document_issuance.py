from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.database import Base
from backend.app.models import filament_sku_settings  # noqa: F401
from backend.app.models.business_profile import (
    BusinessProfile,
    BusinessProfileAddress,
    BusinessProfileBankAccount,
    BusinessProfileTaxIdentifier,
)
from backend.app.models.commercial_document import (
    CommercialDocument,
    CommercialDocumentLine,
    DocumentNumberReservation,
)
from backend.app.models.document_configuration import (
    DocumentBasicPolicy,
    DocumentConfiguration,
    DocumentContentPolicy,
    DocumentTextBlock,
    DunningPolicy,
    EInvoicePolicy,
    PaymentPolicy,
    TaxPolicy,
)
from backend.app.models.number_sequence import NumberSequence
from backend.app.services.commercial_documents import (
    EInvoiceValidationFailed,
    issue_document,
)


@pytest_asyncio.fixture
async def issuance_sessions(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = (tmp_path / "document-issuance.db").as_posix()
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}", pool_size=10)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield sessions
    await engine.dispose()


async def _ready_invoice(
    sessions: async_sessionmaker[AsyncSession],
    *,
    issue_date: date = date(2026, 7, 20),
) -> tuple[int, int]:
    async with sessions() as session:
        profile = BusinessProfile(
            name="Issuance profile",
            legal_name="Issuance GmbH",
            country_code="DE",
            default_currency="EUR",
            default_locale="de-DE",
            default_tax_rate=Decimal("19.00"),
        )
        session.add(profile)
        await session.flush()
        address = BusinessProfileAddress(
            business_profile_id=profile.id,
            kind="registered",
            street="Musterstraße 1",
            postal_code="10115",
            city="Berlin",
            country_code="DE",
            is_default=True,
        )
        tax_id = BusinessProfileTaxIdentifier(
            business_profile_id=profile.id,
            kind="vat",
            value="DE123456789",
            country_code="DE",
            is_primary=True,
        )
        bank = BusinessProfileBankAccount(
            business_profile_id=profile.id,
            label="Geschäftskonto",
            account_holder="Issuance GmbH",
            currency="EUR",
            iban="DE89370400440532013000",
            bic="COBADEFFXXX",
            is_default=True,
        )
        sequence = NumberSequence(
            business_profile_id=profile.id,
            key="invoice",
            prefix="RE",
            pattern="{PREFIX}-{YYYY}-{####}",
            reset_policy="yearly",
        )
        session.add_all([address, tax_id, bank, sequence])
        await session.flush()
        configuration = DocumentConfiguration(
            business_profile_id=profile.id,
            document_type="invoice",
            language="de-DE",
            version=1,
            status="active",
            effective_from=date(2025, 1, 1),
        )
        configuration.basic_policy = DocumentBasicPolicy(subject="Rechnung {DOCUMENT_NUMBER}")
        configuration.payment_policy = PaymentPolicy(
            payment_term_days=14,
            currency="EUR",
            bank_account_id=bank.id,
        )
        configuration.dunning_policy = DunningPolicy(enabled=False)
        configuration.content_policy = DocumentContentPolicy(include_calculation_data=False)
        configuration.tax_policy = TaxPolicy(allowed_cases=["domestic"])
        configuration.einvoice_policy = EInvoicePolicy(
            requirement="rule_required",
            en16931_version="1.3.16",
            cius_name="XRechnung",
            cius_version="3.0.2",
            syntax="ubl_2_1",
            zugferd_profile="EN16931",
            seller_identifier="0088:1234567890123",
            seller_identifier_scheme="0088",
            bank_account_id=bank.id,
        )
        configuration.text_blocks = [
            DocumentTextBlock(purpose="intro", body="Rechnung {DOCUMENT_NUMBER}", position=0),
            DocumentTextBlock(purpose="closing", body="Vielen Dank.", position=1),
            DocumentTextBlock(purpose="payment_terms", body="Zahlbar bis {DUE_DATE}.", position=2),
        ]
        document = CommercialDocument(
            document_type="invoice",
            business_profile_id=profile.id,
            technical_status="ready",
            payment_status="unpaid",
            issue_date=issue_date,
            due_date=date(2026, 8, 3),
            language="de-DE",
            currency="EUR",
            subtotal_amount=Decimal("100.00"),
            tax_amount=Decimal("19.00"),
            total_amount=Decimal("119.00"),
            open_amount=Decimal("119.00"),
            tax_decision={"rule_version": "2026.1", "treatment": "domestic_standard"},
        )
        document.lines = [
            CommercialDocumentLine(
                position=1,
                description="3D-Druck",
                quantity=Decimal("1.000"),
                unit_code="C62",
                unit_price=Decimal("100.00"),
                net_amount=Decimal("100.00"),
                tax_category_code="S",
                tax_rate=Decimal("19.00"),
            )
        ]
        session.add_all([configuration, document])
        await session.commit()
        return document.id, document.lock_version


async def _issue_once(
    sessions: async_sessionmaker[AsyncSession],
    document_id: int,
    version: int,
    key: str,
) -> tuple[str, str]:
    async with sessions() as session:
        document = await issue_document(
            session,
            document_id,
            version,
            None,
            key,
            "corr-issue-1",
        )
        return document.number, document.snapshot.sha256


@pytest.mark.asyncio
async def test_concurrent_issuance_returns_one_document_and_one_idempotent_replay(issuance_sessions):
    document_id, version = await _ready_invoice(issuance_sessions)

    first, second = await asyncio.gather(
        _issue_once(issuance_sessions, document_id, version, "issue-key-123"),
        _issue_once(issuance_sessions, document_id, version, "issue-key-123"),
    )

    assert first == second
    async with issuance_sessions() as session:
        document = await session.get(CommercialDocument, document_id)
        reservations = list(
            await session.scalars(
                select(DocumentNumberReservation).where(
                    DocumentNumberReservation.document_id == document_id
                )
            )
        )
        assert document.technical_status == "issued"
        assert len(reservations) == 1
        assert reservations[0].status == "consumed"


@pytest.mark.asyncio
async def test_failed_artifact_validation_keeps_voided_number_evidence(
    issuance_sessions,
    monkeypatch,
):
    document_id, version = await _ready_invoice(issuance_sessions)

    async def fail_generation(*_args, **_kwargs):
        raise EInvoiceValidationFailed("Generated XRechnung is invalid")

    monkeypatch.setattr(
        "backend.app.services.commercial_documents.generate_required_artifact",
        fail_generation,
    )
    async with issuance_sessions() as session:
        with pytest.raises(EInvoiceValidationFailed):
            await issue_document(
                session,
                document_id,
                version,
                None,
                "issue-key-456",
                "corr-issue-2",
            )

    async with issuance_sessions() as session:
        document = await session.get(CommercialDocument, document_id)
        reservation = await session.scalar(
            select(DocumentNumberReservation).where(
                DocumentNumberReservation.document_id == document_id
            )
        )
        assert document.technical_status == "ready"
        assert document.number is None
        assert reservation.status == "voided"
        assert reservation.number == "RE-2026-0001"
        assert reservation.failure_code == "einvoice_invalid"


@pytest.mark.asyncio
async def test_issuance_number_uses_document_issue_date(issuance_sessions):
    document_id, version = await _ready_invoice(
        issuance_sessions,
        issue_date=date(2025, 12, 31),
    )

    number, _snapshot_hash = await _issue_once(
        issuance_sessions,
        document_id,
        version,
        "issue-key-backdated",
    )

    assert number == "RE-2025-0001"
