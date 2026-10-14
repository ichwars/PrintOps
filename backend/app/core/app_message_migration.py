"""Add opt-in application notifications without granting legacy data access."""


async def migrate_notification_options(conn, safe_execute):
    await safe_execute(conn, "ALTER TABLE api_keys ADD COLUMN can_send_notifications BOOLEAN NOT NULL DEFAULT FALSE")
    await safe_execute(conn, "ALTER TABLE api_keys ADD COLUMN notification_owner_identity VARCHAR(32)")
    await safe_execute(
        conn, "ALTER TABLE notification_providers ADD COLUMN on_app_message BOOLEAN NOT NULL DEFAULT FALSE"
    )
    await safe_execute(conn, "ALTER TABLE notification_providers ADD COLUMN attach_photo BOOLEAN NOT NULL DEFAULT TRUE")
