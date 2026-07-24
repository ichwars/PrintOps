from __future__ import annotations

from unittest.mock import patch

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.commercial_document import CommercialDocument
from backend.app.models.group import Group
from backend.app.models.settings import Settings
from backend.app.models.user import User

BASE_URL = "/api/v1/document-layouts"


async def _profile(db_session, name: str = "Layout API") -> BusinessProfile:
    profile = BusinessProfile(
        name=name,
        legal_name=f"{name} GmbH",
        country_code="DE",
        default_currency="EUR",
        default_locale="de-DE",
    )
    db_session.add(profile)
    await db_session.commit()
    return profile


async def _headers(db_session, username: str, permissions: list[str]) -> dict[str, str]:
    group = Group(name=f"{username}-group", permissions=permissions)
    user = User(username=username, password_hash="unused", role="user")
    user.groups.append(group)
    db_session.add_all([group, user])
    await db_session.commit()
    token = create_access_token(data={"sub": username})
    return {"Authorization": f"Bearer {token}"}


async def _api_key_headers(db_session, name: str, *, can_render_documents: bool) -> dict[str, str]:
    full_key, key_hash, key_prefix = generate_api_key()
    db_session.add(
        APIKey(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            can_queue=False,
            can_control_printer=False,
            can_read_status=False,
            can_manage_library=False,
            can_manage_inventory=False,
            can_manage_maintenance=False,
            can_manage_archives=False,
            can_manage_projects=False,
            can_render_documents=can_render_documents,
            enabled=True,
        )
    )
    await db_session.commit()
    return {"X-API-Key": full_key}


async def test_layout_catalog_draft_autosave_detail_and_readiness(async_client, db_session):
    profile = await _profile(db_session)
    catalog = await async_client.get(f"{BASE_URL}/catalog")
    samples = await async_client.get(f"{BASE_URL}/samples")
    created = await async_client.post(
        BASE_URL,
        json={
            "scope": {"business_profile_id": profile.id},
            "template_key": "classic",
            "reason": "Initial profile layout",
        },
    )

    assert catalog.status_code == 200
    assert {item["key"] for item in catalog.json()["templates"]} == {
        "classic",
        "modern",
        "compact",
    }
    assert samples.status_code == 200
    assert len(samples.json()) == 26
    assert created.status_code == 201, created.text
    layout_id = created.json()["id"]

    patched = await async_client.patch(
        f"{BASE_URL}/{layout_id}",
        json={
            "expected_lock_version": 1,
            "edit_session_id": "editor-0001",
            "typography": {"accent_color": "#123456"},
        },
    )
    listing = await async_client.get(
        BASE_URL,
        params={"business_profile_id": profile.id},
    )
    detail = await async_client.get(f"{BASE_URL}/{layout_id}")
    readiness = await async_client.get(f"{BASE_URL}/{layout_id}/readiness")

    assert patched.status_code == 200, patched.text
    assert patched.json()["lock_version"] == 2
    assert listing.status_code == 200
    assert listing.json()[0]["id"] == layout_id
    assert detail.status_code == 200, detail.text
    assert detail.json()["effective"]["typography"]["accent_color"] == "#123456"
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True


async def test_preview_contract_rejects_stale_layout_and_guessed_document(async_client, db_session):
    profile = await _profile(db_session, "Preview API")
    foreign_profile = await _profile(db_session, "Foreign Preview API")
    foreign_document = CommercialDocument(
        document_type="invoice",
        business_profile_id=foreign_profile.id,
        language="de-DE",
        currency="EUR",
    )
    db_session.add(foreign_document)
    await db_session.commit()
    created = await async_client.post(
        BASE_URL,
        json={
            "scope": {"business_profile_id": profile.id},
            "reason": "Preview profile layout",
        },
    )
    layout_id = created.json()["id"]

    stale = await async_client.post(
        f"{BASE_URL}/preview",
        json={
            "layout_id": layout_id,
            "layout_lock_version": 99,
            "source_kind": "sample",
            "source_id": "invoice-de-standard",
        },
    )
    guessed = await async_client.post(
        f"{BASE_URL}/preview",
        json={
            "layout_id": layout_id,
            "layout_lock_version": 1,
            "source_kind": "document",
            "source_id": "999999",
        },
    )
    cross_profile = await async_client.post(
        f"{BASE_URL}/preview",
        json={
            "layout_id": layout_id,
            "layout_lock_version": 1,
            "source_kind": "document",
            "source_id": str(foreign_document.id),
        },
    )

    assert stale.status_code == 409
    assert guessed.status_code == 404
    assert cross_profile.status_code == 404


async def test_layout_read_and_manage_permissions_are_separate(async_client, db_session):
    profile = await _profile(db_session, "Permissions API")
    read_headers = await _headers(
        db_session,
        "layout-reader",
        [Permission.DOCUMENT_LAYOUTS_READ.value],
    )
    manage_headers = await _headers(
        db_session,
        "layout-manager",
        [Permission.DOCUMENT_LAYOUTS_MANAGE.value],
    )

    with patch("backend.app.core.auth.is_auth_enabled", return_value=True):
        read = await async_client.get(
            BASE_URL,
            params={"business_profile_id": profile.id},
            headers=read_headers,
        )
        denied_write = await async_client.post(
            BASE_URL,
            headers=read_headers,
            json={
                "scope": {"business_profile_id": profile.id},
                "reason": "Permission separation",
            },
        )
        denied_read = await async_client.get(
            BASE_URL,
            params={"business_profile_id": profile.id},
            headers=manage_headers,
        )

    assert read.status_code == 200
    assert denied_write.status_code == 403
    assert denied_read.status_code == 403


async def test_document_render_api_key_scope_is_explicit_and_complete(async_client, db_session):
    profile = await _profile(db_session, "API Key Scope")
    allowed_headers = await _api_key_headers(
        db_session,
        "document-renderer",
        can_render_documents=True,
    )
    denied_headers = await _api_key_headers(
        db_session,
        "status-only",
        can_render_documents=False,
    )
    db_session.add(Settings(key="auth_enabled", value="true"))
    await db_session.commit()

    allowed_read = await async_client.get(f"{BASE_URL}/catalog", headers=allowed_headers)
    allowed_manage = await async_client.post(
        BASE_URL,
        headers=allowed_headers,
        json={
            "scope": {"business_profile_id": profile.id},
            "reason": "External layout automation",
        },
    )
    denied = await async_client.get(f"{BASE_URL}/catalog", headers=denied_headers)

    assert allowed_read.status_code == 200
    assert allowed_manage.status_code == 201, allowed_manage.text
    assert denied.status_code == 403


async def test_render_openapi_contains_only_id_based_strict_inputs(async_client):
    schema = (await async_client.get("/openapi.json")).json()
    schemas = schema["components"]["schemas"]
    forbidden = {"html", "css", "url", "path", "content", "snapshot"}
    for name in ("PreviewRequest", "ExternalRenderRequest"):
        properties = set(schemas[name]["properties"])
        assert properties.isdisjoint(forbidden)
        assert schemas[name]["additionalProperties"] is False
