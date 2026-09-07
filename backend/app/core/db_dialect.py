"""Database dialect helpers for SQLite/PostgreSQL dual support.

PrintOps defaults to SQLite (zero-config). When DATABASE_URL points to PostgreSQL,
these helpers ensure dialect-specific operations use the correct SQL.
"""

from sqlalchemy import func, text

_PG_ALREADY_APPLIED = frozenset({"42701", "42P07", "42710", "23505"})
_PG_UNDEFINED_COLUMN = "42703"


def is_postgres() -> bool:
    """Check if using PostgreSQL based on DATABASE_URL."""
    from backend.app.core.config import settings

    return settings.database_url.startswith("postgresql")


def is_sqlite() -> bool:
    """Check if using SQLite based on DATABASE_URL."""
    from backend.app.core.config import settings

    return settings.database_url.startswith("sqlite")


def postgres_connect_args(database_url: str, *, sqlite: bool) -> dict:
    """Pin PostgreSQL sessions to UTC while leaving SQLite untouched."""
    if sqlite:
        return {}
    if "+asyncpg" in database_url:
        return {"server_settings": {"timezone": "UTC"}}
    return {"options": "-c timezone=UTC"}


def sqlstate(exc: BaseException) -> str | None:
    """Return a SQLAlchemy-wrapped PostgreSQL SQLSTATE when available."""
    orig = getattr(exc, "orig", None)
    for attr in ("sqlstate", "pgcode"):
        code = getattr(orig, attr, None)
        if code:
            return str(code)
    return None


def is_already_applied(exc: BaseException, sql: str) -> bool:
    """Classify idempotent DDL by SQLSTATE, with SQLite's text fallback."""
    is_rename = "rename column" in sql.lower()
    state = sqlstate(exc)
    if state is not None:
        return state in _PG_ALREADY_APPLIED or (state == _PG_UNDEFINED_COLUMN and is_rename)

    message = str(exc).lower()
    if any(
        marker in message for marker in ("already exists", "duplicate key", "duplicate column name", "no such column")
    ):
        return True
    return is_rename and "column" in message and "does not exist" in message


async def upsert_setting(db, model, key: str, value: str):
    """Dialect-aware INSERT ... ON CONFLICT UPDATE for the Settings table."""
    if is_postgres():
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = pg_insert(model).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={"value": value, "updated_at": func.now()},
        )
    else:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        stmt = sqlite_insert(model).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"],
            set_={"value": value, "updated_at": func.now()},
        )
    await db.execute(stmt)


async def run_pragma(conn, pragma_sql: str):
    """Run a PRAGMA statement only on SQLite (no-op on PostgreSQL)."""
    if is_sqlite():
        await conn.execute(text(pragma_sql))
