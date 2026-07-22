"""Lifecycle contracts and command-specific authorization for commercial documents."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from backend.app.core.auth import create_access_token
from backend.app.core.permissions import Permission
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument
from backend.app.models.group import Group
from backend.app.models.user import User

BASE_URL = "/api/v1/commercial-documents"


async def _permission_headers(db_session, username: str, permissions: list[str]) -> dict[str, str]:
    group = Group(name=f"{username}-permissions", permissions=permissions)
    user = User(username=username, password_hash="unused", role="user")
    user.groups.append(group)
    db_session.add_all([group, user])
    await db_session.commit()
    token = create_access_token(data={"sub": username})
    return {"Authorization": f"Bearer {token}"}


async def _profile(db_session) -> BusinessProfile:
    profile = BusinessProfile(
        name="Commercial API profile",
        legal_name="Commercial API GmbH",
        country_code="DE",
        default_currency="EUR",
        default_locale="de-DE",
    )
    db_session.add(profile)
    await db_session.commit()
    return profile


async def test_draft_crud_and_list_resources_are_exposed(async_client, db_session):
    profile = await _profile(db_session)
    payload = {
        "document_type": "invoice",
        "business_profile_id": profile.id,
        "issue_date": date(2026, 7, 22).isoformat(),
        "language": "de-DE",
        "currency": "EUR",
        "lines": [
            {
                "position": 1,
                "description": "3D-Druck",
                "quantity": "1.000",
                "unit_code": "C62",
                "unit_price": "100.00",
                "net_amount": "100.00",
                "tax_category_code": "S",
                "tax_rate": "19.00",
            }
        ],
    }

    created = await async_client.post(BASE_URL, json=payload)
    assert created.status_code == 201
    document_id = created.json()["id"]
    assert created.json()["lock_version"] == 1

    listing = await async_client.get(BASE_URL, params={"business_profile_id": profile.id})
    detail = await async_client.get(f"{BASE_URL}/{document_id}")
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == document_id
    assert detail.status_code == 200
    assert detail.json()["lines"][0]["description"] == "3D-Druck"

    payload["lines"][0]["description"] = "3D-Druck, geändert"
    updated = await async_client.patch(
        f"{BASE_URL}/{document_id}",
        json={"expected_version": 1, "document": payload},
    )
    assert updated.status_code == 200
    assert updated.json()["lock_version"] == 2
    assert updated.json()["lines"][0]["description"] == "3D-Druck, geändert"


async def test_issue_requires_issue_permission(async_client, db_session):
    profile = await _profile(db_session)
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        technical_status="ready",
        payment_status="unpaid",
        issue_date=date(2026, 7, 22),
        language="de-DE",
        currency="EUR",
    )
    db_session.add(document)
    await db_session.commit()
    draft_headers = await _permission_headers(
        db_session,
        "document-drafter",
        [Permission.COMMERCIAL_DOCUMENTS_DRAFT.value],
    )

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        response = await async_client.post(
            f"{BASE_URL}/{document.id}/issue",
            json={"expected_version": 1, "idempotency_key": "issue-12345678"},
            headers=draft_headers,
        )

    assert response.status_code == 403


async def test_invalid_document_returns_field_rule_and_correlation(async_client, db_session):
    profile = await _profile(db_session)
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        technical_status="draft",
        payment_status="unpaid",
        language="de-DE",
        currency="EUR",
    )
    db_session.add(document)
    await db_session.commit()
    issue_headers = await _permission_headers(
        db_session,
        "document-issuer",
        [Permission.COMMERCIAL_DOCUMENTS_ISSUE.value],
    )

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        response = await async_client.post(
            f"{BASE_URL}/{document.id}/validate",
            headers=issue_headers,
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "document_not_ready"
    assert detail["findings"][0]["field_path"]
    assert detail["findings"][0]["code"]
    assert detail["correlation_id"]
