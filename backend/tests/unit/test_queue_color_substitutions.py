"""Compare the effective filament and the loaded tray without inventing colours."""

import json
from types import SimpleNamespace
from unittest.mock import patch

from backend.app.models.print_queue import PrintQueueItem
from backend.app.services.print_scheduler import PrintScheduler


def test_dispatch_color_notes_compare_actual_plate_and_ignore_missing_or_nearby_colors(tmp_path):
    scheduler = PrintScheduler()
    item = PrintQueueItem(
        id=21, use_ams=True, filament_overrides='[{"slot_id": 1, "type": "PETG", "color": "#FFFFFF"}]'
    )
    state = SimpleNamespace(
        raw_data={
            "ams": [
                {
                    "id": 0,
                    "tray": [
                        {"id": 0, "tray_type": "PETG", "tray_color": "FF0000FF"},
                        {"id": 1, "tray_type": "PLA", "tray_color": "FF0010FF"},
                        {"id": 2, "tray_type": "PLA", "tray_color": "FFFFFF00", "exists": False},
                        {"id": 3, "tray_type": "PLA", "tray_color": "00000000"},
                    ],
                }
            ],
        }
    )
    requirements = [{"slot_id": slot, "type": "PLA", "color": "#FF0000"} for slot in range(1, 5)]
    path = tmp_path / "multi.3mf"
    with patch(
        "backend.app.services.filament_requirements.extract_filament_requirements", return_value=requirements
    ) as extract:
        encoded = scheduler._dispatch_color_substitutions(item, path, 2, [0, 1, 2, 3], state)
    extract.assert_called_once_with(path, plate_id=2)
    assert json.loads(encoded) == [{"slot_id": 1, "type": "PETG", "wanted": "#FFFFFF", "got": "#FF0000", "tray": 0}]
