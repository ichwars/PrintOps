"""Plate evidence and printer scope are evaluated for each run."""

import logging
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app import main
from backend.app.core import database
from backend.app.core.auth import generate_api_key
from backend.app.core.database import _safe_execute
from backend.app.core.print_run_migrations import migrate_print_run_columns
from backend.app.models.api_key import APIKey
from backend.app.models.print_log import INCLUDE_OPEN_RUNS, PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.user import User
from backend.app.services import print_sd_cleanup, usage_tracker
from backend.app.services.mqtt_relay import MQTTRelayService
from backend.app.services.offline_queue_stop import record_offline_stop
from backend.app.services.print_event_tasks import calculate_print_energy
from backend.app.services.print_log import write_log_entry
from backend.app.services.print_log_run import record_run_energy_start
from backend.app.services.running_print_archive import find_running_archive
from backend.tests.integration.test_media_tokens import _admin_token, _make_user
from backend.tests.integration.test_reprint_archive_lifecycle import quiet_start  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_old_run_plate_migration_retains_uncertainty_and_is_repeatable(
    test_engine, db_session, archive_factory, printer_factory
):
    current_start = datetime(2026, 7, 20, 14)
    previous_start = current_start - timedelta(days=1)
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, plate_id=3, started_at=current_start)
    archive_id = archive.id
    item = PrintQueueItem(archive_id=archive_id, status="completed", plate_id=2)
    db_session.add(item)
    await db_session.flush()
    db_session.add_all(
        [
            PrintLogEntry(archive_id=archive_id, queue_item_id=item.id, status="completed", started_at=previous_start),
            PrintLogEntry(archive_id=archive_id, printer_id=printer.id, status="completed", started_at=previous_start),
            PrintLogEntry(archive_id=archive_id, printer_id=printer.id, status="completed", started_at=current_start),
        ]
    )
    await db_session.commit()

    async with test_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE print_log_entries DROP COLUMN plate_id"))
        await migrate_print_run_columns(conn, _safe_execute)
        values = await conn.execute(text("SELECT plate_id FROM print_log_entries ORDER BY id"))
        assert values.scalars().all() == [2, None, 3]

    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE print_queue SET plate_id = 4"))
        await migrate_print_run_columns(conn, _safe_execute)
        values = await conn.execute(text("SELECT plate_id FROM print_log_entries ORDER BY id"))
        assert values.scalars().all() == [2, None, 3]


@pytest.mark.parametrize("credential", ["user", "key"])
async def test_shared_archive_runs_and_bulk_clear_respect_printer_scope(
    async_client, db_session, archive_factory, printer_factory, credential
):
    visible = await printer_factory()
    hidden = await printer_factory()
    archive = await archive_factory(visible.id, with_run=False)
    archive_id = archive.id
    first = await write_log_entry(
        db_session, status="completed", archive_id=archive_id, printer_id=visible.id, plate_id=1
    )
    second = await write_log_entry(
        db_session, status="completed", archive_id=archive_id, printer_id=hidden.id, plate_id=2
    )
    first_id, second_id = first.id, second.id
    await db_session.commit()
    admin = await _admin_token(async_client, "_run_scope")
    if credential == "user":
        jwt, user_id = await _make_user(
            async_client,
            admin,
            username="scoped_runs",
            permissions=["archives:read_all", "archives:update_all", "archives:delete_all"],
        )
        await db_session.execute(update(User).where(User.id == user_id).values(allowed_printer_ids=[visible.id]))
        headers = {"Authorization": f"Bearer {jwt}"}
        denied = 404
    else:
        secret, key_hash, prefix = generate_api_key()
        db_session.add(
            APIKey(
                name="Scoped print log key",
                key_hash=key_hash,
                key_prefix=prefix,
                can_manage_archives=True,
                can_read_status=True,
                printer_ids=[visible.id],
            )
        )
        headers = {"X-API-Key": secret}
        denied = 403
    await db_session.commit()
    log_path = "/api/v1/print-log/"

    for path in (log_path, f"/api/v1/archives/{archive_id}/runs"):
        response = await async_client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 1
        assert [(r["id"], r["plate_id"]) for r in response.json()["items"]] == [(first_id, 1)]

    exported = await async_client.get("/api/v1/archives/export", params={"fields": "run_id,plate_id"}, headers=headers)
    assert exported.status_code == 200, exported.text
    assert exported.text.splitlines() == ["Print ID,Plate", f"{first_id},1"]

    hidden_path = f"{log_path}{second_id}"
    assert (await async_client.patch(hidden_path, json={"status": "failed"}, headers=headers)).status_code == denied
    assert (await async_client.delete(hidden_path, headers=headers)).status_code == denied

    response = await async_client.delete(log_path, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] == 1
    admin_log = await async_client.get(log_path, headers={"Authorization": f"Bearer {admin}"})
    assert [(r["id"], r["plate_id"]) for r in admin_log.json()["items"]] == [(second_id, 2)]


