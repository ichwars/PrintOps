"""Restore must await the real polling cancellation before replacing its database."""

import asyncio
import io
import zipfile
from unittest.mock import AsyncMock

from backend.app.core import database, db_dialect
from backend.app.core.config import settings
from backend.app.services import telegram_polling


async def test_restore_awaits_polling_cleanup_before_database_swap(async_client, monkeypatch, tmp_path):
    from backend.app.api.routes import settings as route

    monkeypatch.setattr(settings, "base_dir", tmp_path)
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
        assert order == ["poller stopped", "connections closed", "database swapped"]
        assert telegram_polling._task is None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
