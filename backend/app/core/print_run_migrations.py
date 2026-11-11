"""Add and conservatively backfill print-run metadata."""

from sqlalchemy import text


async def migrate_print_run_columns(conn, safe_execute):
    await safe_execute(conn, "ALTER TABLE print_archives ADD COLUMN plate_estimates JSON")
    await safe_execute(
        conn,
        "ALTER TABLE print_archives ADD COLUMN source_library_file_id INTEGER REFERENCES library_files(id) ON DELETE SET NULL",
    )
    await safe_execute(conn, "ALTER TABLE print_log_entries ADD COLUMN plate_id INTEGER")
    await safe_execute(conn, "ALTER TABLE print_log_entries ADD COLUMN subtask_id VARCHAR(64)")
    await safe_execute(conn, "ALTER TABLE print_log_entries ADD COLUMN ended_offline BOOLEAN")
    await safe_execute(conn, "ALTER TABLE print_log_entries ADD COLUMN timelapse_path VARCHAR(500)")
    await safe_execute(conn, "ALTER TABLE print_log_entries ADD COLUMN timelapse_baseline JSON")
    await safe_execute(conn, "ALTER TABLE print_log_entries ADD COLUMN photos JSON")
    await safe_execute(conn, "ALTER TABLE print_log_entries ADD COLUMN confirm_token_run_scoped BOOLEAN")
    energy_type = "REAL" if conn.dialect.name == "sqlite" else "DOUBLE PRECISION"
    await safe_execute(conn, f"ALTER TABLE print_log_entries ADD COLUMN energy_start_kwh {energy_type}")
    await safe_execute(conn, "ALTER TABLE print_log_entries ADD COLUMN energy_start_plug_id INTEGER")
    marker = "_backfill_print_log_plate_ids_done"
    params = {"key": marker}
    async with conn.begin_nested():
        migrated = await conn.scalar(text('SELECT value FROM settings WHERE "key" = :key'), params)
        if migrated is not None:
            return

        await conn.execute(
            text(
                "UPDATE print_log_entries AS run SET plate_id = ("
                "SELECT q.plate_id FROM print_queue q WHERE q.id = run.queue_item_id"
                ") WHERE run.plate_id IS NULL AND run.queue_item_id IS NOT NULL"
            )
        )
        # The archive holds the latest run's plate. A historical run can use
        # it only when its start time and printer identify the same print.
        await conn.execute(
            text(
                "UPDATE print_log_entries AS run SET plate_id = ("
                "SELECT a.plate_id FROM print_archives a WHERE a.id = run.archive_id "
                "AND a.printer_id = run.printer_id AND a.started_at = run.started_at "
                "AND a.deleted_at IS NULL AND a.status <> 'printing'"
                ") WHERE run.plate_id IS NULL AND run.archive_id IS NOT NULL AND run.started_at IS NOT NULL"
            )
        )
        await conn.execute(text("INSERT INTO settings (\"key\", value) VALUES (:key, '1')"), params)
