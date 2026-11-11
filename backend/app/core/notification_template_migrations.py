"""Upgrade shipped notification templates while preserving customized text."""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncConnection


async def migrate_account_templates(conn: AsyncConnection) -> None:
    from backend.app.models.notification_template import (
        LEGACY_PASSWORD_RESET_TEMPLATE_BODY,
        LEGACY_WELCOME_TEMPLATE_BODY,
        PASSWORD_RESET_TEMPLATE_BODY,
        WELCOME_TEMPLATE_BODY,
        NotificationTemplate,
    )

    for event, old_body, body in (
        ("user_created", LEGACY_WELCOME_TEMPLATE_BODY, WELCOME_TEMPLATE_BODY),
        ("password_reset", LEGACY_PASSWORD_RESET_TEMPLATE_BODY, PASSWORD_RESET_TEMPLATE_BODY),
    ):
        await conn.execute(
            update(NotificationTemplate)
            .where(
                NotificationTemplate.event_type == event,
                NotificationTemplate.body_template == old_body,
            )
            .values(body_template=body)
        )
