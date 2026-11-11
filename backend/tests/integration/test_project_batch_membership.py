"""Project batch writes report only rows within the selected credential's grants."""

import pytest
from sqlalchemy import select

from backend.app.core.auth import generate_api_key
from backend.app.core.permissions import Permission
from backend.app.models.api_key import APIKey
from backend.app.models.archive import PrintArchive
from backend.app.models.group import Group
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.project import Project
from backend.app.models.user import User
from backend.tests.integration.test_long_lived_tokens_api import _setup_admin

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_project_key_updates_only_its_owners_rows_on_allowed_printers(
    async_client, db_session, printer_factory, archive_factory
):
    await _setup_admin(async_client)
    visible, hidden = await printer_factory(), await printer_factory()
    editor = User(
        username="batch-editor",
        groups=[
            Group(
                name="Own rows", permissions=[Permission.ARCHIVES_UPDATE_OWN.value, Permission.QUEUE_UPDATE_OWN.value]
            )
        ],
        allowed_printer_ids=[visible.id],
    )
    project = Project(name="Batch project")
    db_session.add_all([editor, project])
    await db_session.flush()
    token, key_hash, prefix = generate_api_key()
    denied_token, denied_hash, denied_prefix = generate_api_key()
    db_session.add_all(
        [
            APIKey(
                name="Project-only key",
                key_hash=key_hash,
                key_prefix=prefix,
                user_id=editor.id,
                printer_ids=[visible.id, hidden.id],
                can_manage_projects=True,
                can_manage_archives=False,
                can_queue=False,
            ),
            APIKey(
                name="Key without project grants",
                key_hash=denied_hash,
                key_prefix=denied_prefix,
                user_id=editor.id,
                can_manage_projects=False,
            ),
        ]
    )
    await db_session.commit()

    own = await archive_factory(visible.id, created_by_id=editor.id)
    other_owner = await archive_factory(visible.id)
    other_printer = await archive_factory(hidden.id, created_by_id=editor.id)
    jobs = [
        PrintQueueItem(printer_id=visible.id, created_by_id=editor.id),
        PrintQueueItem(printer_id=visible.id),
        PrintQueueItem(printer_id=hidden.id, created_by_id=editor.id),
    ]
    db_session.add_all(jobs)
    await db_session.commit()

    path = f"/api/v1/projects/{project.id}"
    archives = {"archive_ids": [own.id, other_owner.id, other_printer.id, own.id]}
    for headers, expected in (
        ({}, 401),
        ({"X-API-Key": "invalid"}, 401),
        ({"X-API-Key": denied_token}, 403),
    ):
        response = await async_client.post(f"{path}/add-archives", headers=headers, json=archives)
        assert response.status_code == expected

    headers = {"X-API-Key": "invalid", "Authorization": f"Bearer {token}"}
    assigned = await async_client.post(f"{path}/add-archives", headers=headers, json=archives)
    queued = await async_client.post(
        f"{path}/add-queue", headers=headers, json={"queue_item_ids": [job.id for job in jobs]}
    )
    assert assigned.json() == {"message": "Added 1 archives to project", "count": 1}
    assert queued.json() == {"message": "Added 1 queue items to project", "count": 1}
    archive_projects = await db_session.execute(select(PrintArchive.project_id).order_by(PrintArchive.id))
    queue_projects = await db_session.execute(select(PrintQueueItem.project_id).order_by(PrintQueueItem.id))
    assert archive_projects.scalars().all() == [project.id, None, None]
    assert queue_projects.scalars().all() == [project.id, None, None]

    removed = await async_client.post(f"{path}/remove-archives", headers=headers, json=archives)
    assert removed.json() == {"message": "Removed 1 archives from project", "count": 1}
    assert await db_session.scalar(select(PrintArchive.project_id).where(PrintArchive.id == own.id)) is None
