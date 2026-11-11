"""A daily digest retains failed deliveries and runs at its configured time."""

from datetime import timedelta
from unittest.mock import AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from backend.app.core import database
from backend.app.models.notification import NotificationDigestQueue, NotificationLog
from backend.app.services.notification_service import NotificationService
from backend.app.utils.local_time import utcnow_naive


async def test_digest_bypasses_quiet_hours_and_keeps_failed_events(
    db_session, test_engine, notification_provider_factory, monkeypatch
):
    provider = await notification_provider_factory(daily_digest_enabled=True, quiet_hours_enabled=True)
    service = NotificationService()
    sessions = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session", sessions)
    monkeypatch.setattr(service, "_is_in_quiet_hours", lambda _: True)
    send = AsyncMock(side_effect=[(False, "temporary failure"), (True, "sent")])
    monkeypatch.setattr(service, "_send_ntfy", send)
    now = utcnow_naive()
    db_session.add_all(
        NotificationDigestQueue(
            provider_id=provider.id,
            event_type="print_complete",
            title=title,
            message=title,
            created_at=now - timedelta(hours=age),
        )
        for age, title in ((49, "Expired"), (25, "Yesterday"), (0, "Today"))
    )
    await db_session.commit()

    await service.send_digest(provider.id)
    assert send.await_count == 1
    assert "Expired" not in send.await_args.args[2]
    assert "Yesterday" in send.await_args.args[2]
    assert "Today" in send.await_args.args[2]
    titles = select(NotificationDigestQueue.title).order_by(NotificationDigestQueue.created_at)
    async with sessions() as read:
        assert list(await read.scalars(titles)) == ["Yesterday", "Today"]

    await service.send_digest(provider.id)
    assert send.await_count == 2
    async with sessions() as read:
        assert list(await read.scalars(titles)) == []
        results = select(NotificationLog.success).order_by(NotificationLog.id)
        assert list(await read.scalars(results)) == [False, True]


async def test_template_editor_lists_all_defaults_and_previews_quality(async_client):
    from backend.app.models.notification_template import DEFAULT_TEMPLATES

    response = await async_client.get("/api/v1/notification-templates/variables")
    assert response.status_code == 200, response.text
    names = {row["event_type"]: row["event_name"] for row in response.json()}
    assert names == {row["event_type"]: row["name"] for row in DEFAULT_TEMPLATES}
    preview = await async_client.post(
        "/api/v1/notification-templates/preview",
        json={
            "event_type": "print_confirm_request",
            "title_template": "{printer}",
            "body_template": "{filename} {run_id} {confirm_url}",
        },
    )
    assert preview.status_code == 200, preview.text
    assert "Mounting bracket 19 https://printops.example/archives?confirm=42&run=19" in preview.json().values()


async def test_queue_notifications_respect_printer_scope_and_fleet_events(
    db_session, printer_factory, notification_provider_factory, monkeypatch
):
    first, second = await printer_factory(), await printer_factory()
    fleet = await notification_provider_factory(
        name="Fleet", on_queue_job_added=True, on_queue_job_waiting=True, on_queue_completed=True
    )
    scoped = await notification_provider_factory(
        name="First",
        printer_id=first.id,
        on_queue_job_added=True,
        on_queue_job_waiting=True,
        on_queue_completed=True,
    )
    service = NotificationService()
    send = AsyncMock()
    monkeypatch.setattr(service, "_send_to_providers", send)

    await service.on_queue_job_added("Bracket", "Any X1C", db_session)
    assert [row.id for row in send.await_args.args[0]] == [fleet.id]

    await service.on_queue_job_waiting("Bracket", "X1C", "needs PLA", db_session, printer_id=first.id)
    assert {row.id for row in send.await_args.args[0]} == {fleet.id, scoped.id}
    assert send.await_args.kwargs["printer_id"] == first.id

    await service.on_queue_job_waiting("Bracket", "X1C", "needs PLA", db_session, printer_id=second.id)
    assert [row.id for row in send.await_args.args[0]] == [fleet.id]

    await service.on_queue_completed(1, db_session)
    assert {row.id for row in send.await_args.args[0]} == {fleet.id, scoped.id}
