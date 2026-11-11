"""Deleting an account detaches active work and retains historical records."""

import io
import zipfile
from datetime import datetime

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select

from backend.app.api.routes import library
from backend.app.core.account_retirement import capture_account, repair_deleted_accounts, require_current_account
from backend.app.core.auth import OwnershipAccess
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.services.printer_manager import printer_manager
from backend.app.services.slice_dispatch import SliceJob, slice_dispatch

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_account_delete_preserves_print_history_and_holds_restricted_jobs(
    async_client, db_session, printer_factory, monkeypatch
):
    from backend.app import main

    printer_id = (await printer_factory()).id
    user = User(username="original", role="user", allowed_printer_ids=[printer_id])
    other = User(username="other", role="user")
    db_session.add_all([user, other])
    await db_session.flush()
    owner_id, other_id = user.id, other.id
    expected_key = (printer_id, "retained")
    monkeypatch.setattr(main, "_expected_print_creators", {expected_key: owner_id, (99, "other"): other_id})
    monkeypatch.setattr(
        printer_manager,
        "_current_print_user",
        {
            printer_id: {"user_id": owner_id, "username": user.username},
            99: {"user_id": other_id, "username": other.username},
        },
    )
    slicing = SliceJob(id=1, kind="archive", source_id=3, source_name="retained", owner_id=owner_id)
    monkeypatch.setattr(slice_dispatch, "_jobs", {1: slicing})

    archive = PrintArchive(
        filename="retained.3mf",
        file_path="/fixture",
        file_size=7,
        created_by_id=owner_id,
        created_by_identity=user.connected_identity,
    )
    queue_item = PrintQueueItem(target_model="X1C", status="pending", created_by_id=owner_id)
    db_session.add_all(
        [
            archive,
            queue_item,
            PrintLogEntry(status="completed", created_by_id=owner_id, created_by_username="original", cost=2.5),
            Settings(key=f"user_{owner_id}_email_2fa_enabled", value="true"),
            Settings(key=f"user_{other_id}_email_2fa_enabled", value="true"),
        ]
    )
    await db_session.commit()

    response = await async_client.delete(f"/api/v1/users/{owner_id}")
    assert response.status_code == 204
    assert await db_session.scalar(select(User.id).where(User.id == owner_id)) is None
    assert (
        await db_session.scalar(select(Settings.value).where(Settings.key == f"user_{owner_id}_email_2fa_enabled"))
        is None
    )
    assert (
        await db_session.scalar(select(Settings.value).where(Settings.key == f"user_{other_id}_email_2fa_enabled"))
        == "true"
    )
    await db_session.refresh(archive)
    await db_session.refresh(queue_item)
    assert archive.created_by_id is None and archive.created_by_identity is None
    assert queue_item.manual_start and queue_item.created_by_id is None
    retained = await db_session.scalar(select(PrintLogEntry))
    assert retained.created_by_id is None and retained.created_by_username == "original" and retained.cost == 2.5
    assert slicing.owner_id is None
    assert main._expected_print_creators == {(99, "other"): other_id}
    assert printer_manager.get_current_print_user(printer_id) is None
    await PrintScheduler()._propagate_owner_to_printer_manager(db_session, queue_item)
    assert printer_manager.get_current_print_user(printer_id) is None
    assert printer_manager.get_current_print_user(99)["user_id"] == other_id


async def test_sqlite_startup_repair_detaches_historical_rows_and_clears_email_mfa(db_session):
    missing_id = 999
    stable_timestamp = datetime(2024, 5, 6)
    file = LibraryFile(
        filename="orphan.stl",
        file_path="/fixture",
        file_type="stl",
        file_size=7,
        created_by_id=missing_id,
        updated_at=stable_timestamp,
    )
    queue_item = PrintQueueItem(target_model="X1C", status="pending", created_by_id=missing_id)
    db_session.add_all([file, queue_item, Settings(key=f"user_{missing_id}_email_2fa_enabled", value="true")])
    await db_session.flush()
    await repair_deleted_accounts(await db_session.connection())
    await db_session.commit()
    await db_session.refresh(file)
    await db_session.refresh(queue_item)

    assert file.created_by_id is None and file.updated_at == stable_timestamp
    assert queue_item.created_by_id is None and queue_item.manual_start
    assert (
        await db_session.scalar(select(Settings.value).where(Settings.key == f"user_{missing_id}_email_2fa_enabled"))
        is None
    )


