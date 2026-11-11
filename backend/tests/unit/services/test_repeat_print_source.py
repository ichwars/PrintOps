"""Touchscreen repeats borrow only the same printer's proven print source."""

import asyncio
import zipfile
from datetime import datetime

import pytest

from backend.app.services.repeat_print_source import archived_repeat_source, copy_repeat_source

GCODE = "/data/Metadata/plate_3.gcode"


def source_file(path, plate=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"Metadata/plate_{plate}.gcode", "G28\n")
        archive.writestr(
            "Metadata/slice_info.config", f'<config><plate><metadata key="index" value="{plate}"/></plate></config>'
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch", [None, "printer", "title", "gcode", "layers", "deleted", "missing", "escape", "plate"]
)
async def test_repeat_source_requires_matching_run_and_safe_existing_file(
    mismatch, db_session, printer_factory, archive_factory, tmp_path
):
    printer = await printer_factory()
    other = await printer_factory()
    source_file(tmp_path / "old.3mf", plate=2 if mismatch == "plate" else 3)
    archive = await archive_factory(
        other.id if mismatch == "printer" else printer.id,
        with_run=False,
        filename="Original card filename.gcode.3mf",
        file_path={"missing": "gone.3mf", "escape": "../old.3mf"}.get(mismatch, "old.3mf"),
        total_layers=400 if mismatch == "layers" else 300,
        deleted_at=datetime.now() if mismatch == "deleted" else None,
        extra_data={
            "_print_data": {
                "subtask_name": "Different title" if mismatch == "title" else "Internal title",
                "filename": "/data/Metadata/plate_2.gcode" if mismatch == "gcode" else GCODE,
            }
        },
    )
    result = await archived_repeat_source(db_session, printer.id, "Internal title", GCODE, 300, base_dir=tmp_path)
    assert (result is archive) is (mismatch is None)


@pytest.mark.asyncio
async def test_failed_copy_removes_partial_destination(monkeypatch, tmp_path):
    from backend.app.services import repeat_print_source

    destination = tmp_path / "copy.3mf"

    def fail(source, target):
        target.write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(repeat_print_source.shutil, "copyfile", fail)
    with pytest.raises(OSError, match="disk full"):
        await copy_repeat_source(tmp_path / "source.3mf", destination)
    assert not destination.exists()


@pytest.mark.asyncio
async def test_cancelled_copy_settles_worker_before_removing_destination(monkeypatch, tmp_path):
    from backend.app.services import repeat_print_source

    destination = tmp_path / "copy.3mf"
    entered, finish = asyncio.Event(), asyncio.Event()

    async def delayed(function, *args):
        entered.set()
        await finish.wait()
        destination.write_bytes(b"copy")

    monkeypatch.setattr(repeat_print_source.asyncio, "to_thread", delayed)
    operation = asyncio.create_task(copy_repeat_source(tmp_path / "source.3mf", destination))
    await entered.wait()
    operation.cancel()
    await asyncio.sleep(0)
    assert not operation.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert not destination.exists()
