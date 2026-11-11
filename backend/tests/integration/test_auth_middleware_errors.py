"""Gateway failures must preserve the distinction between auth and application errors."""

import logging

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.core import auth
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_route_error_with_auth_disabled_uses_normal_server_error(async_client, monkeypatch):
    from backend.app.main import app

    async def broken_route():
        raise RuntimeError("synthetic route failure")

    monkeypatch.setattr(app.router, "routes", list(app.router.routes))
    app.add_api_route("/api/v1/test-gateway-error", broken_route, methods=["POST"])
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url=str(async_client.base_url)) as client:
        response = await client.post("/api/v1/test-gateway-error")
    assert response.status_code == 500


@pytest.mark.parametrize("failed_check", ["is_auth_enabled", "get_user_by_username"])
async def test_unavailable_database_check_returns_retryable_error(async_client, monkeypatch, failed_check):
    token = await _setup_admin(async_client)

    async def unavailable(*_args, **_kwargs):
        # The JWT path must distinguish this lookup failure from a bad JWT's ValueError.
        raise ValueError("synthetic auth database failure")

    monkeypatch.setattr(auth, failed_check, unavailable)
    response = await async_client.get("/api/v1/settings/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Authentication service temporarily unavailable"
    assert "WWW-Authenticate" not in response.headers


async def test_invalid_bearer_token_is_still_rejected_as_401(async_client):
    await _setup_admin(async_client)
    response = await async_client.get("/api/v1/settings/", headers={"Authorization": "Bearer invalid.fixture.token"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_uvicorn_errors_use_printops_file_handler():
    from backend.app import main

    if not main.app_settings.log_to_file:
        pytest.skip("File logging disabled in this test environment")
    assert main.file_handler in logging.getLogger("uvicorn.error").handlers
