"""Tests for PRINTOPS_OIDC_* startup configuration."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import undefer

from backend.app.core.oidc_env import apply_env_oidc_provider, env_bool, read_env_oidc_config
from backend.app.models.group import Group
from backend.app.models.oidc_provider import OIDCProvider

pytestmark = pytest.mark.integration

_OIDC_ENV_KEYS = (
    "PRINTOPS_OIDC_NAME",
    "PRINTOPS_OIDC_ISSUER_URL",
    "PRINTOPS_OIDC_CLIENT_ID",
    "PRINTOPS_OIDC_CLIENT_SECRET",
    "PRINTOPS_OIDC_SCOPES",
    "PRINTOPS_OIDC_ENABLED",
    "PRINTOPS_OIDC_ALLOW_PRIVATE_NETWORK",
    "PRINTOPS_OIDC_AUTO_CREATE_USERS",
    "PRINTOPS_OIDC_AUTO_LINK_EXISTING",
    "PRINTOPS_OIDC_EMAIL_CLAIM",
    "PRINTOPS_OIDC_REQUIRE_EMAIL_VERIFIED",
    "PRINTOPS_OIDC_ICON_URL",
    "PRINTOPS_OIDC_AUTOLOGIN",
    "PRINTOPS_OIDC_DEFAULT_GROUP",
)


@pytest.fixture
def clear_oidc_env(monkeypatch):
    for key in _OIDC_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def test_read_env_oidc_config_defaults_and_bool_parsing(clear_oidc_env):
    clear_oidc_env.setenv("PRINTOPS_OIDC_NAME", "PocketID")
    clear_oidc_env.setenv("PRINTOPS_OIDC_ISSUER_URL", "https://id.example.test")
    clear_oidc_env.setenv("PRINTOPS_OIDC_CLIENT_ID", "printops")
    clear_oidc_env.setenv("PRINTOPS_OIDC_CLIENT_SECRET", "super-secret")
    clear_oidc_env.setenv("PRINTOPS_OIDC_AUTO_CREATE_USERS", "yes")
    clear_oidc_env.setenv("PRINTOPS_OIDC_REQUIRE_EMAIL_VERIFIED", "0")

    config = read_env_oidc_config()

    assert config is not None
    assert config["name"] == "PocketID"
    assert config["client_secret"] == "super-secret"
    assert config["scopes"] == "openid email profile"
    assert config["is_enabled"] is True
    assert config["auto_create_users"] is True
    assert config["require_email_verified"] is False


def test_env_bool_rejects_invalid_values(clear_oidc_env):
    clear_oidc_env.setenv("PRINTOPS_OIDC_ENABLED", "definitely")

    with pytest.raises(Exception, match="PRINTOPS_OIDC_ENABLED"):
        env_bool("PRINTOPS_OIDC_ENABLED", True)


@pytest.mark.asyncio
async def test_apply_env_oidc_provider_creates_env_managed_provider(db_session, clear_oidc_env):
    group = Group(name="SSO Users", permissions=[])
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    clear_oidc_env.setenv("PRINTOPS_OIDC_NAME", "PocketID")
    clear_oidc_env.setenv("PRINTOPS_OIDC_ISSUER_URL", "https://id.example.test")
    clear_oidc_env.setenv("PRINTOPS_OIDC_CLIENT_ID", "printops")
    clear_oidc_env.setenv("PRINTOPS_OIDC_CLIENT_SECRET", "super-secret")
    clear_oidc_env.setenv("PRINTOPS_OIDC_AUTO_CREATE_USERS", "true")
    clear_oidc_env.setenv("PRINTOPS_OIDC_DEFAULT_GROUP", "SSO Users")

    await apply_env_oidc_provider(db_session)

    provider = (await db_session.execute(select(OIDCProvider).where(OIDCProvider.name == "PocketID"))).scalar_one()
    assert provider.is_env_managed is True
    assert provider.is_enabled is True
    assert provider.auto_create_users is True
    assert provider.default_group_id == group.id
    assert provider.client_secret == "super-secret"


@pytest.mark.asyncio
async def test_apply_env_oidc_provider_fetches_and_caches_icon(db_session, clear_oidc_env, monkeypatch):
    clear_oidc_env.setenv("PRINTOPS_OIDC_NAME", "PocketID")
    clear_oidc_env.setenv("PRINTOPS_OIDC_ISSUER_URL", "https://id.example.test")
    clear_oidc_env.setenv("PRINTOPS_OIDC_CLIENT_ID", "printops")
    clear_oidc_env.setenv("PRINTOPS_OIDC_CLIENT_SECRET", "super-secret")
    clear_oidc_env.setenv("PRINTOPS_OIDC_ICON_URL", "https://id.example.test/icon.png")

    async def fake_fetch_icon(url: str):
        assert url == "https://id.example.test/icon.png"
        return b"png-bytes", "image/png", "etag-1"

    monkeypatch.setattr("backend.app.services.oidc_icon.fetch_icon", fake_fetch_icon)

    await apply_env_oidc_provider(db_session)

    provider = (
        await db_session.execute(
            select(OIDCProvider).options(undefer(OIDCProvider.icon_data)).where(OIDCProvider.name == "PocketID")
        )
    ).scalar_one()
    assert provider.icon_url == "https://id.example.test/icon.png"
    assert provider.icon_data == b"png-bytes"
    assert provider.icon_content_type == "image/png"
    assert provider.icon_etag == "etag-1"


@pytest.mark.asyncio
async def test_apply_env_oidc_provider_releases_provider_when_env_removed(db_session, clear_oidc_env):
    provider = OIDCProvider(
        name="Env SSO",
        issuer_url="https://id.example.test",
        client_id="printops",
        scopes="openid email profile",
        is_enabled=True,
        is_autologin=True,
        is_env_managed=True,
    )
    provider.client_secret = "super-secret"
    db_session.add(provider)
    await db_session.commit()

    await apply_env_oidc_provider(db_session)

    released = (await db_session.execute(select(OIDCProvider).where(OIDCProvider.name == "Env SSO"))).scalar_one()
    assert released.is_env_managed is False
    assert released.is_enabled is False
    assert released.is_autologin is False
