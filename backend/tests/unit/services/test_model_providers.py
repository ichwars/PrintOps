"""Provider registration and real MakerWorld service contract regressions."""

import httpx
import pytest

from backend.app.services.makerworld import MakerWorldUrlError, set_shared_http_client
from backend.app.services.model_providers.base import ModelProvider
from backend.app.services.model_providers.catalog import model_providers
from backend.app.services.model_providers.makerworld import MAKERWORLD_PROVIDER, MakerWorldAdapter
from backend.app.services.model_providers.registry import ProviderRegistry


@pytest.mark.parametrize(
    "url, expected",
    [
        ("makerworld.com/models/123", (123, None)),
        ("https://www.makerworld.com/de/models/123-slug#profileId-456", (123, 456)),
        ("https://makerworld.com/en/models/123?from=search#profileId=456", (123, 456)),
    ],
)
def test_url_lookup_preserves_known_forms(url, expected):
    provider = model_providers.for_url(url)
    assert provider is model_providers.for_source("makerworld")
    assert provider.parse_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://thingiverse.com/models/123",
        "https://makerworld.com.evil.test/models/123",
        "https://makerworld.com@evil.test/models/123",
        "https://evilmakerworld.com/models/123",
        "https://makerworld.com/designs/123",
        "https://[broken/models/123",
        "",
    ],
)
def test_unknown_or_spoofed_url_rejected(url):
    with pytest.raises(MakerWorldUrlError):
        model_providers.for_url(url)


def test_unknown_source_and_duplicate_registration_fail_closed():
    registry = ProviderRegistry()
    registry.register(MAKERWORLD_PROVIDER)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(MAKERWORLD_PROVIDER)
    assert registry.for_source("makerworld") is MAKERWORLD_PROVIDER
    with pytest.raises(KeyError):
        registry.for_source("unknown")


@pytest.mark.asyncio
async def test_registry_builds_independent_adapters_reusing_shared_transport():
    sent = []

    def handle(request):
        sent.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"id": 123})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        set_shared_http_client(client)
        try:
            provider = model_providers.for_source("makerworld")
            first = provider.create(auth_token="first")
            second = provider.create(auth_token="second")
            anonymous = provider.create(auth_token=None)
            assert isinstance(first, MakerWorldAdapter)
            assert isinstance(first, ModelProvider)
            for service in (first, second, anonymous, first):
                assert await service.get_design(123) == {"id": 123}
                await service.close()
                assert not client.is_closed
            assert sent == ["Bearer first", "Bearer second", None, "Bearer first"]
        finally:
            set_shared_http_client(None)
