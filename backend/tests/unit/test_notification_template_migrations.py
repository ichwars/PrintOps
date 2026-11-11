import pytest

from backend.app.core.notification_template_migrations import migrate_account_templates
from backend.app.models.notification_template import (
    LEGACY_PASSWORD_RESET_TEMPLATE_BODY,
    LEGACY_WELCOME_TEMPLATE_BODY,
    PASSWORD_RESET_TEMPLATE_BODY,
    WELCOME_TEMPLATE_BODY,
    NotificationTemplate,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("use_shipped_default", [True, False])
@pytest.mark.parametrize(
    ("event", "legacy", "default"),
    [
        ("user_created", LEGACY_WELCOME_TEMPLATE_BODY, WELCOME_TEMPLATE_BODY),
        ("password_reset", LEGACY_PASSWORD_RESET_TEMPLATE_BODY, PASSWORD_RESET_TEMPLATE_BODY),
    ],
)
async def test_account_template_upgrade_preserves_customized_templates(
    db_session, use_shipped_default, event, legacy, default
):
    body = legacy if use_shipped_default else "Customized {username} {password}"
    template = NotificationTemplate(
        event_type=event,
        name="Welcome",
        title_template="Custom subject",
        body_template=body,
    )
    db_session.add(template)
    await db_session.flush()
    conn = await db_session.connection()
    await migrate_account_templates(conn)
    await migrate_account_templates(conn)
    await db_session.refresh(template)

    assert template.body_template == (default if use_shipped_default else body)
    assert template.title_template == "Custom subject"
