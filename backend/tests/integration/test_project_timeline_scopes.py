from backend.app.core.auth import create_access_token
from backend.app.core.permissions import Permission
from backend.app.models.group import Group
from backend.app.models.print_queue import PrintQueueItem
from backend.app.models.project import Project
from backend.app.models.user import User
from backend.tests.integration.test_media_tokens import _admin_token


async def test_timeline_lists_queued_and_active_items_within_printer_grants(
    async_client, db_session, printer_factory, archive_factory
):
    first, second = await printer_factory(), await printer_factory()
    project = Project(name="Workshop timeline")
    db_session.add(project)
    await db_session.commit()
    visible = await archive_factory(first.id, print_name="Visible job", project_id=project.id)
    hidden = await archive_factory(second.id, print_name="Hidden job", project_id=project.id)
    db_session.add_all(
        [
            PrintQueueItem(project_id=project.id, printer_id=first.id, archive_id=visible.id, status="pending"),
            PrintQueueItem(project_id=project.id, printer_id=second.id, archive_id=hidden.id, status="printing"),
        ]
    )
    await db_session.commit()
    route = f"/api/v1/projects/{project.id}/timeline"
    response = await async_client.get(route)
    assert response.status_code == 200, response.text
    entries = {(row["event_type"], row["description"]) for row in response.json()}
    assert {("queued", "Visible job"), ("print_started", "Hidden job")} <= entries

    await _admin_token(async_client, "project_timeline")
    member = User(
        username="timeline_reader",
        allowed_printer_ids=[first.id],
        groups=[
            Group(
                name="Project timeline",
                permissions=[
                    Permission.PROJECTS_READ.value,
                    Permission.ARCHIVES_READ_ALL.value,
                    Permission.QUEUE_READ_ALL.value,
                ],
            )
        ],
    )
    db_session.add(member)
    await db_session.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': member.username})}"}
    response = await async_client.get(route, headers=headers)
    assert response.status_code == 200, response.text
    entries = {(row["event_type"], row["description"]) for row in response.json()}
    assert {("queued", "Visible job"), ("print_completed", "Visible job")} <= entries
    assert not any(description == "Hidden job" for _, description in entries)
