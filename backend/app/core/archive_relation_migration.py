"""Apply archival, queue, and production delete rules."""

from collections import defaultdict

from sqlalchemy import delete, exists, inspect, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql.schema import MetaData

# Only relationships whose deletion behavior matches the application. The queue's
# direct library-file source is released by the service so runs and batches survive.
_REFERENCES = {
    "active_print_spoolman": ("archive_id",),
    "library_file_tags": ("file_id",),
    "library_files": ("project_id",),
    "library_folders": ("archive_id", "project_id"),
    "pending_uploads": ("archived_id", "project_id"),
    "pipeline_jobs": ("queue_entry_id",),
    "pipeline_runs": ("source_archive_id", "source_library_file_id", "sliced_library_file_id"),
    "print_archives": ("project_id",),
    "print_batch_plates": ("batch_id",),
    "print_batches": ("archive_id", "library_file_id", "project_id"),
    "print_log_entries": ("archive_id", "created_by_id", "project_id", "queue_item_id"),
    "print_queue": ("archive_id", "batch_id", "project_id"),
    "print_queue_variants": ("library_file_id", "queue_item_id"),
    "project_bom_items": ("archive_id", "project_id"),
    "spool_refill_events": ("spool_id",),
    "spool_usage_history": ("printer_id",),
    "telegram_quality_messages": ("archive_id",),
}
_SQLITE_PRODUCTION_PROJECT_REFERENCES = {
    "project_production_outputs": ("project_id",),
    "project_production_receipts": ("project_id",),
}
_FTS_REBUILD_KEY = "_archive_fts_rebuilt_once"


def _rules(metadata: MetaData, references):
    for table, columns in references.items():
        for name in columns:
            column = metadata.tables[table].c[name]
            (key,) = column.foreign_keys
            if key.ondelete not in ("CASCADE", "SET NULL") or key.column.name != "id":
                raise RuntimeError(f"Unexpected delete rule for {column}")
            yield column, key.column, key.ondelete


async def rebuild_legacy_archive_fts(conn: AsyncConnection) -> None:
    available = await conn.scalar(text("SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'archive_fts'"))
    if not available:
        return
    claimed = await conn.scalar(
        text("INSERT INTO settings (key, value) VALUES (:key, 'true') ON CONFLICT (key) DO NOTHING RETURNING key"),
        {"key": _FTS_REBUILD_KEY},
    )
    if claimed:
        await conn.exec_driver_sql("INSERT INTO archive_fts(archive_fts) VALUES ('rebuild')")


async def _create_sqlite_delete_triggers(conn: AsyncConnection, rules, suffix: str) -> None:
    quote = conn.dialect.identifier_preparer.quote_identifier
    statements_by_parent = defaultdict(list)
    for child, parent, action in rules:
        table = quote(child.table.name)
        name = quote(child.name)
        # The identifiers are dialect-quoted ORM metadata.
        if action == "CASCADE":
            delete_statement = f"DELETE FROM {table}"  # nosec B608
        else:
            delete_statement = f"UPDATE {table} SET {name} = NULL"  # nosec B608
        statements_by_parent[parent.table.name].append(f"{delete_statement} WHERE {name} = OLD.id;")
    for parent, statements in statements_by_parent.items():
        name = quote(f"printops_delete_{parent}_{suffix}")
        body = "\n".join(statements)
        await conn.exec_driver_sql(
            f"CREATE TRIGGER IF NOT EXISTS {name} AFTER DELETE ON {quote(parent)} BEGIN {body} END"
        )


