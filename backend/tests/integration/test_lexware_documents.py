"""External-document behavior with isolated DBs and httpx transport, never live Lexware."""

from datetime import date
from decimal import Decimal
from hashlib import sha256
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.api.routes.lexware_documents import router
from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.database import get_db
from backend.app.models.api_key import APIKey
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument, DocumentPayment
from backend.app.models.group import Group
from backend.app.models.lexware import LexwareConnection
from backend.app.models.lexware_documents import LexwareDocument, LexwareOriginal
from backend.app.models.user import User
from backend.app.services.lexware_client import LexwareClient, LexwareError
from backend.app.services.lexware_connections import encrypt_api_key
from backend.app.services.lexware_document_finance import project_finance
from backend.app.services.lexware_documents import fetch_vouchers, replace_vouchers

BASE = "/api/v1/lexware"
READ = "commercial_documents:read"
PAY = "payments:read"
DRAFT = "commercial_documents:draft"


@pytest.fixture
async def document_client(test_engine):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def session():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = session
    with (
        patch("backend.app.core.auth.async_session", sessions),
        patch("backend.app.core.database.async_session", sessions),
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


def snapshot(
    kind="invoice", status="open", amount="119.00", open_amount="19.00", items=None, payment_state="known", file_id=None
):
    identifier = str(uuid4())
    return {
        "summary": {
            "id": identifier,
            "voucherType": kind,
            "voucherStatus": status,
            "voucherNumber": "LEX-42",
            "contactName": "External customer",
            "voucherDate": "2026-01-01",
            "dueDate": "2026-02-01",
            "totalAmount": amount,
            "currency": "EUR",
        },
        "detail": {"id": identifier, "voucherStatus": status, "files": {"documentFileId": file_id} if file_id else {}},
        "payment": {
            "openAmount": open_amount,
            "currency": "EUR",
            "paymentStatus": "balanced" if open_amount == "0.00" else "openRevenue",
            "paymentItems": items or [],
        },
        "payment_state": payment_state,
    }


async def seed(db, rows):
    profile = BusinessProfile(
        name=f"External {uuid4()}",
        legal_name="Test GmbH",
        country_code="DE",
        default_currency="EUR",
        default_locale="de-DE",
    )
    db.add(profile)
    await db.flush()
    connection = LexwareConnection(
        business_profile_id=profile.id,
        organization_id=str(uuid4()),
        company_name="Mock Lexware",
        encrypted_api_key=encrypt_api_key("test-only-key"),
        enabled=True,
    )
    db.add(connection)
    await db.flush()
    await replace_vouchers(db, connection.id, rows)
    await db.commit()
    documents = (
        await db.scalars(
            select(LexwareDocument).where(LexwareDocument.connection_id == connection.id).order_by(LexwareDocument.id)
        )
    ).all()
    return connection, documents


async def headers(db, permissions):
    username = f"document-{uuid4()}"
    group = Group(name=username, permissions=permissions)
    user = User(username=username, password_hash="unused", role="user")
    user.groups.append(group)
    db.add(user)
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token(data={'sub': username})}"}


async def test_fetch_reads_every_status_details_and_unknown_payments(monkeypatch):
    monkeypatch.setattr("backend.app.services.lexware_client._throttle", AsyncMock())
    entries = [snapshot(), snapshot(status="draft"), snapshot(kind="creditnote"), snapshot(kind="deliverynote")]
    requests = []

    def respond(request):
        requests.append(request)
        assert request.method == "GET"
        if request.url.path == "/v1/voucherlist":
            assert request.url.params["voucherStatus"] == "any"
            assert request.url.params["voucherType"] == "any"
            page = int(request.url.params["page"])
            return httpx.Response(
                200,
                json={"content": [entry["summary"] for entry in entries[page * 2 : page * 2 + 2]], "last": page == 1},
            )
        identifier = request.url.path.split("/")[-1]
        entry = next(row for row in entries if row["summary"]["id"] == identifier)
        if request.url.path.startswith("/v1/payments/"):
            if entry["summary"]["voucherType"] == "creditnote":
                return httpx.Response(406)
            return httpx.Response(200, json=entry["payment"])
        return httpx.Response(200, json=entry["detail"])

    async with LexwareClient("mock-key", transport=httpx.MockTransport(respond)) as client:
        rows = await fetch_vouchers(client)
    assert [row["payment_state"] for row in rows] == ["known", "not_applicable", "unknown", "not_applicable"]
    assert sum("/payments/" in str(request.url) for request in requests) == 2
    assert rows[3]["detail"] == {}


async def test_transient_failure_does_not_publish_empty_snapshot(db_session, monkeypatch):
    connection, documents = await seed(db_session, [snapshot()])
    monkeypatch.setattr("backend.app.services.lexware_client._throttle", AsyncMock())
    monkeypatch.setattr("backend.app.services.lexware_client.asyncio.sleep", AsyncMock())
    async with LexwareClient("mock-key", transport=httpx.MockTransport(lambda request: httpx.Response(503))) as client:
        with pytest.raises(LexwareError):
            rows = await fetch_vouchers(client)
            await replace_vouchers(db_session, connection.id, rows)
    await db_session.refresh(documents[0])
    assert documents[0].in_latest_sync
    assert documents[0].total_amount == Decimal("119.00")


