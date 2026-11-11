"""Store security timestamps as UTC instants on either database."""

from datetime import datetime

from sqlalchemy import DateTime, TypeDecorator, text
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.app.utils.local_time import to_naive_utc


class AuthDateTime(TypeDecorator[datetime]):
    """UTC timestamp with the same binding rules in SQLite and PostgreSQL."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return to_naive_utc(value)


_AUTH_TIMESTAMPS = {
    ("users", "password_changed_at"),
    ("auth_ephemeral_tokens", "expires_at"),
    ("auth_ephemeral_tokens", "created_at"),
    ("auth_rate_limit_events", "occurred_at"),
}


async def _legacy_auth_timestamps(conn: AsyncConnection) -> set[tuple[str, str]]:
    rows = await conn.execute(
        text("""
            SELECT table_name, column_name FROM information_schema.columns
            WHERE table_schema = current_schema() AND data_type = 'timestamp with time zone'
        """)
    )
    return {(table, column) for table, column in rows} & _AUTH_TIMESTAMPS


async def migrate_auth_timestamps(conn: AsyncConnection) -> None:
    """Convert old PostgreSQL auth timestamps and invalidate affected sessions once."""
    if conn.dialect.name != "postgresql" or not await _legacy_auth_timestamps(conn):
        return

    from backend.app.core.auth_sessions import invalidate_all_sessions

    # A second startup can observe the old column types before the first commits.
    await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('printops.auth_timestamps_utc'))"))
    legacy = await _legacy_auth_timestamps(conn)
    if not legacy:
        return

    quote = conn.dialect.identifier_preparer.quote_identifier
    for table, column in sorted(legacy):
        column_sql = quote(column)
        await conn.execute(
            text(
                f"ALTER TABLE {quote(table)} ALTER COLUMN {column_sql} TYPE TIMESTAMP USING ({column_sql} AT TIME ZONE 'UTC')"
            )
        )

    # The offset of earlier writers is unknown. Reset the security cutoff and
    # discard incomplete auth flows so none depend on those old timestamps.
    await invalidate_all_sessions(conn)
