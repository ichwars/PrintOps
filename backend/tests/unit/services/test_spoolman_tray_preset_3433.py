"""The AMS sync keeps the tray's filament preset on the Spoolman spool (#3433).

An internal RFID spool stores the tray's ``tray_info_idx`` as its
``slicer_filament``. A Spoolman spool the sync created from the same tray got
only its tag, so assigning it to the external slot later -- no reader there --
wrote the generic preset for its material: a Bambu PLA Basic became Generic PLA.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.spoolman import AMSTray, SpoolmanClient, SpoolmanUnavailableError

UUID = "A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4"


def _tray(*, preset="GFA00", uuid=UUID, tag="", sub_brands="PLA Basic"):
    return AMSTray(
        ams_id=0,
        tray_id=0,
        tray_type="PLA",
        tray_sub_brands=sub_brands,
        tray_color="000000FF",
        remain=100,
        tag_uid=tag,
        tray_uuid=uuid,
        tray_info_idx=preset,
        tray_weight=1000,
    )


@pytest.fixture
def client():
    return SpoolmanClient("http://localhost:7912")


async def _create(client, tray):
    """Run the sync's auto-create for an unknown tag."""
    with (
        patch.object(client, "find_spool_by_tag", AsyncMock(return_value=None)),
        patch.object(client, "_find_or_create_filament", AsyncMock(return_value={"id": 5})),
        patch.object(client, "find_or_create_filament", AsyncMock(return_value=5)),
        patch.object(client, "create_spool", AsyncMock(return_value={"id": 9, "extra": {}})) as create,
        patch("backend.app.services.spoolman.resolve_bambu_color", AsyncMock(return_value=None)),
    ):
        await client.sync_ams_tray(tray, "X2D", None, auto_add_unknown_rfid=True)
    return create


class TestAutoCreate:
    @pytest.mark.asyncio
    async def test_a_bambu_tray_s_preset_is_stored_with_its_name(self, client):
        create = await _create(client, _tray())
        extra = create.call_args.kwargs["extra"]
        assert extra["bambu_slicer_filament"] == json.dumps("GFA00")
        assert extra["bambu_slicer_filament_name"] == json.dumps("Bambu PLA Basic")

    @pytest.mark.asyncio
    async def test_an_unlisted_preset_is_named_by_the_sub_brand(self, client):
        create = await _create(client, _tray(preset="GFZ77", sub_brands="PLA Something"))
        extra = create.call_args.kwargs["extra"]
        assert extra["bambu_slicer_filament"] == json.dumps("GFZ77")
        assert extra["bambu_slicer_filament_name"] == json.dumps("PLA Something")

    @pytest.mark.asyncio
    async def test_a_third_party_tag_gets_no_preset(self, client):
        create = await _create(client, _tray(preset="", uuid="0" * 32, tag="0A1B2C3D4E5F6071"))
        extra = create.call_args.kwargs["extra"]
        assert "bambu_slicer_filament" not in extra


class TestExistingSpool:
    async def _sync(self, client, spool, *, merge=None):
        merge = merge or AsyncMock(return_value={})
        with (
            patch.object(client, "find_spool_by_tag", AsyncMock(return_value=spool)),
            patch.object(client, "update_spool", AsyncMock(return_value={"id": spool["id"]})) as update,
            patch.object(client, "merge_spool_extra", merge),
        ):
            result = await client.sync_ams_tray(_tray(), "X2D", None)
        return merge, update, result

    @pytest.mark.asyncio
    async def test_a_spool_without_a_preset_gets_the_tray_s_once(self, client):
        merge, _, _ = await self._sync(client, {"id": 6, "extra": {"tag": json.dumps(UUID)}})
        merge.assert_awaited_once_with(
            6,
            {"bambu_slicer_filament": json.dumps("GFA00"), "bambu_slicer_filament_name": json.dumps("Bambu PLA Basic")},
            only_if_missing="bambu_slicer_filament",
        )

    @pytest.mark.asyncio
    async def test_an_empty_preset_counts_as_none(self, client):
        merge, _, _ = await self._sync(client, {"id": 6, "extra": {"bambu_slicer_filament": json.dumps("")}})
        merge.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_preset_set_by_hand_stays(self, client):
        merge, _, _ = await self._sync(client, {"id": 6, "extra": {"bambu_slicer_filament": json.dumps("GFA01")}})
        merge.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_spoolman_refusing_the_write_does_not_stop_the_sync(self, client):
        merge = AsyncMock(side_effect=SpoolmanUnavailableError("down"))
        _, update, result = await self._sync(client, {"id": 6, "extra": {}}, merge=merge)
        update.assert_awaited_once()
        assert result == {"id": 6}


@pytest.mark.asyncio
@pytest.mark.parametrize("current", [json.dumps("GFA01"), "malformed-but-set"])
async def test_a_preset_set_after_the_snapshot_is_preserved(client, current):
    latest = {"id": 6, "extra": {"bambu_slicer_filament": current, "own": "kept"}}
    with (
        patch.object(client, "get_spool", AsyncMock(return_value=latest)),
        patch.object(client, "update_spool_full", AsyncMock()) as write,
    ):
        await client._fill_missing_tray_preset({"id": 6, "extra": {}}, _tray())
    write.assert_not_awaited()


@pytest.mark.asyncio
async def test_filling_a_missing_preset_keeps_other_extra_fields(client):
    latest = {"id": 6, "extra": {"own": "kept"}}
    with (
        patch.object(client, "get_spool", AsyncMock(return_value=latest)),
        patch.object(client, "update_spool_full", AsyncMock()) as write,
    ):
        await client._fill_missing_tray_preset({"id": 6, "extra": {}}, _tray())
    fields = write.call_args.kwargs["extra"]
    assert fields["own"] == "kept"
    assert json.loads(fields["bambu_slicer_filament"]) == "GFA00"
