"""One generic filament catalog shared by runtime Python and frontend pickers."""

import json
from pathlib import Path

GENERIC_FILAMENT_CATALOG: dict[str, str] = json.loads(
    (Path(__file__).resolve().parents[1] / "resources" / "filaments" / "generic_ids.json").read_text(encoding="utf-8")
)
GENERIC_FILAMENT_IDS = {material.upper(): filament_id for material, filament_id in GENERIC_FILAMENT_CATALOG.items()}
GENERIC_FILAMENT_IDS["NYLON"] = GENERIC_FILAMENT_IDS["PA"]
