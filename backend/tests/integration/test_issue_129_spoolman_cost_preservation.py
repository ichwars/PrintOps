from unittest.mock import MagicMock, patch

import pytest

from backend.app.models.settings import Settings


@pytest.mark.asyncio
@pytest.mark.integration
async def test_recalculate_preserves_marked_spoolman_actual(
    async_client,
    archive_factory,
    printer_factory,
    db_session,
):
    db_session.add(Settings(key="default_filament_cost", value="25"))
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id,
        cost=4.0,
        filament_used_grams=100.0,
        filament_type="PLA",
        extra_data={"cost_source": "spoolman"},
    )
    await db_session.commit()

    response = await async_client.post("/api/v1/archives/recalculate-costs")

    assert response.status_code == 200
    await db_session.refresh(archive)
    assert archive.cost == pytest.approx(4.0)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_recalculate_still_updates_unmarked_estimates(
    async_client,
    archive_factory,
    printer_factory,
    db_session,
):
    db_session.add(Settings(key="default_filament_cost", value="25"))
    printer = await printer_factory()
    archive = await archive_factory(
        printer.id,
        cost=999.0,
        filament_used_grams=100.0,
        filament_type="PLA",
    )
    await db_session.commit()

    response = await async_client.post("/api/v1/archives/recalculate-costs")

    assert response.status_code == 200
    await db_session.refresh(archive)
    assert archive.cost == pytest.approx(2.5)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rescan_preserves_marked_spoolman_actual(
    async_client,
    archive_factory,
    printer_factory,
    db_session,
    tmp_path,
    monkeypatch,
):
    db_session.add(Settings(key="default_filament_cost", value="25"))
    printer = await printer_factory()
    source = tmp_path / "priced.gcode.3mf"
    source.write_bytes(b"test")
    archive = await archive_factory(
        printer.id,
        file_path=source.name,
        cost=4.0,
        filament_used_grams=100.0,
        filament_type="PLA",
        extra_data={"cost_source": "spoolman"},
    )
    await db_session.commit()

    from backend.app.api.routes import archives as archives_route

    monkeypatch.setattr(archives_route.settings, "base_dir", tmp_path)
    parser = MagicMock()
    parser.parse.return_value = {"filament_used_grams": 100.0, "filament_type": "PLA"}
    with patch("backend.app.services.archive.ThreeMFParser", return_value=parser):
        response = await async_client.post(f"/api/v1/archives/{archive.id}/rescan")

    assert response.status_code == 200
    await db_session.refresh(archive)
    assert archive.cost == pytest.approx(4.0)
