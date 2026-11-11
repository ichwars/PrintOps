"""Keep principal and resource IDs above values that may still be referenced."""

import json
import logging
import re
from collections import defaultdict

from sqlalchemy import text

logger = logging.getLogger(__name__)

IDENTITY_TABLES = ("users", "api_keys", "printers", "print_archives", "long_lived_tokens", "spool", "projects")

# These references intentionally outlive the referenced row or are kept
# outside a foreign key. The camera token uses provider_id for API keys only.
_NON_FK_REFERENCES = {
    "users": (("telegram_quality_messages", "owner_id"),),
    "print_archives": (("archive_aliases", "merged_archive_id"),),
    "printers": (
        ("print_log_entries", "printer_id"),
        ("printer_ha_interlock_audit", "printer_id"),
        ("notification_live_activities", "printer_id"),
        ("notification_lock_screen_widgets", "printer_id"),
    ),
}
_PRINTER_LISTS = (("api_keys", "printer_ids"), ("users", "allowed_printer_ids"))
_SQLITE_COLUMNS = """
    SELECT schema.name, columns.name FROM sqlite_schema AS schema
    JOIN pragma_table_xinfo(schema.name) AS columns
    WHERE schema.type = 'table'
"""
_POSTGRES_COLUMNS = """
    SELECT table_name, column_name FROM information_schema.columns
    WHERE table_schema = current_schema()
"""
_ID_NAME = r'(?:id|"id"|`id`|\[id\])'
_ID_COLUMN = re.compile(rf"(?:\(|,)\s*({_ID_NAME}\s+INTEGER\b(?:\s+NOT NULL)?)", re.IGNORECASE)
_TABLE_PK = re.compile(rf",\s*PRIMARY KEY\s*\(\s*{_ID_NAME}\s*\)", re.IGNORECASE)
_INLINE_PK = re.compile(r"\s+PRIMARY KEY\b", re.IGNORECASE)


async def _identity_floors(conn, metadata):
    """Find retained IDs even where a legacy SQLite database has orphan rows."""
    sqlite = conn.dialect.name == "sqlite"
    rows = await conn.exec_driver_sql(_SQLITE_COLUMNS if sqlite else _POSTGRES_COLUMNS)
    columns = defaultdict(set)
    for table, column in rows:
        columns[table].add(column)

    references = {table: {(table, "id"), *_NON_FK_REFERENCES.get(table, ())} for table in IDENTITY_TABLES}
    for table in metadata.tables.values():
        for fk in table.foreign_keys:
            target = fk.column
            if target.name == "id" and target.table.name in references:
                references[target.table.name].add((table.name, fk.parent.name))

    quote = conn.dialect.identifier_preparer.quote_identifier
    floors = {}
    for table, fields in references.items():
        floor = 0
        for ref_table, column in sorted(fields):
            if column in columns[ref_table]:
                sql = f"SELECT max({quote(column)}) FROM {quote(ref_table)}"  # noqa: S608
                floor = max(floor, (await conn.exec_driver_sql(sql)).scalar_one() or 0)
        floors[table] = floor

    if {"provider_id", "token_type"} <= columns["auth_ephemeral_tokens"]:
        floor = (
            await conn.execute(
                text(
                    "SELECT max(provider_id) FROM auth_ephemeral_tokens WHERE token_type IN ('camera_stream', 'websocket')"
                )
            )
        ).scalar_one()
        floors["api_keys"] = max(floors["api_keys"], floor or 0)

    for ref_table, column in _PRINTER_LISTS:
        if column not in columns[ref_table]:
            continue
        sql = f"SELECT {quote(column)} FROM {quote(ref_table)} WHERE {quote(column)} IS NOT NULL"  # noqa: S608
        for value in (await conn.exec_driver_sql(sql)).scalars():
            ids = json.loads(value) if isinstance(value, str) else value
            if isinstance(ids, list):
                floor = max((item for item in ids if type(item) is int), default=0)
                floors["printers"] = max(floors["printers"], floor)
    return floors


def _sqlite_identity_ddl(table: str, ddl: str, staged: str) -> str:
    """Keep the actual stored schema, including columns from earlier migrations."""
    body = ddl[ddl.index("(") :]
    column = _ID_COLUMN.search(body)
    if column is not None:
        inline_pk = _INLINE_PK.match(body, column.end())
        if inline_pk is not None:
            body = body[: inline_pk.end()] + " AUTOINCREMENT" + body[inline_pk.end() :]
            return f'CREATE TABLE "{staged}" ' + body
        table_pk = _TABLE_PK.search(body)
        if table_pk is not None and table_pk.start() >= column.end():
            body = body[: table_pk.start()] + body[table_pk.end() :]
            body = body[: column.end()] + " PRIMARY KEY AUTOINCREMENT" + body[column.end() :]
            return f'CREATE TABLE "{staged}" ' + body
    raise RuntimeError(f"Cannot preserve SQLite identity schema for {table}")


