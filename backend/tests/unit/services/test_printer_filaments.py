from __future__ import annotations

from types import SimpleNamespace

from backend.app.services.printer_filaments import collect_available_filaments


def test_collect_available_filaments_deduplicates_by_rgb_sub_brand_and_extruder():
    printers = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
    statuses = {
        1: SimpleNamespace(
            raw_data={
                "ams_extruder_map": {"0": 1},
                "ams": [
                    {
                        "id": 0,
                        "tray": [
                            {
                                "tray_type": "PLA",
                                "tray_color": "00000000",
                                "tray_info_idx": "GFA00",
                                "tray_sub_brands": "Basic",
                            },
                            {
                                "tray_type": "PLA",
                                "tray_color": "#000000FF",
                                "tray_sub_brands": "Basic",
                            },
                        ],
                    }
                ],
                "vt_tray": [{"id": 254, "tray_type": "PETG", "tray_color": "112233", "tray_sub_brands": "HF"}],
            }
        ),
        2: SimpleNamespace(
            raw_data={
                "ams_extruder_map": {"0": 0},
                "ams": [{"id": 0, "tray": [{"tray_type": "PLA", "tray_color": "000000", "tray_sub_brands": "Basic"}]}],
            }
        ),
    }

    result = collect_available_filaments(printers, statuses.get)

    assert result == [
        {
            "type": "PLA",
            "color": "#00000000",
            "tray_info_idx": "GFA00",
            "tray_sub_brands": "Basic",
            "extruder_id": 1,
        },
        {
            "type": "PETG",
            "color": "#112233",
            "tray_info_idx": "",
            "tray_sub_brands": "HF",
            "extruder_id": 1,
        },
        {
            "type": "PLA",
            "color": "#000000",
            "tray_info_idx": "",
            "tray_sub_brands": "Basic",
            "extruder_id": 0,
        },
    ]
