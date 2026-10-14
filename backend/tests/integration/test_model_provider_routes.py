"""Offline request tests using the production registry and real adapter.

Only HTTP transport is replaced: credentials, permission dependencies, error
mapping, source dedupe and library persistence run through production code.
"""

from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select

from backend.app.models.library import LibraryFile
from backend.app.models.user import User
from backend.app.services.makerworld import set_shared_http_client
from backend.app.services.model_providers.catalog import model_providers
from backend.tests.integration.test_makerworld_apikey_auth import (
    _make_key,
    _setup_auth_with_admin,
    _store_admin_cloud_token,
)


@asynccontextmanager
async def upstream(status=200, signed_url="https://makerworld.bblmw.com/cube.3mf"):
    requests = []

    def handle(request):
        requests.append(request)
        if request.url.host == "makerworld.bblmw.com":
            return httpx.Response(200, content=b"PK\x03\x04offline-3mf", headers={"content-type": "image/png"})
        if "/iot-service/" in request.url.path:
            return httpx.Response(status, json={"url": signed_url, "name": "Cube%20One.3mf", "error": "Restricted"})
        if request.url.path.endswith("/instances"):
            return httpx.Response(200, json={"hits": [{"id": 10, "profileId": 456}]})
        return httpx.Response(200, json={"id": 123, "modelId": "USmodel", "instances": [{"profileId": 456}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        set_shared_http_client(client)
        try:
            yield requests, client
        finally:
            set_shared_http_client(None)


@pytest.mark.asyncio
async def test_real_adapter_resolve_import_dedupe_thumbnail_and_owner(async_client, db_session):
    await _setup_auth_with_admin(async_client)
    admin = await _store_admin_cloud_token(db_session, "mwadmin", "owner-token")
    key = await _make_key(db_session, owner=admin, name="real-provider")
    headers = {"X-API-Key": key}
    async with upstream() as (requests, client):
        with (
            patch.object(model_providers, "for_source", wraps=model_providers.for_source) as by_source,
            patch.object(model_providers, "for_url", wraps=model_providers.for_url) as by_url,
        ):
            resolved = await async_client.post(
                "/api/v1/makerworld/resolve",
                headers=headers,
                json={"url": "https://www.makerworld.com/en/models/123-slug#profileId-456"},
            )
            assert resolved.status_code == 200, resolved.text
            assert resolved.json() == {
                "model_id": 123,
                "profile_id": 456,
                "design": {"id": 123, "modelId": "USmodel", "instances": [{"profileId": 456}]},
                "instances": [{"id": 10, "profileId": 456}],
                "already_imported_library_ids": [],
            }
            first = await async_client.post(
                "/api/v1/makerworld/import",
                headers=headers,
                json={"model_id": 123},
            )
            assert first.status_code == 200, first.text
            assert first.json()["filename"] == "Cube One.3mf"
            assert first.json()["profile_id"] == 456
            second = await async_client.post(
                "/api/v1/makerworld/import",
                headers=headers,
                json={"model_id": 123, "profile_id": 456},
            )
            assert second.status_code == 200, second.text
            assert second.json()["was_existing"] is True
            assert second.json()["library_file_id"] == first.json()["library_file_id"]
            thumbnail = await async_client.get(
                "/api/v1/makerworld/thumbnail",
                params={"url": "https://makerworld.bblmw.com/cover.png"},
            )
            assert thumbnail.status_code == 200
            assert thumbnail.headers["content-type"] == "image/png"
            assert thumbnail.headers["cache-control"] == "public, max-age=86400, immutable"
            by_url.assert_called_once()
            assert by_source.call_count >= 3, "Import and thumbnail must construct providers via registry"
        assert not client.is_closed
        row = (await db_session.execute(select(LibraryFile))).scalar_one()
        assert row.created_by_id == admin.id
        assert row.source_type == "makerworld"
        assert row.source_url == "https://makerworld.com/models/123#profileId-456"
        api_requests = [r for r in requests if r.url.host == "api.bambulab.com"]
        assert all(r.headers["authorization"] == "Bearer owner-token" for r in api_requests)
        downloads = [r for r in requests if r.url.path == "/cube.3mf"]
        assert len(downloads) == 1
        assert "authorization" not in downloads[0].headers
        manifests = [r for r in requests if "/iot-service/" in r.url.path]
        assert all(r.url.params["model_id"] == "USmodel" for r in manifests)


@pytest.mark.asyncio
async def test_real_adapter_denies_cloud_scope_and_isolates_request_credentials(async_client, db_session):
    await _setup_auth_with_admin(async_client)
    admin = await _store_admin_cloud_token(db_session, "mwadmin", "first-token")
    first = await _make_key(db_session, owner=admin, name="first")
    other = User(username="other", password_hash="unused", cloud_token="second-token", cloud_region="global")
    db_session.add(other)
    await db_session.commit()
    second = await _make_key(db_session, owner=other, name="second")
    denied = await _make_key(db_session, owner=admin, name="denied-cloud", can_access_cloud=False)
    async with upstream() as (requests, client):
        for key in (first, second, denied, first):
            response = await async_client.post(
                "/api/v1/makerworld/resolve",
                headers={"X-API-Key": key},
                json={"url": "makerworld.com/models/123"},
            )
            assert response.status_code == 200, response.text
        assert [r.headers.get("authorization") for r in requests] == [
            "Bearer first-token",
            "Bearer first-token",
            "Bearer second-token",
            "Bearer second-token",
            None,
            None,
            "Bearer first-token",
            "Bearer first-token",
        ]
        requests.clear()
        response = await async_client.post(
            "/api/v1/makerworld/import",
            headers={"X-API-Key": denied},
            json={"model_id": 123},
        )
        assert response.status_code == 401, response.text
        assert response.json()["detail"] == "Downloading files from MakerWorld requires a Bambu Cloud login"
        assert len(requests) == 1 and "authorization" not in requests[0].headers
        assert not client.is_closed
        assert (await db_session.execute(select(LibraryFile))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("scope, endpoint", [("can_read_status", "resolve"), ("can_manage_library", "import")])
async def test_route_permission_denial_precedes_provider_network(async_client, db_session, scope, endpoint):
    await _setup_auth_with_admin(async_client)
    admin = await _store_admin_cloud_token(db_session, "mwadmin", "owner-token")
    key = await _make_key(db_session, owner=admin, name="denied", **{scope: False})
    async with upstream() as (requests, _client):
        response = await async_client.post(
            f"/api/v1/makerworld/{endpoint}",
            headers={"X-API-Key": key},
            json={"url": "makerworld.com/models/123"} if endpoint == "resolve" else {"model_id": 123},
        )
        assert response.status_code == 403, response.text
        assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status, expected", [(401, 401), (403, 403), (404, 404), (503, 502)])
async def test_real_adapter_preserves_upstream_error_mapping(async_client, db_session, status, expected):
    await _setup_auth_with_admin(async_client)
    admin = await _store_admin_cloud_token(db_session, "mwadmin", "owner-token")
    key = await _make_key(db_session, owner=admin, name="error")
    async with upstream(status=status) as (requests, client):
        response = await async_client.post(
            "/api/v1/makerworld/import",
            headers={"X-API-Key": key},
            json={"model_id": 123},
        )
        assert response.status_code == expected, response.text
        assert len(requests) == 2
        assert not client.is_closed
        if status in (401, 403):
            assert response.json()["detail"] == "Restricted"


@pytest.mark.asyncio
async def test_real_adapter_download_and_thumbnail_ssrf_guard(async_client, db_session):
    await _setup_auth_with_admin(async_client)
    admin = await _store_admin_cloud_token(db_session, "mwadmin", "owner-token")
    key = await _make_key(db_session, owner=admin, name="ssrf")
    async with upstream(signed_url="http://127.0.0.1/private.3mf") as (requests, client):
        response = await async_client.post(
            "/api/v1/makerworld/import",
            headers={"X-API-Key": key},
            json={"model_id": 123},
        )
        assert response.status_code == 400, response.text
        assert len(requests) == 2
        thumbnail = await async_client.get(
            "/api/v1/makerworld/thumbnail",
            params={"url": "https://makerworld.bblmw.com.evil.test/a.png"},
        )
        assert thumbnail.status_code == 400
        assert len(requests) == 2
        assert not client.is_closed


@pytest.mark.asyncio
@pytest.mark.parametrize("cloud_scope", [True, False])
async def test_provider_status_uses_scoped_token_without_http_client(async_client, db_session, cloud_scope):
    await _setup_auth_with_admin(async_client)
    admin = await _store_admin_cloud_token(db_session, "mwadmin", "owner-token")
    key = await _make_key(db_session, owner=admin, name="status", can_access_cloud=cloud_scope)
    with patch.object(model_providers, "for_source", wraps=model_providers.for_source) as lookup:
        async with upstream() as (requests, _client):
            response = await async_client.get("/api/v1/makerworld/status", headers={"X-API-Key": key})
            assert response.status_code == 200
            assert response.json() == {"has_cloud_token": cloud_scope, "can_download": cloud_scope}
            assert requests == []
        lookup.assert_called_once_with("makerworld")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "https://unknown.test/models/123",
        "https://makerworld.com.evil.test/models/123",
        "https://makerworld.com@evil.test/models/123",
        "https://makerworld.com/designs/123",
    ],
)
async def test_unknown_model_url_rejected_before_provider_http(async_client, url):
    async with upstream() as (requests, _client):
        response = await async_client.post("/api/v1/makerworld/resolve", json={"url": url})
        assert response.status_code == 400, response.text
        assert requests == []
