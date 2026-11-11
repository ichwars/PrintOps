"""Automatic filament moves require current grants and the candidate's source."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.models.user import User
from backend.app.services.filament_deficit import compute_deficit_for_queue_item
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.queue_filament_mapping import creator_printer_ids
from backend.tests.unit.services.test_filament_deficit import (
    _assign,
    _queue_item,
    _setup_archive_3mf,
    _spool,
)
from backend.tests.unit.test_scheduler_model_filament_short_3137 import (
    _add_item,
    _get_item,
    _run,
    queue_db,  # noqa: F401
)

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("owner", [None, 999])
async def test_an_unknown_creator_cannot_automatically_move_to_any_printer(queue_db, owner):
    item_id = await _add_item(queue_db, printer_id=1, manual_start=True, filament_short=True, created_by_id=owner)
    launched = MagicMock()
    with patch("backend.app.services.queue_filament_mapping.is_auth_enabled", AsyncMock(return_value=True)):
        await _run(queue_db, PrintScheduler(), short={1}, launched=launched)
    launched.assert_not_called()
    assert (await _get_item(queue_db, item_id)).printer_id == 1


@pytest.mark.parametrize(
    ("allowed", "active", "expected"), [([], True, 1), ([3], True, 3), ([2], False, 1), (None, True, 2)]
)
async def test_an_automatic_move_uses_the_creators_current_grants(queue_db, allowed, active, expected):
    async with queue_db.session_maker() as db:
        user = User(username="creator", is_active=active, allowed_printer_ids=allowed)
        db.add(user)
        await db.commit()
        user_id = user.id
    item_id = await _add_item(queue_db, printer_id=1, manual_start=True, filament_short=True, created_by_id=user_id)
    launched = MagicMock()
    with patch("backend.app.services.queue_filament_mapping.is_auth_enabled", AsyncMock(return_value=True)):
        await _run(queue_db, PrintScheduler(), short={1}, launched=launched)
    assert (await _get_item(queue_db, item_id)).printer_id == expected
    assert launched.called is (expected != 1)


async def test_auth_disabled_keeps_unowned_local_jobs_available(queue_db):
    async with queue_db.session_maker() as db:
        with patch("backend.app.services.queue_filament_mapping.is_auth_enabled", AsyncMock(return_value=False)):
            assert await creator_printer_ids(db, None) is None


async def test_a_held_job_is_not_released_without_a_readable_requirement_source():
    scheduler = PrintScheduler()
    item = SimpleNamespace(id=1, skip_filament_check=False)
    with (
        patch.object(scheduler, "_compute_ams_mapping_for_printer", AsyncMock(return_value=[0])),
        patch.object(scheduler, "_get_filament_requirements", AsyncMock(return_value=None)),
        patch(
            "backend.app.services.print_scheduler.compute_deficit_for_queue_item", AsyncMock(return_value=[])
        ) as check,
    ):
        assert await scheduler._filament_short_on(MagicMock(), item, 2, require_known=True)
    check.assert_not_awaited()


async def test_candidate_amount_checks_read_the_candidates_file_without_changing_the_job(
    db_session, printer_factory, tmp_path
):
    printer = await printer_factory()
    a_path, b_path = tmp_path / "first", tmp_path / "alternative"
    a_path.mkdir()
    b_path.mkdir()
    a = await _setup_archive_3mf(db_session, a_path, [{"id": "1", "type": "PLA", "color": "#FFFFFF", "used_g": "10"}])
    b = await _setup_archive_3mf(db_session, b_path, [{"id": "1", "type": "PLA", "color": "#FFFFFF", "used_g": "900"}])
    spool = await _spool(db_session, label_weight=1000, weight_used=800)
    await _assign(db_session, printer_id=printer.id, spool_id=spool.id, ams_id=0, tray_id=0)
    item = await _queue_item(db_session, printer_id=printer.id, archive=a, ams_mapping=[0])
    candidate = SimpleNamespace(archive=b, library_file=None, plate_id=None)

    assert await compute_deficit_for_queue_item(db_session, item) == []
    short = await compute_deficit_for_queue_item(db_session, item, ams_mapping=[0], source_item=candidate)
    assert [(d.required_grams, d.remaining_grams) for d in short] == [(900, 200)]
    assert item.archive_id == a.id
    assert item.library_file_id is None
