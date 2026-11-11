from datetime import datetime

import pytest
from sqlalchemy import select

from backend.app.models.print_log import PrintLogEntry


async def test_berlin_fall_back_day_is_consistent_across_archive_endpoints(
    async_client, archive_factory, printer_factory
):
    printer = await printer_factory()
    for name, instant in (
        ("Before range", datetime(2026, 10, 24, 21, 59, 59, 999999)),
        ("First instant", datetime(2026, 10, 24, 22)),
        ("Last instant", datetime(2026, 10, 25, 22, 59, 59, 999999)),
        ("After range", datetime(2026, 10, 25, 23)),
    ):
        await archive_factory(printer.id, created_at=instant, print_name=name)

    params = {"date_from": "2026-10-25", "date_to": "2026-10-25", "tz": "Europe/Berlin"}
    for path in ("/archives/", "/archives/slim"):
        response = await async_client.get(f"/api/v1{path}", params=params)
        assert response.status_code == 200, response.text
        assert {row["print_name"] for row in response.json()} == {"First instant", "Last instant"}
    for path in ("/archives/stats", "/archives/analysis/failures"):
        response = await async_client.get(f"/api/v1{path}", params=params)
        assert response.status_code == 200, response.text
        assert response.json()["total_prints"] == 2
    response = await async_client.get("/api/v1/archives/export", params={**params, "fields": "print_name"})
    assert response.status_code == 200, response.text
    assert "First instant" in response.text and "Last instant" in response.text
    assert "Before range" not in response.text and "After range" not in response.text


@pytest.mark.parametrize(
    ("status", "http_status", "stored"),
    [
        ("cancelled", 200, "cancelled"),
        ("aborted", 200, "aborted"),
        ("printing", 422, "completed"),
        (None, 200, "completed"),
    ],
)
async def test_archive_edit_only_writes_finished_statuses(
    async_client, archive_factory, printer_factory, db_session, status, http_status, stored
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id)
    response = await async_client.patch(f"/api/v1/archives/{archive.id}", json={"status": status})
    assert response.status_code == http_status, response.text
    await db_session.refresh(archive)
    assert archive.status == stored
    run_status = await db_session.scalar(select(PrintLogEntry.status).where(PrintLogEntry.archive_id == archive.id))
    assert run_status == stored


async def test_invalid_speed_is_rejected_before_sending_a_command(async_client, printer_factory, monkeypatch):
    from backend.app.api.routes import printers_controls

    printer = await printer_factory()

    async def unexpected(*args, **kwargs):
        pytest.fail("An invalid speed mode must not reach the printer command sender")

    monkeypatch.setattr(printers_controls, "_send_print_command_with_cloud_fallback", unexpected)
    response = await async_client.post(f"/api/v1/printers/{printer.id}/print-speed", params={"mode": 5})
    assert response.status_code == 422, response.text
