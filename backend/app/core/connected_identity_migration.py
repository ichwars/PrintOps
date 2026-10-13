"""Additive, idempotent generation binding for PrintOps connected identities."""

import secrets

from sqlalchemy import inspect, text


async def migrate_connected_identity(conn) -> None:
    columns = await conn.run_sync(lambda sync: {column["name"] for column in inspect(sync).get_columns("users")})
    if "connected_identity" not in columns:
        await conn.execute(text("ALTER TABLE users ADD COLUMN connected_identity VARCHAR(32)"))
    # Random values cannot derive from rowid/username/timestamps: all are reusable
    # in SQLite. Persist each legacy user's value exactly once on either dialect.
    ids = (await conn.execute(text("SELECT id FROM users WHERE connected_identity IS NULL"))).scalars().all()
    for user_id in ids:
        await conn.execute(
            text("UPDATE users SET connected_identity = :identity WHERE id = :id AND connected_identity IS NULL"),
            {"identity": secrets.token_hex(16), "id": user_id},
        )
