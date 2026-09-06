"""Plate-scoped archive metadata updates shared by dispatch paths."""

from pathlib import Path

from backend.app.services.archive import ThreeMFParser


def refresh_archive_plate_metadata(archive, file_path: Path, plate_id: int) -> None:
    """Replace stale cross-plate fields with evidence from the selected plate."""
    metadata = ThreeMFParser(file_path, plate_number=plate_id).parse()
    archive.plate_id = plate_id
    for field in ("layer_height", "bed_type", "bed_temperature"):
        setattr(archive, field, metadata.get(field))
