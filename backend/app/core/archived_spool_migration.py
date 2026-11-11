"""Release references left by spools archived before slot cleanup existed."""

from sqlalchemy import text


async def release_slots_of_archived_spools(conn) -> None:
    async with conn.begin_nested():
        await conn.execute(
            text("DELETE FROM spool_assignment WHERE spool_id IN (SELECT id FROM spool WHERE archived_at IS NOT NULL)")
        )
