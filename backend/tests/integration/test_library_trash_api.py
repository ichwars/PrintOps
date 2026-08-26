"""Integration tests for the library trash bin + admin purge (#1008)."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


@pytest.fixture
async def file_factory(db_session):
    """Factory for LibraryFile rows with sensible defaults."""
    _counter = [0]

    async def _create_file(**kwargs):
        from backend.app.models.library import LibraryFile

        _counter[0] += 1
        counter = _counter[0]
        defaults = {
            "filename": f"trash_test_{counter}.3mf",
            "file_path": f"/test/library/trash_test_{counter}.3mf",
            "file_size": 1024 * counter,
            "file_type": "3mf",
        }
        defaults.update(kwargs)
        lib_file = LibraryFile(**defaults)
        db_session.add(lib_file)
        await db_session.commit()
        await db_session.refresh(lib_file)
        return lib_file

    return _create_file


@pytest.fixture
async def queue_factory(db_session):
    """Create queue rows that point at a library file."""
    from backend.app.models.print_queue import PrintQueueItem
    from backend.app.models.printer import Printer

    printer = Printer(
        name="Queue reference printer",
        serial_number="QUEUE-REF-PRINTER",
        ip_address="127.0.0.1",
        access_code="access-code",
        model="X1C",
    )
    db_session.add(printer)
    await db_session.commit()

    async def _create(library_file, status="pending"):
        item = PrintQueueItem(printer_id=printer.id, library_file_id=library_file.id, status=status)
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)
        return item

    return _create


async def _reload_queue_item(db_session, item):
    """Discard the fixture session's identity-map copy and read route changes."""
    from sqlalchemy import select

    from backend.app.models.print_queue import PrintQueueItem

    item_id = item.id
    db_session.expunge_all()
    return (await db_session.execute(select(PrintQueueItem).where(PrintQueueItem.id == item_id))).scalar_one_or_none()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_file_moves_to_trash(async_client: AsyncClient, file_factory, db_session):
    """DELETE /library/files/{id} soft-deletes (managed) files into trash."""
    from backend.app.models.library import LibraryFile

    f = await file_factory()
    response = await async_client.delete(f"/api/v1/library/files/{f.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["trashed"] is True

    # Row still exists with deleted_at stamped
    await db_session.refresh(f)
    assert f.deleted_at is not None

    # Normal listing hides it
    list_resp = await async_client.get("/api/v1/library/files")
    assert list_resp.status_code == 200
    ids = [row["id"] for row in list_resp.json()]
    assert f.id not in ids

    # Trash listing surfaces it
    trash_resp = await async_client.get("/api/v1/library/trash")
    assert trash_resp.status_code == 200
    payload = trash_resp.json()
    trashed_ids = [item["id"] for item in payload["items"]]
    assert f.id in trashed_ids
    assert payload["total"] >= 1
    assert payload["retention_days"] >= 1

    # Row's file_type is preserved in the original table (sanity check on the filter)
    row = await db_session.get(LibraryFile, f.id)
    assert row is not None
    assert row.file_type == "3mf"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_external_file_hard_deletes(async_client: AsyncClient, file_factory, db_session):
    """External files skip the trash — DB row is dropped directly."""
    from backend.app.models.library import LibraryFile

    f = await file_factory(is_external=True)
    file_id = f.id
    response = await async_client.delete(f"/api/v1/library/files/{file_id}")
    assert response.status_code == 200
    assert response.json()["trashed"] is False

    # The route commits in its own session; expire ours so get() re-reads.
    db_session.expire_all()
    missing = await db_session.get(LibraryFile, file_id)
    assert missing is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_hard_delete_cancels_waiting_queue_item_and_names_file(
    async_client: AsyncClient, file_factory, queue_factory, db_session
):
    """A permanent delete must fail waiting work immediately without deleting its row."""
    file = await file_factory(filename="queued-source.3mf", is_external=True)
    waiting = await queue_factory(file)

    response = await async_client.delete(f"/api/v1/library/files/{file.id}")
    assert response.status_code == 200

    row = await _reload_queue_item(db_session, waiting)
    assert row is not None
    assert row.status == "cancelled"
    assert "queued-source.3mf" in row.error_message
    assert row.library_file_id is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_hard_delete_detaches_running_and_finished_queue_history(
    async_client: AsyncClient, file_factory, queue_factory, db_session
):
    """Printing and completed rows survive; only their doomed FK is removed."""
    file = await file_factory(is_external=True)
    running = await queue_factory(file, status="printing")
    completed = await queue_factory(file, status="completed")

    await async_client.delete(f"/api/v1/library/files/{file.id}")

    for item, expected_status in ((running, "printing"), (completed, "completed")):
        row = await _reload_queue_item(db_session, item)
        assert row is not None
        assert row.status == expected_status
        assert row.library_file_id is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_soft_delete_leaves_queue_reference_reversible(
    async_client: AsyncClient, file_factory, queue_factory, db_session
):
    """Moving a managed file to trash must not rewrite work that restore can recover."""
    file = await file_factory()
    waiting = await queue_factory(file)

    response = await async_client.delete(f"/api/v1/library/files/{file.id}")
    assert response.json()["trashed"] is True

    row = await _reload_queue_item(db_session, waiting)
    assert row.status == "pending"
    assert row.library_file_id == file.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_folder_delete_releases_queue_items_in_nested_subfolders(
    async_client: AsyncClient, file_factory, queue_factory, db_session
):
    """Folder cascades must detach queue rows for the complete descendant tree."""
    from backend.app.models.library import LibraryFolder

    parent = LibraryFolder(name="parent")
    db_session.add(parent)
    await db_session.commit()
    child = LibraryFolder(name="child", parent_id=parent.id)
    db_session.add(child)
    await db_session.commit()
    file = await file_factory(filename="nested.3mf", folder_id=child.id)
    waiting = await queue_factory(file)

    response = await async_client.delete(f"/api/v1/library/folders/{parent.id}")
    assert response.status_code == 200

    row = await _reload_queue_item(db_session, waiting)
    assert row is not None
    assert row.status == "cancelled"
    assert row.library_file_id is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_bulk_hard_delete_releases_all_queue_references(
    async_client: AsyncClient, file_factory, queue_factory, db_session
):
    """Bulk deletion must release references before its first autoflush/delete."""
    first = await file_factory(filename="bulk-one.3mf", is_external=True)
    second = await file_factory(filename="bulk-two.3mf", is_external=True)
    first_item = await queue_factory(first)
    second_item = await queue_factory(second, status="completed")

    response = await async_client.post(
        "/api/v1/library/bulk-delete",
        json={"file_ids": [first.id, second.id], "folder_ids": []},
    )
    assert response.status_code == 200
    assert response.json()["deleted_files"] == 2

    waiting = await _reload_queue_item(db_session, first_item)
    completed = await _reload_queue_item(db_session, second_item)
    assert waiting.status == "cancelled"
    assert waiting.library_file_id is None
    assert completed.status == "completed"
    assert completed.library_file_id is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_retention_sweeper_releases_queue_reference(file_factory, queue_factory, db_session):
    """The delayed hard-delete path must apply the same queue policy as API deletion."""
    from backend.app.services.library_trash import library_trash_service

    file = await file_factory(filename="expired.3mf")
    file.deleted_at = datetime.now(timezone.utc) - timedelta(days=400)
    await db_session.commit()
    waiting = await queue_factory(file)

    deleted = await library_trash_service._sweep(db_session)
    assert deleted == 1

    row = await _reload_queue_item(db_session, waiting)
    assert row is not None
    assert row.status == "cancelled"
    assert "expired.3mf" in row.error_message
    assert row.library_file_id is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_restore_from_trash(async_client: AsyncClient, file_factory, db_session):
    """Restoring a trashed file clears deleted_at and makes it visible again."""
    f = await file_factory()
    await async_client.delete(f"/api/v1/library/files/{f.id}")

    resp = await async_client.post(f"/api/v1/library/trash/{f.id}/restore")
    assert resp.status_code == 200

    await db_session.refresh(f)
    assert f.deleted_at is None

    list_resp = await async_client.get("/api/v1/library/files")
    ids = [row["id"] for row in list_resp.json()]
    assert f.id in ids


@pytest.mark.asyncio
@pytest.mark.integration
async def test_hard_delete_from_trash(async_client: AsyncClient, file_factory, db_session):
    """Hard-delete from trash removes the DB row immediately."""
    from backend.app.models.library import LibraryFile

    f = await file_factory()
    file_id = f.id
    await async_client.delete(f"/api/v1/library/files/{file_id}")

    resp = await async_client.delete(f"/api/v1/library/trash/{file_id}")
    assert resp.status_code == 200

    db_session.expire_all()
    row = await db_session.get(LibraryFile, file_id)
    assert row is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_empty_trash(async_client: AsyncClient, file_factory, db_session):
    """Empty-trash hard-deletes every trashed row in the caller's scope."""
    from sqlalchemy import func, select

    from backend.app.models.library import LibraryFile

    for _ in range(3):
        f = await file_factory()
        await async_client.delete(f"/api/v1/library/files/{f.id}")

    resp = await async_client.delete("/api/v1/library/trash")
    assert resp.status_code == 200
    assert resp.json()["deleted"] >= 3

    count = await db_session.execute(select(func.count(LibraryFile.id)).where(LibraryFile.deleted_at.isnot(None)))
    assert (count.scalar() or 0) == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_hard_delete_rejects_active_file(async_client: AsyncClient, file_factory):
    """Trash endpoints 404 for files that aren't actually trashed."""
    f = await file_factory()
    resp = await async_client.delete(f"/api/v1/library/trash/{f.id}")
    assert resp.status_code == 404

    resp = await async_client.post(f"/api/v1/library/trash/{f.id}/restore")
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
async def test_purge_preview_counts_old_files(async_client: AsyncClient, file_factory, db_session):
    """Preview counts only files past the threshold and returns total size + samples."""
    old_cutoff = datetime.now(timezone.utc) - timedelta(days=120)

    old1 = await file_factory(file_size=5000)
    old2 = await file_factory(file_size=7000)
    # A young file whose created_at stays near "now" — must not be counted.
    await file_factory(file_size=3000)

    # Stamp created_at into the past so the never-printed branch matches.
    for row, ts in ((old1, old_cutoff), (old2, old_cutoff)):
        row.created_at = ts
    await db_session.commit()

    resp = await async_client.get(
        "/api/v1/library/purge/preview",
        params={"older_than_days": 90, "include_never_printed": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert body["total_bytes"] == 12000
    assert body["older_than_days"] == 90
    assert len(body["sample_filenames"]) == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_purge_excludes_never_printed_when_requested(async_client: AsyncClient, file_factory, db_session):
    """With include_never_printed=False, only files with last_printed_at are eligible."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=200)

    recently_printed = await file_factory()
    recently_printed.last_printed_at = long_ago
    never_printed = await file_factory()
    never_printed.created_at = long_ago
    await db_session.commit()

    # Exclude never-printed → only 1 match
    resp = await async_client.get(
        "/api/v1/library/purge/preview",
        params={"older_than_days": 90, "include_never_printed": False},
    )
    assert resp.json()["count"] == 1

    # Include → 2 matches
    resp = await async_client.get(
        "/api/v1/library/purge/preview",
        params={"older_than_days": 90, "include_never_printed": True},
    )
    assert resp.json()["count"] == 2


@pytest.mark.asyncio
@pytest.mark.integration
async def test_purge_execute_moves_to_trash(async_client: AsyncClient, file_factory, db_session):
    """POST /library/purge moves matching files into trash (deleted_at stamped)."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=200)
    f = await file_factory()
    f.created_at = long_ago
    await db_session.commit()

    resp = await async_client.post(
        "/api/v1/library/purge",
        json={"older_than_days": 90, "include_never_printed": True},
    )
    assert resp.status_code == 200
    assert resp.json()["moved_to_trash"] >= 1

    await db_session.refresh(f)
    assert f.deleted_at is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_purge_skips_external_files(async_client: AsyncClient, file_factory, db_session):
    """External files are never eligible for purge, regardless of age."""
    long_ago = datetime.now(timezone.utc) - timedelta(days=300)
    ext = await file_factory(is_external=True)
    ext.created_at = long_ago
    await db_session.commit()

    resp = await async_client.get(
        "/api/v1/library/purge/preview",
        params={"older_than_days": 90, "include_never_printed": True},
    )
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_trash_settings_roundtrip(async_client: AsyncClient):
    """Retention setting persists and is clamped to [MIN, MAX]."""
    resp = await async_client.get("/api/v1/library/trash/settings")
    assert resp.status_code == 200
    default = resp.json()["retention_days"]
    assert 1 <= default <= 365

    resp = await async_client.put("/api/v1/library/trash/settings", json={"retention_days": 60})
    assert resp.status_code == 200
    assert resp.json()["retention_days"] == 60

    resp = await async_client.get("/api/v1/library/trash/settings")
    assert resp.json()["retention_days"] == 60


@pytest.mark.asyncio
@pytest.mark.integration
async def test_trash_settings_rejects_out_of_range(async_client: AsyncClient):
    """retention_days must fall within the clamped range."""
    resp = await async_client.put("/api/v1/library/trash/settings", json={"retention_days": 0})
    assert resp.status_code == 422  # Pydantic ge=1 trip

    resp = await async_client.put("/api/v1/library/trash/settings", json={"retention_days": 9999})
    assert resp.status_code == 422


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sweeper_hard_deletes_past_retention(db_session):
    """The background sweeper clears rows whose deleted_at is older than retention."""
    from backend.app.models.library import LibraryFile
    from backend.app.services.library_trash import library_trash_service

    # Retention = 30 days; stamp one row 40 days ago, one 5 days ago.
    await library_trash_service.set_retention_days(db_session, 30)

    fresh = LibraryFile(
        filename="fresh.3mf",
        file_path="/test/library/fresh.3mf",
        file_size=1024,
        file_type="3mf",
        deleted_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    stale = LibraryFile(
        filename="stale.3mf",
        file_path="/test/library/stale.3mf",
        file_size=2048,
        file_type="3mf",
        deleted_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    db_session.add_all([fresh, stale])
    await db_session.commit()

    stale_id = stale.id
    fresh_id = fresh.id
    deleted = await library_trash_service._sweep(db_session)
    assert deleted >= 1

    # The sweeper commits in its own session; expire ours so get() re-reads.
    db_session.expire_all()
    remaining = await db_session.get(LibraryFile, stale_id)
    assert remaining is None
    still_there = await db_session.get(LibraryFile, fresh_id)
    assert still_there is not None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_auto_purge_settings_roundtrip(async_client: AsyncClient):
    """Auto-purge fields on /library/trash/settings round-trip correctly."""
    resp = await async_client.put(
        "/api/v1/library/trash/settings",
        json={
            "retention_days": 30,
            "auto_purge_enabled": True,
            "auto_purge_days": 120,
            "auto_purge_include_never_printed": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_purge_enabled"] is True
    assert body["auto_purge_days"] == 120
    assert body["auto_purge_include_never_printed"] is False

    # GET surfaces the same saved values
    resp = await async_client.get("/api/v1/library/trash/settings")
    got = resp.json()
    assert got["auto_purge_enabled"] is True
    assert got["auto_purge_days"] == 120
    assert got["auto_purge_include_never_printed"] is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_auto_purge_runs_when_enabled_and_throttles_by_24h(file_factory, db_session):
    """The scheduler loop's auto-purge branch runs once, then the 24h throttle blocks."""
    from backend.app.services.library_trash import library_trash_service

    long_ago = datetime.now(timezone.utc) - timedelta(days=200)
    f = await file_factory()
    f.created_at = long_ago
    await db_session.commit()

    # Enable auto-purge with a 90-day threshold
    await library_trash_service.set_auto_purge_settings(db_session, enabled=True, days=90, include_never_printed=True)

    moved = await library_trash_service._maybe_run_auto_purge(db_session)
    assert moved >= 1

    db_session.expire_all()
    await db_session.refresh(f)
    assert f.deleted_at is not None

    # Second invocation within 24h should be throttled — no additional rows moved.
    long_ago2 = datetime.now(timezone.utc) - timedelta(days=200)
    f2 = await file_factory()
    f2.created_at = long_ago2
    await db_session.commit()

    moved_again = await library_trash_service._maybe_run_auto_purge(db_session)
    assert moved_again == 0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_auto_purge_skipped_when_disabled(file_factory, db_session):
    """If the toggle is off, old files stay put even when everything else matches."""
    from backend.app.services.library_trash import library_trash_service

    long_ago = datetime.now(timezone.utc) - timedelta(days=200)
    f = await file_factory()
    f.created_at = long_ago
    await db_session.commit()

    await library_trash_service.set_auto_purge_settings(db_session, enabled=False, days=90, include_never_printed=True)
    moved = await library_trash_service._maybe_run_auto_purge(db_session)
    assert moved == 0

    db_session.expire_all()
    await db_session.refresh(f)
    assert f.deleted_at is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_trashed_file_hidden_from_makerworld_dedupe(async_client: AsyncClient, file_factory, db_session):
    """MakerWorld 'already imported' dedupe must not match trashed rows."""
    from sqlalchemy import select

    from backend.app.models.library import LibraryFile

    f = await file_factory(source_type="makerworld", source_url="https://makerworld.com/en/models/99#profileId-1")
    # Trash it.
    await async_client.delete(f"/api/v1/library/files/{f.id}")

    # The dedupe query used by the makerworld helper is `source_url == X AND deleted_at IS NULL`.
    result = await db_session.execute(
        LibraryFile.active().where(LibraryFile.source_url == "https://makerworld.com/en/models/99#profileId-1")
    )
    assert result.scalar_one_or_none() is None

    # Direct lookup WITHOUT the active filter still sees the row.
    direct = await db_session.execute(
        select(LibraryFile).where(LibraryFile.source_url == "https://makerworld.com/en/models/99#profileId-1")
    )
    assert direct.scalar_one_or_none() is not None
