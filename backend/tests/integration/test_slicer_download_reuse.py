"""Desktop slicers can fetch their resource-bound download URL more than once."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from backend.app.models.auth_ephemeral import AuthEphemeralToken
from backend.app.models.library import LibraryFile


@pytest.fixture
async def slicer_resources(async_client, db_session, tmp_path, printer_factory, archive_factory):
    await async_client.post(
        "/api/v1/auth/setup",
        json={"auth_enabled": True, "admin_username": "sliceradmin", "admin_password": "AdminPass1!"},
    )
    login = await async_client.post("/api/v1/auth/login", json={"username": "sliceradmin", "password": "AdminPass1!"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    path = tmp_path / "source.3mf"
    path.write_bytes(b"test model content")
    library = LibraryFile(filename="model.3mf", file_path=str(path), file_type="3mf", file_size=18)
    db_session.add(library)
    printer = await printer_factory()
    archive = await archive_factory(printer.id, file_path=str(path), source_3mf_path=str(path))
    await db_session.commit()
    return {
        "library": (f"/api/v1/library/files/{library.id}/slicer-token", f"/api/v1/library/files/{library.id}/dl"),
        "archive": (f"/api/v1/archives/{archive.id}/slicer-token", f"/api/v1/archives/{archive.id}/dl"),
        "source": (f"/api/v1/archives/{archive.id}/source-slicer-token", f"/api/v1/archives/{archive.id}/source-dl"),
    }, headers


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.parametrize("kind", ["library", "archive", "source"])
async def test_protocol_url_allows_repeated_fetches_without_auth_headers(async_client, slicer_resources, kind):
    resources, headers = slicer_resources
    mint_url, download_url = resources[kind]
    minted = await async_client.post(mint_url, headers=headers)
    assert minted.status_code == 200
    url = f"{download_url}/{minted.json()['token']}/model.3mf"

    for _attempt in range(3):
        response = await async_client.get(url)
        assert response.status_code == 200
        assert response.content == b"test model content"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reusable_token_still_expires(async_client, db_session, slicer_resources):
    resources, headers = slicer_resources
    mint_url, download_url = resources["library"]
    token = (await async_client.post(mint_url, headers=headers)).json()["token"]
    await db_session.execute(
        update(AuthEphemeralToken)
        .where(AuthEphemeralToken.token == token)
        .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    )
    await db_session.commit()

    response = await async_client.get(f"{download_url}/{token}/model.3mf")

    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.integration
async def test_wrong_resource_cannot_redeem_or_consume_protocol_token(async_client, slicer_resources):
    resources, headers = slicer_resources
    mint_url, download_url = resources["library"]
    token = (await async_client.post(mint_url, headers=headers)).json()["token"]
    _archive_mint, archive_download = resources["archive"]

    wrong = await async_client.get(f"{archive_download}/{token}/model.3mf")
    assert wrong.status_code == 403
    assert (await async_client.get(f"{download_url}/{token}/model.3mf")).status_code == 200
    assert (await async_client.get(f"{download_url}/{token}/model.3mf")).status_code == 200
