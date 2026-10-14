"""MakerWorld adapter: reuse the proven client and its HTTP/security lifecycle."""

from backend.app.services.makerworld import MakerWorldService

from .base import ProviderDescriptor
from .registry import ProviderRegistration


class MakerWorldAdapter(MakerWorldService):
    """Request-scoped implementation of the model provider service contract."""


MAKERWORLD_PROVIDER = ProviderRegistration(
    descriptor=ProviderDescriptor(
        source_type="makerworld",
        display_name="MakerWorld",
        download_requires_token=True,
    ),
    parse_url=MakerWorldAdapter.parse_url,
    create=MakerWorldAdapter,
)
