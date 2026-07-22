"""Protected E-invoice metadata, validation report and verified download contracts."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from backend.app.core.auth import create_access_token
from backend.app.core.paths import resolve_data_dir
from backend.app.core.permissions import Permission
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument, DocumentArtifact
from backend.app.models.group import Group
from backend.app.models.user import User

BASE_URL = "/api/v1/einvoices"


async def _permission_headers(db_session, username: str, permissions: list[str]) -> dict[str, str]:
    group = Group(name=f"{username}-permissions", permissions=permissions)
    user = User(username=username, password_hash="unused", role="user")
    user.groups.append(group)
    db_session.add_all([group, user])
    await db_session.commit()
    token = create_access_token(data={"sub": username})
    return {"Authorization": f"Bearer {token}"}


async def _artifact(db_session, xml: bytes = b'<?xml version="1.0"?><Invoice/>') -> DocumentArtifact:
    profile = BusinessProfile(
        name="EInvoice API profile",
        legal_name="EInvoice API GmbH",
        country_code="DE",
        default_currency="EUR",
        default_locale="de-DE",
    )
    db_session.add(profile)
    await db_session.flush()
    document = CommercialDocument(
        document_type="invoice",
        business_profile_id=profile.id,
        number="RE-2026-0042",
        technical_status="issued",
        payment_status="unpaid",
        language="de-DE",
        currency="EUR",
    )
    db_session.add(document)
    await db_session.flush()
    digest = sha256(xml).hexdigest()
    relative = Path("document-artifacts") / str(document.id) / f"{digest}.xml"
    target = resolve_data_dir() / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(xml)
    artifact = DocumentArtifact(
        document_id=document.id,
        kind="xrechnung_xml",
        content_type="application/xml",
        storage_path=relative.as_posix(),
        sha256=digest,
        validation_status="valid",
        validation_report={
            "valid": True,
            "standard": "xrechnung",
            "syntax": "ubl-2.1",
            "profile": "xrechnung",
            "findings": [],
            "byte_size": len(xml),
        },
        rule_versions={"xrechnung": "3.0.2-2026-01-31"},
    )
    db_session.add(artifact)
    await db_session.commit()
    return artifact


async def test_metadata_validation_and_xml_download_are_exposed(async_client, db_session):
    xml = b'<?xml version="1.0"?><Invoice/>'
    artifact = await _artifact(db_session, xml)

    metadata = await async_client.get(f"{BASE_URL}/{artifact.id}")
    validation = await async_client.get(f"{BASE_URL}/{artifact.id}/validation")
    download = await async_client.get(f"{BASE_URL}/{artifact.id}/download")

    assert metadata.status_code == 200
    assert metadata.json()["sha256"] == artifact.sha256
    assert "storage_path" not in metadata.json()
    assert validation.status_code == 200
    assert validation.json()["findings"] == []
    assert download.status_code == 200
    assert download.content == xml
    assert download.headers["content-type"] == "application/xml"
    assert "attachment" in download.headers["content-disposition"]
    assert "RE-2026-0042" in download.headers["content-disposition"]


async def test_xml_download_requires_export_permission(async_client, db_session):
    artifact = await _artifact(db_session)
    read_headers = await _permission_headers(
        db_session,
        "einvoice-reader",
        [Permission.COMMERCIAL_DOCUMENTS_READ.value],
    )

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        response = await async_client.get(
            f"{BASE_URL}/{artifact.id}/download",
            headers=read_headers,
        )

    assert response.status_code == 403


async def test_tampered_artifact_returns_structured_integrity_conflict(async_client, db_session):
    artifact = await _artifact(db_session)
    assert artifact.storage_path is not None
    (resolve_data_dir() / artifact.storage_path).write_bytes(b"tampered")

    response = await async_client.get(f"{BASE_URL}/{artifact.id}/download")

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "artifact_integrity_failed"
    assert detail["correlation_id"]
