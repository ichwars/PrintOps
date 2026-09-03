from unittest.mock import AsyncMock, patch

import httpx
import pytest

from backend.app.services import lexware_client as module
from backend.app.services.lexware_client import LexwareClient, LexwareError
from backend.app.services.lexware_connections import encrypt_api_key

ID = "12345678-1234-4234-8234-123456789abc"


@pytest.fixture(autouse=True)
def no_rate_delay(monkeypatch):
    monkeypatch.setattr(module, "_throttle", AsyncMock())


@pytest.mark.parametrize(
    "path",
    [
        "https://other.example/v1/profile",
        "//other.example/v1/profile",
        "/v1/event-subscriptions",
        "/v1/invoices/../profile",
        "/v1/profile?token=secret",
        "/v1/invoices/%2e%2e/file",
        f"/v1/invoices/{ID}/document",
        f"/v1/contacts/{ID}/file",
    ],
)
async def test_forbidden_paths_never_reach_network(path):
    called = []
    async with LexwareClient(
        "test-key", transport=httpx.MockTransport(lambda request: called.append(request))
    ) as client:
        with pytest.raises(LexwareError):
            await client.get_json(path)
    assert called == []


async def test_get_only_and_redirect_does_not_forward_credentials():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example/"})

    async with LexwareClient("hidden-token", transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(LexwareError) as caught:
            await client.get_json("/v1/profile")
    assert "hidden-token" not in str(caught.value)
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.host == "api.lexware.io"


async def test_page_sequence_completes_and_duplicate_pages_abort():
    def handle(request):
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"content": [{"id": str(page)}], "last": page == 1})

    async with LexwareClient("test-key", transport=httpx.MockTransport(handle)) as client:
        assert await client.list_pages("/v1/articles") == [{"id": "0"}, {"id": "1"}]
    async with LexwareClient(
        "test-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"content": [{"id": ID}], "last": False})
        ),
    ) as client:
        with pytest.raises(LexwareError, match="paging"):
            await client.list_pages("/v1/articles")


async def test_failure_response_body_is_never_exposed():
    async with LexwareClient(
        "hidden-token",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, text="internal token hidden-token private customer")
        ),
    ) as client:
        with pytest.raises(LexwareError) as caught:
            await client.get_json("/v1/profile")
    assert caught.value.status_code == 403
    assert "hidden-token" not in str(caught.value)
    assert "customer" not in str(caught.value)


async def test_declared_size_cap_and_guard_prevent_request(monkeypatch):
    monkeypatch.setattr(module, "MAX_JSON_BYTES", 5)
    async with LexwareClient(
        "test-key", transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"large": True}))
    ) as client:
        with pytest.raises(LexwareError, match="size"):
            await client.get_json("/v1/profile")
    guard = AsyncMock(side_effect=LexwareError("Disconnected"))
    called = []
    async with LexwareClient(
        "test-key", before_request=guard, transport=httpx.MockTransport(lambda req: called.append(req))
    ) as client:
        with pytest.raises(LexwareError, match="Disconnected"):
            await client.get_json("/v1/profile")
    assert not called


async def test_rate_limit_retry_is_bounded_and_rechecks_guard():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"})

    guard = AsyncMock()
    async with LexwareClient("test-key", transport=httpx.MockTransport(handle), before_request=guard) as client:
        with pytest.raises(LexwareError) as caught:
            await client.get_json("/v1/profile")
    assert caught.value.status_code == 429
    assert len(requests) == guard.await_count == 3


def test_integration_rejects_existing_plaintext_recovery_mode():
    with (
        patch("backend.app.services.lexware_connections.encryption.mfa_encrypt", return_value="private-key"),
        pytest.raises(LexwareError, match="storage"),
    ):
        encrypt_api_key("private-key")


async def test_original_filename_is_generated_not_trusted():
    async with LexwareClient(
        "test-key",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                content=b"%PDF-1.7\n",
                headers={
                    "Content-Type": "application/pdf",
                    "Content-Disposition": 'attachment; filename="../../secret"',
                },
            )
        ),
    ) as client:
        data, media_type, filename = await client.get_file(f"/v1/invoices/{ID}/file")
    assert filename == f"lexware-{ID}.pdf"
    assert data.startswith(b"%PDF") and media_type == "application/pdf"


async def test_upstream_decimal_tokens_keep_their_exact_value():
    async with LexwareClient(
        "test-key",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b'{"netPrice": 123456789.123456}')),
    ) as client:
        value = await client.get_json("/v1/profile")
    assert value["netPrice"] == "123456789.123456"
