"""REST contracts and authorization for document configuration settings."""

from datetime import date
from unittest.mock import patch

from backend.app.core.auth import create_access_token
from backend.app.core.permissions import Permission
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.document_configuration import DocumentConfiguration
from backend.app.models.group import Group
from backend.app.models.user import User

BASE_URL = "/api/v1/document-configurations"


async def _permission_headers(db_session, username: str, permissions: list[str]) -> dict[str, str]:
    group = Group(name=f"{username}-permissions", permissions=permissions)
    user = User(username=username, password_hash="unused", role="user")
    user.groups.append(group)
    db_session.add_all([group, user])
    await db_session.commit()
    token = create_access_token(data={"sub": username})
    return {"Authorization": f"Bearer {token}"}


async def _draft_configuration(db_session) -> DocumentConfiguration:
    profile = BusinessProfile(
        name="API document profile",
        legal_name="API Documents GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    configuration = DocumentConfiguration(
        business_profile_id=profile.id,
        document_type="invoice",
        language="de",
        version=1,
        status="draft",
        lock_version=1,
    )
    db_session.add(configuration)
    await db_session.commit()
    return configuration


async def test_catalog_list_detail_and_readiness_resources_are_exposed(async_client, db_session):
    draft = await _draft_configuration(db_session)

    catalog = await async_client.get(f"{BASE_URL}/catalog")
    listing = await async_client.get(BASE_URL + "/", params={"business_profile_id": draft.business_profile_id})
    detail = await async_client.get(f"{BASE_URL}/{draft.id}")
    readiness = await async_client.get(f"{BASE_URL}/{draft.id}/readiness")

    assert catalog.status_code == 200
    assert len(catalog.json()["document_types"]) == 13
    assert catalog.json()["tax_rule_version"] == "2026.1"
    assert catalog.json()["einvoice_rule_versions"]["en16931"] == "1.3.16"
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == draft.id
    assert detail.status_code == 200
    assert detail.json()["lock_version"] == 1
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "blocked"


async def test_publish_endpoint_requires_template_manage_permission(async_client, db_session):
    draft = await _draft_configuration(db_session)
    read_headers = await _permission_headers(
        db_session,
        "document-reader",
        [Permission.DOCUMENT_TEMPLATES_READ.value],
    )
    manage_headers = await _permission_headers(
        db_session,
        "document-manager",
        [Permission.DOCUMENT_TEMPLATES_MANAGE.value],
    )
    payload = {
        "expected_version": 1,
        "effective_from": date.today().isoformat(),
        "reason": "Initial release",
        "rule_versions": {"tax": "2026.1", "en16931": "1.3.16"},
    }

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        denied = await async_client.post(f"{BASE_URL}/{draft.id}/publish", json=payload, headers=read_headers)
        read_denied = await async_client.get(f"{BASE_URL}/{draft.id}", headers=manage_headers)

    assert denied.status_code == 403
    assert read_denied.status_code == 403


async def test_create_and_history_expose_version_metadata_and_audit(async_client, db_session):
    profile = BusinessProfile(
        name="History profile",
        legal_name="History Documents GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.commit()

    created = await async_client.post(
        BASE_URL + "/",
        json={
            "business_profile_id": profile.id,
            "document_type": "invoice",
            "language": "de",
            "change_reason": "Initial document policy",
        },
    )

    assert created.status_code == 201
    configuration_id = created.json()["id"]
    history = await async_client.get(f"{BASE_URL}/{configuration_id}/history")
    audit = await async_client.get(f"{BASE_URL}/{configuration_id}/audit")

    assert history.status_code == 200
    assert history.json()[0]["created_at"]
    assert history.json()[0]["rule_versions"] == {}
    assert audit.status_code == 200
    assert audit.json()[0]["action"] == "create"
    assert audit.json()[0]["reason"] == "Initial document policy"
