"""Retain calibration rows while widening the old Spoolman uniqueness scope."""

from sqlalchemy import MetaData, inspect, text
from sqlalchemy.schema import CreateIndex, CreateTable


async def _unique_constraints(conn, table_name):
    return await conn.run_sync(lambda sync: inspect(sync).get_unique_constraints(table_name))


async def _rebuild_sqlite(conn, table):
    """Copy every row/ID/FK and explicit index inside the caller's savepoint."""
    metadata = MetaData()
    for foreign_key in table.foreign_keys:
        foreign_key.column.table.to_metadata(metadata)
    staged = table.to_metadata(metadata, name=f"{table.name}_context_v2")
    old_indexes = (
        (
            await conn.execute(
                text("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=:table AND sql IS NOT NULL"),
                {"table": table.name},
            )
        )
        .scalars()
        .all()
    )
    await conn.execute(CreateTable(staged))
    columns = ", ".join(conn.dialect.identifier_preparer.quote(c.name) for c in table.columns)
    await conn.execute(text(f"INSERT INTO {staged.name} ({columns}) SELECT {columns} FROM {table.name}"))
    original = (await conn.execute(text(f"SELECT count(*) FROM {table.name}"))).scalar_one()
    copied = (await conn.execute(text(f"SELECT count(*) FROM {staged.name}"))).scalar_one()
    if original != copied:
        raise RuntimeError("K-profile context migration copied an unexpected row count")
    await conn.execute(text(f"DROP TABLE {table.name}"))
    await conn.execute(text(f"ALTER TABLE {staged.name} RENAME TO {table.name}"))
    for sql in old_indexes:
        await conn.execute(text(sql))


async def migrate_spool_k_profile_contexts(conn):
    """Idempotent on fresh, legacy and restored SQLite/PostgreSQL databases.

    Only the four-column Spoolman UNIQUE is removed. No stored nozzle value is
    rewritten; HS/HH are indexed from explicit prefixes and unknown stays NULL.
    Errors roll back the entire migration, preserving all source rows.
    """
    from backend.app.models.spool_k_profile import SpoolKProfile
    from backend.app.models.spoolman_k_profile import SpoolmanKProfile

    async with conn.begin_nested():
        for model in (SpoolKProfile, SpoolmanKProfile):
            table = model.__table__
            await conn.run_sync(lambda sync, table=table: table.create(sync, checkfirst=True))
            if model is SpoolmanKProfile:
                legacy_columns = {"spoolman_spool_id", "printer_id", "extruder", "nozzle_diameter"}
                old = [
                    c for c in await _unique_constraints(conn, table.name) if set(c["column_names"]) == legacy_columns
                ]
                if old and conn.dialect.name == "sqlite":
                    await _rebuild_sqlite(conn, table)
                elif old:
                    quote = conn.dialect.identifier_preparer.quote
                    for constraint in old:
                        await conn.execute(
                            text(f"ALTER TABLE {quote(table.name)} DROP CONSTRAINT {quote(constraint['name'])}")
                        )
            for index in table.indexes:
                await conn.execute(CreateIndex(index, if_not_exists=True))
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_spoolman_k_profile_spool ON spoolman_k_profile (spoolman_spool_id)")
        )


def validate_restore_contexts(source):
    """Reject ambiguous explicit flows before PostgreSQL's conflict-ignore import.

    Unknown legacy duplicates remain valid backup data. A collision in the new
    reported-flow index must not silently discard rows during cross-DB restore.
    """
    for table, key in [("spool_k_profile", "spool_id"), ("spoolman_k_profile", "spoolman_spool_id")]:
        columns = {row[1] for row in source.execute(f"PRAGMA table_info({table})")}
        if not {key, "printer_id", "extruder", "nozzle_diameter", "nozzle_type"}.issubset(columns):
            continue
        prefix = "upper(substr(trim(nozzle_type),1,2))"
        duplicate = source.execute(
            f"SELECT 1 FROM {table} WHERE {prefix} IN ('HS','HH') "
            f"GROUP BY {key},printer_id,extruder,nozzle_diameter,{prefix} HAVING count(*) > 1 LIMIT 1"
        ).fetchone()
        if duplicate:
            raise ValueError("Backup contains ambiguous K-profile reported flow contexts; resolve duplicates first")
