"""Compare each print with the prediction from its own plate."""

import zipfile
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app import main
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.archive_plate_estimates import fill_archive_plate_estimates
from backend.app.services.print_log import write_log_entry

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_stats_card_and_history_use_latest_printed_plate(
    async_client, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id,
        with_run=False,
        plate_id=1,
        print_time_seconds=900,
        plate_estimates={"1": {"seconds": 300, "grams": 4.2}, "2": {"seconds": 600, "grams": 6.7}},
    )
    now = datetime(2026, 11, 10, 12)
    for plate, start, duration in (
        (2, now, 600),
        (1, now - timedelta(days=1), 240),
        (None, now - timedelta(days=2), 200),
    ):
        await write_log_entry(
            db_session,
            archive_id=archive.id,
            printer_id=printer.id,
            plate_id=plate,
            status="completed",
            started_at=start,
            completed_at=start + timedelta(seconds=duration),
        )
    await db_session.commit()

    card = (await async_client.get(f"/api/v1/archives/{archive.id}")).json()
    assert (card["print_time_seconds"], card["time_estimate_seconds"], card["time_accuracy"]) == (900, 600, 100)
    history = (await async_client.get(f"/api/v1/archives/{archive.id}/runs")).json()["items"]
    assert [(r["plate_id"], r["estimate_seconds"], r["estimate_grams"]) for r in history] == [
        (2, 600, 6.7),
        (1, 300, 4.2),
        (None, None, None),
    ]
    stats = (await async_client.get("/api/v1/archives/stats")).json()
    assert stats["average_time_accuracy"] == 112.5


async def test_backfill_reads_old_files_once_and_preserves_unknown_plates(
    test_engine, db_session, archive_factory, printer_factory, tmp_path
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, file_path="fixture.3mf")
    other = await archive_factory(printer.id, with_run=False, file_path="missing.3mf")
    with zipfile.ZipFile(tmp_path / "fixture.3mf", "w") as output:
        output.writestr("Metadata/plate_2.gcode", "G28")
        output.writestr(
            "Metadata/slice_info.config",
            """<config><plate><metadata key="index" value="1"/>
               <metadata key="prediction" value="600"/><filament used_g="10.25"/>
               <filament used_g="Infinity"/></plate></config>""",
        )

    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    assert await fill_archive_plate_estimates(sessions, tmp_path, batch_size=1) == 1
    await db_session.refresh(archive)
    await db_session.refresh(other)
    assert archive.plate_estimates == {"1": {"seconds": 600, "grams": 10.25}, "2": {"seconds": None, "grams": None}}
    assert other.plate_estimates is None
    assert await fill_archive_plate_estimates(sessions, tmp_path, batch_size=1) == 0
    main.register_expected_print(printer.id, archive.filename, archive.id, plate_id=1)
    try:
        assert main._start_estimated_time(archive, printer.id) == 600
    finally:
        main.unregister_expected_print(printer.id, archive.filename, archive.id)


async def test_queue_plate_change_recomputes_the_scheduler_time(
    async_client, db_session, archive_factory, printer_factory
):
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id,
        with_run=False,
        print_time_seconds=900,
        plate_estimates={"1": {"seconds": 300, "grams": 4.2}, "2": {"seconds": 600, "grams": 6.7}},
    )
    item = PrintQueueItem(
        archive_id=archive.id, printer_id=printer.id, plate_id=1, print_time_seconds=300, status="pending"
    )
    db_session.add(item)
    await db_session.commit()

    response = await async_client.patch(f"/api/v1/queue/{item.id}", json={"plate_id": 2})
    assert response.status_code == 200, response.text
    assert response.json()["print_time_seconds"] == 600
    assert response.json()["filament_used_grams"] == 6.7
    await db_session.refresh(item)
    assert item.print_time_seconds == 600


@pytest.mark.parametrize("rescan_all", [False, True])
async def test_rescan_refreshes_stored_plate_estimates(
    async_client, db_session, archive_factory, printer_factory, tmp_path, monkeypatch, rescan_all
):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id, with_run=False, file_path="changed.3mf", plate_estimates={"1": {"seconds": 100, "grams": 1}}
    )
    with zipfile.ZipFile(tmp_path / "changed.3mf", "w") as output:
        output.writestr("Metadata/plate_2.gcode", "G28")
        output.writestr(
            "Metadata/slice_info.config",
            '<config><plate><metadata key="index" value="2"/><metadata key="prediction" value="200"/></plate></config>',
        )
    await db_session.commit()

    path = "/rescan-all" if rescan_all else f"/{archive.id}/rescan"
    response = await async_client.post(f"/api/v1/archives{path}")
    assert response.status_code == 200, response.text
    await db_session.refresh(archive)
    assert archive.plate_estimates == {"2": {"seconds": 200, "grams": None}}
