"""Recover archive links only from print-log schemas that predate those links."""

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection


async def has_legacy_print_log(conn: AsyncConnection) -> bool:
    columns = await conn.run_sync(lambda sync: inspect(sync).get_columns("print_log_entries"))
    return all(column["name"] != "archive_id" for column in columns)


async def backfill_legacy_print_log(conn: AsyncConnection) -> None:
    """Give pre-link log entries their archive and its latest run's measured costs."""
    async with conn.begin_nested():
        await conn.execute(
            text("""
            UPDATE print_log_entries
            SET archive_id = (
                SELECT a.id
                FROM print_archives a
                WHERE a.print_name = print_log_entries.print_name
                  AND (
                      a.printer_id = print_log_entries.printer_id
                      OR (a.printer_id IS NULL AND print_log_entries.printer_id IS NULL)
                  )
                ORDER BY a.id DESC
                LIMIT 1
            )
            WHERE archive_id IS NULL AND print_name IS NOT NULL
        """)
        )

        # Before per-run costs, the archive carried the latest run's values.
        # Keep existing measured costs and fill at most one run per archive.
        await conn.execute(
            text("""
            UPDATE print_log_entries
            SET cost = (SELECT cost FROM print_archives WHERE id = print_log_entries.archive_id),
                energy_kwh = (SELECT energy_kwh FROM print_archives WHERE id = print_log_entries.archive_id),
                energy_cost = (SELECT energy_cost FROM print_archives WHERE id = print_log_entries.archive_id)
            WHERE id IN (
                SELECT MAX(id)
                FROM print_log_entries
                WHERE archive_id IS NOT NULL
                GROUP BY archive_id
                HAVING SUM(CASE WHEN cost IS NOT NULL THEN 1 ELSE 0 END) = 0
            )
        """)
        )
