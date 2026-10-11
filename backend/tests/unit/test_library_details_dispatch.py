"""Transient source cleanup carries user details to the durable archive."""

import pytest

from backend.app.core.config import settings
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.library_queue_references import consume_transient_library_source
from backend.app.utils.library_paths import library_photos_dir
from backend.app.utils.safe_path import PathTraversalError
from backend.tests.unit.test_scheduler_cleanup_library import (
    _dispatch_library_item,
    _queue_snapshot,
    queue_factory,
)

__all__ = ["queue_factory"]


@pytest.mark.asyncio
async def test_consumed_library_source_preserves_details_and_photos(queue_factory, monkeypatch):
    ctx = await queue_factory(cleanup=True)
    monkeypatch.setattr(settings, "archive_dir", ctx.base_dir / "archive")
    directory = library_photos_dir(ctx.library_file_id)
    directory.mkdir(parents=True)
    (directory / "result.png").write_bytes(b"user photo")
    async with ctx.session_maker() as db:
        source = await db.get(LibraryFile, ctx.library_file_id)
        source.notes = "Use textured plate"
        source.external_url = "https://example.org/design"
        source.photos = ["result.png"]
        await db.commit()

    await _dispatch_library_item(ctx)

    _item, source, archive = await _queue_snapshot(ctx)
    assert source is None
    assert archive.notes == "Use textured plate"
    assert archive.external_url == "https://example.org/design"
    assert archive.photos == ["result.png"]
    assert (ctx.archive_path.parent / "photos" / "result.png").read_bytes() == b"user photo"
    assert not directory.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("escape", ["relative", "absolute", "archive-symlink", "photos-symlink"])
async def test_photo_handoff_rejects_destinations_outside_archive_storage(queue_factory, monkeypatch, escape):
    ctx = await queue_factory(cleanup=True)
    monkeypatch.setattr(settings, "base_dir", ctx.base_dir)
    monkeypatch.setattr(settings, "archive_dir", ctx.base_dir / "archive")
    photos = library_photos_dir(ctx.library_file_id)
    photos.mkdir(parents=True)
    source_photo = photos / "result.png"
    source_photo.write_bytes(b"private result photo")
    outside = ctx.base_dir.parent / "outside"
    outside.mkdir()
    if escape == "relative":
        archive_path = "../outside/model.3mf"
    elif escape == "absolute":
        archive_path = str(outside / "model.3mf")
    elif escape == "archive-symlink":
        (ctx.base_dir / "archives").symlink_to(outside, target_is_directory=True)
        archive_path = "archives/model.3mf"
    else:
        own_dir = ctx.base_dir / "archives"
        own_dir.mkdir()
        (own_dir / "photos").symlink_to(outside, target_is_directory=True)
        archive_path = "archives/model.3mf"
    async with ctx.session_maker() as db:
        library = await db.get(LibraryFile, ctx.library_file_id)
        library.photos = ["result.png"]
        item = await db.get(PrintQueueItem, ctx.queue_item_id)
        archive = PrintArchive(
            printer_id=ctx.printer_id, filename="model.3mf", file_path=archive_path, file_size=1, status="completed"
        )
        db.add(archive)
        await db.flush()
        with pytest.raises(PathTraversalError):
            await consume_transient_library_source(db, item, library, archive.id)
        assert source_photo.read_bytes() == b"private result photo"
        assert list(outside.iterdir()) == []
        assert item.library_file_id == ctx.library_file_id
