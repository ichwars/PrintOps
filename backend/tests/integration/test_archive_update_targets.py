"""Archive writes validate destination references before mutating files or records."""

import pytest
from sqlalchemy import select

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.archive import PrintArchive
from backend.app.models.group import Group
from backend.app.models.project import Project
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_archive_destination_obeys_both_account_and_key_printer_grants(
    async_client, db_session, printer_factory, archive_factory
):
    await _setup_admin(async_client)
    first, team, other = await printer_factory(), await printer_factory(), await printer_factory()
    role = Group(
        name="Archive editors", permissions=[Permission.ARCHIVES_UPDATE_ALL.value, Permission.ARCHIVES_CREATE.value]
    )
    editor = User(username="archive-editor", groups=[role], allowed_printer_ids=[first.id, team.id])
    db_session.add(editor)
    await db_session.flush()
    token, key_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="Archive tool",
            key_hash=key_hash,
            key_prefix=prefix,
            user_id=editor.id,
            printer_ids=[first.id, other.id],
        )
    )
    await db_session.commit()
    archive = await archive_factory(first.id)
    endpoint = f"/api/v1/archives/{archive.id}"
    bearer = {"Authorization": f"Bearer {create_access_token({'sub': editor.username})}"}
    key = {"X-API-Key": "invalid", "Authorization": f"Bearer {token}"}

    for headers, printer in ((bearer, other), (key, other), (key, team)):
        response = await async_client.patch(
            endpoint, headers=headers, json={"printer_id": printer.id, "notes": "Denied"}
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Printer not found"
    stored = await db_session.execute(select(PrintArchive.printer_id, PrintArchive.notes))
    assert stored.one() == (first.id, None)

    for suffix, field in (("upload", "file"), ("upload-bulk", "files")):
        response = await async_client.post(
            f"/api/v1/archives/{suffix}",
            headers=key,
            params={"printer_id": other.id},
            files={field: ("part.3mf", b"invalid fixture", "application/octet-stream")},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Printer not found"

    moved = await async_client.patch(endpoint, headers=bearer, json={"printer_id": team.id})
    assert moved.status_code == 200, moved.text
    assert moved.json()["printer_id"] == team.id
    cleared = await async_client.patch(endpoint, headers=bearer, json={"printer_id": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["printer_id"] is None


@pytest.mark.parametrize("missing", [0, 9999])
async def test_archive_rejects_missing_targets_and_can_set_or_clear_project(
    async_client, db_session, printer_factory, archive_factory, missing
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id)
    project = Project(name="Project")
    db_session.add(project)
    await db_session.commit()
    endpoint = f"/api/v1/archives/{archive.id}"

    for field, detail in (("printer_id", "Printer not found"), ("project_id", "Project not found")):
        rejected = await async_client.patch(endpoint, json={field: missing})
        assert rejected.status_code == 400
        assert rejected.json()["detail"] == detail

    linked = await async_client.patch(endpoint, json={"project_id": project.id})
    assert linked.status_code == 200, linked.text
    assert linked.json()["project_id"] == project.id
    cleared = await async_client.patch(endpoint, json={"project_id": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["project_id"] is None
