"""Same-printer controls and deletion must acquire local then database locks."""

import asyncio
from contextvars import ContextVar
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import event

from backend.app.services import drying_ownership
from backend.tests.integration.test_overlay_authorization_boundaries import mint
from backend.tests.integration.test_overlay_grant_transactions import test_engine  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]
_operation = ContextVar("overlay_lock_order_operation", default="")


async def labelled(label, request):
    token = _operation.set(label)
    try:
        return await request
    finally:
        _operation.reset(token)


@pytest.mark.parametrize("first", ["patch", "delete"])
async def test_same_printer_delete_and_patch_use_local_then_database_lock(
    async_client, printer_factory, test_engine, first
):
    printer = await printer_factory()
    _, headers, _ = await mint(async_client, [])
    held, release, competing_lock_attempted = asyncio.Event(), asyncio.Event(), asyncio.Event()
    second = "delete" if first == "patch" else "patch"
    writes = []

    class GateLock(asyncio.Lock):
        async def acquire(self):
            if _operation.get() == second:
                competing_lock_attempted.set()
            acquired = await super().acquire()
            if _operation.get() == first:
                held.set()
                await release.wait()
            return acquired

    # Keep the real drying guard and its real mutex, only introduce a scheduling
    # barrier after acquisition and before its first DB writer statement.
    locks = drying_ownership._locks.setdefault(asyncio.get_running_loop(), {})
    locks[printer.id] = GateLock()

    def observe(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("UPDATE printers SET"):
            writes.append(_operation.get())

    event.listen(test_engine.sync_engine, "before_cursor_execute", observe)
    with (
        patch("backend.app.api.routes.printers.printer_manager.disconnect_printer"),
        patch("backend.app.api.routes.printers.printer_manager.connect_printer", AsyncMock()),
    ):

        def request(operation):
            if operation == "delete":
                return async_client.delete(f"/api/v1/printers/{printer.id}", headers=headers)
            return async_client.patch(
                f"/api/v1/printers/{printer.id}", headers=headers, json={"name": "Edited concurrently"}
            )

        first_task = asyncio.create_task(labelled(first, request(first)))
        second_task = None
        try:
            await asyncio.wait_for(held.wait(), 5)
            second_task = asyncio.create_task(labelled(second, request(second)))
            await asyncio.wait_for(competing_lock_attempted.wait(), 5)
            assert second not in writes, "Competing request acquired the database writer before the local printer mutex"
        finally:
            release.set()
            results = await asyncio.wait_for(
                asyncio.gather(first_task, *([second_task] if second_task else []), return_exceptions=True), 10
            )
            event.remove(test_engine.sync_engine, "before_cursor_execute", observe)
            locks.pop(printer.id, None)
    assert not any(isinstance(result, BaseException) for result in results), results
    assert results[0].status_code == 200
    assert results[1].status_code == (200 if second == "delete" else 404)
