"""One-shot repair for legacy RFID spools with demonstrably wrong tare."""

import logging

from sqlalchemy import bindparam, text

from backend.app.utils.spool_core_weights import BAMBU_RFID_CORE_CATALOG_NAME, BAMBU_RFID_CORE_WEIGHT

logger = logging.getLogger(__name__)

RFID_CORE_WEIGHT_REPAIR_FLAG = "_printops_137_rfid_core_weight_done"


async def repair_rfid_core_weights(conn) -> None:
    """Repair untouched auto-created rows once while preserving user edits.

    The broken creator stored a weight from an arbitrary Bambu catalog row and
    left ``core_weight_catalog_id`` empty. Requiring that exact signature keeps
    rows saved through the editor, manual rows, and custom tares out of scope.
    """
    async with conn.begin_nested():
        already = (
            await conn.execute(
                text('SELECT value FROM settings WHERE "key" = :key'),
                {"key": RFID_CORE_WEIGHT_REPAIR_FLAG},
            )
        ).scalar_one_or_none()
        if already:
            return

        correct = (
            await conn.execute(
                text("SELECT id, weight FROM spool_catalog WHERE UPPER(name) = :name ORDER BY id LIMIT 1"),
                {"name": BAMBU_RFID_CORE_CATALOG_NAME.upper()},
            )
        ).fetchone()
        correct_id = correct[0] if correct else None
        correct_weight = correct[1] if correct else BAMBU_RFID_CORE_WEIGHT
        bambu_weights = {
            row[0]
            for row in (
                await conn.execute(
                    text("SELECT weight FROM spool_catalog WHERE UPPER(name) LIKE :prefix"),
                    {"prefix": "BAMBU LAB%"},
                )
            ).fetchall()
        }
        wrong_weights = sorted(bambu_weights - {correct_weight})
        repaired = reweighed = 0
        if wrong_weights:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, core_weight, label_weight, weight_used, last_weighed_at FROM spool "
                        "WHERE data_origin = 'rfid_auto' AND tag_type = 'bambulab' "
                        "AND core_weight_catalog_id IS NULL AND core_weight IN :wrong"
                    ).bindparams(bindparam("wrong", expanding=True)),
                    {"wrong": wrong_weights},
                )
            ).fetchall()
            for row in rows:
                used = row.weight_used or 0.0
                if row.last_weighed_at is not None:
                    used = min(max(0.0, used + correct_weight - row.core_weight), float(row.label_weight or 0))
                    reweighed += 1
                await conn.execute(
                    text(
                        "UPDATE spool SET core_weight = :weight, core_weight_catalog_id = :catalog_id, "
                        "weight_used = :used WHERE id = :id"
                    ),
                    {"weight": correct_weight, "catalog_id": correct_id, "used": used, "id": row.id},
                )
                repaired += 1
        if repaired:
            logger.info(
                "[#137] Corrected %d untouched RFID spool tare(s) to %d g; adjusted %d weighed spool(s)",
                repaired,
                correct_weight,
                reweighed,
            )
        await conn.execute(
            text('INSERT INTO settings ("key", value) VALUES (:key, :value)'),
            {"key": RFID_CORE_WEIGHT_REPAIR_FLAG, "value": "true"},
        )
