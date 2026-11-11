"""Dispatch evidence wins over the source archive's original plate."""

import zipfile
from types import SimpleNamespace

import pytest

from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.archive import ArchiveService
from backend.app.services.usage_tracker import _load_dispatch_context


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
async def test_dispatch_context_prefers_this_printers_newest_queue_plate(
    status, db_session, printer_factory, archive_factory
):
    printer = await printer_factory()
    other = await printer_factory()
    archive = await archive_factory(printer.id, with_run=False, plate_id=1)
    old = PrintQueueItem(printer_id=printer.id, archive_id=archive.id, status="completed", plate_id=1)
    current = PrintQueueItem(printer_id=printer.id, archive_id=archive.id, status=status, plate_id=2)
    unrelated = PrintQueueItem(printer_id=other.id, archive_id=archive.id, status="printing", plate_id=3)
    db_session.add_all([old, current, unrelated])
    await db_session.commit()
    item, plate = await _load_dispatch_context(db_session, printer.id, archive.id, archive, None, False)
    assert item is current and plate == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit,expected", [(None, 1), (2, 2)])
async def test_only_a_real_sliced_plate_is_inferred_from_the_reported_filename(
    explicit, expected, monkeypatch, db_session, tmp_path
):
    from backend.app.services import archive as archive_module

    source = tmp_path / "part.3mf"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Metadata/plate_1.gcode", "G28")
        archive.writestr(
            "Metadata/slice_info.config", '<config><plate><metadata key="index" value="1"/></plate></config>'
        )
    monkeypatch.setattr(
        archive_module, "settings", SimpleNamespace(base_dir=tmp_path, archive_dir=tmp_path / "archives")
    )
    result = await ArchiveService(db_session).archive_print(
        None, source, print_data={"filename": "User_model_plate_2.gcode.3mf", "status": "printing"}, plate_id=explicit
    )
    assert result.plate_id == expected
