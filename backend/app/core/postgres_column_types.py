"""Convert the legacy PostgreSQL column types used by active prints and inventory."""

import json
import logging

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

logger = logging.getLogger(__name__)

_TYPES = (
    ("active_print_sessions", "spool_change_log", "text", "JSON"),
    ("active_print_spoolman", "tray_remain_start", "text", "JSON"),
    ("smart_plugs", "rest_energy_total_multiplier", "real", "DOUBLE PRECISION"),
    ("spool", "weight_used_baseline", "real", "DOUBLE PRECISION"),
)
_JSON_KEYS = {"active_print_sessions": "printer_id", "active_print_spoolman": "id"}
_GET_TYPE = text("""
    SELECT data_type FROM information_schema.columns
    WHERE table_schema = current_schema() AND table_name = :table AND column_name = :column
""")


def _invalid_constant(value: str):
    raise ValueError(f"{value} is not JSON")


async def _convert_active_print_json(conn: AsyncConnection, table: str, column: str) -> None:
    # Identifiers are selected only from _TYPES and _JSON_KEYS.
    key = _JSON_KEYS[table]
    rows = await conn.exec_driver_sql(
        f"SELECT {key}, {column} FROM {table} WHERE {column} IS NOT NULL"  # noqa: S608  # nosec B608
    )
    invalid_ids = []
    for row_id, value in rows:
        try:
            json.loads(value, parse_constant=_invalid_constant)
        except (ValueError, RecursionError):
            invalid_ids.append(row_id)
    if invalid_ids:
        sql = f"UPDATE {table} SET {column} = NULL WHERE {key} IN :ids"  # noqa: S608  # nosec B608
        await conn.execute(text(sql).bindparams(bindparam("ids", expanding=True)), {"ids": invalid_ids})
        logger.warning("Cleared %d invalid active-print %s values during PostgreSQL upgrade", len(invalid_ids), column)
    await conn.exec_driver_sql(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
    await conn.exec_driver_sql(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE JSON USING {column}::json")


async def _widen_float(conn: AsyncConnection, table: str, column: str, new_type: str) -> None:
    previous = await conn.scalar(text("SHOW extra_float_digits"))
    await conn.exec_driver_sql("SET LOCAL extra_float_digits = 1")
    try:
        # PostgreSQL formats real as the shortest decimal that reads back as the
        # same float4. Widen from that decimal without exposing float4 noise.
        async with conn.begin_nested():
            await conn.exec_driver_sql(
                f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type} USING {column}::text::double precision"
            )
    finally:
        await conn.execute(text("SELECT set_config('extra_float_digits', :previous, true)"), {"previous": previous})


async def migrate_postgres_column_types(conn: AsyncConnection) -> None:
    if conn.dialect.name != "postgresql":
        return
    for table, column, old_type, new_type in _TYPES:
        params = {"table": table, "column": column}
        if await conn.scalar(_GET_TYPE, params) != old_type:
            continue
        # Another startup can finish the type change while this one waits.
        await conn.exec_driver_sql(f"LOCK TABLE {table} IN ACCESS EXCLUSIVE MODE")
        if await conn.scalar(_GET_TYPE, params) != old_type:
            continue
        if new_type == "JSON":
            await _convert_active_print_json(conn, table, column)
        else:
            await _widen_float(conn, table, column, new_type)