async def test_long_write_rejects_explicit_reuse_of_the_account_id_and_username(db_session):
    original = User(username="reused", role="user")
    db_session.add(original)
    await db_session.commit()
    account = capture_account(original)
    owner_id = original.id
    await db_session.execute(delete(User).where(User.id == owner_id))
    await db_session.commit()
    db_session.add(User(id=owner_id, username="reused", role="user"))
    await db_session.commit()

    with pytest.raises(HTTPException) as error:
        await require_current_account(db_session, account)
    assert error.value.status_code == 401


async def test_zip_upload_stops_if_account_was_deleted_during_read(db_session, monkeypatch):
    user = User(username="zip-owner", role="user")
    db_session.add(user)
    await db_session.commit()
    owner_id = user.id
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("fixture.stl", "solid fixture\nendsolid fixture\n")
    content.seek(0)
    upload = UploadFile(file=content, filename="fixture.zip")
    read = library.read_upload_limited

    async def read_and_delete(file):
        data = await read(file)
        await db_session.execute(delete(User).where(User.id == owner_id))
        await db_session.commit()
        return data

    monkeypatch.setattr(library, "read_upload_limited", read_and_delete)
    with pytest.raises(HTTPException) as error:
        await library.extract_zip_file(
            file=upload,
            folder_id=None,
            preserve_structure=True,
            create_folder_from_zip=True,
            generate_stl_thumbnails=False,
            db=db_session,
            access=OwnershipAccess(user, True),
        )
    assert error.value.status_code == 401
    assert await db_session.scalar(select(LibraryFile.id)) is None


async def test_model_pipeline_copies_wait_if_the_scoped_creator_is_deleted_mid_slice(
    db_session,
    monkeypatch,
    tmp_path,
):
    from contextlib import asynccontextmanager

    from sqlalchemy import update

    from backend.app.api.routes import pipeline_runs
    from backend.app.models.pipeline_run import PipelineJob, PipelineRun
    from backend.app.models.slicer_pipeline import SlicerPipeline
    from backend.app.schemas.slicer import SliceResponse

    user = User(username="pipeline-owner", role="user", allowed_printer_ids=[1])
    source = LibraryFile(filename="source.3mf", file_path="/fixture", file_type="3mf", file_size=7)
    pipeline = SlicerPipeline(
        name="Model class",
        printer_preset_source="local",
        printer_preset_id="printer",
        process_preset_source="local",
        process_preset_id="process",
        filament_presets_json='[{"source":"local","id":"filament"}]',
        target_kind="printer_class",
        target_model_class="X1C",
    )
    db_session.add_all([user, pipeline, source])
    await db_session.flush()
    creator_id, pipeline_id, source_id = user.id, pipeline.id, source.id
    run = PipelineRun(pipeline_id=pipeline_id, source_library_file_id=source_id, created_by=creator_id)
    db_session.add(run)
    await db_session.flush()
    run_id = run.id
    db_session.add(PipelineJob(pipeline_run_id=run_id, copy_index=0))
    await db_session.commit()

    @asynccontextmanager
    async def session_factory():
        yield db_session

    async def slice_while_owner_is_deleted(db, **_kwargs):
        await db.execute(update(PipelineRun).where(PipelineRun.id == run_id).values(created_by=None))
        await db.execute(delete(User).where(User.id == creator_id))
        await db.commit()
        return SliceResponse(
            library_file_id=source_id,
            name="sliced",
            print_time_seconds=15,
            filament_used_g=1,
            filament_used_mm=100,
        )

    monkeypatch.setattr(pipeline_runs, "async_session", session_factory)
    monkeypatch.setattr(library, "slice_and_persist", slice_while_owner_is_deleted)
    src_path = tmp_path / "fixture.3mf"
    src_path.write_bytes(b"fixture")
    run_pipeline = pipeline_runs._make_orchestration_callable(
        run_id=run_id,
        pipeline_id=pipeline_id,
        src_kind="library_file",
        src_id=source_id,
        src_filename=src_path.name,
        src_path=src_path,
        creator_user_id=creator_id,
        copies=1,
        creator_restricted=True,
    )

    await run_pipeline(1)
    item = await db_session.scalar(select(PrintQueueItem))
    assert item.created_by_id is None and item.manual_start
    assert item.target_model == "X1C" and item.printer_id is None
