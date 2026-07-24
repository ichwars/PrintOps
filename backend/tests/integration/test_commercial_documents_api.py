"""Lifecycle contracts and command-specific authorization for commercial documents."""

from __future__ import annotations

from datetime import UTC, date, datetime
from hashlib import sha256
from unittest.mock import patch

from sqlalchemy import select

from backend.app.core.auth import create_access_token
from backend.app.core.permissions import Permission
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument, DocumentArtifact
from backend.app.models.document_audit import DocumentAuditEvent
from backend.app.models.group import Group
from backend.app.models.user import User
from backend.app.schemas.document_layout import (
    CloneLayoutRequest,
    CreateLayoutRequest,
    LayoutScope,
    PublishLayoutRequest,
)
from backend.app.services.document_layouts import clone_layout, create_draft as create_layout_draft, publish_layout

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


async def test_artifact_list_manifest_download_and_integrity_audit(
    async_client,
    db_session,
    monkeypatch,
    tmp_path,
):
    data_dir = tmp_path / "document-data"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    profile = await _profile(db_session)
    first_layout = await create_layout_draft(
        db_session,
        CreateLayoutRequest(
            scope=LayoutScope(business_profile_id=profile.id),
            reason="Historical layout version one",
        ),
        actor_id=None,
    )
    await publish_layout(
        db_session,
        first_layout.id,
        PublishLayoutRequest(
            expected_lock_version=first_layout.lock_version,
            reason="Initial historical layout",
            effective_from=datetime(2025, 1, 1, tzinfo=UTC),
        ),
        actor_id=None,
    )
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        technical_status="issued",
        payment_status="unpaid",
        number="RE-2026-0042",
        issue_date=date(2026, 7, 22),
        language="de-DE",
        currency="EUR",
    )
    db_session.add(document)
    await db_session.flush()
    content = b"%PDF-1.7\nimmutable document\n"
    digest = sha256(content).hexdigest()
    relative = f"document-render-artifacts/{document.id}/{digest}.pdf"
    target = data_dir / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    artifact = DocumentArtifact(
        document_id=document.id,
        kind="pdf",
        content_type="application/pdf",
        storage_path=relative,
        sha256=digest,
        validation_status="valid",
        validation_report={"byte_size": len(content)},
        rule_versions={"pdfa": "3u"},
        layout_configuration_id=first_layout.id,
        layout_version=first_layout.version,
        layout_effective_sha256="a" * 64,
        renderer_version="test-renderer",
        validator_version="test-validator",
        render_receipt={
            "original_role": "original",
            "export_manifest": {"pdf_sha256": digest},
        },
    )
    db_session.add(artifact)
    await db_session.commit()

    second_layout = await clone_layout(
        db_session,
        CloneLayoutRequest(
            source_layout_id=first_layout.id,
            reason="Replacement layout after issuance",
        ),
        actor_id=None,
    )
    await publish_layout(
        db_session,
        second_layout.id,
        PublishLayoutRequest(
            expected_lock_version=second_layout.lock_version,
            reason="Activate replacement after historical issuance",
            effective_from=datetime(2026, 7, 23, tzinfo=UTC),
        ),
        actor_id=None,
    )
    await db_session.commit()

    listing = await async_client.get(f"{BASE_URL}/{document.id}/artifacts")
    manifest = await async_client.get(
        f"{BASE_URL}/{document.id}/artifacts/{artifact.id}/manifest"
    )
    download = await async_client.get(
        f"{BASE_URL}/{document.id}/artifacts/{artifact.id}/download"
    )

    assert listing.status_code == 200
    assert listing.json()[0]["original_role"] == "original"
    assert listing.json()[0]["layout_configuration_id"] == first_layout.id
    assert listing.json()[0]["layout_version"] == 1
    assert manifest.json()["export_manifest"]["pdf_sha256"] == digest
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["etag"] == f'"{digest}"'

    target.write_bytes(content + b"tampered")
    blocked = await async_client.get(
        f"{BASE_URL}/{document.id}/artifacts/{artifact.id}/download"
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "artifact_integrity_failed"
    integrity_event = await db_session.scalar(
        select(DocumentAuditEvent).where(
            DocumentAuditEvent.object_id == document.id,
            DocumentAuditEvent.action == "integrity_failure",
        )
    )
    assert integrity_event is not None
