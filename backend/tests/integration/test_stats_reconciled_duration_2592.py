"""Regression test for reconnect reconciliation inflating Total Print Time (#2592)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from backend.app.models.print_log import PrintLogEntry


@pytest.mark.asyncio
@pytest.mark.integration
async def test_stats_total_time_ignores_reconciled_but_keeps_real_runtime(async_client: AsyncClient, db_session):
    base = datetime(2026, 7, 15, 10, 0, 0)
    reconnect = base + timedelta(days=2, hours=4)

    rows = [
        PrintLogEntry(printer_id=1, status="aborted", started_at=base, completed_at=reconnect, duration_seconds=0),
        PrintLogEntry(printer_id=1, status="aborted", started_at=base, completed_at=reconnect, duration_seconds=0),
        PrintLogEntry(
            printer_id=1,
            status="completed",
            started_at=base,
            completed_at=base + timedelta(hours=30),
            duration_seconds=30 * 3600,
        ),
        PrintLogEntry(
            printer_id=1,
            status="completed",
            started_at=base,
            completed_at=base + timedelta(hours=2),
            duration_seconds=None,
        ),
    ]
    for row in rows:
        db_session.add(row)
    await db_session.commit()

    resp = await async_client.get("/api/v1/archives/stats")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["total_print_time_hours"] == 32.0
