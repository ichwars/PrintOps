"""Keep measured usage after deleting a spool or a print archive."""

import re

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection

from backend.app.core.identity_sequence_migration import rebuild_sqlite_table

_LINKS = {"spool_id": "spool", "archive_id": "print_archives"}


async def _sqlite_changes(conn: AsyncConnection) -> dict[str, bool]:
    """Map columns that need changes to whether they have an existing key."""
    columns = (await conn.exec_driver_sql("PRAGMA table_info(spool_usage_history)")).mappings()
    required = {column["name"] for column in columns if column["notnull"]}
    keys = (await conn.exec_driver_sql("PRAGMA foreign_key_list(spool_usage_history)")).mappings().all()
    changes = {}
    for column, parent in _LINKS.items():
        links = [key for key in keys if key["from"] == column]
        correct = (
            len(links) == 1
            and links[0]["table"] == parent
            and links[0]["to"] == "id"
            and links[0]["on_delete"] == "SET NULL"
        )
        if column in required or not correct:
            changes[column] = bool(links)
    return changes


def _sqlite_link_ddl(body: str, column: str, parent: str, has_key: bool) -> str:
    name = rf'"?{column}"?'
    body = re.sub(rf"({name}\s+INTEGER)\s+NOT\s+NULL\b", r"\1", body, flags=re.IGNORECASE)
    reference = (
        rf"((?:FOREIGN\s+KEY\s*\(\s*{name}\s*\)\s*|{name}\s+INTEGER\s+)"
        rf'REFERENCES\s+"?{parent}"?\s*\(\s*"?id"?\s*\))'
        r"(?:\s+ON\s+DELETE\s+(?:CASCADE|SET\s+NULL|SET\s+DEFAULT|RESTRICT|NO\s+ACTION))?"
    )
    body, matched = re.subn(reference, r"\1 ON DELETE SET NULL", body, flags=re.IGNORECASE)
    if matched == 1:
        return body
    if not matched and not has_key:
        end = body.rindex(")")
        return body[:end] + f", FOREIGN KEY ({column}) REFERENCES {parent}(id) ON DELETE SET NULL" + body[end:]
    raise RuntimeError(f"Unexpected SQLite foreign key for spool_usage_history.{column}")


async def _detach_missing(conn: AsyncConnection, column: str, parent: str) -> None:
    # Identifiers come from the fixed _LINKS mapping.
    sql = (
        f"UPDATE spool_usage_history SET {column} = NULL "  # noqa: S608  # nosec B608
        f"WHERE {column} IS NOT NULL AND NOT EXISTS ("
        f"SELECT 1 FROM {parent} WHERE {parent}.id = spool_usage_history.{column})"
    )
    await conn.exec_driver_sql(sql)


async def _upgrade_sqlite(conn: AsyncConnection) -> None:
    changes = await _sqlite_changes(conn)
    if changes:
        ddl = await conn.scalar(
            text("SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = 'spool_usage_history'")
        )
        body = ddl[ddl.index("(") :]
        for column, has_key in changes.items():
            body = _sqlite_link_ddl(body, column, _LINKS[column], has_key)

        stage = "spool_usage_history_detach_migration"
        # Keep the historical AUTOINCREMENT floor even if the latest rows were deleted.
        params = {"name": "spool_usage_history"}
        sequence = None
        if re.search(r"\bAUTOINCREMENT\b", ddl, re.IGNORECASE):
            sequence = await conn.scalar(text("SELECT max(seq) FROM sqlite_sequence WHERE name = :name"), params)
        await rebuild_sqlite_table(conn, "spool_usage_history", stage, f'CREATE TABLE "{stage}" {body}')
        if sequence is not None:
            await conn.execute(text("DELETE FROM sqlite_sequence WHERE name = :name"), params)
            await conn.execute(
                text("INSERT INTO sqlite_sequence (name, seq) VALUES (:name, :seq)"),
                {**params, "seq": sequence},
            )
        if await _sqlite_changes(conn):
            raise RuntimeError("Failed to make SQLite spool history detachable")

    # SQLite runs without FK enforcement. Triggers cover both ORM and SQL deletion.
    for column, parent in _LINKS.items():
        trigger = f"spool_usage_detach_{column.removesuffix('_id')}"
        update = f"UPDATE spool_usage_history SET {column} = NULL WHERE {column} = OLD.id;"  # nosec B608
        await conn.exec_driver_sql(
            f"CREATE TRIGGER IF NOT EXISTS {trigger} AFTER DELETE ON {parent} BEGIN {update} END"
        )
        await _detach_missing(conn, column, parent)


def _postgres_changes(sync):
    inspector = inspect(sync)
    required = {column["name"] for column in inspector.get_columns("spool_usage_history") if not column["nullable"]}
    keys = inspector.get_foreign_keys("spool_usage_history")
    changes = {}
    for column, parent in _LINKS.items():
        links = [key for key in keys if key["constrained_columns"] == [column]]
        correct = (
            len(links) == 1
            and links[0]["referred_table"] == parent
            and links[0]["referred_columns"] == ["id"]
            and links[0]["options"].get("ondelete") == "SET NULL"
        )
        if column in required or not correct:
            changes[column] = (column in required, None if correct else links)
    return changes


async def _upgrade_postgres(conn: AsyncConnection) -> None:
    if not await conn.run_sync(_postgres_changes):
        return
    await conn.exec_driver_sql("LOCK TABLE spool_usage_history IN ACCESS EXCLUSIVE MODE")
    quote = conn.dialect.identifier_preparer.quote_identifier
    for column, (required, old_keys) in (await conn.run_sync(_postgres_changes)).items():
        if required:
            await conn.exec_driver_sql(f"ALTER TABLE spool_usage_history ALTER COLUMN {column} DROP NOT NULL")
        if old_keys is None:
            continue
        for key in old_keys:
            await conn.exec_driver_sql(f"ALTER TABLE spool_usage_history DROP CONSTRAINT {quote(key['name'])}")
        parent = _LINKS[column]
        await _detach_missing(conn, column, parent)
        await conn.exec_driver_sql(f"""
            ALTER TABLE spool_usage_history ADD FOREIGN KEY ({column}) REFERENCES {parent}(id) ON DELETE SET NULL
        """)


async def migrate_spool_usage_history(conn: AsyncConnection) -> None:
    """Run after capturing SQLite sequence floors from the old references."""
    async with conn.begin_nested():
        if conn.dialect.name == "sqlite":
            await _upgrade_sqlite(conn)
        elif conn.dialect.name == "postgresql":
            await _upgrade_postgres(conn)
        for column in _LINKS:
            await conn.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_spool_usage_history_{column} ON spool_usage_history ({column})"
            )
