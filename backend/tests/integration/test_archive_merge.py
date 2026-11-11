"""Duplicate archive merges preserve files, run identity, scope and references."""

import hashlib
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from backend.app.core.auth import create_access_token
from backend.app.core.config import settings
from backend.app.core.permissions import Permission
from backend.app.models.archive import PrintArchive
from backend.app.models.archive_alias import ArchiveAlias
from backend.app.models.group import Group
from backend.app.models.library import LibraryFolder
from backend.app.models.print_batch import PrintBatch
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.user import User
from backend.tests.integration.test_media_tokens import _admin_token

BASE = "/api/v1/archives"
START = datetime(2026, 10, 9, 9)
FILE = b"Identical fixture bytes for two archive rows"


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def duplicates(db_session, tmp_path, monkeypatch, printer_factory, archive_factory):
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archives")
    first, second = await printer_factory(), await printer_factory()
    owner = User(username="Archive owner")
    db_session.add(owner)
    await db_session.commit()

    async def create(printer, directory, minute, photo, *, owner_id=owner.id):
        root = tmp_path / "archives" / directory
        (root / "photos").mkdir(parents=True)
        (root / "part.gcode.3mf").write_bytes(FILE)
        (root / "photos" / "finish.jpg").write_bytes(photo)
        (root / "video.mp4").write_bytes(photo)
        start = START + timedelta(minutes=minute)
        return await archive_factory(
            printer.id,
            filename="part.gcode.3mf",
            file_path=f"archives/{directory}/part.gcode.3mf",
            content_hash=hashlib.sha256(FILE).hexdigest(),
            timelapse_path=f"archives/{directory}/video.mp4",
            timelapse_plate_id=minute + 1,
            photos=["finish.jpg"],
            created_by_id=owner_id,
            started_at=start,
            completed_at=start + timedelta(minutes=1),
            plate_id=minute + 1,
            notes=directory,
            tags=directory,
            with_run=False,
        )

    survivor = await create(first, "old", 0, b"old media")
    source = await create(second, "duplicate", 1, b"new media")
    return first, second, survivor, source, create


def _body(survivor, source):
    return {"groups": [{"survivor_id": survivor.id, "merged_ids": [source.id]}]}


async def test_merge_keeps_two_printers_media_quality_and_original_references(
    async_client, db_session, duplicates, tmp_path, monkeypatch
):
    first, second, survivor, source, _ = duplicates
    runs = [
        PrintLogEntry(
            archive_id=row.id,
            printer_id=row.printer_id,
            status="completed",
            plate_id=row.plate_id,
            started_at=row.started_at,
            completed_at=row.completed_at,
            photos=row.photos,
            timelapse_path=row.timelapse_path,
            quantity=2,
            good_quantity=1,
            reject_quantity=1,
        )
        for row in (survivor, source)
    ]
    batch = PrintBatch(name="Workshop order", archive_id=source.id)
    folder = LibraryFolder(name="Reference", archive_id=source.id)
    item = PrintQueueItem(archive_id=source.id, printer_id=second.id, status="completed")
    db_session.add_all([*runs, batch, folder, item])
    await db_session.commit()
    source_id = source.id
    assert (await async_client.get(f"{BASE}/merge-count")).json() == {"groups": 1}
    preview = (await async_client.get(f"{BASE}/merge-preview")).json()["groups"]
    assert [(group["survivor"]["id"], group["merged"][0]["id"]) for group in preview] == [(survivor.id, source_id)]
    assert preview[0]["skipped"] is None

    from backend.app.services import archive_merge

    with monkeypatch.context() as patch:
        patch.setattr(archive_merge, "project_latest_finished_run", AsyncMock(side_effect=RuntimeError("fixture")))
        failed = await async_client.post(f"{BASE}/merge", json=_body(survivor, source))
        assert failed.json()["skipped"][0]["reason"] == "failed"
    assert (tmp_path / "archives" / "duplicate" / "video.mp4").is_file()
    assert sorted(path.name for path in (tmp_path / "archives" / "old" / "photos").iterdir()) == ["finish.jpg"]
    await db_session.refresh(item)
    assert item.archive_id == source_id

    response = await async_client.post(f"{BASE}/merge", json=_body(survivor, source))
    assert response.status_code == 200, response.text
    assert response.json() == {"merged": [{"survivor_id": survivor.id, "merged_ids": [source_id]}], "skipped": []}
    for record in (*runs, batch, folder, item, survivor):
        await db_session.refresh(record)
    assert all(record.archive_id == survivor.id for record in (*runs, batch, folder, item))
    assert [(run.printer_id, run.plate_id, run.good_quantity, run.reject_quantity) for run in runs] == [
        (first.id, 1, 1, 1),
        (second.id, 2, 1, 1),
    ]
    assert survivor.printer_id == second.id
    assert survivor.notes == "old\n\nduplicate"
    assert survivor.tags == "old, duplicate"
    assert len(survivor.photos) == 2
    new_photo = await async_client.get(f"{BASE}/{survivor.id}/photos/{runs[1].photos[0]}?run_id={runs[1].id}")
    assert new_photo.content == b"new media"
    assert (tmp_path / runs[1].timelapse_path).read_bytes() == b"new media"
    alias = await db_session.get(ArchiveAlias, source_id)
    assert alias.archive_id == survivor.id
    assert await db_session.scalar(select(PrintArchive.id).where(PrintArchive.id == source_id)) is None
    assert not (tmp_path / "archives" / "duplicate").exists()
    old_link = await async_client.get(f"{BASE}/{source_id}?run_id={runs[1].id}")
    assert old_link.status_code == 200, old_link.text
    assert old_link.json()["id"] == survivor.id
    assert (await async_client.get(f"{BASE}/merge-count")).json() == {"groups": 0}