async def test_finance_handles_credits_drafts_void_unknown_and_settlement_categories(document_client, db_session):
    categories = [
        "partPaymentFinancialTransaction",
        "partPaymentCreditNote",
        "cashDiscount",
        "irrecoverableReceivable",
        "manualPayment",
        "partPaymentCashBox",
    ]
    items = [
        {"paymentItemType": kind, "amount": "0.10", "currency": "EUR", "postingDate": "2026-01-02"}
        for kind in categories
    ]
    rows = [
        snapshot(open_amount="0.30", items=items),
        snapshot(kind="creditnote", open_amount="0.10"),
        snapshot(kind="purchaseinvoice", open_amount="50.00"),
        snapshot(kind="purchasecreditnote", open_amount="10.00"),
        snapshot(status="draft"),
        snapshot(status="voided", open_amount="0.00"),
        snapshot(status="paid", open_amount="0.00", payment_state="unknown"),
        snapshot(kind="downpaymentinvoice"),
    ]
    connection, documents = await seed(db_session, rows)
    response = await document_client.get(f"{BASE}/finance")
    assert response.status_code == 200
    totals = response.json()["totals"][0]
    assert totals["receivables"] == "0.20"
    assert totals["payables"] == "40.00"
    assert totals["overdue_receivables"] == "0.20"
    assert response.json()["unknown_count"] == 1
    assert response.json()["unsupported_count"] == 1
    detail = (await document_client.get(f"{BASE}/documents/{documents[0].id}")).json()
    assert [item["category"] for item in detail["finance"]["payment_items"]] == [
        "bank_payment",
        "credit_offset",
        "cash_discount",
        "write_off",
        "manual_payment",
        "cash_payment",
    ]
    assert detail["source"] == "lexware"
    for index in (4, 5):
        assert project_finance(documents[index]).payment_state == "not_applicable"
    assert project_finance(documents[6]).open_amount is None
    assert await db_session.scalar(select(func.count()).select_from(CommercialDocument)) == 0


@pytest.mark.parametrize(
    "payment",
    [
        None,
        {},
        {"openAmount": "0.00", "currency": "EUR", "paymentStatus": "balanced"},
        {"openAmount": "NaN", "currency": "EUR", "paymentStatus": "balanced", "paymentItems": []},
    ],
)
async def test_incomplete_payment_is_never_paid(db_session, payment):
    row = snapshot(status="paid", open_amount="0.00")
    row["payment"] = payment
    _, documents = await seed(db_session, [row])
    projected = project_finance(documents[0])
    assert projected.payment_state == "unknown"
    assert projected.open_amount is None
    assert not projected.included_in_totals


async def test_read_permissions_filter_every_financial_surface(document_client, db_session):
    _, documents = await seed(db_session, [snapshot(status="paid", file_id=str(uuid4()))])
    read = await headers(db_session, [READ])
    manage = await headers(db_session, ["accounting_integrations:manage"])
    with patch("backend.app.core.auth.is_auth_enabled", AsyncMock(return_value=True)):
        listing = await document_client.get(f"{BASE}/documents", headers=read)
        detail = await document_client.get(f"{BASE}/documents/{documents[0].id}", headers=read)
        assert listing.status_code == detail.status_code == 200
        for body in (listing.json()["items"][0], detail.json()):
            assert "finance" not in body and "files" not in body and "due_date" not in body
            assert "payload" not in body and "encrypted_api_key" not in body
            assert body["voucher_status"] == "final"
        assert (await document_client.get(f"{BASE}/finance", headers=read)).status_code == 403
        assert (
            await document_client.get(f"{BASE}/documents/{documents[0].id}/files/{uuid4()}", headers=read)
        ).status_code == 403
        assert (
            await document_client.put(
                f"{BASE}/documents/{documents[0].id}/link",
                headers=read,
                json={"local_document_id": None, "expected_version": 1},
            )
        ).status_code == 403
        assert (await document_client.get(f"{BASE}/documents", headers=manage)).status_code == 403