@pytest.fixture
def quiet_completion(monkeypatch, test_engine):
    monkeypatch.setattr(database, "async_session", async_sessionmaker(test_engine, expire_on_commit=False))
    monkeypatch.setattr(main, "prepare_print_completion", AsyncMock(return_value=(None, False)))
    monkeypatch.setattr(main.print_provenance, "resolve_completed_print_owner", AsyncMock(return_value=False))
    monkeypatch.setattr(main.print_provenance, "discard_print_session", AsyncMock())
    monkeypatch.setattr(main, "settle_archive_cost_estimate", AsyncMock())
    monkeypatch.setattr(print_sd_cleanup, "cleanup_after_print", AsyncMock())
    monkeypatch.setattr(usage_tracker, "on_print_complete", AsyncMock(return_value=[]))
    monkeypatch.setattr(main.printer_manager, "set_awaiting_plate_clear", lambda *args: None)
    monkeypatch.setattr(main.printer_manager, "clear_current_print_user", lambda *args: None)
    monkeypatch.setattr(main.ws_manager, "send_print_complete", AsyncMock())
    monkeypatch.setattr(main.mqtt_relay, "on_archive_updated", AsyncMock())


@pytest.mark.parametrize("reconnect", [False, True])
async def test_parallel_runs_end_on_their_own_printer_after_bindings_are_lost(
    quiet_start, quiet_completion, monkeypatch, db_session, printer_factory, archive_factory, reconnect
):
    events = AsyncMock()
    monkeypatch.setattr(main.mqtt_relay, "on_run_event", events)
    first = await printer_factory()
    second = await printer_factory()
    archive = await archive_factory(first.id, with_run=False, filename="shared.gcode.3mf")
    for printer, plate, subtask in ((first, 1, "job-1"), (second, 2, "job-2")):
        main.register_expected_print(printer.id, archive.filename, archive.id, plate_id=plate, ams_mapping=[10 + plate])
        await main.on_print_start(
            printer.id,
            {"filename": archive.filename, "subtask_name": "shared", "raw_data": {"subtask_id": subtask}},
        )

    query = select(PrintLogEntry).where(PrintLogEntry.archive_id == archive.id).order_by(PrintLogEntry.id)
    initial = (await db_session.scalars(query.execution_options(**{INCLUDE_OPEN_RUNS: True}))).all()
    assert [(r.printer_id, r.plate_id, r.status) for r in initial] == [
        (first.id, 1, "printing"),
        (second.id, 2, "printing"),
    ]
    first_run_id, second_run_id = [run.id for run in initial]
    assert await db_session.scalar(select(func.count(PrintLogEntry.id))) == 0

    # Mimic a restart before the first printer sends its completion.
    main._active_prints.clear()
    main._print_plate_ids.clear()
    state = SimpleNamespace(subtask_id="job-1")
    running = await find_running_archive(db_session, first.id, state, bindings={})
    assert running.id == archive.id

    if reconnect:
        state.connected = True
        state.state = "FAILED"
        state.subtask_name = "shared"
        state.raw_data = {}
        state.hms_errors = []
        monkeypatch.setattr(main.printer_manager, "get_status", lambda _printer_id: state)
        assert await main.reconcile_stale_active_prints(first.id) == 1
    else:
        await main.on_print_complete(
            first.id,
            {
                "filename": archive.filename,
                "subtask_name": "shared",
                "subtask_id": "job-1",
                "status": "failed",
                "ams_mapping": [30],
            },
        )
    assert (first.id, archive.id) not in main._print_ams_mappings
    assert main._print_ams_mappings[(second.id, archive.id)] == [12]
    if not reconnect:
        assert usage_tracker.on_print_complete.await_args.kwargs["ams_mapping"] == [30]
    await db_session.refresh(archive)
    assert archive.printer_id == second.id and archive.status == "printing"
    first_result = await db_session.scalar(query.execution_options(populate_existing=True))
    assert (first_result.id, first_result.printer_id, first_result.plate_id, first_result.status) == (
        first_run_id,
        first.id,
        1,
        "failed",
    )

    await main.on_print_complete(
        second.id,
        {"filename": archive.filename, "subtask_name": "shared", "subtask_id": "job-2", "status": "completed"},
    )
    await db_session.refresh(archive)
    assert archive.printer_id == second.id and archive.status == "completed"
    assert (second.id, archive.id) not in main._print_ams_mappings
    assert usage_tracker.on_print_complete.await_args.kwargs["ams_mapping"] == [12]
    finished = (await db_session.scalars(query.execution_options(populate_existing=True))).all()
    assert [(r.id, r.printer_id, r.plate_id, r.status) for r in finished] == [
        (first_run_id, first.id, 1, "failed"),
        (second_run_id, second.id, 2, "completed"),
    ]

    await main.on_print_complete(
        second.id,
        {"filename": archive.filename, "subtask_name": "shared", "subtask_id": "job-2", "status": "completed"},
    )
    assert [(call.args[0], call.args[1].id) for call in events.await_args_list] == [
        ("started", first_run_id),
        ("started", second_run_id),
        ("completed", first_run_id),
        ("completed", second_run_id),
    ]


