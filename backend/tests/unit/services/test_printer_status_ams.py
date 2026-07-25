from __future__ import annotations

from types import SimpleNamespace

from backend.app.services.printer_status_ams import build_ams_units, build_kprofile_map, build_virtual_trays


def test_build_ams_units_applies_kprofile_and_drying_fallback():
    raw_data = {
        "ams": [
            {
                "id": 0,
                "humidity_raw": "42",
                "temp": "29",
                "sn": "AMS123",
                "tray": [
                    {
                        "id": 0,
                        "tray_type": "PLA",
                        "tray_color": "FF0000FF",
                        "tray_info_idx": "GFL99",
                        "tray_sub_brands": "Basic",
                        "cali_idx": 7,
                        "tag_uid": "0000000000000000",
                        "tray_uuid": "00000000000000000000000000000000",
                        "drying_temp": "55",
                    }
                ],
            }
        ]
    }
    kprofile_map = build_kprofile_map([SimpleNamespace(slot_id=7, k_value="0.031")])

    ams_units, ams_exists = build_ams_units(raw_data, kprofile_map, {})

    assert ams_exists is True
    assert len(ams_units) == 1
    ams = ams_units[0]
    assert ams.humidity == 42
    assert ams.serial_number == "AMS123"
    assert ams.dry_target_temp == 55
    assert ams.dry_filament == "PLA"
    assert ams.tray[0].k == 0.031
    assert ams.tray[0].tag_uid is None
    assert ams.tray[0].tray_uuid is None


def test_build_virtual_trays_applies_kprofile_and_keeps_valid_tags():
    raw_data = {
        "vt_tray": [
            {
                "id": 254,
                "tray_type": "PETG",
                "tray_color": "112233FF",
                "cali_idx": 3,
                "tag_uid": "ABCDEF",
                "tray_uuid": "123456",
            }
        ]
    }

    trays = build_virtual_trays(raw_data, {3: 0.022})

    assert len(trays) == 1
    assert trays[0].id == 254
    assert trays[0].k == 0.022
    assert trays[0].tag_uid == "ABCDEF"
    assert trays[0].tray_uuid == "123456"
