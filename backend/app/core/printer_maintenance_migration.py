"""Repair duplicate printer maintenance assignments before enforcing uniqueness."""

from sqlalchemy import text


async def migrate_printer_maintenance(conn) -> None:
    if conn.dialect.name == "postgresql":
        await conn.execute(text("LOCK TABLE printer_maintenance IN SHARE ROW EXCLUSIVE MODE"))
    rows = (
        await conn.execute(
            text(
                "SELECT id, printer_id, maintenance_type_id FROM printer_maintenance "
                "WHERE (printer_id, maintenance_type_id) IN ("
                "SELECT printer_id, maintenance_type_id FROM printer_maintenance "
                "GROUP BY printer_id, maintenance_type_id HAVING COUNT(*) > 1) "
                "ORDER BY printer_id, maintenance_type_id, "
                "last_performed_at IS NULL, last_performed_at DESC, id DESC"
            )
        )
    ).all()

    retained: dict[tuple[int, int], int] = {}
    for row in rows:
        keeper = retained.setdefault((row.printer_id, row.maintenance_type_id), row.id)
        if row.id == keeper:
            continue
        await conn.execute(
            text(
                "UPDATE maintenance_history SET printer_maintenance_id = :keeper "
                "WHERE printer_maintenance_id = :duplicate"
            ),
            {"keeper": keeper, "duplicate": row.id},
        )
        await conn.execute(text("DELETE FROM printer_maintenance WHERE id = :duplicate"), {"duplicate": row.id})

    await conn.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_printer_maintenance_printer_type "
            "ON printer_maintenance (printer_id, maintenance_type_id)"
        )
    )
