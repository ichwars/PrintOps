"""Best-effort startup diagnostic for one worker's PostgreSQL pool ceiling."""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)
_PROBE_TIMEOUT_SECONDS = 5
_LIMITS_QUERY = text(
    "SELECT current_setting('max_connections'), "
    "current_setting('superuser_reserved_connections'), "
    "current_setting('reserved_connections', true)"
)


def _connection_limit(value: str) -> int:
    # PostgreSQL returns text. Reject malformed/oversized responses before
    # conversion; never include response values or exception text in logs.
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 10:
        raise ValueError("Invalid connection limit")
    result = int(value)
    if result > 2147483647:
        raise ValueError("Invalid connection limit")
    return result


async def _read_limits(engine: AsyncEngine) -> tuple[int, int]:
    async with engine.connect() as conn:
        maximum, superuser_reserved, role_reserved = (await conn.execute(_LIMITS_QUERY)).one()
    maximum = _connection_limit(maximum)
    reserved = _connection_limit(superuser_reserved)
    # reserved_connections is absent on older PostgreSQL versions. NULL from
    # current_setting(..., true) means absent, not a failed/restricted query.
    if role_reserved is not None:
        reserved += _connection_limit(role_reserved)
    if maximum <= reserved:
        raise ValueError("Invalid connection limits")
    return maximum, reserved


async def check_pool_fits_server() -> None:
    """Warn without changing pools or suppressing unrelated startup errors.

    This compares a per-process ceiling with the server's non-reserved slots,
    not free slots or a whole deployment's demand. Keep emergency reserves even
    if this connection's role has privileges to use them.
    """
    from backend.app.core import database

    if database.engine.dialect.name != "postgresql":
        return
    try:
        maximum, reserved = await asyncio.wait_for(_read_limits(database.engine), timeout=_PROBE_TIMEOUT_SECONDS)
    except Exception:
        # Do not log exception strings/tracebacks: drivers may include DSNs,
        # credentials or server-controlled text. Cancellation still propagates.
        logger.warning(
            "Could not read PostgreSQL connection limits; pool capacity check skipped. "
            "Check database access and server settings; startup continues."
        )
        return

    pool_size = database._pool_config["pool_size"]
    overflow = database._pool_config["max_overflow"]
    ceiling = pool_size + overflow
    available = maximum - reserved
    if ceiling > available:
        logger.warning(
            "PostgreSQL pool ceiling per worker is %d (pool_size %d + max_overflow %d), "
            "exceeding %d non-reserved connections (max_connections %d minus %d reserved). "
            "Lower DB_POOL_SIZE / DB_MAX_OVERFLOW or review server max_connections; "
            "account for all workers and other clients. Pool configuration is unchanged.",
            ceiling,
            pool_size,
            overflow,
            available,
            maximum,
            reserved,
        )
