"""Add issuer metadata to ephemeral credentials on existing databases."""

from sqlalchemy import inspect, text

_COLUMNS = {
    "code_verifier": "VARCHAR(128)",
    "challenge_id": "VARCHAR(128)",
    "issuer_identity": "VARCHAR(32)",
    "issuer_jti": "VARCHAR(128)",
    "issuer_epoch": "VARCHAR(32)",
}


async def migrate_auth_ephemeral_columns(conn):
    existing = await conn.run_sync(
        lambda sync: {column["name"] for column in inspect(sync).get_columns("auth_ephemeral_tokens")}
    )
    for column, column_type in _COLUMNS.items():
        if column not in existing:
            await conn.execute(text(f"ALTER TABLE auth_ephemeral_tokens ADD COLUMN {column} {column_type}"))
