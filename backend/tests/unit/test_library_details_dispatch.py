"""Transient source cleanup carries user details to the durable archive."""

import pytest

from backend.app.core.config import settings
from backend.app.models.library import LibraryFile
from backend.app.utils.library_paths import library_photos_dir
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
