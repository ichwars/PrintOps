"""Stateless provider definitions indexed by library source type or model URL."""

from collections.abc import Callable
from dataclasses import dataclass

from .base import ModelProviderUrlError, ProviderDescriptor, ProviderFactory


@dataclass(frozen=True)
class ProviderRegistration:
    descriptor: ProviderDescriptor
    parse_url: Callable[[str], tuple[int, int | None]]
    create: ProviderFactory


class ProviderRegistry:
    """Store factories, never request services or credentials.

    URL matching uses each provider's validating parser rather than substring
    matching; unsuccessful lookups cannot create an HTTP client.
    """

    def __init__(self) -> None:
        self._providers: dict[str, ProviderRegistration] = {}

    def register(self, provider: ProviderRegistration) -> None:
        source_type = provider.descriptor.source_type
        if source_type in self._providers:
            raise ValueError(f"Provider {source_type!r} is already registered")
        self._providers[source_type] = provider

    def for_source(self, source_type: str) -> ProviderRegistration:
        return self._providers[source_type]

    def for_url(self, url: str) -> ProviderRegistration:
        last_error: ModelProviderUrlError = ModelProviderUrlError("No provider supports this URL")
        for provider in self._providers.values():
            try:
                provider.parse_url(url)
            except ModelProviderUrlError as exc:
                last_error = exc
            else:
                return provider
        raise last_error
