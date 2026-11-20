"""Migrate legacy H3C queue slot identifiers once."""

import logging

logger = logging.getLogger(__name__)

H3C_QUEUE_TRAY_MIGRATION_KEY = "_migrate_h3c_queue_tray_ids_done"


async def _migrate_h3c_queue_tray_ids(conn) -> None:
    """Renumber the AMS 3H slots of queued H3C jobs from 128 + k to Studio's 28 + k.

    PrintOps without H3C support numbered the AMS 3H (unit 32) as
    ``32 * 4 + k``, the AMS-HT range, so an H3C job queued then carries 128-136
    where the slot is now 28-36. Only jobs for an H3C (its printer, or
    target_model H3C) are touched; the H3C has no AMS-HT, so 128-136 there can
    only mean that. Once only, gated by a settings flag, so a mapping written
    afterwards is never rewritten.
    """
    import json

    from sqlalchemy import text

    from backend.app.utils.tray_ids import AMS3H_UNIT_ID, RACK_SLOT_COUNT, TrayLayout, legacy_tray_index

    old_base = legacy_tray_index(AMS3H_UNIT_ID, 0)  # 128
    ams3h = TrayLayout.ams3h()
    flag = H3C_QUEUE_TRAY_MIGRATION_KEY
    async with conn.begin_nested():
        already = (
            await conn.execute(text('SELECT value FROM settings WHERE "key" = :k'), {"k": flag})
        ).scalar_one_or_none()
        if already is not None:
            return
        targets = (
            (
                "print_queue",
                "q.ams_mapping IS NOT NULL AND (UPPER(q.target_model) IN ('H3C', 'N10') "
                "OR q.printer_id IN (SELECT id FROM printers WHERE UPPER(model) IN ('H3C', 'N10')))",
            ),
            ("print_queue_variants", "q.ams_mapping IS NOT NULL AND UPPER(q.target_model) IN ('H3C', 'N10')"),
        )
        renumbered = 0
        for table, where in targets:
            query = f"SELECT q.id, q.ams_mapping FROM {table} q WHERE {where}"  # nosec B608 -- table and filter from the fixed targets above
            rows = (await conn.execute(text(query))).all()
            for row_id, raw in rows:
                try:
                    mapping = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(mapping, list):
                    continue
                new = [
                    ams3h.global_tray_id(AMS3H_UNIT_ID, v - old_base)
                    if type(v) is int and old_base <= v < old_base + RACK_SLOT_COUNT
                    else v
                    for v in mapping
                ]
                if new != mapping:
                    await conn.execute(
                        text(f"UPDATE {table} SET ams_mapping = :m WHERE id = :id"),  # nosec B608 -- table from the fixed targets above
                        {"m": json.dumps(new), "id": row_id},
                    )
                    renumbered += 1
        if renumbered:
            logger.info("Renumbered the AMS 3H slots of %d queued H3C job(s) to Bambu Studio's 28-36", renumbered)
        await conn.execute(text('INSERT INTO settings ("key", value) VALUES (:k, :v)'), {"k": flag, "v": "true"})
