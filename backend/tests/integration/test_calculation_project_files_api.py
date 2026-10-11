import shutil
from decimal import Decimal
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from backend.app.core.config import settings as app_settings
from backend.app.models.business_profile import BusinessProfile
from backend.app.models.calculation import Calculation
from backend.app.models.calculation_project import CalculationProjectFile
from backend.app.models.calculation_slice import CalculationSliceResult
from backend.app.services.calculation_slicing import build_cache_key


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


@pytest.mark.asyncio
async def test_project_plate_thumbnail_requires_calculation_permission(async_client):
    from backend.tests.integration.test_media_tokens import _admin_token, _make_user, _mint_media_token

    admin = await _admin_token(async_client, "_calc_plate")
    jwt, _ = await _make_user(async_client, admin, username="calcreader", permissions=["calculations:read"])
    token = await _mint_media_token(async_client, jwt)
    # An authorized user reaches the row lookup, even without camera:view.
    response = await async_client.get(f"/api/v1/calculations/project-files/1/plates/1/thumbnail?token={token}")
    assert response.status_code == 404
    jwt, _ = await _make_user(async_client, admin, username="otherreader", permissions=["projects:read"])
    token = await _mint_media_token(async_client, jwt)
    response = await async_client.get(f"/api/v1/calculations/project-files/1/plates/1/thumbnail?token={token}")
    assert response.status_code == 403


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


