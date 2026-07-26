import logging
from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from backend.app.core.db_dialect import is_sqlite

logger = logging.getLogger(__name__)

SafeExecute = Callable[[object, str], Awaitable[None]]


async def migrate_number_sequence_monthly_reset_policy(conn, safe_execute: SafeExecute) -> None:
    """Allow monthly reset policy in existing number sequence check constraints."""

    constraint_name = "ck_number_sequence_reset_policy"
    old_formula = "reset_policy IN ('none', 'yearly')"
    new_formula = "reset_policy IN ('none', 'yearly', 'monthly')"
    if is_sqlite():
        try:
            result = await conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='table' AND name='number_sequences'")
            )
            table_sql = result.scalar()
            if table_sql and old_formula in table_sql and new_formula not in table_sql:
                version_result = await conn.execute(text("PRAGMA schema_version"))
                schema_version = version_result.scalar() or 0
                await conn.execute(text("PRAGMA writable_schema = ON"))
                await conn.execute(
                    text(
                        "UPDATE sqlite_master "
                        "SET sql = replace(sql, :old_formula, :new_formula) "
                        "WHERE type = 'table' AND name = 'number_sequences'"
                    ),
                    {"old_formula": old_formula, "new_formula": new_formula},
                )
                await conn.execute(text(f"PRAGMA schema_version = {schema_version + 1}"))
                await conn.execute(text("PRAGMA writable_schema = OFF"))
        except (OperationalError, ProgrammingError) as exc:
            logger.error(
                "Failed to widen number_sequences.reset_policy constraint for monthly reset: %s",
                exc,
                exc_info=True,
            )
            raise
    else:
        await safe_execute(conn, f"ALTER TABLE number_sequences DROP CONSTRAINT IF EXISTS {constraint_name}")
        await safe_execute(conn, f"ALTER TABLE number_sequences ADD CONSTRAINT {constraint_name} CHECK ({new_formula})")
