"""Small contract used by the current model import routes.

Providers own upstream HTTP behavior. Library persistence and caller credential
resolution belong to the application, and credentials must stay request-local.
"""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


class ModelProviderError(Exception):
    """Base upstream model provider failure."""


class ModelProviderAuthError(ModelProviderError):
    """Missing or rejected upstream credentials."""


class ModelProviderForbiddenError(ModelProviderError):
    """Upstream refused access despite authentication."""


class ModelProviderNotFoundError(ModelProviderError):
    """Upstream model or profile does not exist."""


class ModelProviderUnavailableError(ModelProviderError):
    """Network, upstream status or malformed response failure."""


class ModelProviderUrlError(ModelProviderError):
    """Unsupported model URL or disallowed asset host."""


@dataclass(frozen=True)
class ProviderDescriptor:
    source_type: str
    display_name: str
    download_requires_token: bool


@runtime_checkable
class ModelProvider(Protocol):
    """Request-scoped upstream operations consumed by model import routes.

    IDs and metadata preserve the existing MakerWorld response shapes. A future
    provider must adapt to these shapes before it can use the current routes.
    """

    async def get_design(self, model_id: int) -> dict[str, Any]: ...
    async def get_design_instances(self, model_id: int) -> dict[str, Any]: ...
    async def get_profile_download(self, profile_id: int, model_id: str) -> dict[str, Any]: ...
    async def download_3mf(self, signed_url: str) -> tuple[bytes, str]: ...
    async def fetch_thumbnail(self, url: str) -> tuple[bytes, str]: ...
    async def close(self) -> None: ...


class ProviderFactory(Protocol):
    def __call__(self, *, auth_token: str | None = None) -> ModelProvider: ...
