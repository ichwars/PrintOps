"""Apply the reviewed archival and queue delete rules on SQLite."""

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
_FTS_REBUILD_KEY = "_archive_fts_rebuilt_once"


def _rules(metadata: MetaData):
    for table, columns in _REFERENCES.items():
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


async def _sqlite_rules(conn: AsyncConnection, metadata: MetaData, rules) -> None:
    from backend.app.services.library_queue_references import release_queue_references

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
        name = quote(f"printops_delete_{parent}_refs")
        body = "\n".join(statements)
        await conn.exec_driver_sql(
            f"CREATE TRIGGER IF NOT EXISTS {name} AFTER DELETE ON {quote(parent)} BEGIN {body} END"
        )

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

    for child, parent, action in rules:
        missing = child.is_not(None) & ~exists().where(parent == child)
        if action == "CASCADE":
            await conn.execute(delete(child.table).where(missing))
        else:
            values = {column.key: column for column in child.table.c if column.onupdate is not None}
            values[child.key] = None
            await conn.execute(update(child.table).where(missing).values(values))


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


async def migrate_archive_relations(conn: AsyncConnection, metadata: MetaData) -> None:
    rules = tuple(_rules(metadata))
    if conn.dialect.name == "sqlite":
        await _sqlite_rules(conn, metadata, rules)
    elif conn.dialect.name == "postgresql":
        await _postgres_rules(conn, rules)
