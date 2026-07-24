"""Regression tests for per-cloud-identity filament caches."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.api.routes import cloud


@pytest.fixture(autouse=True)
def clear_filament_caches():
    cloud._filament_cache.clear()
    cloud._filament_cache_time.clear()
    cloud._filament_id_name_cache.clear()
    cloud._filament_id_name_cache_time.clear()


@pytest.mark.asyncio
async def test_filament_info_cache_is_scoped_to_cloud_identity():
    cloud._filament_cache[1] = {"preset": {"name": "User One", "k": 0.02}}
    cloud._filament_cache[2] = {"preset": {"name": "User Two", "k": 0.04}}
    cloud._filament_cache_time[1] = cloud._filament_cache_time[2] = 10**12

    first = await cloud.get_filament_info(["preset"], AsyncMock(), SimpleNamespace(id=1))
    second = await cloud.get_filament_info(["preset"], AsyncMock(), SimpleNamespace(id=2))

    assert first["preset"]["name"] == "User One"
    assert second["preset"]["name"] == "User Two"


@pytest.mark.asyncio
async def test_filament_id_map_does_not_fall_back_to_another_users_cache():
    cloud._filament_id_name_cache[1] = {"secret-id": "Private preset"}
    cloud._filament_id_name_cache_time[1] = 10**12

    with patch.object(cloud, "build_authenticated_cloud", new=AsyncMock(return_value=None)):
        result = await cloud.get_filament_id_map(AsyncMock(), SimpleNamespace(id=2))

    assert result == {}
