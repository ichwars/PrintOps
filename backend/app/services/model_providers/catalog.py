"""Explicit production catalog. MakerWorld is currently the sole provider."""

from .makerworld import MAKERWORLD_PROVIDER
from .registry import ProviderRegistry

model_providers = ProviderRegistry()
model_providers.register(MAKERWORLD_PROVIDER)
