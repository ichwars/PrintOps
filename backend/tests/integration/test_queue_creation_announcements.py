"""Job creation applies defaults and announces each committed queue item."""

import zipfile
from datetime import datetime
from unittest.mock import AsyncMock

from sqlalchemy import select

from backend.app.core.auth import generate_api_key
from backend.app.core.config import settings
from backend.app.models.api_key import APIKey
from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.settings import Settings
from backend.app.services.mqtt_relay import mqtt_relay
from backend.app.services.notification_service import notification_service


async def test_queue_entry_points_use_defaults_and_announce_committed_ids(
    async_client, db_session, printer_factory, archive_factory, tmp_path, monkeypatch
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, filename="Bracket.3mf", file_path="Bracket.3mf", with_run=False)
    source = tmp_path / "Bracket.3mf"
    with zipfile.ZipFile(source, "w") as file:
        for plate in (3, 2):
            file.writestr(f"Metadata/plate_{plate}.gcode", "G90\n")
    other = tmp_path / "Cover.3mf"
    with zipfile.ZipFile(other, "w") as file:
        file.writestr("Metadata/plate_1.gcode", "G90\n")
    files = [
        LibraryFile(filename=path.name, file_path=str(path), file_size=path.stat().st_size, file_type="3mf")
        for path in (source, other)
    ]
    key, hashed, prefix = generate_api_key()
    db_session.add_all(
        [
            *files,
            Settings(key="default_timelapse", value="true"),
            Settings(key="default_bed_levelling", value="false"),
            APIKey(name="Test webhook", key_hash=hashed, key_prefix=prefix, can_queue=True),
        ]
    )
    await db_session.commit()
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    mqtt_events = AsyncMock()
    channel_events = AsyncMock()
    monkeypatch.setattr(mqtt_relay, "on_queue_job_added", mqtt_events)
    monkeypatch.setattr(notification_service, "on_queue_job_added", channel_events)

    direct = await async_client.post(
        "/api/v1/queue/",
        json={"archive_id": archive.id, "printer_id": printer.id, "quantity": 2, "timelapse": False},
    )
    assert direct.status_code == 200, direct.text
    webhook = await async_client.post(
        "/api/v1/webhook/queue/add",
        json={
            "archive_id": archive.id,
            "printer_id": printer.id,
            "scheduled_time": "2026-11-09T19:30:00+02:00",
        },
        headers={"X-API-Key": key},
    )
    assert webhook.status_code == 200, webhook.text
    bulk = await async_client.post(
        "/api/v1/library/files/add-to-queue",
        json={"file_ids": [file.id for file in files], "printer_id": printer.id},
    )
    assert bulk.status_code == 200, bulk.text

    items = list(await db_session.scalars(select(PrintQueueItem).order_by(PrintQueueItem.id)))
    assert len(items) == 5
    assert all(not item.bed_levelling for item in items)
    assert [item.timelapse for item in items] == [False, False, True, True, True]
    assert [item.plate_id for item in items[:3]] == [2, 2, 2]
    assert items[2].scheduled_time == datetime(2026, 11, 9, 17, 30)
    assert [call.kwargs["job_id"] for call in mqtt_events.await_args_list] == [item.id for item in items]
    assert [call.args[:2] for call in channel_events.await_args_list] == [
        ("Bracket ×2", printer.name),
        ("Bracket", printer.name),
        ("2 jobs (Bracket, Cover)", printer.name),
    ]
