"""Exports preserve each run, including open runs, and apply run filters."""

import csv
from datetime import datetime
from io import BytesIO

import pytest

from backend.app.services.print_log import write_log_entry

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_exports_each_run_and_applies_inclusive_end_date(
    async_client, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False)
    run_ids = {}
    for status, day, plate in (("aborted", 9, 1), ("failed", 10, 2), ("printing", 11, 3)):
        run = await write_log_entry(
            db_session,
            status=status,
            started_at=datetime(2026, 11, day, 22, 59),
            printer_id=printer.id,
            archive_id=archive.id,
            plate_id=plate,
        )
        run_ids[status] = str(run.id)
    await archive_factory(printer.id, with_run=False, status="archived", created_at=datetime(2026, 11, 8))
    await db_session.commit()

    export = "/api/v1/archives/export"
    fields = "run_id,plate_id,status"
    response = await async_client.get(export, params={"fields": fields})
    assert response.status_code == 200, response.text
    rows = list(csv.reader(response.text.splitlines()))
    assert rows == [
        ["Print ID", "Plate", "Status"],
        [run_ids["printing"], "3", "printing"],
        [run_ids["failed"], "2", "failed"],
        [run_ids["aborted"], "1", "aborted"],
        ["", "", "archived"],
    ]

    filtered = await async_client.get(
        export, params={"fields": fields, "status": "failed,aborted", "date_to": "2026-11-10"}
    )
    assert filtered.status_code == 200
    assert list(csv.reader(filtered.text.splitlines())) == [rows[0], *rows[2:4]]
    assert (await async_client.get(export, params={"fields": "id,extra_data"})).status_code == 400


async def test_csv_and_excel_export_write_user_text_as_text(async_client, printer_factory, archive_factory):
    from openpyxl import load_workbook

    printer = await printer_factory()
    await archive_factory(printer.id, print_name="=1+2")
    export = "/api/v1/archives/export"
    csv_response = await async_client.get(export, params={"fields": "print_name"})
    assert csv_response.text.splitlines()[1] == "'=1+2"
    xlsx_response = await async_client.get(export, params={"fields": "print_name", "format": "xlsx"})
    assert xlsx_response.status_code == 200
    book = load_workbook(BytesIO(xlsx_response.content), read_only=True)
    try:
        assert book.active["A2"].value == "=1+2"
        assert book.active["A2"].data_type == "s"
    finally:
        book.close()