async def test_late_terminal_frame_corrects_offline_stop_without_using_the_next_plate(
    quiet_start, quiet_completion, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, filename="shared.gcode.3mf")
    archive_id = archive.id
    item = PrintQueueItem(archive_id=archive_id, printer_id=printer.id, status="printing", plate_id=1)
    db_session.add(item)
    await db_session.commit()
    main.register_expected_print(printer.id, archive.filename, archive_id, ams_mapping=[4], plate_id=1)
    await main.on_print_start(
        printer.id,
        {"filename": archive.filename, "subtask_name": "shared", "raw_data": {"subtask_id": "offline-job"}},
    )
    await db_session.refresh(archive)
    item.status = "cancelled"
    stopped, archive_status = await record_offline_stop(db_session, item)
    assert stopped.archive_id == archive_id and archive_status == "cancelled"
    await db_session.commit()
    initial = await db_session.scalar(select(PrintLogEntry))
    assert initial.status == "cancelled" and initial.ended_offline is True
    run_id = initial.id

    main.register_expected_print(printer.id, archive.filename, archive_id, ams_mapping=[8], plate_id=2)
    await main.on_print_start(
        printer.id,
        {"filename": archive.filename, "subtask_name": "shared", "raw_data": {"subtask_id": "new-job"}},
    )
    await main.on_print_complete(
        printer.id,
        {"filename": archive.filename, "subtask_name": "shared", "subtask_id": "offline-job", "status": "completed"},
    )

    await db_session.refresh(archive)
    await db_session.refresh(initial)
    assert (initial.id, initial.status, initial.plate_id, initial.ended_offline) == (run_id, "completed", 1, None)
    assert archive.status == "printing" and archive.subtask_id == "new-job"
    assert main._get_start_ams_mapping({}, printer.id, archive_id) == [8]
    assert main._get_start_plate_id(printer.id, archive_id) == 2
    assert main._active_prints[(printer.id, archive.filename)] == archive_id


