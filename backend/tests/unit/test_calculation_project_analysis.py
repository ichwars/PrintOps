from decimal import Decimal
from zipfile import ZIP_DEFLATED, ZipFile

from backend.app.services.calculation_estimator import BoundsMm, EstimatorSettings, PlateGeometry, estimate_plate
from backend.app.services.calculation_project import analyze_project_file


def test_analyzer_returns_per_plate_metadata_and_thumbnails(tmp_path):
    path = tmp_path / "multi.3mf"
    slice_info = """<config>
      <plate><metadata key="index" value="1"/><metadata key="name" value="Links"/><metadata key="prediction" value="3600"/><object id="10"/><object id="11"/><filament id="1" used_g="12.5" type="PETG" color="#fff"/></plate>
      <plate><metadata key="index" value="2"/><metadata key="name" value="Rechts"/><metadata key="prediction" value="1800"/><object id="12"/><filament id="1" used_g="5" type="PETG" color="#fff"/></plate>
    </config>"""
    model_settings = """<config><plate><metadata key="plater_id" value="1"/></plate><plate><metadata key="plater_id" value="2"/></plate></config>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("Metadata/model_settings.config", model_settings)
        archive.writestr("Metadata/slice_info.config", slice_info)
        archive.writestr("Metadata/project_settings.config", '{"printer_model":"Bambu Lab P2S"}')
        archive.writestr("Metadata/plate_1.png", b"\x89PNG\r\n\x1a\npreview")

    result = analyze_project_file(path)

    assert result.printer_metadata["printer_model"] == "Bambu Lab P2S"
    assert [(plate.plate_index, plate.name, plate.object_count) for plate in result.plates] == [
        (1, "Links", 2),
        (2, "Rechts", 1),
    ]
    assert result.plates[0].detected_grams == Decimal("12.5")
    assert result.plates[0].detected_hours == Decimal("1")
    assert result.plates[0].thumbnail_bytes.startswith(b"\x89PNG")
    assert result.plates[1].thumbnail_bytes is None
    assert result.plates[0].stable_key != result.plates[1].stable_key


def test_forgedesk_geometry_estimate_is_explicit_and_deterministic():
    result = estimate_plate(
        PlateGeometry(
            object_count=2,
            triangle_count=100,
            volume_cm3=Decimal("10"),
            bounds_mm=BoundsMm(Decimal("20"), Decimal("30"), Decimal("10")),
        ),
        EstimatorSettings(
            density_g_cm3=Decimal("1.24"),
            infill_percent=Decimal("20"),
            layer_height_mm=Decimal("0.2"),
            nozzle_mm=Decimal("0.4"),
            speed_mm_s=Decimal("60"),
            wall_lines=2,
        ),
        "PLA",
    )

    assert result.material_grams is not None and result.material_grams > 0
    assert result.print_hours is not None and result.print_hours > 0
    assert "Geometry estimate" in result.warnings
