"""Existing archives are repaired conservatively for issue #138."""

import json
import zipfile

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.app.models  # noqa: F401
from backend.app.core.archive_metadata_migration import repair_archive_plate_metadata, repair_bare_filament_colors
from backend.app.core.database import Base
from backend.app.models.archive import PrintArchive
from backend.app.models.print_log import PrintLogEntry
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer


def _write_3mf(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "curr_bed_type": "Cool Plate",
        "cool_plate_temp_initial_layer": ["35", "0"],
        "textured_plate_temp_initial_layer": ["0", "70"],
        "nozzle_temperature_initial_layer": ["210", "255"],
    }
    slice_info = """<config>
      <plate><metadata key="index" value="1"/><metadata key="curr_bed_type" value="Cool Plate"/><filament id="1" used_g="8"/></plate>
      <plate><metadata key="index" value="2"/><metadata key="curr_bed_type" value="Textured PEI Plate"/><filament id="2" used_g="9"/></plate>
    </config>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps(config))
        archive.writestr("Metadata/slice_info.config", slice_info)
        archive.writestr("Metadata/plate_1.gcode", "; layer_height = 0.20\n")
        archive.writestr("Metadata/plate_2.gcode", "; layer_height = 0.08\n")


def test_nozzle_temperature_follows_the_used_filament(tmp_path):
    from backend.app.services.archive import ThreeMFParser

    source = tmp_path / "multi.3mf"
    _write_3mf(source)
    assert ThreeMFParser(source, 2).parse()["nozzle_temperature"] == 255
    assert ThreeMFParser(source).parse()["nozzle_temperature"] == 210


@pytest.mark.asyncio
async def test_existing_bare_colors_are_repaired_in_archives_and_runs(test_engine, db_session):
    archive = PrintArchive(filename="fallback.3mf", file_path="", file_size=0, filament_color="ff8800ff,#00AE42,Custom")
    run = PrintLogEntry(status="completed", filament_color="112233,#445566,abcdef")
    db_session.add_all([archive, run])
    await db_session.commit()
    async with test_engine.begin() as conn:
        await repair_bare_filament_colors(conn)
        await repair_bare_filament_colors(conn)
    await db_session.refresh(archive)
    await db_session.refresh(run)
    assert archive.filament_color == "#FF8800,#00AE42,Custom"
    assert run.filament_color == "#112233,#445566,#ABCDEF"


@pytest.mark.asyncio
async def test_repair_recovers_selected_plate_without_clobbering_existing_values(tmp_path, monkeypatch):
    from backend.app.core import archive_metadata_migration as migration

    monkeypatch.setattr(migration.settings, "base_dir", tmp_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/metadata.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        relative = "archives/1/multi.3mf"
        _write_3mf(tmp_path / relative)
        async with session() as db:
            printer = Printer(name="P", serial_number="S", ip_address="10.0.0.1", access_code="x", model="X1C")
            db.add(printer)
            await db.flush()
            recovered = PrintArchive(
                filename="multi.3mf",
                file_path=relative,
                file_size=1,
                status="completed",
                print_name="Keep me",
                notes="user note",
                layer_height=0.2,
                bed_type="Cool Plate",
            )
            preserved = PrintArchive(
                filename="multi.3mf",
                file_path=relative,
                file_size=1,
                status="completed",
                plate_id=1,
                bed_temperature=99,
                notes="manual value",
            )
            ambiguous = PrintArchive(filename="multi.3mf", file_path=relative, file_size=1, status="completed")
            db.add_all([recovered, preserved, ambiguous])
            await db.flush()
            db.add_all(
                [
                    PrintQueueItem(printer_id=printer.id, archive_id=recovered.id, status="completed", plate_id=2),
                    PrintQueueItem(printer_id=printer.id, archive_id=preserved.id, status="completed", plate_id=2),
                ]
            )
            await db.commit()

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE VIRTUAL TABLE archive_fts USING fts5(print_name, content='print_archives', content_rowid='id')"
                )
            )
            await conn.execute(
                text(
                    "CREATE TRIGGER archive_fts_update AFTER UPDATE ON print_archives BEGIN "
                    "INSERT INTO archive_fts(archive_fts, rowid, print_name) "
                    "VALUES ('delete', old.id, old.print_name); "
                    "INSERT INTO archive_fts(rowid, print_name) VALUES (new.id, new.print_name); END"
                )
            )
            await repair_archive_plate_metadata(conn)
            await repair_archive_plate_metadata(conn)

        async with session() as db:
            repaired = await db.get(PrintArchive, recovered.id)
            kept = await db.get(PrintArchive, preserved.id)
            unknown = await db.get(PrintArchive, ambiguous.id)
            assert (repaired.plate_id, repaired.layer_height) == (2, 0.08)
            assert (repaired.bed_type, repaired.bed_temperature) == ("Textured PEI Plate", 70)
            assert (repaired.print_name, repaired.notes) == ("Keep me", "user note")
            assert (kept.plate_id, kept.bed_temperature, kept.notes) == (1, 99, "manual value")
            assert unknown.bed_temperature is None

        async with engine.begin() as conn:
            count = (
                await conn.execute(
                    text('SELECT COUNT(*) FROM settings WHERE "key" = :key'),
                    {"key": "_printops_138_archive_metadata_done"},
                )
            ).scalar_one()
            assert count == 1
    finally:
        await engine.dispose()
