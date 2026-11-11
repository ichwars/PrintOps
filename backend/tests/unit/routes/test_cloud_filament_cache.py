"""Regression tests for per-cloud-identity filament caches."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.api.routes import cloud


@pytest.fixture(autouse=True)
def clear_filament_caches():
    cloud.forget_all_cloud_presets()
    yield
    cloud.forget_all_cloud_presets()


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
        result = await cloud.get_filament_id_map(current_user=SimpleNamespace(id=2))

    assert result == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("envelope", [None, "P-envelope"])
async def test_filament_map_reads_nested_id_with_envelope_precedence(envelope):
    client = SimpleNamespace(
        is_authenticated=True,
        get_slicer_settings=AsyncMock(return_value={"filament": {"private": [{"setting_id": "PF-test"}]}}),
        get_setting_detail=AsyncMock(
            return_value={
                "filament_id": envelope,
                "setting": {"filament_id": "P-nested"},
                "name": "PLA Silk @Bambu Lab X1C 0.4 nozzle",
            }
        ),
        close=AsyncMock(),
    )
    with patch.object(cloud, "build_authenticated_cloud", AsyncMock(return_value=client)):
        result = await cloud.get_filament_id_map(current_user=SimpleNamespace(id=3))
    assert result == {envelope or "P-nested": "PLA Silk"}
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_simultaneous_details_share_a_request_only_with_the_same_account():
    started, release = asyncio.Event(), asyncio.Event()
    cloud_calls = []

    def make_client(account):
        async def get_detail(setting_id):
            cloud_calls.append((account, setting_id))
            if account == 1:
                started.set()
                await release.wait()
            return {"name": f"Account {account}"}

        return SimpleNamespace(is_authenticated=True, get_setting_detail=get_detail, close=AsyncMock())

    async def build(_db, user):
        return make_client(user.id)

    async def request(account):
        return await cloud.get_filament_info(["same-id"], AsyncMock(), SimpleNamespace(id=account))

    with patch.object(cloud, "build_authenticated_cloud", build):
        first = asyncio.create_task(request(1))
        await started.wait()
        second = asyncio.create_task(request(1))
        assert await request(2) == {"same-id": {"name": "Account 2", "k": None}}
        release.set()
        assert await asyncio.gather(first, second) == [{"same-id": {"name": "Account 1", "k": None}}] * 2
    assert cloud_calls == [(1, "same-id"), (2, "same-id")]


@pytest.mark.asyncio
async def test_old_inflight_details_cannot_populate_or_replace_a_relinked_accounts_cache():
    started, release = asyncio.Event(), asyncio.Event()

    async def get_old(_setting_id):
        started.set()
        await release.wait()
        return {"name": "Old account"}

    old_client = SimpleNamespace(is_authenticated=True, get_setting_detail=get_old, close=AsyncMock())
    new_client = SimpleNamespace(
        is_authenticated=True, get_setting_detail=AsyncMock(return_value={"name": "New account"}), close=AsyncMock()
    )
    user = SimpleNamespace(id=1)

    with patch.object(cloud, "build_authenticated_cloud", AsyncMock(side_effect=[old_client, new_client])):
        old_request = asyncio.create_task(cloud.get_filament_info(["same-id"], AsyncMock(), user))
        await started.wait()
        cloud.forget_cloud_presets_for_account(user.id)
        expected = {"same-id": {"name": "New account", "k": None}}
        assert await cloud.get_filament_info(["same-id"], AsyncMock(), user) == expected
        release.set()
        assert await old_request == {}
        assert await cloud.get_filament_info(["same-id"], AsyncMock(), user) == expected
