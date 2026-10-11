"""Overrides survive concrete-printer dispatch and keep per-plate filtering."""

import zipfile

import pytest

from backend.tests.integration.test_print_queue_api import TestPrintQueueAPI as _QueueFixtures


class TestFixedPrinterOverrides:
    printer_factory = _QueueFixtures.printer_factory
    archive_factory = _QueueFixtures.archive_factory

    @pytest.mark.asyncio
    @pytest.mark.parametrize("target", ["fixed", "model"])
    async def test_plate_overrides_persist_on_both_target_kinds(
        self, async_client, printer_factory, archive_factory, tmp_path, target
    ):
        file = tmp_path / "overrides.3mf"
        with zipfile.ZipFile(file, "w") as zf:
            zf.writestr(
                "Metadata/slice_info.config",
                '<config><plate><metadata key="index" value="2"/><filament id="2" type="PLA" color="FF0000FF" used_g="10"/></plate></config>',
            )
        archive = await archive_factory(file_path=str(file))
        printer = await printer_factory(model="P1S")
        overrides = [
            {"slot_id": 1, "type": "ABS", "color": "#FFFFFF"},
            {"slot_id": 2, "type": "PETG", "color": "#000000"},
        ]
        selection = {"printer_id": printer.id} if target == "fixed" else {"target_model": "P1S"}
        response = await async_client.post(
            "/api/v1/queue/",
            json={"archive_id": archive.id, "plate_id": 2, "filament_overrides": overrides, **selection},
        )
        assert response.status_code == 200, response.text
        assert response.json()["filament_overrides"] == [overrides[1]]
        assert "PETG" in response.json()["required_filament_types"]
