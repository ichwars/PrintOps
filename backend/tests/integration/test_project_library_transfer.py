"""Project transfers preserve independent library folders and their access rules."""

import io
import json
import zipfile

import pytest
from sqlalchemy import select

from backend.app.api.routes.library import get_library_files_dir
from backend.app.models.library import LibraryFolder
from backend.tests.integration.test_media_tokens import _admin_token, _make_user

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def accounts(async_client):
    token = await _admin_token(async_client, "_project_transfer")
    permissions = ["projects:read", "projects:create", "library:read_own", "library:upload"]
    reader, _ = await _make_user(async_client, token, username="transfer_reader", permissions=permissions)
    no_library, _ = await _make_user(
        async_client, token, username="transfer_no_library", permissions=["projects:read", "projects:create"]
    )
    return tuple({"Authorization": f"Bearer {jwt}"} for jwt in (token, reader, no_library))


def _zip(folder_name, entries):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("project.json", json.dumps({"name": "Imported", "linked_folders": [{"name": folder_name}]}))
        for filename, content in entries.items():
            archive.writestr(f"files/{folder_name}/{filename}", content)
    return {"file": ("project.zip", payload.getvalue(), "application/zip")}


async def _project_folders(client, project_id, headers):
    response = await client.get(f"/api/v1/library/folders/by-project/{project_id}", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_json_import_does_not_relink_an_existing_folder_without_update_all(async_client, db_session, accounts):
    admin, _, creator = accounts
    original = LibraryFolder(name="Models")
    db_session.add(original)
    await db_session.commit()
    payload = {"name": "New project", "linked_folders": [{"name": "Models"}]}

    response = await async_client.post("/api/v1/projects/import", headers=creator, json=payload)
    assert response.status_code == 200, response.text
    project_id = response.json()["id"]
    linked = await _project_folders(async_client, project_id, admin)
    assert len(linked) == 1 and linked[0]["id"] != original.id
    assert (await db_session.scalar(select(LibraryFolder.project_id).where(LibraryFolder.id == original.id))) is None

    response = await async_client.post("/api/v1/projects/import", headers=admin, json=payload)
    assert response.status_code == 200, response.text
    linked = await _project_folders(async_client, response.json()["id"], admin)
    assert [folder["id"] for folder in linked] == [original.id]


async def test_zip_import_preserves_the_bytes_and_ownership_of_two_same_named_imports(async_client, accounts):
    admin, reader, _ = accounts
    created = []
    for content in (b"First version", b"Second version"):
        response = await async_client.post(
            "/api/v1/projects/import/file",
            headers=reader,
            files=_zip("Models", {"sub/part.txt": content}),
        )
        assert response.status_code == 200, response.text
        folder = (await _project_folders(async_client, response.json()["id"], admin))[0]
        response = await async_client.get("/api/v1/library/files", headers=reader, params={"folder_id": folder["id"]})
        assert response.status_code == 200
        files = response.json()
        assert len(files) == 1 and files[0]["filename"] == "sub/part.txt"
        created.append((folder["id"], files[0]["id"], content))

    assert created[0][0] != created[1][0]
    for _, file_id, content in created:
        response = await async_client.get(f"/api/v1/library/files/{file_id}/download", headers=reader)
        assert response.status_code == 200
        assert response.content == content


async def test_export_filters_project_library_metadata_and_bytes(async_client, accounts):
    admin, reader, no_library = accounts
    project = await async_client.post("/api/v1/projects/import", headers=admin, json={"name": "Transfer project"})
    assert project.status_code == 200, project.text
    project_id = project.json()["id"]

    async def upload(folder_name, filename, headers):
        folders = await _project_folders(async_client, project_id, admin)
        folder = next((entry for entry in folders if entry["name"] == folder_name), None)
        if folder is None:
            response = await async_client.post(
                "/api/v1/library/folders/", headers=admin, json={"name": folder_name, "project_id": project_id}
            )
            assert response.status_code == 200, response.text
            folder = response.json()
        response = await async_client.post(
            "/api/v1/library/files",
            headers=headers,
            params={"folder_id": folder["id"]},
            files={"file": (filename, filename.encode(), "text/plain")},
        )
        assert response.status_code == 200, response.text

    await upload("Other", "secret.txt", admin)
    await upload("Shared", "theirs.txt", admin)
    await upload("Shared", "mine.txt", reader)
    endpoint = f"/api/v1/projects/{project_id}/export"
    for headers, expected in (
        (admin, {"Other": ["secret.txt"], "Shared": ["mine.txt", "theirs.txt"]}),
        (reader, {"Shared": ["mine.txt"]}),
        (no_library, {}),
    ):
        response = await async_client.get(endpoint, headers=headers, params={"format": "json"})
        assert response.status_code == 200
        assert {
            folder["name"]: [file["filename"] for file in folder["files"]]
            for folder in response.json()["linked_folders"]
        } == expected
        response = await async_client.get(endpoint, headers=headers)
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            expected_entries = {
                f"files/{folder}/{name}": name.encode() for folder, names in expected.items() for name in names
            }
            assert {
                name: archive.read(name) for name in archive.namelist() if name != "project.json"
            } == expected_entries


async def test_zip_import_cleans_up_files_if_a_later_entry_is_invalid(async_client):
    library_files = get_library_files_dir()
    before = set(library_files.iterdir())
    response = await async_client.post(
        "/api/v1/projects/import/file",
        files=_zip("Models", {"part.txt": b"will be removed", "../../../escape.txt": b"invalid"}),
    )
    assert response.status_code == 400
    assert set(library_files.iterdir()) == before
