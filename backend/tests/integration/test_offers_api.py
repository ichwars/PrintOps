from datetime import date
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import func, select

from backend.app.core.auth import generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.calculation import Calculation, CalculationRevision, CalculationVariant
from backend.app.models.commerce import CustomerOrder, Offer, OfferAcceptance
from backend.app.models.commercial_document import CommercialDocument, CommercialDocumentLine, DocumentRelation
from backend.app.models.customer import Customer
from backend.app.models.number_sequence import NumberSequence
from backend.app.models.small_part import SmallPart, SmallPartLedgerEntry, SmallPartUnit
from backend.app.models.spool import Spool
from backend.app.models.stock_reservation import StockReservation
from backend.app.schemas.commercial_document import IssuedDocumentSnapshot
from backend.app.services.document_snapshot import attach_issued_snapshot


async def _approved_revision(
    db_session, *, with_requirements: bool = False, customer_id: int | None = None
) -> CalculationRevision:
    profile = BusinessProfile(
        name="Commerce",
        legal_name="Commerce GmbH",
        country_code="DE",
        default_currency="EUR",
        default_tax_rate=Decimal("7.00"),
    )
    db_session.add(profile)
    await db_session.flush()
    db_session.add_all(
        [
            NumberSequence(
                business_profile_id=profile.id,
                key="offer",
                prefix="ANG",
                pattern="{PREFIX}-{YYYY}-{#####}",
                reset_policy="yearly",
            ),
            NumberSequence(
                business_profile_id=profile.id,
                key="order",
                prefix="AUF",
                pattern="{PREFIX}-{YYYY}-{#####}",
                reset_policy="yearly",
            ),
        ]
    )
    calculation = Calculation(
        business_profile_id=profile.id, customer_id=customer_id, title="Mounting set", status="approved"
    )
    calculation.variants.append(CalculationVariant(name="Standard", is_preferred=True, sort_order=0))
    db_session.add(calculation)
    await db_session.flush()
    plates = []
    small_parts = []
    if with_requirements:
        plates = [
            {
                "project_plate_id": 1,
                "stable_key": "plate-one",
                "plate_name": "Plate 1",
                "good_parts": 2,
                "parts_per_print": 2,
                "scrap_prints": 0,
                "material_code": "PETG",
                "grams_per_print": "120",
            }
        ]
        small_parts = [{"small_part_id": 1, "quantity": "3", "unit_code": "C62", "description": "M3 screw"}]
    revision = CalculationRevision(
        calculation_id=calculation.id,
        revision_number=1,
        snapshot={
            "calculation": {
                "id": calculation.id,
                "title": calculation.title,
                "business_profile_id": profile.id,
                "customer_id": customer_id,
                "currency": "EUR",
            },
            "variants": [
                {
                    "name": "Standard",
                    "sort_order": 0,
                    "is_preferred": True,
                    "plates": plates,
                    "small_parts": small_parts,
                }
            ],
        },
        production_cost=Decimal("15"),
        selling_price=Decimal("25"),
        currency="EUR",
    )
    db_session.add(revision)
    await db_session.commit()
    await db_session.refresh(revision)
    return revision


async def test_offer_draft_send_and_reject_do_not_reserve_stock(async_client, db_session):
    revision = await _approved_revision(db_session)

    created = await async_client.post("/api/v1/offers", json={"calculation_revision_id": revision.id})
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "draft"
    assert created.json()["number"].startswith("ANG-")
    quotation = await db_session.scalar(
        select(CommercialDocument).where(
            CommercialDocument.source_offer_id == created.json()["id"],
            CommercialDocument.document_type == "quotation",
        )
    )
    assert quotation is not None
    assert quotation.number == created.json()["number"]
    assert quotation.tax_amount == Decimal("1.75")
    assert created.json()["quotation_document_id"] == quotation.id
    listing = await async_client.get("/api/v1/offers", params={"status": "draft"})
    assert listing.status_code == 200, listing.text
    assert listing.json()[0]["customer_display_name"] is None
    sent = await async_client.post(f"/api/v1/offers/{created.json()['id']}/send", json={"expected_version": 1})
    assert sent.status_code == 200, sent.text
    rejected = await async_client.post(f"/api/v1/offers/{created.json()['id']}/reject", json={"expected_version": 2})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert await db_session.scalar(select(func.count()).select_from(StockReservation)) == 0


