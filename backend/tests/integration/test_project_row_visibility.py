"""Project relationships cannot disclose or modify another owner's rows."""

from datetime import datetime

import pytest
from sqlalchemy import select

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.group import Group
from backend.app.models.library import LibraryFolder
from backend.app.models.pipeline_run import PipelineJob, PipelineRun
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.project import Project
from backend.app.models.project_bom import ProjectBOMItem
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_project_relationships_apply_row_ownership_and_both_printer_scopes(
    async_client,
    db_session,
    printer_factory,
    archive_factory,
):
    admin = await _setup_admin(async_client)
    permitted = await printer_factory()
    other_printer = await printer_factory()
    role = Group(
        name="Project editor",
        permissions=[
            Permission.PROJECTS_READ.value,
            Permission.PROJECTS_UPDATE.value,
            Permission.ARCHIVES_READ_OWN.value,
            Permission.ARCHIVES_REPRINT_OWN.value,
            Permission.ARCHIVES_UPDATE_OWN.value,
            Permission.QUEUE_READ_OWN.value,
            Permission.QUEUE_CREATE.value,
            Permission.QUEUE_UPDATE_OWN.value,
            Permission.LIBRARY_READ_OWN.value,
            Permission.LIBRARY_UPDATE_ALL.value,
            Permission.LIBRARY_UPLOAD.value,
            Permission.PIPELINES_READ.value,
            Permission.PIPELINES_RUN.value,
        ],
    )
    viewer = User(username="project-editor", role="user", allowed_printer_ids=[permitted.id], groups=[role])
    other_user = User(username="other-project-owner", role="user")
    project = Project(name="Shared project")
    db_session.add_all([viewer, other_user, project])
    await db_session.commit()

    own = await archive_factory(project_id=project.id, printer_id=permitted.id, created_by_id=viewer.id)
    other = await archive_factory(project_id=project.id, printer_id=permitted.id, created_by_id=other_user.id)
    outside = await archive_factory(project_id=project.id, printer_id=other_printer.id, created_by_id=viewer.id)
    deleted = await archive_factory(project_id=project.id, printer_id=permitted.id, created_by_id=viewer.id)
    deleted.deleted_at = datetime(2024, 1, 1)

    own_folder = LibraryFolder(name="Own archive folder", archive_id=own.id, project_id=project.id)
    hidden_folder = LibraryFolder(name="Hidden archive folder", archive_id=other.id, project_id=project.id)
    db_session.add_all([own_folder, hidden_folder])
    own_queue = PrintQueueItem(
        project_id=project.id, printer_id=permitted.id, created_by_id=viewer.id, position=2, manual_start=True
    )
    other_queue = PrintQueueItem(
        project_id=project.id, printer_id=permitted.id, created_by_id=other_user.id, position=1, manual_start=True
    )
    other_run = PipelineRun(source_archive_id=other.id, created_by=other_user.id)
    db_session.add_all([other_queue, other_run])
    await db_session.flush()
    db_session.add(PipelineJob(pipeline_run_id=other_run.id, queue_entry_id=other_queue.id, copy_index=0))
    db_session.add_all(
        [
            own_queue,
            PrintQueueItem(project_id=project.id, printer_id=other_printer.id, created_by_id=viewer.id),
            ProjectBOMItem(project_id=project.id, name="Own part", archive_id=own.id),
            ProjectBOMItem(project_id=project.id, name="Other part", archive_id=other.id),
        ]
    )
    full_key, key_hash, key_prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="Different printer",
            key_hash=key_hash,
            key_prefix=key_prefix,
            user_id=viewer.id,
            printer_ids=[other_printer.id],
        )
    )
    control_key, control_hash, control_prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="Queue control",
            key_hash=control_hash,
            key_prefix=control_prefix,
            user_id=viewer.id,
            can_control_printer=True,
        )
    )
    await db_session.commit()

    path = f"/api/v1/projects/{project.id}"
    headers = {"Authorization": f"Bearer {create_access_token({'sub': viewer.username})}"}
    archives = await async_client.get(f"{path}/archives", headers=headers)
    queue = await async_client.get(f"{path}/queue", headers=headers)
    listing = await async_client.get("/api/v1/projects/", headers=headers)
    assert [row["id"] for row in archives.json()] == [own.id]
    assert [row["id"] for row in queue.json()] == [own_queue.id]
    assert [row["id"] for row in listing.json()[0]["archives"]] == [own.id]

    bom_path = f"{path}/bom"
    assert (await async_client.get(bom_path)).status_code == 401
    assert (await async_client.get(bom_path, headers={"X-API-Key": "invalid"})).status_code == 401
    bom = await async_client.get(bom_path, headers=headers)
    links = {row["name"]: (row["archive_id"], row["archive_name"]) for row in bom.json()}
    assert links == {"Own part": (own.id, own.print_name), "Other part": (None, None)}
    zero = await async_client.post(f"{path}/bom", headers=headers, json={"name": "No link", "archive_id": 0})
    assert zero.status_code == 200
    assert zero.json()["archive_id"] is None and zero.json()["archive_name"] is None
    other_line = next(row for row in bom.json() if row["name"] == "Other part")
    same_hidden_link = await async_client.patch(
        f"{path}/bom/{other_line['id']}", headers=headers, json={"archive_id": other.id}
    )
    assert same_hidden_link.status_code == 404
    forbidden = await async_client.post(
        f"{path}/bom", headers=headers, json={"name": "Forbidden link", "archive_id": other.id}
    )
    assert forbidden.status_code == 404

    linked = await async_client.get(f"/api/v1/library/folders/by-project/{project.id}", headers=headers)
    assert {row["id"]: row["archive_id"] for row in linked.json()} == {own_folder.id: own.id, hidden_folder.id: None}
    hidden_links = await async_client.get(f"/api/v1/library/folders/by-archive/{other.id}", headers=headers)
    assert hidden_links.json() == []
    rejected_link = await async_client.post(
        "/api/v1/library/folders/", headers=headers, json={"name": "Forbidden", "archive_id": other.id}
    )
    assert rejected_link.status_code == 404
    unlink = await async_client.put(
        f"/api/v1/library/folders/{hidden_folder.id}", headers=headers, json={"archive_id": 0}
    )
    assert unlink.json()["archive_id"] is None
    await db_session.refresh(hidden_folder)
    assert hidden_folder.archive_id == other.id

    key_headers = {"X-API-Key": full_key}
    assert (await async_client.get(f"{path}/archives", headers=key_headers)).json() == []
    assert (await async_client.get(f"{path}/queue", headers=key_headers)).json() == []

    run_path = f"/api/v1/pipeline-runs/{other_run.id}"
    pipeline = (await async_client.get(run_path, headers=headers)).json()
    assert pipeline["source_archive_id"] is None and pipeline["source_filename"] is None
    assert pipeline["jobs"][0]["queue_entry_id"] is None
    assert (await async_client.post(f"{run_path}/cancel", headers=headers)).status_code == 403

    fallback = {"X-API-Key": "invalid", "Authorization": f"Bearer {control_key}"}
    by_key = await async_client.get(f"{path}/bom", headers=fallback)
    assert by_key.status_code == 200
    assert {row["name"]: (row["archive_id"], row["archive_name"]) for row in by_key.json()} == links

    control_headers = {"X-API-Key": control_key}
    queue_status = await async_client.get("/api/v1/webhook/queue", headers=control_headers)
    assert [row["printer_id"] for row in queue_status.json()] == [permitted.id]
    assert [row["id"] for row in queue_status.json()[0]["items"]] == [own_queue.id]
    started = await async_client.post(f"/api/v1/webhook/printer/{permitted.id}/start", headers=control_headers)
    assert started.json()["queue_item_id"] == own_queue.id
    assert await db_session.scalar(select(PrintQueueItem.manual_start).where(PrintQueueItem.id == other_queue.id))
    added = await async_client.post(
        "/api/v1/webhook/queue/add",
        headers=control_headers,
        json={"archive_id": own.id, "printer_id": permitted.id},
    )
    assert added.status_code == 200
    assert (
        await db_session.scalar(select(PrintQueueItem.created_by_id).where(PrintQueueItem.id == added.json()["id"]))
        == viewer.id
    )

    removed = await async_client.post(
        f"{path}/remove-archives", headers=headers, json={"archive_ids": [own.id, other.id, outside.id]}
    )
    assert removed.json() == {"message": "Removed 1 archives from project", "count": 1}
    admin_archives = await async_client.get(f"{path}/archives", headers={"Authorization": f"Bearer {admin}"})
    assert {row["id"] for row in admin_archives.json()} == {other.id, outside.id}


