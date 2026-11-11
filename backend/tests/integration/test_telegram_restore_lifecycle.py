"""Restore must await the real polling cancellation before replacing its database."""

import asyncio
import io
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.app.core import auth_sessions, database, db_dialect
from backend.app.core.config import settings
from backend.app.services import telegram_polling


async def test_restore_awaits_polling_cleanup_before_database_swap(async_client, monkeypatch, tmp_path):
    from backend.app.api.routes import cloud, settings as route
    from backend.app.services import virtual_printer

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setitem(cloud._filament_id_name_cache, 17, {"old": "Previous account"})
    monkeypatch.setitem(cloud._filament_cache, 17, {"old": {"name": "Previous account"}})
    started, stopped = asyncio.Event(), asyncio.Event()
    order = []

    async def worker():
        try:
            started.set()
            await asyncio.Future()
        finally:
            await asyncio.sleep(0.01)  # Cancellation cleanup itself must be awaited.
            order.append("poller stopped")
            stopped.set()

    task = asyncio.create_task(worker())
    monkeypatch.setattr(telegram_polling, "_task", task)
    await started.wait()

    async def stop_virtual_printers():
        await asyncio.sleep(0)
        order.append("virtual printers stopped")

    stop_all = AsyncMock(side_effect=stop_virtual_printers)
    monkeypatch.setattr(virtual_printer, "virtual_printer_manager", SimpleNamespace(is_enabled=True, stop_all=stop_all))

    async def close():
        assert stopped.is_set(), "database closed while Telegram poller is still alive"
        assert task.done()
        order.append("connections closed")

    async def swap(*args):
        assert stopped.is_set() and task.done()
        order.append("database swapped")

    monkeypatch.setattr(database, "close_all_connections", close)
    monkeypatch.setattr(database, "reinitialize_database", AsyncMock())
    monkeypatch.setattr(database, "init_db", AsyncMock())
    monkeypatch.setattr(auth_sessions, "handle_restored_sessions", AsyncMock())
    monkeypatch.setattr(db_dialect, "is_sqlite", lambda: False)
    monkeypatch.setattr(route, "_import_sqlite_to_postgres", swap)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as backup:
        backup.writestr("printops.db", b"SQLite format 3")
    try:
        response = await async_client.post(
            "/api/v1/settings/restore", files={"file": ("backup.zip", archive.getvalue(), "application/zip")}
        )
        assert response.status_code == 200, response.text
        stop_all.assert_awaited_once()
        assert order == ["virtual printers stopped", "poller stopped", "connections closed", "database swapped"]
        assert telegram_polling._task is None
        assert 17 not in cloud._filament_id_name_cache
        assert 17 not in cloud._filament_cache
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