@pytest.mark.asyncio
async def test_slice_cache_result_is_mapped_to_requested_plate(async_client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "base_dir", tmp_path)
    profile = BusinessProfile(
        name="Slice cache",
        legal_name="Slice cache GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    calculation = Calculation(business_profile=profile, title="Cache plates", currency="EUR")
    db_session.add(calculation)
    await db_session.commit()
    first = await async_client.post(
        f"/api/v1/calculations/{calculation.id}/project-files",
        files={"file": ("first.3mf", _project_file(), "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")},
    )
    second = await async_client.post(
        f"/api/v1/calculations/{calculation.id}/project-files",
        files={"file": ("second.3mf", _project_file(), "application/vnd.ms-package.3dmanufacturing-3dmodel+xml")},
    )
    first_plate = first.json()["plates"][0]
    second_plate = second.json()["plates"][0]
    key = build_cache_key(
        file_sha256=first.json()["sha256"],
        plate_index=first_plate["plate_index"],
        profiles={
            "slicer": "bambu_studio",
            "mode": "embedded",
            "printer": None,
            "process": None,
            "filament": None,
        },
    )
    db_session.add(
        CalculationSliceResult(
            project_plate_id=first_plate["id"],
            cache_key=key,
            status="completed",
            source="slicer",
            print_hours=Decimal("1"),
            material_grams=Decimal("10"),
            warnings=[],
            profile_snapshot={},
        )
    )
    await db_session.commit()

    response = await async_client.post(
        f"/api/v1/calculations/project-files/{second.json()['id']}/slice",
        json={"plate_ids": [second_plate["id"]]},
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["project_plate_id"] == second_plate["id"]


@pytest.mark.asyncio
async def test_delete_draft_removes_project_file_rows_and_storage(async_client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "base_dir", tmp_path)
    profile = BusinessProfile(
        name="Delete draft issuer",
        legal_name="Delete draft issuer GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    calculation = Calculation(
        business_profile_id=profile.id,
        title="Temporary 3MF draft",
        request_kind="single",
        quantity=1,
        currency="EUR",
    )
    db_session.add(calculation)
    await db_session.commit()
    calculation_id = calculation.id

    uploaded = await async_client.post(
        f"/api/v1/calculations/{calculation_id}/project-files",
        files={
            "file": (
                "project.3mf",
                _project_file(),
                "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
            )
        },
    )
    assert uploaded.status_code == 201
    project_file_id = uploaded.json()["id"]
    storage_dir = tmp_path / "calculations" / str(calculation_id)
    assert storage_dir.is_dir()

    deleted = await async_client.delete(f"/api/v1/calculations/{calculation_id}", params={"expected_version": 1})

    assert deleted.status_code == 204
    db_session.expire_all()
    assert await db_session.get(Calculation, calculation_id) is None
    assert await db_session.get(CalculationProjectFile, project_file_id) is None
    assert not storage_dir.exists()


@pytest.mark.asyncio
async def test_delete_draft_keeps_database_result_when_storage_cleanup_fails(
    async_client, db_session, tmp_path, monkeypatch, caplog
):
    monkeypatch.setattr(app_settings, "base_dir", tmp_path)
    profile = BusinessProfile(
        name="Cleanup failure issuer",
        legal_name="Cleanup failure issuer GmbH",
        country_code="DE",
        default_currency="EUR",
    )
    db_session.add(profile)
    await db_session.flush()
    calculation = Calculation(
        business_profile_id=profile.id,
        title="Cleanup failure draft",
        request_kind="single",
        quantity=1,
        currency="EUR",
    )
    db_session.add(calculation)
    await db_session.commit()
    calculation_id = calculation.id
    storage_dir = tmp_path / "calculations" / str(calculation_id)
    storage_dir.mkdir(parents=True)
    (storage_dir / "leftover.3mf").write_bytes(b"3mf")

    def fail_cleanup(_path):
        raise OSError("filesystem busy")

    monkeypatch.setattr(shutil, "rmtree", fail_cleanup)
    deleted = await async_client.delete(f"/api/v1/calculations/{calculation_id}", params={"expected_version": 1})

    assert deleted.status_code == 204
    db_session.expire_all()
    assert await db_session.get(Calculation, calculation_id) is None
    assert storage_dir.exists()
    assert "Failed to remove calculation storage directory" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("preferred", ["bambu_studio", "orcaslicer"])
async def test_calculation_slice_sanitizes_sidecar_bytes_and_retains_source_identity(
    preferred, async_client, db_session, tmp_path, monkeypatch
):
    import hashlib
    import json
    from email import policy
    from email.parser import BytesParser

    import httpx

    from backend.app.models.settings import Settings
    from backend.app.services import slicer_api
    from backend.tests.integration.test_media_tokens import _admin_token, _make_user

    monkeypatch.setattr(app_settings, "base_dir", tmp_path)
    profile = BusinessProfile(
        name="MakerWorld", legal_name="MakerWorld GmbH", country_code="DE", default_currency="EUR"
    )
    calculation = Calculation(business_profile=profile, title="Embedded profiles", currency="EUR")
    db_session.add_all([calculation, Settings(key="preferred_slicer", value=preferred)])
    await db_session.commit()
    settings_payload = {
        "wall_filament": "0",
        "sparse_infill_filament": 0,
        "solid_infill_filament": "0",
        "support_filament": "0",
        "support_interface_filament": 0,
        "layer_height": "0.2",
        "z_offset": "-1",
    }
    output = BytesIO()
    with ZipFile(BytesIO(_project_file())) as source, ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for item in source.infolist():
            archive.writestr(item, source.read(item))
        archive.writestr("Metadata/project_settings.config", json.dumps(settings_payload))
    original = output.getvalue()
    observed = []

    def sidecar(request):
        assert request.method == "POST"
        assert request.url.path == "/slice"
        headers = f"Content-Type: {request.headers['content-type']}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        message = BytesParser(policy=policy.default).parsebytes(headers + request.content)
        part = next(
            part for part in message.iter_parts() if part.get_param("name", header="content-disposition") == "file"
        )
        with ZipFile(BytesIO(part.get_payload(decode=True))) as archive:
            observed.append(json.loads(archive.read("Metadata/project_settings.config")))
            assert archive.read("Metadata/model_settings.config") == (
                b'<config><metadata key="plater_id" value="1"/><metadata key="plater_id" value="2"/></config>'
            )
        return httpx.Response(
            200, content=b"; sliced G-code", headers={"X-Print-Time-Seconds": "7200", "X-Filament-Used-G": "12.5"}
        )

    admin = await _admin_token(async_client, "calc_sanitize")
    updater, _ = await _make_user(
        async_client, admin, username="calc_sanitize_updater", permissions=["calculations:update"]
    )
    reader, _ = await _make_user(
        async_client, admin, username="calc_sanitize_reader", permissions=["calculations:read"]
    )
    update_headers = {"Authorization": f"Bearer {updater}"}
    uploaded = await async_client.post(
        f"/api/v1/calculations/{calculation.id}/project-files",
        headers=update_headers,
        files={"file": ("makerworld.3mf", original, "model/3mf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]
    selected = [plate["id"] for plate in uploaded.json()["plates"]]
    url = f"/api/v1/calculations/project-files/{file_id}/slice"
    async with httpx.AsyncClient(transport=httpx.MockTransport(sidecar)) as client:
        monkeypatch.setattr(slicer_api, "_shared_http_client", client)
        denied = await async_client.post(
            url, json={"plate_ids": selected}, headers={"Authorization": f"Bearer {reader}"}
        )
        assert denied.status_code == 403
        assert observed == []
        response = await async_client.post(url, json={"plate_ids": selected}, headers=update_headers)
    assert response.status_code == 200, response.text
    assert len(observed) == 2
    assert (
        observed
        == [
            {
                "support_filament": "0",
                "support_interface_filament": 0,
                "layer_height": "0.2",
                "z_offset": "-1",
            }
        ]
        * 2
    )
    assert [Decimal(item["print_hours"]) for item in response.json()] == [Decimal("2")] * 2
    stored = await db_session.get(CalculationProjectFile, file_id)
    assert uploaded.json()["sha256"] == stored.sha256 == hashlib.sha256(original).hexdigest()
    assert (tmp_path / stored.stored_path).read_bytes() == original
