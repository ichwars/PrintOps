"""Database-backed coverage for virtual printer reconciliation and slicer intake."""

import json
import zipfile
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.api.routes import printers
from backend.app.core.config import settings
from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.virtual_printer import VirtualPrinter
from backend.app.services import virtual_printer
from backend.app.services.queue_source_metadata import saved_slicer_ams_mapping
from backend.app.services.virtual_printer.manager import VirtualPrinterInstance, VirtualPrinterManager


async def test_proxy_restarts_after_rename_and_target_ip_update(
    async_client, db_session, printer_factory, test_engine, tmp_path, monkeypatch
):
    printer = await printer_factory(ip_address="192.0.2.10")
    vp = VirtualPrinter(
        name="Proxy",
        enabled=True,
        mode="proxy",
        bind_ip="192.0.2.20",
        target_printer_id=printer.id,
        queue_force_color_match=True,
        gcode_injection=True,
    )
    db_session.add(vp)
    await db_session.commit()
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    manager = VirtualPrinterManager()
    manager.set_session_factory(async_sessionmaker(test_engine, expire_on_commit=False))
    start_proxy, stop_proxy = AsyncMock(), AsyncMock()
    monkeypatch.setattr(VirtualPrinterInstance, "start_proxy", start_proxy)
    monkeypatch.setattr(VirtualPrinterInstance, "stop_proxy", stop_proxy)
    monkeypatch.setattr(virtual_printer, "virtual_printer_manager", manager)
    monkeypatch.setattr(printers.printer_manager, "connect_printer", AsyncMock())
    monkeypatch.setattr(printers.printer_manager, "disconnect_printer", Mock())

    await manager.sync_from_db()
    initial = manager.get_instance(vp.id)
    assert initial.target_printer_ip == "192.0.2.10"
    await manager.sync_from_db()
    assert manager.get_instance(vp.id) is initial
    start_proxy.assert_awaited_once()
    stop_proxy.assert_not_awaited()

    vp.name = "Renamed"
    await db_session.commit()
    await manager.sync_from_db()
    renamed = manager.get_instance(vp.id)
    assert renamed.name == "Renamed"
    assert renamed is not initial

    response = await async_client.patch(f"/api/v1/printers/{printer.id}", json={"ip_address": "192.0.2.11"})
    assert response.status_code == 200, response.text
    current = manager.get_instance(vp.id)
    assert current is not renamed
    assert current.target_printer_ip == "192.0.2.11"
    assert start_proxy.await_count == 3
    assert stop_proxy.await_count == 2
    await manager.stop_all()
    assert manager.get_instance(vp.id) is None
    assert stop_proxy.await_count == 3


def _upload(path):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/plate_1.gcode", "G90\n")
        archive.writestr("Metadata/plate_2.gcode", "G90\n")
        archive.writestr(
            "Metadata/slice_info.config",
            '<config><plate><metadata key="index" value="1"/>'
            '<filament id="1" type="PLA" color="#FFFFFF" used_g="1"/></plate>'
            '<plate><metadata key="index" value="2"/>'
            '<filament id="3" type="PLA" color="#FFFFFF" used_g="1"/></plate></config>',
        )
    return path


def _queue_instance(tmp_path, test_engine, **options):
    return VirtualPrinterInstance(
        vp_id=1,
        name="Queue",
        mode="queue",
        model="O1C2",
        access_code="12345678",
        serial_suffix="391800001",
        base_dir=tmp_path,
        session_factory=async_sessionmaker(test_engine, expire_on_commit=False),
        **options,
    )