async def rebuild_sqlite_table(conn, table: str, staged: str, statement: str) -> None:
    """Copy all stored columns and restore indexes and triggers during a table rebuild."""
    extras = (
        (
            await conn.execute(
                text(
                    "SELECT sql FROM sqlite_schema WHERE tbl_name = :name AND type IN ('index', 'trigger') AND sql IS NOT NULL"
                ),
                {"name": table},
            )
        )
        .scalars()
        .all()
    )
    columns = (
        await conn.execute(text("SELECT name FROM pragma_table_xinfo(:name) WHERE hidden = 0"), {"name": table})
    ).scalars()
    quote = conn.dialect.identifier_preparer.quote_identifier
    names = ", ".join(quote(column) for column in columns)
    legacy_alter = (await conn.exec_driver_sql("PRAGMA legacy_alter_table")).scalar_one()
    # Views and triggers on other tables must keep referencing the original name.
    await conn.exec_driver_sql("PRAGMA legacy_alter_table = ON")
    try:
        await conn.exec_driver_sql(statement)
        await conn.exec_driver_sql(
            f"INSERT INTO {quote(staged)} ({names}) SELECT {names} FROM {quote(table)}"  # noqa: S608
        )
        original = (await conn.exec_driver_sql(f"SELECT count(*) FROM {quote(table)}")).scalar_one()  # noqa: S608
        copied = (await conn.exec_driver_sql(f"SELECT count(*) FROM {quote(staged)}")).scalar_one()  # noqa: S608
        if original != copied:
            raise RuntimeError(f"SQLite table rebuild changed the row count of {table}")
        await conn.exec_driver_sql(f"DROP TABLE {quote(table)}")
        await conn.exec_driver_sql(f"ALTER TABLE {quote(staged)} RENAME TO {quote(table)}")
        for sql in extras:
            await conn.exec_driver_sql(sql)
    finally:
        await conn.exec_driver_sql("PRAGMA legacy_alter_table = " + ("ON" if legacy_alter else "OFF"))


async def migrate_sqlite_identity_sequences(conn, metadata) -> None:
    if conn.dialect.name != "sqlite":
        return
    async with conn.begin_nested():
        floors = await _identity_floors(conn, metadata)
        for table, floor in floors.items():
            ddl = (
                await conn.execute(
                    text("SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = :name"), {"name": table}
                )
            ).scalar_one_or_none()
            if not ddl:
                continue
            if not re.search(r"\bPRIMARY KEY\s+AUTOINCREMENT\b", ddl, re.IGNORECASE):
                if (await conn.exec_driver_sql("PRAGMA foreign_keys")).scalar_one():
                    raise RuntimeError("SQLite identity migration requires foreign key enforcement off during rebuild")
                staged = f"{table}_identity_migration"
                await rebuild_sqlite_table(conn, table, staged, _sqlite_identity_ddl(table, ddl, staged))

            params = {"name": table, "floor": floor}
            current = (
                await conn.execute(text("SELECT max(seq) FROM sqlite_sequence WHERE name = :name"), params)
            ).scalar_one()
            if floor > (current or 0):
                await conn.execute(text("DELETE FROM sqlite_sequence WHERE name = :name"), params)
                await conn.execute(text("INSERT INTO sqlite_sequence (name, seq) VALUES (:name, :floor)"), params)
                logger.info("SQLite: %s IDs now continue above %s", table, floor)


async def raise_postgres_identity_sequences(conn, metadata, source_floors=None) -> None:
    if conn.dialect.name != "postgresql":
        return
    floors = await _identity_floors(conn, metadata)
    for table, floor in floors.items():
        floor = max(floor, (source_floors or {}).get(table) or 0)
        if floor <= 0:
            continue
        sequence = (
            await conn.execute(text("SELECT pg_get_serial_sequence(:name, 'id')"), {"name": table})
        ).scalar_one()
        if sequence is None:
            continue
        # PostgreSQL supplies the quoted relation name. Most startup checks
        # need no lock or change to the sequence.
        sequence_state = f"SELECT last_value, is_called FROM {sequence}"  # noqa: S608
        current, called = (await conn.exec_driver_sql(sequence_state)).one()
        if floor < current or (floor == current and called):
            continue
        # Re-read under a lock so a concurrent insert cannot raise the sequence
        # between the check and setval.
        await conn.exec_driver_sql(f"LOCK TABLE {table} IN SHARE ROW EXCLUSIVE MODE")
        current, called = (await conn.exec_driver_sql(sequence_state)).one()
        if floor > current or (floor == current and not called):
            await conn.execute(
                text("SELECT setval(CAST(:name AS regclass), :floor)"), {"name": sequence, "floor": floor}
            )


async def migrate_identity_sequences(conn, metadata) -> None:
    if conn.dialect.name == "sqlite":
        await migrate_sqlite_identity_sequences(conn, metadata)
    else:
        await raise_postgres_identity_sequences(conn, metadata)
