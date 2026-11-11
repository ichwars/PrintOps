"""Completion must retain its weight-sync hold after claiming the session."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.models.active_print_session import ActivePrintSession
from backend.app.services.print_usage_lifecycle import _completing, hold_completion_charges, printer_is_charging
from backend.app.services.usage_tracker import PrintSession, _active_sessions, persist_session

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def isolate():
    _active_sessions.clear()
    _completing.clear()
    yield
    _active_sessions.clear()
    _completing.clear()


async def test_overlapping_completions_keep_the_hold_until_both_finish():
    entered = [asyncio.Event(), asyncio.Event()]
    release = [asyncio.Event(), asyncio.Event()]

    @hold_completion_charges
    async def complete(printer_id, data):
        index = data["index"]
        entered[index].set()
        await release[index].wait()

    first = asyncio.create_task(complete(7, {"index": 0}))
    second = asyncio.create_task(complete(7, {"index": 1}))
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered)), 2)
        release[0].set()
        await first
        assert printer_is_charging(7)
        assert not printer_is_charging(8)
        # A newly started print must not drop a previous completion's hold.
        _active_sessions[7] = PrintSession(7, "next", datetime.now(timezone.utc))
        _active_sessions.pop(7)
        assert printer_is_charging(7)
    finally:
        for event in release:
            event.set()
        await asyncio.gather(first, second)
    assert not printer_is_charging(7)


async def test_failure_releases_the_hold():
    from backend.app.main import on_print_complete

    with (
        patch("backend.app.main.prepare_print_completion", AsyncMock(side_effect=RuntimeError("failed"))),
        pytest.raises(RuntimeError, match="failed"),
    ):
        await on_print_complete(7, {})
    assert not printer_is_charging(7)


async def test_nameless_completion_discards_only_its_claimed_generation(test_engine, db_session, printer_factory):
    from backend.app.main import on_print_complete

    printer = await printer_factory()
    printer_id = printer.id
    session = PrintSession(printer_id, "part", datetime.now(timezone.utc))
    _active_sessions[printer_id] = session
    await persist_session(db_session, session)
    maker = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def prepare(*args, internal_job):
        claimed = _active_sessions.pop(printer_id)
        assert printer_is_charging(printer_id)
        return claimed, False

    with (
        patch("backend.app.main.prepare_print_completion", prepare),
        patch("backend.app.main.async_session", maker),
        patch("backend.app.main.printer_manager", MagicMock()),
        patch("backend.app.main.ws_manager.send_print_complete", AsyncMock()),
        patch("backend.app.main.mqtt_relay.on_print_complete", AsyncMock()),
        patch("backend.app.services.active_print_provenance.async_session", maker),
    ):
        await on_print_complete(printer_id, {"status": "completed"})

    assert not printer_is_charging(printer_id)
    db_session.expire_all()
    assert await db_session.get(ActivePrintSession, printer_id) is None
