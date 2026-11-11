"""Library dispatch keeps one valid archive for the same source and ownership."""

import asyncio
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.core.config import settings
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.library_dispatch_archive import archive_library_dispatch

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def write_source(path, value):
    with zipfile.ZipFile(path, "w") as output:
        output.writestr("Metadata/plate_1.gcode", value)


async def create_source(db, path, *, created_by_id=None):
    row = LibraryFile(
        filename="model.3mf",
        file_path=str(path),
        file_type="3mf",
        file_size=path.stat().st_size,
        is_external=True,
        created_by_id=created_by_id,
    )
    db.add(row)
    await db.flush()
    return row


async def test_concurrent_dispatches_reuse_one_archive_even_while_it_is_printing(
    db_session, test_engine, printer_factory, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archives")
    path = tmp_path / "model.3mf"
    write_source(path, "G28")
    first, second = await printer_factory(), await printer_factory()
    source = await create_source(db_session, path)
    source_id = source.id
    await db_session.commit()
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)

    async def choose(printer_id):
        async with sessions() as db:
            item = PrintQueueItem(printer_id=printer_id, library_file_id=source_id, plate_id=1)
            archive = await archive_library_dispatch(db, item, path, path.name)
            await db.commit()
            return archive.id

    ids = await asyncio.gather(choose(first.id), choose(second.id))
    assert ids[0] == ids[1]
    archive = await db_session.get(PrintArchive, ids[0])
    assert archive.source_library_file_id == source_id
    archive.status = "printing"
    await db_session.commit()
    assert await choose(second.id) == archive.id
    assert await db_session.scalar(select(func.count(PrintArchive.id))) == 1


async def test_reuse_requires_matching_bytes_and_library_source(db_session, printer_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archives")
    path = tmp_path / "model.3mf"
    write_source(path, "G28")
    printer = await printer_factory()
    first_source = await create_source(db_session, path)
    second_source = await create_source(db_session, path)
    await db_session.commit()

    async def choose(source):
        item = PrintQueueItem(printer_id=printer.id, library_file_id=source.id, plate_id=1)
        return await archive_library_dispatch(db_session, item, path, path.name)

    first = await choose(first_source)
    second = await choose(second_source)
    assert first.id != second.id
    assert first.file_path != second.file_path
    original_path = tmp_path / Path(first.file_path)
    original_bytes = original_path.read_bytes()
    write_source(path, "G28\nM73 P100")
    changed = await choose(first_source)
    assert changed.id not in (first.id, second.id)
    assert original_path.read_bytes() == original_bytes
    changed_file = tmp_path / changed.file_path
    assert changed_file.read_bytes() == path.read_bytes()
    write_source(changed_file, "G28\nM104 S0")
    repaired = await choose(first_source)
    assert repaired.id != changed.id
    assert (tmp_path / repaired.file_path).read_bytes() == path.read_bytes()