async def test_manual_link_is_versioned_unique_and_preserves_local_payments(document_client, db_session):
    rows = [snapshot(), snapshot()]
    connection, documents = await seed(db_session, rows)
    local = CommercialDocument(
        document_type="invoice",
        business_profile_id=connection.business_profile_id,
        technical_status="issued",
        language="de-DE",
        currency="EUR",
        total_amount=Decimal("119.00"),
        open_amount=Decimal("87.00"),
    )
    db_session.add(local)
    await db_session.flush()
    payment = DocumentPayment(
        document_id=local.id, amount=Decimal("32.00"), currency="EUR", paid_at=date(2026, 1, 3), method="cash"
    )
    db_session.add(payment)
    await db_session.commit()
    body = {"local_document_id": local.id, "expected_version": 1}
    linked = await document_client.put(f"{BASE}/documents/{documents[0].id}/link", json=body)
    assert linked.status_code == 200, linked.text
    assert linked.json()["finance"]["exclusion_reason"] == "linked_local_document"
    assert (await document_client.get(f"{BASE}/finance")).json()["totals"][0]["receivables"] == "19.00"
    assert (await document_client.put(f"{BASE}/documents/{documents[0].id}/link", json=body)).status_code == 409
    assert (await document_client.put(f"{BASE}/documents/{documents[1].id}/link", json=body)).status_code == 409
    await db_session.refresh(local)
    await db_session.refresh(payment)
    assert local.open_amount == Decimal("87.00") and payment.amount == Decimal("32.00")
    await db_session.refresh(documents[0])
    await replace_vouchers(db_session, connection.id, rows)
    await db_session.commit()
    assert documents[0].local_document_id == local.id
    unlinked = await document_client.put(
        f"{BASE}/documents/{documents[0].id}/link",
        json={"local_document_id": None, "expected_version": documents[0].version},
    )
    assert unlinked.status_code == 200
    assert (await document_client.get(f"{BASE}/finance")).json()["totals"][0]["receivables"] == "38.00"


async def test_rejected_link_cannot_hide_receivable(document_client, db_session):
    connection, documents = await seed(db_session, [snapshot()])
    local = CommercialDocument(
        document_type="invoice",
        business_profile_id=connection.business_profile_id,
        technical_status="draft",
        language="de-DE",
        currency="EUR",
        total_amount=Decimal("119.00"),
    )
    db_session.add(local)
    await db_session.commit()
    response = await document_client.put(
        f"{BASE}/documents/{documents[0].id}/link", json={"local_document_id": local.id, "expected_version": 1}
    )
    assert response.status_code == 422
    assert (await document_client.get(f"{BASE}/finance")).json()["totals"][0]["receivables"] == "19.00"


async def test_full_refresh_keeps_missing_evidence_and_excludes_its_balance(document_client, db_session):
    connection, documents = await seed(db_session, [snapshot()])
    await replace_vouchers(db_session, connection.id, [])
    await db_session.commit()
    detail = (await document_client.get(f"{BASE}/documents/{documents[0].id}")).json()
    assert detail["in_latest_sync"] is False
    assert detail["finance"]["exclusion_reason"] == "missing_from_latest_sync"
    assert (await document_client.get(f"{BASE}/finance")).json()["totals"] == []


async def test_api_key_document_scope_does_not_grant_payments(document_client, db_session):
    _, documents = await seed(db_session, [snapshot()])
    raw, hashed, prefix = generate_api_key()
    db_session.add(APIKey(name="Document renderer", key_hash=hashed, key_prefix=prefix, can_render_documents=True))
    await db_session.commit()
    with patch("backend.app.core.auth.is_auth_enabled", AsyncMock(return_value=True)):
        for auth_headers in ({"X-API-Key": raw}, {"Authorization": f"Bearer {raw}"}):
            detail = await document_client.get(f"{BASE}/documents/{documents[0].id}", headers=auth_headers)
            assert detail.status_code == 200
            assert "finance" not in detail.json() and "files" not in detail.json()
            listing = await document_client.get(f"{BASE}/documents", headers=auth_headers)
            assert "finance" not in listing.json()["items"][0]
            assert (await document_client.get(f"{BASE}/finance", headers=auth_headers)).status_code == 403
            assert (
                await document_client.get(f"{BASE}/documents/{documents[0].id}/files/{uuid4()}", headers=auth_headers)
            ).status_code == 403


async def test_inconsistent_payment_snapshot_is_unknown(db_session):
    row = snapshot()
    row["payment"]["voucherStatus"] = "voided"
    _, documents = await seed(db_session, [row])
    assert project_finance(documents[0]).payment_state == "unknown"
    assert not project_finance(documents[0]).included_in_totals


@pytest.mark.parametrize("resource", ["summary", "detail", "payment"])
async def test_wrong_organization_does_not_replace_evidence(db_session, resource):
    row = snapshot()
    connection, documents = await seed(db_session, [row])
    row[resource]["organizationId"] = str(uuid4())
    with pytest.raises(LexwareError, match="different organization"):
        await replace_vouchers(db_session, connection.id, [row])
    assert documents[0].version == 1


@pytest.mark.parametrize(
    "kind,gross_fields",
    [
        ("invoice", {"totalPrice": {"totalGrossAmount": "119.00"}}),
        ("purchaseinvoice", {"totalGrossAmount": "119.00"}),
    ],
)
async def test_detail_gross_amount_takes_precedence_over_summary(db_session, kind, gross_fields):
    row = snapshot(kind=kind, amount="100.00")
    row["detail"].update(gross_fields)
    _, documents = await seed(db_session, [row])
    assert project_finance(documents[0]).total_amount == Decimal("119.00")
