"""Dispatch must address the plate present in a separately exported 3MF.

These regressions catch independent plate fallbacks in injection, expected
usage registration and the printer command. SQLite, ZIP editing and usage
selection stay real; only printer/network operations are replaced.
"""

import json
import zipfile
from pathlib import Path

import pytest

import backend.app.main as main
import backend.app.services.print_scheduler as scheduler_module
from backend.app.models.archive import PrintArchive
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.printer import Printer
from backend.app.models.settings import Settings
from backend.app.services.print_scheduler import PrintScheduler
from backend.app.utils.threemf_tools import extract_filament_usage_from_3mf


@pytest.fixture
async def dispatch_case(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler_module.settings, "base_dir", tmp_path)
    for name in (
        "_expected_prints",
        "_print_plate_ids",
        "_print_ams_mappings",
        "_expected_print_creators",
        "_expected_print_registered_at",
    ):
        monkeypatch.setattr(main, name, {})

    commands = []
    uploaded_members = []

    async def ftp_settings():
        return False, 0, 0, 1.0

    async def delete_remote(*args, **kwargs):
        return True

    async def upload_remote(_ip, _access_code, path, _remote_path, **kwargs):
        try:
            with zipfile.ZipFile(path) as zf:
                uploaded_members.append({name: zf.read(name) for name in zf.namelist()})
        except zipfile.BadZipFile:
            uploaded_members.append({})
        return True

    def start_print(printer_id, filename, **kwargs):
        commands.append({"printer_id": printer_id, "filename": filename, **kwargs})
        return True

    async def notify(*args, **kwargs):
        pass

    manager = scheduler_module.printer_manager
    monkeypatch.setattr(manager, "is_connected", lambda _printer_id: True)
    monkeypatch.setattr(manager, "get_status", lambda _printer_id: None)
    monkeypatch.setattr(manager, "start_print", start_print)
    monkeypatch.setattr(manager, "set_awaiting_plate_clear", lambda *args: None)
    monkeypatch.setattr(scheduler_module, "get_ftp_retry_settings", ftp_settings)
    monkeypatch.setattr(scheduler_module, "delete_file_async", delete_remote)
    monkeypatch.setattr(scheduler_module, "upload_file_async", upload_remote)
    monkeypatch.setattr(scheduler_module, "cache_3mf_download", lambda *args: None)
    monkeypatch.setattr(scheduler_module.notification_service, "on_queue_job_started", notify)
    from backend.app.services.mqtt_relay import mqtt_relay

    monkeypatch.setattr(mqtt_relay, "on_queue_job_started", notify)

    async def dispatch(names, *, plate_id=None, inject=False, malformed=False):
        source = tmp_path / "export.gcode.3mf"
        if malformed:
            source.write_bytes(b"not a ZIP archive")
        else:
            with zipfile.ZipFile(source, "w") as zf:
                for name in names:
                    zf.writestr(name, b"G28\nM400\n")
                zf.writestr(
                    "Metadata/slice_info.config",
                    '<config><plate><metadata key="index" value="1"/>'
                    '<filament id="1" used_g="80" type="PLA" color="#FF0000"/></plate>'
                    '<plate><metadata key="index" value="2"/>'
                    '<filament id="2" used_g="20" type="PLA" color="#00FF00"/></plate></config>',
                )

        printer = Printer(
            name="Plate selection printer",
            serial_number="PLATE-SELECTION",
            ip_address="127.0.0.1",
            access_code="test-code",
            model="H2C",
        )
        db_session.add(printer)
        await db_session.flush()
        archive = PrintArchive(
            printer_id=printer.id,
            filename=source.name,
            file_path=source.name,
            file_size=source.stat().st_size,
            status="completed",
        )
        db_session.add(archive)
        await db_session.flush()
        item = PrintQueueItem(
            printer_id=printer.id,
            archive_id=archive.id,
            status="pending",
            plate_id=plate_id,
            gcode_injection=inject,
            preheat_override="off",
            ams_mapping="[4, 5]",
            nozzle_mapping='[{"ams_id":0,"slot_id":2}]',
        )
        db_session.add(item)
        if inject:
            db_session.add(
                Settings(key="gcode_snippets", value=json.dumps({"H2C": {"start_gcode": "M117 Plate start"}}))
            )
        await db_session.commit()

        await PrintScheduler()._start_print(db_session, item)
        await db_session.refresh(item)
        return source, archive, item, commands, uploaded_members

    return dispatch


@pytest.mark.parametrize(
    ("names", "explicit", "expected"),
    [
        (["Metadata/plate_2.gcode"], None, 2),
        (["Metadata/plate_2.gcode"], 0, 2),
        (["Metadata/plate_2.gcode"], -1, 2),
        (["Metadata/plate_2.gcode", "Metadata/plate_1.gcode"], None, 1),
        (["Metadata/plate_10.gcode", "Metadata/plate_2.gcode"], None, 2),
        (["Metadata/plate_1.gcode.md5", "Metadata/plate_2.gcode"], None, 2),
        (["Metadata/plate_1.gcode", "Metadata/plate_2.gcode"], 2, 2),
        (["Metadata/plate_2.gcode"], 1, 1),
        (["Metadata/custom.gcode"], None, 1),
        (["3D/3dmodel.model"], None, 1),
        (["3D/3dmodel.model"], 3, 3),
    ],
    ids=(
        "single-original-plate",
        "zero-unset",
        "negative-unset",
        "zip-order-is-not-plate-order",
        "numeric-plate-order",
        "ignore-md5-sidecar",
        "explicit-multiplate",
        "missing-explicit-plate-is-not-redirected",
        "unnumbered-gcode",
        "unsliced-fallback",
        "unsliced-explicit-selection",
    ),
)
async def test_dispatch_and_usage_address_the_same_effective_plate(dispatch_case, names, explicit, expected):
    _, archive, item, commands, _ = await dispatch_case(names, plate_id=explicit)

    assert len(commands) == 1
    assert commands[0]["plate_id"] == expected
    assert main._get_start_plate_id(archive.id) == expected
    assert item.status == "printing"
    assert item.plate_id == explicit
    # Preserve slicer nozzle/rack choices and queue filament assignments.
    assert commands[0]["nozzle_mapping"] == '[{"ams_id":0,"slot_id":2}]'
    assert commands[0]["ams_mapping"] == [4, 5]


async def test_injection_and_usage_use_the_lowest_numbered_plate_before_upload_cleanup(dispatch_case):
    source, archive, _, commands, uploads = await dispatch_case(
        ["Metadata/plate_10.gcode", "Metadata/plate_2.gcode"], inject=True
    )

    assert uploads[0]["Metadata/plate_2.gcode"].startswith(b"M117 Plate start\n")
    assert uploads[0]["Metadata/plate_10.gcode"] == b"G28\nM400\n"
    assert commands[0]["plate_id"] == 2
    selected_usage = extract_filament_usage_from_3mf(source, main._get_start_plate_id(archive.id))
    assert selected_usage == [{"slot_id": 2, "used_g": 20.0, "type": "PLA", "color": "#00FF00"}]
    with zipfile.ZipFile(source) as zf:
        assert zf.read("Metadata/plate_2.gcode") == b"G28\nM400\n"


@pytest.mark.parametrize(("explicit", "expected"), [(None, 1), (3, 3)])
async def test_unreadable_archive_preserves_dispatch_fallback_and_explicit_selection(dispatch_case, explicit, expected):
    _, archive, _, commands, _ = await dispatch_case([], plate_id=explicit, malformed=True)

    assert commands[0]["plate_id"] == expected
    assert main._get_start_plate_id(archive.id) == expected
