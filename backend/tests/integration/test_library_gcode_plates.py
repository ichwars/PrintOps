"""Exercise actual library plate selection through the authenticated API."""

import zipfile

import pytest

from backend.app.models.library import LibraryFile


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize(
    ("plate", "status", "expected"),
    [
        (None, 200, b"first plate"),
        ("1", 200, b"first plate"),
        ("2", 200, b"second plate"),
        ("3", 404, None),
        ("0", 400, None),
        ("-1", 400, None),
        ("2x", 422, None),
    ],
)
async def test_requested_library_plate_is_never_silently_replaced(
    async_client,
    db_session,
    tmp_path,
    plate,
    status,
    expected,
):
    path = tmp_path / "multi.gcode.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/plate_2.gcode", b"second plate")
        archive.writestr("Metadata/plate_01.gcode", b"first plate")
    file = LibraryFile(filename=path.name, file_path=str(path), file_type="gcode.3mf", file_size=path.stat().st_size)
    db_session.add(file)
    await db_session.commit()
    query = "" if plate is None else f"?plate={plate}"
    response = await async_client.get(f"/api/v1/library/files/{file.id}/gcode{query}")
    assert response.status_code == status
    if expected is not None:
        assert response.content == expected


@pytest.mark.asyncio
@pytest.mark.integration
async def test_plain_gcode_has_only_one_plate(async_client, db_session, tmp_path):
    path = tmp_path / "single.gcode"
    path.write_bytes(b"G28\n")
    file = LibraryFile(filename=path.name, file_path=str(path), file_type="gcode", file_size=4)
    db_session.add(file)
    await db_session.commit()
    for plate, expected_status in [(1, 200), (2, 404)]:
        response = await async_client.get(f"/api/v1/library/files/{file.id}/gcode?plate={plate}")
        assert response.status_code == expected_status


@pytest.mark.asyncio
@pytest.mark.integration
async def test_archive_default_uses_plate_order_not_zip_order(
    async_client,
    archive_factory,
    printer_factory,
    monkeypatch,
    tmp_path,
):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "base_dir", tmp_path)
    path = tmp_path / "multi.3mf"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Metadata/plate_2.gcode", b"second plate")
        archive.writestr("Metadata/plate_01.gcode", b"first plate")
    printer = await printer_factory()
    archive = await archive_factory(printer.id, filename=path.name, file_path=path.name)
    response = await async_client.get(f"/api/v1/archives/{archive.id}/gcode")
    assert response.status_code == 200
    assert response.content == b"first plate"
