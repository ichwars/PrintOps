"""Stamp archive ownership at assignment, never infer it from reusable IDs later."""

from sqlalchemy import event, inspect, select


def register_archive_owner_identity(archive_model):
    def stamp(mapper, connection, target):
        from backend.app.models.user import User

        state = inspect(target)
        if state.pending or state.attrs.created_by_id.history.has_changes():
            target.created_by_identity = (
                connection.execute(
                    select(User.connected_identity).where(User.id == target.created_by_id)
                ).scalar_one_or_none()
                if target.created_by_id is not None
                else None
            )

    event.listen(archive_model, "before_insert", stamp)
    event.listen(archive_model, "before_update", stamp)


async def migrate_archive_owner_identity(conn, safe_execute):
    # No backfill: a legacy numeric owner ID may already denote a replacement.
    await safe_execute(conn, "ALTER TABLE print_archives ADD COLUMN created_by_identity VARCHAR(32)")
