"""A VP's missing AMS is not the AMS choice for every printer of its model."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.virtual_printer.manager import VirtualPrinterInstance


@pytest.fixture
async def intake(tmp_path):
    added = []
    db = AsyncMock()
    db.get_bind = MagicMock(return_value=MagicMock())
    db.get_bind.return_value.dialect.name = "sqlite"
    db.execute.return_value.scalar = MagicMock(return_value=None)
    db.execute.return_value.all = MagicMock(return_value=[(101,)])

    def add(item):
        added.append(item)
        item.id = 101

    db.add = MagicMock(side_effect=add)
    context = AsyncMock()
    context.__aenter__.return_value = db
    factory = MagicMock(return_value=context)

    def vp(bound):
        return VirtualPrinterInstance(
            vp_id=1,
            name="VP",
            mode="queue",
            model="C12",
            access_code="test",
            serial_suffix="391800001",
            target_printer_id=99 if bound else None,
            base_dir=tmp_path,
            session_factory=factory,
        )

    return vp, db, added


@pytest.mark.asyncio
@pytest.mark.parametrize("bound", [False, True])
async def test_initial_slicer_ams_choice_belongs_only_to_the_bound_printer(intake, tmp_path, bound):
    vp, _db, added = intake
    instance = vp(bound)
    file = tmp_path / "job.3mf"
    file.write_bytes(b"test-archive")
    instance._slicer_print_options[file.name] = {"use_ams": False}
    archive = MagicMock(id=1, print_name="job")
    with (
        patch("backend.app.api.routes.settings.get_setting", AsyncMock(return_value=None)),
        patch("backend.app.services.archive.ArchiveService.archive_print", AsyncMock(return_value=archive)),
    ):
        await instance._add_to_print_queue(file, "192.0.2.1")
    assert len(added) == 1
    assert added[0].use_ams is (not bound)


@pytest.mark.asyncio
@pytest.mark.parametrize("bound", [False, True])
async def test_late_slicer_ams_choice_belongs_only_to_the_bound_printer(intake, bound):
    vp, db, _added = intake
    instance = vp(bound)
    instance._recent_queue_items["job.3mf"] = ([101], time.monotonic())
    await instance._restamp_recent_queue_item("job.3mf", {"use_ams": False, "timelapse": True})
    params = db.execute.await_args_list[-1].args[0].compile().params
    assert params["timelapse"] is True
    assert ("use_ams" in params) is bound
    if bound:
        assert params["use_ams"] is False