async def test_upload_captures_slicer_options_per_plate(
    db_session, printer_factory, test_engine, tmp_path, monkeypatch
):
    printer = await printer_factory(model="H2C", model_code="O1C2")
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archive")
    vp = _queue_instance(tmp_path, test_engine, target_printer_id=printer.id)
    upload = _upload(tmp_path / "plates.3mf")
    await vp.on_print_command(
        upload.name,
        {
            "command": "project_file",
            "auto_bed_leveling": 0,
            "bed_leveling": True,
            "extrude_cali_flag": 1,
            "nozzle_offset_cali": 0,
            "nozzle_mapping": [16, -1, 1],
            "ams_mapping": [-1],
            "ams_mapping2": [{"ams_id": 255, "slot_id": 0}],
        },
    )
    await vp._add_to_print_queue(upload, "192.0.2.8")

    first, second = (await db_session.scalars(select(PrintQueueItem).order_by(PrintQueueItem.plate_id))).all()
    assert (first.plate_id, second.plate_id) == (1, 2)
    assert json.loads(first.ams_mapping) == [255]
    assert second.ams_mapping is None
    archive = await db_session.get(PrintArchive, first.archive_id)
    assert saved_slicer_ams_mapping(archive, printer.id, 1) == "[255]"
    assert saved_slicer_ams_mapping(archive, printer.id, 2) is None
    for item in (first, second):
        assert item.printer_id == printer.id
        assert item.bed_levelling is False
        assert item.flow_cali is True
        assert item.nozzle_offset_cali is False
        assert json.loads(item.nozzle_mapping) == [16, -1, 1]


@pytest.mark.parametrize("claim_first_plate", [False, True])
async def test_late_options_only_update_unclaimed_original_targets(
    db_session, printer_factory, test_engine, tmp_path, monkeypatch, claim_first_plate
):
    printer, other = await printer_factory(), await printer_factory()
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archive")
    vp = _queue_instance(tmp_path, test_engine, target_printer_id=printer.id)
    upload = _upload(tmp_path / "late.3mf")
    await vp._add_to_print_queue(upload, "192.0.2.8")
    first, second = (await db_session.scalars(select(PrintQueueItem).order_by(PrintQueueItem.plate_id))).all()
    if claim_first_plate:
        first.dispatching_at = datetime(2026, 11, 9)
    reassigned = PrintQueueItem(printer_id=other.id)
    started = PrintQueueItem(printer_id=printer.id, status="printing")
    protected = (reassigned, started)
    db_session.add_all(protected)
    await db_session.commit()
    tracked_ids, _ = vp._recent_queue_items[upload.name]
    tracked_ids.extend(row.id for row in protected)

    await vp.on_print_command(
        upload.name,
        {
            "command": "project_file",
            "ams_mapping": [4],
            "nozzle_offset_cali": False,
            "timelapse": True,
        },
    )
    for row in (first, second, *protected):
        await db_session.refresh(row)
    assert first.ams_mapping == (None if claim_first_plate else "[4]")
    assert first.timelapse is not claim_first_plate
    assert first.nozzle_offset_cali is claim_first_plate
    assert second.ams_mapping is None
    assert second.timelapse is True
    assert second.nozzle_offset_cali is False
    archive = await db_session.get(PrintArchive, first.archive_id)
    assert saved_slicer_ams_mapping(archive, printer.id, 1) == "[4]"
    assert saved_slicer_ams_mapping(archive, printer.id, 2) is None
    assert saved_slicer_ams_mapping(archive, other.id, 1) is None
    for row in protected:
        assert row.timelapse is False
        assert row.nozzle_offset_cali is True
        assert row.ams_mapping is None


def test_model_wide_queue_drops_rack_assignments_and_strict_mode_keeps_color_matching(tmp_path, test_engine):
    data = {
        "ams_mapping": [4],
        "nozzle_mapping": [16],
        "auto_bed_leveling": 2,
        "nozzle_offset_cali": 0,
    }
    model_wide = _queue_instance(tmp_path, test_engine)
    strict = _queue_instance(tmp_path, test_engine, target_printer_id=1, queue_force_color_match=True)
    assert model_wide._captured_queue_options(data) == {"nozzle_offset_cali": False}
    assert strict._captured_queue_options(data) == {"nozzle_offset_cali": False, "nozzle_mapping": "[16]"}