async def test_energy_belongs_to_the_run_even_after_the_archive_starts_another_plate(
    test_engine, db_session, printer_factory, archive_factory
):
    first = await printer_factory()
    second = await printer_factory()
    first_start = datetime(2026, 11, 11, 12)
    second_start = first_start + timedelta(minutes=2)
    archive = await archive_factory(second.id, with_run=False, started_at=second_start)
    archive_id = archive.id
    first_run = await write_log_entry(
        db_session, status="printing", archive_id=archive_id, printer_id=first.id, started_at=first_start, plate_id=1
    )
    second_run = await write_log_entry(
        db_session, status="printing", archive_id=archive_id, printer_id=second.id, started_at=second_start, plate_id=2
    )
    await record_run_energy_start(db_session, archive, first.id, 12.0, 10, run=first_run)
    await record_run_energy_start(db_session, archive, second.id, 32.0, 20, run=second_run)
    assert archive.energy_start_kwh == 32.0 and archive.energy_start_plug_id == 20
    await db_session.commit()
    for printer, run in ((first, first_run), (second, second_run)):
        await write_log_entry(
            db_session,
            status="completed",
            run_id=run.id,
            archive_id=archive_id,
            printer_id=printer.id,
            started_at=run.started_at,
            completed_at=run.started_at + timedelta(hours=1),
        )
    await db_session.commit()

    samples = {10: (object(), {"total": 12.5}), 20: (object(), {"total": 34.0})}
    read = AsyncMock(side_effect=lambda *args, plug_id, **kwargs: samples[plug_id])
    for printer, run_id in ((second, second_run.id), (first, first_run.id), (first, None)):
        await calculate_print_energy(
            printer.id,
            archive_id,
            logging.getLogger(__name__),
            async_session=async_sessionmaker(test_engine, expire_on_commit=False),
            read_printer_energy=read,
            _get_plug_energy=None,
            run_id=run_id,
        )
    assert [call.kwargs["plug_id"] for call in read.await_args_list] == [20, 10]
    await db_session.refresh(first_run)
    await db_session.refresh(second_run)
    assert (first_run.energy_kwh, first_run.energy_cost) == (0.5, 0.075)
    assert (second_run.energy_kwh, second_run.energy_cost) == (2.0, 0.3)


@pytest.mark.parametrize("original_cost,updated", [(1.5, 2.5), (1.23, 1.23)])
async def test_repricing_mirrors_only_the_inherited_run_cost(
    async_client, db_session, printer_factory, archive_factory, original_cost, updated
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, cost=1.5, filament_used_grams=100.0, filament_type="PLA")
    run = await db_session.scalar(select(PrintLogEntry).where(PrintLogEntry.archive_id == archive.id))
    run.cost = original_cost
    await db_session.commit()
    response = await async_client.post("/api/v1/archives/recalculate-costs")
    assert response.status_code == 200, response.text
    await db_session.refresh(run)
    assert run.cost == updated

    response = await async_client.patch(f"/api/v1/archives/{archive.id}", json={"cost": 0})
    assert response.status_code == 200, response.text
    await db_session.refresh(run)
    assert run.cost == (0 if original_cost == 1.5 else original_cost)


