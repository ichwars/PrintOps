from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.app.core.config import settings as app_settings
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.calculation import Calculation


def _project_file() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "Metadata/slice_info.config",
            '<config><plate><metadata key="index" value="1"/><metadata key="name" value="A"/><object id="1"/></plate><plate><metadata key="index" value="2"/><metadata key="name" value="B"/><object id="2"/></plate></config>',
        )
        archive.writestr(
            "Metadata/model_settings.config",
            '<config><metadata key="plater_id" value="1"/><metadata key="plater_id" value="2"/></config>',
        )
        archive.writestr("Metadata/plate_1.png", b"\x89PNG\r\n\x1a\npreview")
    return output.getvalue()


def test_project_plate_thumbnail_uses_stream_token_gate():
    """An img request cannot attach the normal bearer authorization header."""
    from fastapi.routing import APIRoute

    from backend.app.api.routes.calculation_projects import router
    from backend.app.core.auth import require_camera_stream_token_if_auth_enabled

    thumbnail_get = next(
        (
            route
            for route in router.routes
            if isinstance(route, APIRoute) and route.path.endswith("/thumbnail") and "GET" in route.methods
        ),
        None,
    )
    assert thumbnail_get is not None, "project plate thumbnail route missing"
    expected_qualname = require_camera_stream_token_if_auth_enabled().__qualname__
    gate_qualnames = [dependency.call.__qualname__ for dependency in thumbnail_get.dependant.dependencies]
    assert expected_qualname in gate_qualnames, gate_qualnames


@pytest.mark.asyncio
async def test_project_file_upload_persists_revisions_and_plate_preview(
    async_client, db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(app_settings, "base_dir", tmp_path)
    profile = BusinessProfile(
        name="Test",
        legal_name="Test GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    calculation = Calculation(
        business_profile_id=profile.id,
        title="Projektdatei",
        request_kind="single",
        quantity=1,
        currency="EUR",
    )
    db_session.add(calculation)
    await db_session.commit()

    first = await async_client.post(
        f"/api/v1/calculations/{calculation.id}/project-files",
        files={"file": ("project.3mf", _project_file(), "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")},
    )
    second = await async_client.post(
        f"/api/v1/calculations/{calculation.id}/project-files",
        files={"file": ("project-v2.3mf", _project_file(), "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert [
        item["revision_number"]
        for item in (await async_client.get(f"/api/v1/calculations/{calculation.id}/project-files")).json()
    ] == [1, 2]
    assert [(plate["plate_index"], plate["name"]) for plate in first.json()["plates"]] == [(1, "A"), (2, "B")]
    plate_id = first.json()["plates"][0]["id"]
    preview = await async_client.get(
        f"/api/v1/calculations/project-files/{first.json()['id']}/plates/{plate_id}/thumbnail"
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/png"