async def test_library_archive_links_follow_the_selected_key_for_reads_and_writes(
    async_client, db_session, printer_factory, archive_factory
):
    await _setup_admin(async_client)
    visible = await printer_factory()
    hidden = await printer_factory()
    visible_archive = await archive_factory(visible.id, print_name="Allowed archive")
    hidden_archive = await archive_factory(hidden.id, print_name="Restricted archive")
    project = Project(name="Library scope")
    db_session.add(project)
    await db_session.flush()
    folder = LibraryFolder(name="Hidden link", archive_id=hidden_archive.id, project_id=project.id)
    db_session.add(folder)
    secret, key_hash, prefix = generate_api_key()
    db_session.add(
        APIKey(
            name="Library links",
            key_hash=key_hash,
            key_prefix=prefix,
            can_read_status=True,
            can_manage_library=True,
            printer_ids=[visible.id],
        )
    )
    await db_session.commit()

    headers = {"X-API-Key": "invalid", "Authorization": f"Bearer {secret}"}
    base = "/api/v1/library/folders"
    details = await async_client.get(f"{base}/{folder.id}", headers=headers)
    assert details.status_code == 200
    assert (details.json()["archive_id"], details.json()["archive_name"]) == (None, None)
    by_project = await async_client.get(f"{base}/by-project/{project.id}", headers=headers)
    assert by_project.json()[0]["archive_id"] is None
    by_archive = await async_client.get(f"{base}/by-archive/{hidden_archive.id}", headers=headers)
    assert by_archive.json() == []
    hidden_unlink = await async_client.put(f"{base}/{folder.id}", headers=headers, json={"archive_id": 0})
    assert hidden_unlink.status_code == 200
    await db_session.refresh(folder)
    assert folder.archive_id == hidden_archive.id
    denied = await async_client.post(
        f"{base}/", headers=headers, json={"name": "Denied", "archive_id": hidden_archive.id}
    )
    assert denied.status_code == 404

    allowed = await async_client.post(
        f"{base}/", headers=headers, json={"name": "Allowed link", "archive_id": visible_archive.id}
    )
    assert allowed.status_code == 200
    assert allowed.json()["archive_name"] == "Allowed archive"
    visible_folder_id = allowed.json()["id"]
    listing = await async_client.get(base, headers=headers)
    assert {row["id"]: row["archive_id"] for row in listing.json()} == {
        folder.id: None,
        visible_folder_id: visible_archive.id,
    }
    by_archive = await async_client.get(f"{base}/by-archive/{visible_archive.id}", headers=headers)
    assert [row["id"] for row in by_archive.json()] == [visible_folder_id]
    denied_retarget = await async_client.put(
        f"{base}/{visible_folder_id}", headers=headers, json={"archive_id": hidden_archive.id}
    )
    assert denied_retarget.status_code == 404
