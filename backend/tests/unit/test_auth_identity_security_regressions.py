"""Focused regressions for authentication and identity security boundaries."""

from __future__ import annotations

import inspect
import ipaddress
import ssl
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.api.routes import _oidc_helpers, api_keys as api_key_routes, mfa, users as user_routes
from backend.app.core.auth import _validate_api_key, generate_api_key, get_api_key as get_webhook_api_key
from backend.app.models.api_key import APIKey
from backend.app.models.user import User
from backend.app.schemas.auth import OIDCProviderCreate, OIDCProviderUpdate
from backend.app.services import ldap_service


def test_api_key_create_and_update_declare_admin_role_dependencies():
    assert "_admin" in inspect.signature(api_key_routes.create_api_key).parameters
    assert "_admin" in inspect.signature(api_key_routes.update_api_key).parameters


def test_cross_user_mfa_disable_declares_admin_role_dependency():
    assert "_admin" in inspect.signature(mfa.admin_disable_2fa).parameters


def test_oidc_private_ip_literal_requires_and_honors_explicit_opt_in():
    payload = {
        "name": "LAN IdP",
        "issuer_url": "https://192.168.1.10",
        "client_id": "printops",
        "client_secret": "secret",
    }

    with pytest.raises(ValidationError, match="private"):
        OIDCProviderCreate(**payload)

    provider = OIDCProviderCreate(**payload, allow_private_network=True)
    assert provider.issuer_url == "https://192.168.1.10"


def test_oidc_private_ip_literal_update_honors_explicit_opt_in():
    update = OIDCProviderUpdate(
        issuer_url="https://192.168.1.11",
        allow_private_network=True,
    )

    assert update.issuer_url == "https://192.168.1.11"


def test_admin_password_update_advances_session_freshness_timestamp():
    helper = getattr(user_routes, "_set_local_user_password", None)
    assert helper is not None
    user = User(username="reset-target", password_hash="old", role="user", is_active=True)
    before = datetime.now(timezone.utc)

    helper(user, "replacement-password")

    assert user.password_hash != "old"
    assert user.password_changed_at is not None
    changed = user.password_changed_at
    if changed.tzinfo is None:
        changed = changed.replace(tzinfo=timezone.utc)
    assert changed >= before


def test_custom_oidc_claim_cannot_auto_link_without_matching_verified_email():
    provider = SimpleNamespace(
        id=1,
        email_claim="preferred_username",
        require_email_verified=True,
        auto_link_existing_accounts=True,
    )
    claims = {
        "preferred_username": "victim@example.com",
        "email": "attacker@example.com",
        "email_verified": True,
    }

    assert mfa._resolve_provider_email(provider, claims, "attacker-sub") is None


def test_custom_oidc_claim_can_auto_link_when_it_matches_verified_standard_email():
    provider = SimpleNamespace(
        id=1,
        email_claim="preferred_username",
        require_email_verified=True,
        auto_link_existing_accounts=True,
    )
    claims = {
        "preferred_username": "user@example.com",
        "email": "User@Example.com",
        "email_verified": True,
    }

    assert mfa._resolve_provider_email(provider, claims, "user-sub") == "user@example.com"


@pytest.mark.asyncio
async def test_oidc_transport_pins_dns_and_preserves_tls_identity(monkeypatch):
    transport_type = getattr(_oidc_helpers, "OIDCPinnedTransport", None)
    assert transport_type is not None
    seen: list[httpx.Request] = []

    class CaptureTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, request=request, content=b"{}")

    async def resolve(hostname: str) -> tuple[ipaddress._BaseAddress, ...]:
        assert hostname == "idp.example.test"
        return (ipaddress.ip_address("93.184.216.34"),)

    monkeypatch.setattr(_oidc_helpers, "_resolve_oidc_host", resolve, raising=False)
    transport = transport_type("https://idp.example.test", inner=CaptureTransport())
    request = httpx.Request("GET", "https://idp.example.test/.well-known/openid-configuration")

    await transport.handle_async_request(request)

    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "idp.example.test"
    assert seen[0].extensions["sni_hostname"] == "idp.example.test"


@pytest.mark.asyncio
async def test_public_oidc_issuer_cannot_redirect_transport_to_private_endpoint(monkeypatch):
    transport_type = getattr(_oidc_helpers, "OIDCPinnedTransport", None)
    policy_error = getattr(_oidc_helpers, "OIDCEndpointPolicyError", ValueError)
    assert transport_type is not None

    async def resolve(hostname: str) -> tuple[ipaddress._BaseAddress, ...]:
        return {
            "idp.example.test": (ipaddress.ip_address("93.184.216.34"),),
            "internal.example.test": (ipaddress.ip_address("10.0.0.5"),),
        }[hostname]

    monkeypatch.setattr(_oidc_helpers, "_resolve_oidc_host", resolve, raising=False)
    transport = transport_type("https://idp.example.test")

    with pytest.raises(policy_error):
        await transport.handle_async_request(httpx.Request("GET", "https://internal.example.test/jwks"))


