"""One-shot repair for existing plain-named sliced 3MF library rows (#132)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.library_migrations import reclassify_sliced_3mf_library_files


def _write_3mf(path: Path, names: list[str]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, b"x")
    return path.read_bytes()


@pytest.fixture
async def migration_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE TABLE settings (id INTEGER PRIMARY KEY, key VARCHAR(100) UNIQUE, value TEXT NOT NULL)")
        )
        await conn.execute(
            text(
                "CREATE TABLE library_files ("
                "id INTEGER PRIMARY KEY, filename VARCHAR(255), file_path VARCHAR(500), "
                "file_type VARCHAR(10), is_external BOOLEAN, deleted_at DATETIME, project_id INTEGER)"
            )
        )
    yield engine
    await engine.dispose()


async def _insert_file(conn, *, file_id: int, path: str, external: bool = False, deleted: bool = False) -> None:
    await conn.execute(
        text(
            "INSERT INTO library_files "
            "(id, filename, file_path, file_type, is_external, deleted_at, project_id) "
            "VALUES (:id, :filename, :path, '3mf', :external, :deleted_at, 77)"
        ),
        {
            "id": file_id,
            "filename": Path(path).name,
            "path": path,
            "external": external,
            "deleted_at": "2026-01-01" if deleted else None,
        },
    )


@pytest.mark.asyncio
async def test_repair_reclassifies_internal_rows_without_changing_files_or_relationships(migration_engine, tmp_path):
    sliced_bytes = _write_3mf(tmp_path / "files/sliced.3mf", ["Metadata/plate_2.gcode"])
    _write_3mf(tmp_path / "files/source.3mf", ["3D/3dmodel.model"])
    _write_3mf(tmp_path / "files/trashed.3mf", ["Metadata/plate_5.gcode"])
    (tmp_path / "files/broken.3mf").write_bytes(b"PK\x03\x04broken")
    async with migration_engine.begin() as conn:
        await _insert_file(conn, file_id=1, path="files/sliced.3mf")
        await _insert_file(conn, file_id=2, path="files/source.3mf")
        await _insert_file(conn, file_id=3, path="files/broken.3mf")
        await _insert_file(conn, file_id=4, path="files/trashed.3mf", deleted=True)

        await reclassify_sliced_3mf_library_files(conn, tmp_path)

        rows = (
            await conn.execute(text("SELECT id, file_type, file_path, project_id FROM library_files ORDER BY id"))
        ).fetchall()

    assert [(row.id, row.file_type) for row in rows] == [
        (1, "gcode.3mf"),
        (2, "3mf"),
        (3, "3mf"),
        (4, "gcode.3mf"),
    ]
    assert all(row.project_id == 77 for row in rows)
    assert rows[0].file_path == "files/sliced.3mf"
    assert (tmp_path / "files/sliced.3mf").read_bytes() == sliced_bytes


@pytest.mark.asyncio
async def test_repair_is_one_shot_and_skips_external_mounts(migration_engine, tmp_path):
    source_path = tmp_path / "files/source.3mf"
    external_path = tmp_path / "mount/external.3mf"
    _write_3mf(source_path, ["3D/3dmodel.model"])
    _write_3mf(external_path, ["Metadata/plate_1.gcode"])
    async with migration_engine.begin() as conn:
        await _insert_file(conn, file_id=1, path="files/source.3mf")
        await _insert_file(conn, file_id=2, path=str(external_path), external=True)

        await reclassify_sliced_3mf_library_files(conn, tmp_path)
        _write_3mf(source_path, ["Metadata/plate_9.gcode"])
        await reclassify_sliced_3mf_library_files(conn, tmp_path)

        rows = dict((await conn.execute(text("SELECT id, file_type FROM library_files"))).fetchall())
        flags = (
            await conn.execute(text("SELECT value FROM settings WHERE key = '_backfill_132_sliced_3mf_type_done'"))
        ).fetchall()

    assert rows == {1: "3mf", 2: "3mf"}
    assert flags == [("true",)]
