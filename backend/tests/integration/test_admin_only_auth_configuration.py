"""General settings grants cannot change the authentication boundary."""

import pytest
from sqlalchemy import select

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.tests.integration.test_advanced_auth_api import SMTP_DATA
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def settings_editor(async_client, db_session):
    admin = await _setup_admin(async_client)
    editor = User(
        username="settings-editor",
        groups=[
            Group(
                name="Settings editors",
                permissions=[
                    "settings:read",
                    "settings:update",
                    "settings:backup",
                    "settings:restore",
                    "users:create",
                    "users:update",
                ],
            )
        ],
    )
    db_session.add(editor)
    await db_session.commit()
    return {"Authorization": f"Bearer {create_access_token({'sub': editor.username})}"}, {
        "Authorization": f"Bearer {admin}"
    }


async def test_general_editor_can_save_unprotected_settings_and_echo_defaults(
    async_client, db_session, settings_editor
):
    editor, admin = settings_editor
    path = "/api/v1/settings/"
    ordinary = await async_client.put(path, headers=editor, json={"currency": "EUR", "local_login_enabled": True})
    assert ordinary.status_code == 200, ordinary.text
    assert await db_session.scalar(select(Settings.value).where(Settings.key == "local_login_enabled")) is None

    rejected = await async_client.patch(
        path,
        headers=editor,
        json={"currency": "JPY", "session_max_hours": 120, "prometheus_enabled": True, "ldap_enabled": True},
    )
    assert rejected.status_code == 403
    assert rejected.json()["detail"].endswith("ldap_enabled, prometheus_enabled, session_max_hours")
    assert await db_session.scalar(select(Settings.value).where(Settings.key == "currency")) == "EUR"

    allowed = await async_client.patch(path, headers=admin, json={"session_max_hours": 120})
    assert allowed.status_code == 200
    echo = await async_client.put(path, headers=editor, json={"currency": "GBP", "session_max_hours": 120})
    assert echo.status_code == 200, echo.text


async def test_editor_cannot_mutate_auth_or_access_full_backups(async_client, settings_editor):
    editor, admin = settings_editor
    for method, path, kwargs in (
        ("POST", "/auth/smtp", {"json": SMTP_DATA}),
        ("POST", "/auth/smtp/test", {"json": {"test_recipient": "fixture@example.test"}}),
        ("POST", "/auth/ldap/test", {}),
        ("DELETE", "/auth/oidc/providers/9999", {}),
        ("DELETE", "/auth/oidc/providers/9999/icon", {}),
        ("POST", "/auth/oidc/providers/9999/icon/refresh", {}),
        ("DELETE", "/connect/apps/9999", {}),
        ("POST", "/settings/reset", {}),
        ("GET", "/settings/backup", {}),
        ("POST", "/settings/restore", {"files": {"file": ("fixture.zip", b"test", "application/zip")}}),
        ("GET", "/local-backup/backups/fixture.zip/download", {}),
        ("POST", "/local-backup/backups/fixture.zip/restore", {}),
    ):
        response = await async_client.request(method, f"/api/v1{path}", headers=editor, **kwargs)
        assert response.status_code == 403, (path, response.text)
    existing_gate = await async_client.delete("/api/v1/auth/oidc/providers/9999", headers=admin)
    assert existing_gate.status_code == 404


async def test_admin_action_requires_user_credentials(async_client, db_session, settings_editor):
    owner = await db_session.scalar(select(User).where(User.username == "tokenadmin"))
    token, key_hash, prefix = generate_api_key()
    db_session.add(APIKey(name="Admin key", key_hash=key_hash, key_prefix=prefix, user_id=owner.id))
    await db_session.commit()

    for headers, expected in (({}, 401), ({"Authorization": "Bearer invalid"}, 401), ({"X-API-Key": token}, 403)):
        response = await async_client.post("/api/v1/auth/ldap/test", headers=headers)
        assert response.status_code == expected


async def test_delegated_user_permissions_cannot_provision_ldap_or_remove_2fa(
    async_client, db_session, settings_editor, monkeypatch
):
    from unittest.mock import Mock

    from backend.app.services import ldap_service
    from backend.tests.integration.test_ldap_provision import _seed_ldap_settings

    await _seed_ldap_settings(db_session)
    editor, _ = settings_editor
    target = await db_session.scalar(select(User).where(User.username == "tokenadmin"))
    lookup, search = Mock(), Mock()
    monkeypatch.setattr(ldap_service, "lookup_ldap_user", lookup)
    monkeypatch.setattr(ldap_service, "search_ldap_users", search)

    queries = (
        async_client.get("/api/v1/auth/ldap/search?q=te", headers=editor),
        async_client.post("/api/v1/auth/ldap/provision", headers=editor, json={"username": "test-ldap-user"}),
        async_client.delete(f"/api/v1/auth/2fa/admin/{target.id}", headers=editor),
    )
    for query in queries:
        assert (await query).status_code == 403
    search.assert_not_called()
    lookup.assert_not_called()
    assert (
        await db_session.scalar(select(Settings.key).where(Settings.key == f"user_{target.id}_email_2fa_enabled"))
        is None
    )


async def test_missing_user_2fa_reset_has_no_side_effects_in_auth_off_mode(async_client, db_session):
    response = await async_client.delete("/api/v1/auth/2fa/admin/99999")
    assert response.status_code == 404
    assert await db_session.scalar(select(Settings.key).where(Settings.key == "user_99999_email_2fa_enabled")) is None