@pytest.mark.asyncio
async def test_private_oidc_issuer_keeps_same_host_support_but_blocks_other_private_hosts(monkeypatch):
    transport_type = getattr(_oidc_helpers, "OIDCPinnedTransport", None)
    policy_error = getattr(_oidc_helpers, "OIDCEndpointPolicyError", ValueError)
    assert transport_type is not None
    seen: list[httpx.Request] = []

    class CaptureTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, request=request, content=b"{}")

    async def resolve(hostname: str) -> tuple[ipaddress._BaseAddress, ...]:
        return {
            "pocketid.internal.test": (ipaddress.ip_address("10.0.0.10"),),
            "other.internal.test": (ipaddress.ip_address("10.0.0.11"),),
        }[hostname]

    monkeypatch.setattr(_oidc_helpers, "_resolve_oidc_host", resolve, raising=False)
    transport = transport_type(
        "https://pocketid.internal.test",
        allow_private_network=True,
        inner=CaptureTransport(),
    )

    await transport.handle_async_request(httpx.Request("GET", "https://pocketid.internal.test/jwks"))
    assert seen[0].url.host == "10.0.0.10"

    with pytest.raises(policy_error):
        await transport.handle_async_request(httpx.Request("GET", "https://other.internal.test/jwks"))


@pytest.mark.asyncio
async def test_private_oidc_split_host_is_allowed_when_it_pins_to_same_service(monkeypatch):
    transport_type = getattr(_oidc_helpers, "OIDCPinnedTransport", None)
    assert transport_type is not None
    seen: list[httpx.Request] = []

    class CaptureTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, request=request, content=b"{}")

    async def resolve(hostname: str) -> tuple[ipaddress._BaseAddress, ...]:
        assert hostname in {"auth.internal.test", "keys.internal.test"}
        return (ipaddress.ip_address("10.0.0.10"),)

    monkeypatch.setattr(_oidc_helpers, "_resolve_oidc_host", resolve, raising=False)
    transport = transport_type(
        "https://auth.internal.test",
        allow_private_network=True,
        inner=CaptureTransport(),
    )

    await transport.handle_async_request(httpx.Request("GET", "https://keys.internal.test/jwks"))

    assert seen[0].url.host == "10.0.0.10"
    assert seen[0].headers["host"] == "keys.internal.test"


@pytest.mark.asyncio
async def test_private_oidc_endpoint_cannot_switch_to_another_port(monkeypatch):
    transport_type = getattr(_oidc_helpers, "OIDCPinnedTransport", None)
    policy_error = getattr(_oidc_helpers, "OIDCEndpointPolicyError", ValueError)
    assert transport_type is not None

    async def resolve(_hostname: str) -> tuple[ipaddress._BaseAddress, ...]:
        return (ipaddress.ip_address("10.0.0.10"),)

    monkeypatch.setattr(_oidc_helpers, "_resolve_oidc_host", resolve, raising=False)
    transport = transport_type("https://auth.internal.test", allow_private_network=True)

    with pytest.raises(policy_error):
        await transport.handle_async_request(httpx.Request("GET", "https://auth.internal.test:8443/jwks"))


@pytest.mark.asyncio
async def test_private_oidc_issuer_is_denied_without_explicit_opt_in(monkeypatch):
    transport_type = getattr(_oidc_helpers, "OIDCPinnedTransport", None)
    policy_error = getattr(_oidc_helpers, "OIDCEndpointPolicyError", ValueError)
    assert transport_type is not None

    async def resolve(_hostname: str) -> tuple[ipaddress._BaseAddress, ...]:
        return (ipaddress.ip_address("10.0.0.10"),)

    monkeypatch.setattr(_oidc_helpers, "_resolve_oidc_host", resolve, raising=False)
    transport = transport_type("https://idp.example.test")

    with pytest.raises(policy_error, match="private-network access is disabled"):
        await transport.handle_async_request(httpx.Request("GET", "https://idp.example.test/jwks"))


def test_ldap_tls_uses_system_verification_without_custom_ca(monkeypatch):
    captured: dict[str, object] = {}

    class FakeTLS:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    class FakeServer:
        def __init__(self, *_args, **kwargs):
            captured["tls"] = kwargs["tls"]

    monkeypatch.setattr(ldap_service, "Tls", FakeTLS)
    monkeypatch.setattr(ldap_service, "Server", FakeServer)
    config = ldap_service.LDAPConfig(
        server_url="ldaps://ldap.example.test",
        bind_dn="",
        bind_password="",
        search_base="dc=example,dc=test",
        user_filter="(uid={username})",
        security="ldaps",
        group_mapping={},
        auto_provision=False,
        ca_cert_path="",
        default_group="",
    )

    ldap_service._create_server(config)

    assert captured["validate"] == ssl.CERT_REQUIRED
    assert "ca_certs_file" not in captured


@pytest.mark.asyncio
async def test_inactive_owner_invalidates_standard_and_webhook_api_key(db_session):
    owner = User(username="disabled-key-owner", password_hash="x", role="user", is_active=False)
    db_session.add(owner)
    await db_session.flush()
    plaintext, key_hash, key_prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="disabled-owner-key",
            key_hash=key_hash,
            key_prefix=key_prefix,
            user_id=owner.id,
            enabled=True,
            can_read_status=True,
        )
    )
    await db_session.commit()

    assert await _validate_api_key(db_session, plaintext) is None
    with pytest.raises(HTTPException) as exc_info:
        await get_webhook_api_key(authorization=None, x_api_key=plaintext, db=db_session)
    assert exc_info.value.status_code == 401
