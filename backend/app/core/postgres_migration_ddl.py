"""Keep expected PostgreSQL migration no-ops out of the server error log."""

import re
from functools import wraps

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection

_NAME = r'(?:"(?:[^"]|"")*"|[A-Z_][\w$]*)'
_TABLE = rf"{_NAME}(?:\s*\.\s*{_NAME})?"
_ALTER = rf"^\s*ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?P<table>{_TABLE})"
_ADD_COLUMN = re.compile(rf"({_ALTER}\s+ADD\s+COLUMN\b)(?P<body>.*)", re.I | re.S)
_CREATE = re.compile(r"^(\s*CREATE\s+(?:UNIQUE\s+)?(?:INDEX|TABLE)\b)(?P<body>.*)", re.I | re.S)
_ALREADY_GUARDED = re.compile(r"^(?:IF\s+NOT\s+EXISTS\b|CONCURRENTLY\b)", re.I)
_ADD_CONSTRAINT = re.compile(rf"{_ALTER}\s+ADD\s+CONSTRAINT\s+(?P<constraint>{_NAME})", re.I)
_RENAME = re.compile(rf"{_ALTER}\s+RENAME\s+COLUMN\s+(?P<old>{_NAME})\s+TO\s+(?P<new>{_NAME})", re.I)


def is_postgres_connection(conn) -> bool:
    return isinstance(conn, AsyncConnection) and conn.dialect.name == "postgresql"


def idempotent_postgres_ddl(sql: str) -> str:
    """Use PostgreSQL's native object guards for supported DDL."""
    match = _ADD_COLUMN.match(sql) or _CREATE.match(sql)
    if match is None:
        return sql
    body = match["body"].lstrip()
    if not body or _ALREADY_GUARDED.match(body):
        return sql
    return match[1] + " IF NOT EXISTS " + body


def _identifier(value: str) -> str:
    return value[1:-1].replace('""', '"') if value.startswith('"') else value.lower()


async def postgres_ddl_already_applied(conn: AsyncConnection, sql: str) -> bool:
    constraint = _ADD_CONSTRAINT.match(sql)
    if constraint:
        return bool(
            await conn.scalar(
                text("SELECT 1 FROM pg_constraint WHERE conrelid = to_regclass(:table) AND conname = :name"),
                {"table": constraint["table"], "name": _identifier(constraint["constraint"])},
            )
        )
    rename = _RENAME.match(sql)
    if rename:
        # A missing table still produces a genuine migration error.
        return bool(
            await conn.scalar(
                text("""
                SELECT to_regclass(:table) IS NOT NULL AND (
                    NOT EXISTS (
                        SELECT 1 FROM pg_attribute
                        WHERE attrelid = to_regclass(:table) AND attname = :old AND NOT attisdropped
                    ) OR EXISTS (
                        SELECT 1 FROM pg_attribute
                        WHERE attrelid = to_regclass(:table) AND attname = :new AND NOT attisdropped
                    )
                )
            """),
                {"table": rename["table"], "old": _identifier(rename["old"]), "new": _identifier(rename["new"])},
            )
        )
    return False


def _rewrite(_conn, _cursor, statement, parameters, _context, _executemany):
    return idempotent_postgres_ddl(statement), parameters


def quiet_postgres_migration_ddl(migrate):
    """Apply native guards to older DDL that bypasses the migration helper."""

    @wraps(migrate)
    async def run(conn):
        if not is_postgres_connection(conn):
            return await migrate(conn)
        connection = conn.sync_connection
        event.listen(connection, "before_cursor_execute", _rewrite, retval=True)
        try:
            return await migrate(conn)
        finally:
            event.remove(connection, "before_cursor_execute", _rewrite)

    return run
