"""Calibration names do not hide production jobs sent by PrintOps."""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.print_completion_setup import prepare_print_completion
from backend.app.services.printer_job_identity import ignore_internal_event
from backend.app.utils.print_jobs import is_internal_printer_job

pytestmark = pytest.mark.asyncio
NAME = "auto_cali_for_user_param"
DATA = {"filename": f"{NAME}.gcode", "subtask_name": NAME}


def context(engine, **kwargs):
    return {
        "expected": {},
        "registered_at": {},
        "ttl": 7200,
        "active": {},
        "session_factory": async_sessionmaker(engine, expire_on_commit=False),
        **kwargs,
    }


@pytest.mark.parametrize(
    "queue_state,filename,other_printer,internal",
    [
        ("printing", f"{NAME}.gcode.3mf", False, False),
        ("pending", f"{NAME}.gcode.3mf", False, True),
        ("completed", f"{NAME}.gcode.3mf", False, True),
        ("printing", "bracket.3mf", False, True),
        ("printing", f"{NAME}.gcode.3mf", True, True),
    ],
)
async def test_restart_uses_only_this_printers_matching_printing_queue_row(
    queue_state, filename, other_printer, internal, test_engine, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    owner = await printer_factory() if other_printer else printer
    archive = await archive_factory(owner.id, with_run=False, filename=filename)
    db_session.add(PrintQueueItem(printer_id=owner.id, archive_id=archive.id, status=queue_state, position=1))
    await db_session.commit()
    assert await ignore_internal_event(printer.id, DATA, "restart observation", **context(test_engine)) is internal


@pytest.mark.parametrize("stale", [False, True])
async def test_only_a_fresh_dispatch_registration_exempts_the_name(stale, test_engine):
    key = (9, f"{NAME}.gcode.3mf")
    state = context(test_engine, expected={key: 42}, registered_at={key: time.monotonic() - (7201 if stale else 1)})
    assert await ignore_internal_event(9, DATA, "start", **state) is stale


async def test_firmware_path_stays_internal_even_for_an_expected_name(test_engine):
    key = (9, NAME)
    state = context(test_engine, expected={key: 42}, registered_at={key: time.monotonic()}, active={key: 42})
    data = {**DATA, "filename": f"/usr/etc/print/{NAME}.gcode"}
    assert await ignore_internal_event(9, data, "start", **state)


async def test_running_dispatched_job_is_retained_for_completion_but_not_a_new_start(test_engine):
    state = context(test_engine, active={(9, NAME): 42})
    assert not await ignore_internal_event(9, DATA, "completion", **state)
    assert await ignore_internal_event(9, DATA, "start", **state)


async def test_dispatched_completion_keeps_tracking_and_recovery(monkeypatch):
    from backend.app.services import active_print_provenance, bambu_ftp, fallback_archive_recovery

    claimed = SimpleNamespace(print_name=NAME)
    monkeypatch.setattr(active_print_provenance, "claim_print_session", AsyncMock(return_value=claimed))
    discard, recover, clear = AsyncMock(), AsyncMock(), MagicMock()
    monkeypatch.setattr(active_print_provenance, "discard_print_session", discard)
    monkeypatch.setattr(fallback_archive_recovery, "recover_cached_fallback_archive", recover)
    monkeypatch.setattr(bambu_ftp, "clear_3mf_cache", clear)
    assert await prepare_print_completion(9, DATA, MagicMock(), {}, internal_job=False) == (claimed, False)
    discard.assert_not_awaited()
    recover.assert_awaited_once_with(9, DATA)
    clear.assert_called_once_with(9)


async def test_bare_a1_calibration_is_internal_and_nearby_user_names_are_not():
    assert is_internal_printer_job(f"{NAME}.gcode", NAME)
    assert not is_internal_printer_job(f"{NAME}_v2.gcode", None)
    assert not is_internal_printer_job(f"customer_{NAME}.3mf", None)


async def test_regular_user_job_does_not_query_dispatch_identity(test_engine):
    session_factory = MagicMock(side_effect=AssertionError("regular print needs no classification query"))
    assert not await ignore_internal_event(
        9, {"filename": "part.3mf"}, "start", **context(test_engine, session_factory=session_factory)
    )