async def _sqlite_rules(conn: AsyncConnection, metadata: MetaData, rules) -> None:
    from backend.app.services.library_queue_references import release_queue_references

    production_rules = tuple(_rules(metadata, _SQLITE_PRODUCTION_PROJECT_REFERENCES))
    await _create_sqlite_delete_triggers(conn, rules, "refs")
    # Older installs already have the projects trigger. Add a companion trigger.
    await _create_sqlite_delete_triggers(conn, production_rules, "production_refs")
    await conn.exec_driver_sql("""
        CREATE TRIGGER IF NOT EXISTS printops_restrict_delete_booked_runs BEFORE DELETE ON print_log_entries
        WHEN EXISTS (SELECT 1 FROM project_production_receipts WHERE run_id = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'Print run is linked to a production receipt');
        END
    """)

    queue = metadata.tables["print_queue"]
    files = metadata.tables["library_files"]
    missing_source = queue.c.library_file_id.is_not(None) & ~exists().where(files.c.id == queue.c.library_file_id)
    # A failed NAS rescan on an older release can leave many missing file IDs.
    while vanished := (
        await conn.scalars(select(queue.c.library_file_id).where(missing_source).distinct().limit(400))
    ).all():
        await release_queue_references(conn, vanished)
    # Older versions may have dropped an archive already while a run was active.
    archives = metadata.tables["print_archives"]
    missing_archive = queue.c.archive_id.is_not(None) & ~exists().where(archives.c.id == queue.c.archive_id)
    await conn.execute(update(queue).where(missing_archive, queue.c.status == "printing").values(archive_id=None))

    for child, parent, action in (*rules, *production_rules):
        missing = child.is_not(None) & ~exists().where(parent == child)
        if action == "CASCADE":
            await conn.execute(delete(child.table).where(missing))
        else:
            values = {column.key: column for column in child.table.c if column.onupdate is not None}
            values[child.key] = None
            await conn.execute(update(child.table).where(missing).values(values))

    # Preserve the ledger and receipt when a pre-upgrade deletion left a missing run.
    receipts = metadata.tables["project_production_receipts"]
    runs = metadata.tables["print_log_entries"]
    missing_run = receipts.c.run_id.is_not(None) & ~exists().where(runs.c.id == receipts.c.run_id)
    await conn.execute(update(receipts).where(missing_run).values(run_id=None))


def _fk_map(sync):
    return inspect(sync).get_multi_foreign_keys()


async def _postgres_rules(conn: AsyncConnection, rules) -> None:
    foreign_keys = await conn.run_sync(_fk_map)
    quote = conn.dialect.identifier_preparer.quote_identifier
    for child, parent, action in rules:
        if action != "SET NULL":
            continue
        table = child.table.name
        if any(fk["constrained_columns"] == [child.name] for fk in foreign_keys.get((None, table), ())):
            continue
        # A second upgrade process may have added this constraint while we waited.
        await conn.exec_driver_sql(f"LOCK TABLE {quote(table)} IN SHARE ROW EXCLUSIVE MODE")
        existing = await conn.run_sync(lambda sync, name=table: inspect(sync).get_foreign_keys(name))
        if any(fk["constrained_columns"] == [child.name] for fk in existing):
            continue
        missing = child.is_not(None) & ~exists().where(parent == child)
        values = {column.key: column for column in child.table.c if column.onupdate is not None}
        values[child.key] = None
        await conn.execute(update(child.table).where(missing).values(values))
        await conn.exec_driver_sql(
            f"ALTER TABLE {quote(table)} ADD FOREIGN KEY ({quote(child.name)}) "
            f"REFERENCES {quote(parent.table.name)} (id) ON DELETE SET NULL"
        )


def _postgres_production_run_fk(sync):
    return next(
        (
            fk
            for fk in inspect(sync).get_foreign_keys("project_production_receipts")
            if fk["constrained_columns"] == ["run_id"] and fk["referred_table"] == "print_log_entries"
        ),
        None,
    )


async def _postgres_protect_booked_runs(conn: AsyncConnection) -> None:
    existing = await conn.run_sync(_postgres_production_run_fk)
    if existing is not None and existing["options"].get("ondelete") == "RESTRICT":
        return
    # Serialize concurrent upgrades before changing the constraint.
    await conn.exec_driver_sql("LOCK TABLE project_production_receipts IN ACCESS EXCLUSIVE MODE")
    existing = await conn.run_sync(_postgres_production_run_fk)
    if existing is not None and existing["options"].get("ondelete") == "RESTRICT":
        return
    if existing is not None and existing["name"] is not None:
        name = conn.dialect.identifier_preparer.quote_identifier(existing["name"])
        await conn.exec_driver_sql(f"ALTER TABLE project_production_receipts DROP CONSTRAINT {name}")
    await conn.exec_driver_sql("""
        ALTER TABLE project_production_receipts
        ADD CONSTRAINT project_production_receipts_run_id_fkey
        FOREIGN KEY (run_id) REFERENCES print_log_entries (id) ON DELETE RESTRICT
    """)


async def migrate_archive_relations(conn: AsyncConnection, metadata: MetaData) -> None:
    rules = tuple(_rules(metadata, _REFERENCES))
    if conn.dialect.name == "sqlite":
        await _sqlite_rules(conn, metadata, rules)
    elif conn.dialect.name == "postgresql":
        await _postgres_rules(conn, rules)
        await _postgres_protect_booked_runs(conn)