async def test_merge_requires_all_permissions_and_never_widens_printer_or_owner_scope(
    async_client, db_session, duplicates
):
    first, _, survivor, source, create = duplicates
    admin = await _admin_token(async_client, "archive_merge")
    editor = User(
        username="merge_editor",
        allowed_printer_ids=[first.id],
        groups=[
            Group(
                name="Scoped merge",
                permissions=[
                    Permission.ARCHIVES_READ_ALL.value,
                    Permission.ARCHIVES_UPDATE_ALL.value,
                    Permission.ARCHIVES_DELETE_ALL.value,
                ],
            )
        ],
    )
    reader = User(
        username="merge_reader",
        groups=[Group(name="Read archives", permissions=[Permission.ARCHIVES_READ_ALL.value])],
    )
    other = User(username="Other owner")
    db_session.add_all([editor, reader, other])
    await db_session.commit()
    unrelated = await create(first, "other-owner", 3, b"other", owner_id=other.id)
    request = _body(survivor, source)
    for headers, code in (
        ({}, 401),
        (_headers("bad-token"), 401),
        (_headers(create_access_token({"sub": editor.username}, timedelta(seconds=-1))), 401),
        (_headers(create_access_token({"sub": reader.username})), 403),
    ):
        assert (await async_client.get(f"{BASE}/merge-preview", headers=headers)).status_code == code
        response = await async_client.post(f"{BASE}/merge", json=request, headers=headers)
        assert response.status_code == code, response.text
    scoped = _headers(create_access_token({"sub": editor.username}))
    assert (await async_client.get(f"{BASE}/merge-preview", headers=scoped)).json() == {"groups": []}
    limited = await async_client.post(f"{BASE}/merge", json=request, headers=scoped)
    assert limited.json()["skipped"][0]["reason"] == "invalid_group"
    cross_owner = await async_client.post(f"{BASE}/merge", json=_body(survivor, unrelated), headers=_headers(admin))
    assert cross_owner.json()["skipped"][0]["reason"] == "invalid_group"
    merged = await async_client.post(f"{BASE}/merge", json=request, headers=_headers(admin))
    assert merged.json()["merged"]
    assert (await async_client.get(f"{BASE}/{source.id}", headers=scoped)).status_code == 404
    assert (await async_client.get(f"{BASE}/{survivor.id}", headers=scoped)).status_code == 200


async def test_busy_group_stays_intact(async_client, db_session, duplicates):
    _, second, survivor, source, _ = duplicates
    db_session.add(PrintQueueItem(archive_id=source.id, printer_id=second.id, status="pending"))
    await db_session.commit()
    preview = await async_client.get(f"{BASE}/merge-preview")
    assert preview.json()["groups"][0]["skipped"] == "busy"
    response = await async_client.post(f"{BASE}/merge", json=_body(survivor, source))
    assert response.json()["skipped"][0]["reason"] == "busy"
    assert await db_session.get(ArchiveAlias, source.id) is None


async def test_merge_retains_source_directory_with_unregistered_media(async_client, duplicates, tmp_path):
    _, _, survivor, source, _ = duplicates
    edited_video = tmp_path / "archives" / "duplicate" / "edited.mp4"
    edited_video.write_bytes(b"Edited video from an earlier session")

    response = await async_client.post(f"{BASE}/merge", json=_body(survivor, source))

    assert response.json()["merged"]
    assert edited_video.read_bytes() == b"Edited video from an earlier session"
    assert (edited_video.parent / "part.gcode.3mf").is_file()


async def test_active_timelapse_edit_blocks_merge(async_client, duplicates):
    from backend.app.services.archive_merge import finish_archive_media_edit, start_archive_media_edit

    _, _, survivor, source, _ = duplicates
    assert start_archive_media_edit(source.id)
    try:
        preview = await async_client.get(f"{BASE}/merge-preview")
        assert preview.json()["groups"][0]["skipped"] == "busy"
        response = await async_client.post(f"{BASE}/merge", json=_body(survivor, source))
        assert response.json()["skipped"][0]["reason"] == "busy"
    finally:
        finish_archive_media_edit(source.id)
    response = await async_client.post(f"{BASE}/merge", json=_body(survivor, source))
    assert response.json()["merged"]
