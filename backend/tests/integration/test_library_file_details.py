"""User-authored library details survive moves and respect managed media bounds."""

import io

import pytest
from PIL import Image

from backend.app.models.library import LibraryFile


@pytest.fixture
async def detail_file(db_session, tmp_path, monkeypatch):
    from backend.app.core.config import settings

    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archive")
    path = tmp_path / "part.stl"
    path.write_bytes(b"solid part\nendsolid part")
    file = LibraryFile(
        filename=path.name,
        file_path=str(path),
        file_type="stl",
        file_size=path.stat().st_size,
        source_type="makerworld",
        source_url="https://makerworld.com/en/models/123",
    )
    db_session.add(file)
    await db_session.commit()
    return file


@pytest.mark.asyncio
@pytest.mark.integration
async def test_details_link_is_editable_and_distinct_from_import_provenance(async_client, detail_file):
    url = f"/api/v1/library/files/{detail_file.id}"
    response = await async_client.put(url, json={"notes": "Print two", "external_url": "https://example.org/design"})
    assert response.status_code == 200
    assert response.json()["external_url"] == "https://example.org/design"
    assert response.json()["source_url"] == "https://makerworld.com/en/models/123"
    assert response.json()["notes"] == "Print two"
    assert (await async_client.put(url, json={"external_url": "javascript:alert(1)"})).status_code == 422
    cleared = await async_client.put(url, json={"external_url": ""})
    assert cleared.json()["external_url"] is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_photo_lifecycle_survives_rename_and_trash_restore(async_client, detail_file):
    photo = io.BytesIO()
    Image.new("RGB", (3, 3), "red").save(photo, "PNG")
    url = f"/api/v1/library/files/{detail_file.id}"
    upload = await async_client.post(url + "/photos", files={"file": ("result.png", photo.getvalue(), "image/png")})
    assert upload.status_code == 200, upload.text
    name = upload.json()["filename"]
    assert (await async_client.get(url)).json()["photos"] == [name]
    assert (await async_client.get(url + "/photos/" + name)).content == photo.getvalue()
    await async_client.put(url, json={"filename": "renamed.stl"})
    assert (await async_client.get(url + "/photos/" + name)).status_code == 200
    await async_client.delete(url)
    assert (await async_client.get(url + "/photos/" + name)).status_code == 404
    restored = await async_client.post(f"/api/v1/library/trash/{detail_file.id}/restore")
    assert restored.status_code == 200, restored.text
    assert (await async_client.get(url + "/photos/" + name)).status_code == 200
    deleted = await async_client.delete(url + "/photos/" + name)
    assert deleted.status_code == 200
    assert deleted.json()["photos"] == []
    assert (await async_client.get(url + "/photos/" + name)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.integration
async def test_photo_upload_rejects_disguised_active_content(async_client, detail_file):
    response = await async_client.post(
        f"/api/v1/library/files/{detail_file.id}/photos",
        files={"file": ("result.png", b"<svg onload='alert(1)'/>", "image/png")},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.integration
async def test_photos_keep_owner_permission_with_media_tokens(async_client, db_session, detail_file):
    from backend.tests.integration.test_media_tokens import _admin_token, _make_user, _mint_media_token

    admin = await _admin_token(async_client, "libraryphoto")
    owner, owner_id = await _make_user(
        async_client, admin, username="photo_owner", permissions=["library:read_own", "library:update_own"]
    )
    other, _other_id = await _make_user(
        async_client, admin, username="photo_other", permissions=["library:read_own", "library:update_own"]
    )
    detail_file.created_by_id = owner_id
    await db_session.commit()
    photo = io.BytesIO()
    Image.new("RGB", (3, 3)).save(photo, "PNG")
    url = f"/api/v1/library/files/{detail_file.id}/photos"
    denied = await async_client.post(
        url, headers={"Authorization": f"Bearer {other}"}, files={"file": ("result.png", photo.getvalue(), "image/png")}
    )
    assert denied.status_code == 404
    uploaded = await async_client.post(
        url, headers={"Authorization": f"Bearer {owner}"}, files={"file": ("result.png", photo.getvalue(), "image/png")}
    )
    assert uploaded.status_code == 200, uploaded.text
    photo_url = url + "/" + uploaded.json()["filename"]
    token = await _mint_media_token(async_client, owner)
    other_token = await _mint_media_token(async_client, other)
    assert (await async_client.get(photo_url + "?token=" + token)).status_code == 200
    assert (await async_client.get(photo_url + "?token=" + other_token)).status_code == 404
    assert (await async_client.delete(photo_url, headers={"Authorization": f"Bearer {other}"})).status_code == 404