async def test_archive_edit_during_reprint_preserves_the_previous_run(
    async_client, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, status="completed", cost=2, filament_used_grams=10)
    run = await db_session.scalar(select(PrintLogEntry).where(PrintLogEntry.archive_id == archive.id))
    archive.status = "printing"
    archive.started_at = datetime(2026, 11, 11, 14)
    await db_session.commit()
    response = await async_client.patch(
        f"/api/v1/archives/{archive.id}", json={"cost": 9, "filament_used_grams": 12, "failure_reason": "other"}
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(run)
    assert (run.status, run.cost, run.filament_used_grams, run.failure_reason) == ("completed", 2, 10, None)


@pytest.mark.parametrize("invalid", [b"-1", b"1000001", b"NaN", b"Infinity", b"-Infinity"])
async def test_cost_validation_is_json_safe(async_client, printer_factory, archive_factory, invalid):
    printer = await printer_factory()
    archive = await archive_factory(printer.id)
    response = await async_client.patch(
        f"/api/v1/archives/{archive.id}",
        content=b'{"cost": ' + invalid + b"}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "cost"]


async def test_new_job_discards_only_the_previous_open_run_of_that_printer(
    quiet_start, monkeypatch, db_session, printer_factory, archive_factory
):
    first = await printer_factory()
    second = await printer_factory()
    shared = await archive_factory(first.id, with_run=False, filename="shared.gcode.3mf")
    replacement = await archive_factory(first.id, with_run=False, filename="replacement.gcode.3mf")
    events = AsyncMock()
    monkeypatch.setattr(main.mqtt_relay, "on_run_event", events)
    for printer, archive, job in ((first, shared, "A"), (second, shared, "B"), (first, replacement, "C")):
        main.register_expected_print(printer.id, archive.filename, archive.id, plate_id=1)
        await main.on_print_start(printer.id, {"filename": archive.filename, "subtask_id": job})
    await main.on_print_start(first.id, {"filename": replacement.filename, "subtask_id": "C"})

    rows = await db_session.scalars(
        select(PrintLogEntry).order_by(PrintLogEntry.id).execution_options(**{INCLUDE_OPEN_RUNS: True})
    )
    assert [(row.printer_id, row.archive_id, row.subtask_id) for row in rows] == [
        (second.id, shared.id, "B"),
        (first.id, replacement.id, "C"),
    ]
    assert [(call.args[0], call.args[1].subtask_id) for call in events.await_args_list] == [
        ("started", "A"),
        ("started", "B"),
        ("discarded", "A"),
        ("started", "C"),
    ]
    await db_session.refresh(shared)
    assert shared.status == "printing" and shared.printer_id == second.id


async def test_mqtt_event_serializes_the_run_with_utc_times(monkeypatch):
    relay = MQTTRelayService()
    relay.enabled = relay.connected = True
    relay.topic_prefix = "printops"
    publish = MagicMock()
    monkeypatch.setattr(relay, "_publish", publish)
    run = PrintLogEntry(
        id=9,
        archive_id=7,
        printer_id=3,
        printer_name="Test printer",
        print_name="Fixture",
        status="completed",
        plate_id=2,
        started_at=datetime(2026, 11, 11, 13),
        completed_at=datetime(2026, 11, 11, 14),
        duration_seconds=3600,
        cost=1.5,
    )
    await relay.on_run_event("completed", run, SimpleNamespace(serial_number="SERIAL", name="Fixture printer"))
    topic, payload = publish.call_args.args
    assert topic == "printops/printers/SERIAL/run/completed"
    assert (payload["run_id"], payload["archive_id"], payload["plate_id"]) == (9, 7, 2)
    assert payload["started_at"] == "2026-11-11T13:00:00+00:00"
    assert payload["completed_at"] == "2026-11-11T14:00:00+00:00"
    assert payload["duration_seconds"] == 3600 and payload["cost"] == 1.5


async def test_archive_projection_follows_start_order_when_printers_finish_in_reverse(
    async_client, db_session, archive_factory, printer_factory
):
    from backend.app.services.print_log_run import project_latest_finished_run

    first, second = await printer_factory(), await printer_factory()
    older_start = datetime(2026, 11, 11, 12)
    newer_start = older_start + timedelta(minutes=5)
    archive = await archive_factory(second.id, with_run=False, status="printing", started_at=newer_start, plate_id=2)
    older = PrintLogEntry(
        archive_id=archive.id, printer_id=first.id, status="printing", started_at=older_start, plate_id=1
    )
    newer = PrintLogEntry(
        archive_id=archive.id,
        printer_id=second.id,
        status="completed",
        started_at=newer_start,
        completed_at=newer_start + timedelta(minutes=10),
        plate_id=2,
    )
    db_session.add_all([newer, older])
    await db_session.flush()
    assert older.id > newer.id
    assert await project_latest_finished_run(db_session, archive) is None
    assert archive.status == "printing"

    older.status = "failed"
    older.failure_reason = "noStatusUpdate"
    older.completed_at = newer.completed_at + timedelta(minutes=5)
    assert await project_latest_finished_run(db_session, archive) == "completed"
    assert (archive.plate_id, archive.started_at, archive.completed_at, archive.failure_reason) == (
        2,
        newer.started_at,
        newer.completed_at,
        None,
    )
    await db_session.commit()

    for run, payload, expected in (
        (older, {"status": "cancelled"}, "completed"),
        (newer, {"status": "failed", "failure_reason": "noStatusUpdate"}, "failed"),
    ):
        response = await async_client.patch(f"/api/v1/print-log/{run.id}", json=payload)
        assert response.status_code == 200, response.text
        await db_session.refresh(archive)
        assert (archive.plate_id, archive.status) == (2, expected)


@pytest.mark.parametrize("credential", ["user", "key"])
@pytest.mark.parametrize("current_is_visible", [False, True])
async def test_archive_view_uses_visible_run_and_guards_shared_mutations(
    async_client, db_session, archive_factory, printer_factory, credential, current_is_visible
):
    visible, hidden = await printer_factory(), await printer_factory()
    current = visible if current_is_visible else hidden
    start = datetime(2026, 11, 11, 12)
    archive = await archive_factory(
        current.id,
        with_run=False,
        plate_id=2,
        status="failed",
        failure_reason="hidden failure",
        timelapse_path="hidden.mp4",
        photos=["hidden.png"],
        energy_kwh=99,
    )
    first = await write_log_entry(
        db_session,
        status="completed",
        archive_id=archive.id,
        printer_id=visible.id,
        plate_id=1,
        started_at=start,
        completed_at=start + timedelta(minutes=5),
        filament_used_grams=8,
    )
    second = await write_log_entry(
        db_session,
        status="failed",
        archive_id=archive.id,
        printer_id=hidden.id,
        plate_id=2,
        started_at=start + timedelta(minutes=10),
        completed_at=start + timedelta(minutes=11),
        failure_reason="hidden failure",
        filament_used_grams=70,
    )
    hidden_only = await archive_factory(hidden.id, with_run=False)
    await db_session.commit()
    admin = await _admin_token(async_client, "_run_view")
    if credential == "user":
        jwt, user_id = await _make_user(
            async_client,
            admin,
            username="scoped_run_view",
            permissions=["archives:read_all", "archives:update_all", "archives:delete_all"],
        )
        await db_session.execute(update(User).where(User.id == user_id).values(allowed_printer_ids=[visible.id]))
        headers = {"Authorization": f"Bearer {jwt}"}
    else:
        secret, key_hash, prefix = generate_api_key()
        db_session.add(
            APIKey(
                name="Scoped archive key",
                key_hash=key_hash,
                key_prefix=prefix,
                can_manage_archives=True,
                can_read_status=True,
                printer_ids=[visible.id],
            )
        )
        headers = {"X-API-Key": secret}
    await db_session.commit()

    path = f"/api/v1/archives/{archive.id}"
    detail = await async_client.get(path, headers=headers)
    listing = await async_client.get("/api/v1/archives/", headers=headers)
    history = await async_client.get(f"{path}/runs", headers=headers)
    assert detail.status_code == listing.status_code == history.status_code == 200
    assert [item["id"] for item in listing.json()] == [archive.id]
    assert [item["id"] for item in history.json()["items"]] == [first.id]
    scoped_listing = await async_client.get("/api/v1/archives/", params={"printer_id": visible.id}, headers=headers)
    assert [item["id"] for item in scoped_listing.json()] == [archive.id]
    hidden_listing = await async_client.get("/api/v1/archives/", params={"printer_id": hidden.id}, headers=headers)
    assert hidden_listing.json() == []
    visible_run = await async_client.get(path, params={"run_id": first.id}, headers=headers)
    hidden_run = await async_client.get(path, params={"run_id": second.id}, headers=headers)
    assert visible_run.status_code == 200 and visible_run.json()["run_id"] == first.id
    assert hidden_run.status_code == 404
    for data in (detail.json(), listing.json()[0]):
        assert (data["latest_run_id"], data["printer_id"], data["plate_id"], data["status"]) == (
            first.id,
            visible.id,
            1,
            "completed",
        )
        assert data["run_count"] == 1
        assert data["total_filament_actual_grams"] == 8
        assert all(data[field] is None for field in ("failure_reason", "timelapse_path", "photos", "energy_kwh"))
    assert (await async_client.get(f"/api/v1/archives/{hidden_only.id}", headers=headers)).status_code in (403, 404)
    for response in (
        await async_client.patch(path, json={"notes": "blocked"}, headers=headers),
        await async_client.delete(path, headers=headers),
        await async_client.delete(f"{path}/timelapse", headers=headers),
    ):
        assert response.status_code in (403, 404), response.text
    unrestricted = await async_client.get(path, headers={"Authorization": f"Bearer {admin}"})
    assert unrestricted.json()["latest_run_id"] == second.id
    assert unrestricted.json()["run_count"] == 2


async def test_retry_of_run_commit_does_not_charge_filament_twice(
    quiet_start, quiet_completion, db_session, test_engine, printer_factory, archive_factory, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    from backend.app.services import print_log

    if test_engine.dialect.name != "sqlite":
        pytest.skip("SQLite lock retry")
    printer = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, filament_used_grams=10.0)
    main.register_expected_print(printer.id, archive.filename, archive.id, plate_id=1)
    await main.on_print_start(printer.id, {"filename": archive.filename, "raw_data": {"subtask_id": "retry-job"}})
    active = await db_session.scalar(
        select(PrintLogEntry)
        .where(PrintLogEntry.archive_id == archive.id)
        .execution_options(**{INCLUDE_OPEN_RUNS: True})
    )
    active_id = active.id
    usage_tracker.on_print_complete.return_value = [{"weight_used": 6.0, "cost": 1.2}]
    attempts = []

    async def fail_first_commit(db, **fields):
        run = await write_log_entry(db, **fields)
        attempts.append(run.id)
        if len(attempts) == 1:
            raise OperationalError("print log commit", None, Exception("database is locked"))
        return run

    monkeypatch.setattr(print_log, "write_log_entry", fail_first_commit)
    await main.on_print_complete(
        printer.id, {"filename": archive.filename, "subtask_id": "retry-job", "status": "completed"}
    )
    assert attempts == [active_id, active_id]
    usage_tracker.on_print_complete.assert_awaited_once()
    await db_session.refresh(active)
    assert (active.status, active.filament_used_grams, active.cost) == ("completed", 6.0, 1.2)
    assert await db_session.scalar(select(func.count(PrintLogEntry.id))) == 1


@pytest.mark.parametrize("matched,reconciled", [(False, False), (True, False), (True, True)])
async def test_completion_without_archive_only_notifies_the_job_it_closed(
    matched, reconciled, quiet_start, quiet_completion, monkeypatch, db_session, printer_factory
):
    printer = await printer_factory(auto_archive=False)
    previous_owner = User(username="previous-owner")
    owner = User(username="current-owner")
    db_session.add_all([previous_owner, owner])
    await db_session.flush()
    now = main.utcnow_naive()
    db_session.add(
        PrintQueueItem(
            printer_id=printer.id,
            status="completed",
            completed_at=now,
            created_by_id=previous_owner.id,
            print_time_seconds=270,
        )
    )
    if matched:
        db_session.add(
            PrintQueueItem(
                printer_id=printer.id,
                status="printing",
                started_at=now - timedelta(minutes=12),
                created_by_id=owner.id,
                print_time_seconds=630,
            )
        )
    await db_session.commit()

    pending = []

    def capture_notification(coro, *, name):
        if name == "notify-no-archive":
            pending.append(coro)
        else:
            coro.close()

    notify, email = AsyncMock(), AsyncMock()
    monkeypatch.setattr(main, "spawn_background_task", capture_notification)
    monkeypatch.setattr(main.notification_service, "on_print_complete", notify)
    monkeypatch.setattr(main, "_dispatch_user_print_email", email)
    await main.on_print_complete(
        printer.id,
        {"status": "completed", "filename": "current.gcode", "_reconciled": reconciled},
    )
    assert len(pending) == 1
    await pending[0]

    archive_data = notify.await_args.kwargs["archive_data"]
    if matched:
        assert archive_data["created_by_id"] == owner.id
        assert archive_data["print_time_seconds"] == 630
        assert ("actual_time_seconds" in archive_data) is not reconciled
        assert email.await_args.args[1] == owner.id
    else:
        assert archive_data is None
        email.assert_not_awaited()