async def test_offer_details_return_quotation_lines_totals_and_recipient(async_client, db_session):
    customer = Customer(kind="company", display_name="Current customer name")
    db_session.add(customer)
    await db_session.flush()
    revision = await _approved_revision(db_session, customer_id=customer.id)
    created = await async_client.post("/api/v1/offers", json={"calculation_revision_id": revision.id})
    assert created.status_code == 201, created.text
    offer = created.json()
    quotation = await db_session.get(CommercialDocument, offer["quotation_document_id"])
    quotation.lines[0].quantity = Decimal("2")
    quotation.lines[0].unit_price = Decimal("11.125")
    quotation.lines[0].net_amount = Decimal("22.25")
    quotation.lines.append(
        CommercialDocumentLine(
            position=2,
            description="Hardware",
            quantity=Decimal("0.5"),
            unit_code="KGM",
            unit_price=Decimal("5.5"),
            net_amount=Decimal("2.75"),
            tax_category_code="S",
            tax_rate=Decimal("7"),
        )
    )
    await db_session.commit()

    response = await async_client.get(f"/api/v1/offers/{offer['id']}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["customer_display_name"] == "Current customer name"
    quote = body["quotation"]
    assert quote["customer_id"] == customer.id
    assert quote["currency"] == "EUR"
    assert (quote["subtotal_amount"], quote["tax_amount"], quote["total_amount"]) == ("25.00", "1.75", "26.75")
    assert [line["description"] for line in quote["lines"]] == ["Mounting set", "Hardware"]
    assert [line["unit_price"] for line in quote["lines"]] == ["11.125000", "5.500000"]
    assert "internal_calculation" not in quote["lines"][0]
    assert "source_data" not in quote["lines"][0]

    listing = await async_client.get("/api/v1/offers", params={"status": "draft"})
    assert listing.status_code == 200, listing.text
    assert listing.json()[0]["customer_display_name"] == body["customer_display_name"]
    assert "quotation" not in listing.json()[0]

    recipient = Customer(kind="company", display_name="Quotation recipient")
    db_session.add(recipient)
    await db_session.flush()
    quotation.customer_id = recipient.id
    await db_session.commit()
    listing = await async_client.get("/api/v1/offers")
    assert listing.status_code == 200, listing.text
    assert listing.json()[0]["customer_display_name"] == "Quotation recipient"

    quotation.technical_status = "issued"
    await attach_issued_snapshot(
        db_session,
        quotation,
        IssuedDocumentSnapshot(
            document_type="quotation",
            number=quotation.number,
            issue_date=date(2026, 7, 22),
            language="en",
            currency="EUR",
            seller={},
            buyer={"name": "Historical customer name"},
            totals={"net": Decimal("25.00")},
        ),
        configuration_id=None,
        configuration_version=1,
        tax_rule_version="2026.1",
        einvoice_rule_versions={},
        actor_id=None,
    )
    await db_session.commit()
    issued_detail = await async_client.get(f"/api/v1/offers/{offer['id']}")
    assert issued_detail.status_code == 200, issued_detail.text
    assert issued_detail.json()["customer_display_name"] == "Historical customer name"
    listing = await async_client.get("/api/v1/offers")
    assert listing.status_code == 200, listing.text
    assert listing.json()[0]["customer_display_name"] == issued_detail.json()["customer_display_name"]

    page = await async_client.get("/api/v1/offers/page", params={"q": "HISTORICAL", "sort_by": "customer"})
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["customer_display_name"] == issued_detail.json()["customer_display_name"]
    page = await async_client.get("/api/v1/offers/page", params={"q": "Quotation recipient"})
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 0

    customer.display_name = "Intermediate customer name"
    await db_session.commit()
    next_offer = await async_client.post("/api/v1/offers", json={"calculation_revision_id": revision.id})
    assert next_offer.status_code == 201, next_offer.text
    params = {"sort_by": "customer", "sort_dir": "asc", "limit": 1}
    first = await async_client.get("/api/v1/offers/page", params=params)
    assert first.status_code == 200, first.text
    assert first.json()["total"] == 2
    assert first.json()["items"][0]["id"] == offer["id"]
    second = await async_client.get("/api/v1/offers/page", params={**params, "offset": 1})
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["id"] == next_offer.json()["id"]


async def test_offer_page_sorts_and_filters_before_slicing(async_client, db_session):
    customer = Customer(kind="company", display_name="Müller")
    db_session.add(customer)
    await db_session.flush()
    revision = await _approved_revision(db_session, customer_id=customer.id)
    calculation = await db_session.get(Calculation, revision.calculation_id)
    for number, title, status in [
        ("AG-10", "Kalkulation 10", "draft"),
        ("AG-2", "Kalkulation 2", "draft"),
        ("AG-1", "Kalkulation 1", "rejected"),
    ]:
        db_session.add(
            Offer(
                business_profile_id=calculation.business_profile_id,
                customer_id=customer.id,
                calculation_revision_id=revision.id,
                number=number,
                status=status,
                preferred_variant_sort_order=0,
                snapshot={"calculation": {"id": str(calculation.id), "title": title}},
            )
        )
    await db_session.commit()

    params = {
        "status": "draft",
        "customer_id": customer.id,
        "business_profile_id": calculation.business_profile_id,
        "calculation_id": calculation.id,
        "q": "MÜLLER",
        "sort_by": "number",
        "sort_dir": "asc",
        "limit": 1,
    }
    first = await async_client.get("/api/v1/offers/page", params=params)
    assert first.status_code == 200, first.text
    assert first.json()["total"] == 2
    assert first.json()["items"][0]["number"] == "AG-2"
    second = await async_client.get("/api/v1/offers/page", params={**params, "offset": 1})
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["number"] == "AG-10"
    default_order = await async_client.get("/api/v1/offers/page", params={"limit": 1, "offset": 5})
    assert default_order.status_code == 200, default_order.text
    assert default_order.json() == {"items": [], "total": 3, "offset": 5, "limit": 1}

    by_title = await async_client.get("/api/v1/offers/page", params={"q": "kalkulation 10"})
    assert by_title.status_code == 200, by_title.text
    assert [item["number"] for item in by_title.json()["items"]] == ["AG-10"]


async def test_offer_page_requires_document_read_scope_when_auth_is_enabled(async_client, db_session):
    key, key_hash, key_prefix = generate_api_key()
    api_key = APIKey(name="status only", key_hash=key_hash, key_prefix=key_prefix, can_read_status=True)
    revoked, revoked_hash, revoked_prefix = generate_api_key()
    db_session.add_all(
        [
            api_key,
            APIKey(
                name="revoked reader",
                key_hash=revoked_hash,
                key_prefix=revoked_prefix,
                can_render_documents=True,
                enabled=False,
            ),
        ]
    )
    await db_session.commit()

    endpoint = "/api/v1/offers/page"
    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        assert (await async_client.get(endpoint)).status_code == 401
        assert (await async_client.get(endpoint, headers={"X-API-Key": "invalid"})).status_code == 401
        assert (await async_client.get(endpoint, headers={"X-API-Key": key})).status_code == 403
        assert (await async_client.get(endpoint, headers={"X-API-Key": revoked})).status_code == 401


async def test_accepting_sent_offer_creates_order_project_and_reservations_once(async_client, db_session):
    unit = SmallPartUnit(code="C62", label="Stück", decimal_places=0)
    part = SmallPart(sku="M3", name="M3 screw", unit_code="C62", unit_cost=Decimal("0.05"))
    db_session.add_all([unit, part, Spool(material="PETG", label_weight=500, weight_used=100)])
    await db_session.flush()
    assert part.id == 1
    db_session.add(
        SmallPartLedgerEntry(
            small_part_id=part.id,
            entry_kind="opening",
            physical_delta=10,
            reserved_delta=0,
            reason="Opening",
            idempotency_key="opening-m3",
        )
    )
    await db_session.commit()
    customer = Customer(kind="company", display_name="Order customer")
    db_session.add(customer)
    await db_session.flush()
    revision = await _approved_revision(db_session, with_requirements=True, customer_id=customer.id)
    created = await async_client.post("/api/v1/offers", json={"calculation_revision_id": revision.id})
    sent = await async_client.post(f"/api/v1/offers/{created.json()['id']}/send", json={"expected_version": 1})

    accepted = await async_client.post(
        f"/api/v1/offers/{created.json()['id']}/accept",
        json={"expected_version": sent.json()["version"], "idempotency_key": "accept-mounting-set-1"},
    )

    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["offer"]["status"] == "accepted"
    assert len(accepted.json()["order"]["reservations"]) == 2
    replay = await async_client.post(
        f"/api/v1/offers/{created.json()['id']}/accept",
        json={"expected_version": sent.json()["version"], "idempotency_key": "accept-mounting-set-1"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["order"]["id"] == accepted.json()["order"]["id"]
    assert await db_session.scalar(select(func.count()).select_from(CustomerOrder)) == 1
    assert await db_session.scalar(select(func.count()).select_from(OfferAcceptance)) == 1
    confirmation = await db_session.scalar(
        select(CommercialDocument).where(
            CommercialDocument.source_order_id == accepted.json()["order"]["id"],
            CommercialDocument.document_type == "order_confirmation",
        )
    )
    assert confirmation is not None
    assert confirmation.number == accepted.json()["order"]["number"]
    detail = await async_client.get(f"/api/v1/orders/{accepted.json()['order']['id']}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["customer_display_name"] == "Order customer"
    assert len(body["reservations"]) == 2
    saved = body["confirmation"]
    assert saved["currency"] == "EUR"
    assert (saved["subtotal_amount"], saved["tax_amount"], saved["total_amount"]) == ("25.00", "1.75", "26.75")
    assert [(line["position"], line["description"], line["unit_price"]) for line in saved["lines"]] == [
        (1, "Mounting set", "25.000000"),
    ]
    assert "internal_calculation" not in saved["lines"][0]
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(DocumentRelation)
            .where(
                DocumentRelation.target_document_id == confirmation.id,
                DocumentRelation.relation_type == "successor",
            )
        )
        == 1
    )
