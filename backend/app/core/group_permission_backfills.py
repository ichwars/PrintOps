"""One-time migrations for grants to existing custom groups."""

import logging
from collections.abc import Sequence

from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.group import Group
from backend.app.models.settings import Settings

logger = logging.getLogger(__name__)

_BACKFILLS = (
    (
        "_backfill_446_clear_plate_permission_done",
        "printers:clear_plate",
        (("printers:control", ("printers:clear_plate",)),),
    ),
    (
        "_backfill_1099_makerworld_permissions_done",
        "makerworld:view",
        (("library:upload", ("makerworld:view", "makerworld:import")), ("library:read", ("makerworld:view",))),
    ),
    (
        "_backfill_1184_forecast_permissions_done",
        "inventory:forecast_read",
        (("inventory:read", ("inventory:forecast_read",)), ("inventory:update", ("inventory:forecast_write",))),
    ),
    (
        "_backfill_1425_pipeline_permissions_done",
        "pipelines:read",
        (("library:read_own", ("pipelines:read",)), ("settings:read", ("pipelines:read",))),
    ),
)


GROUP_PERMISSION_BACKFILL_KEYS = tuple(flag for flag, _, _ in _BACKFILLS)


async def apply_legacy_group_grants(
    session: AsyncSession, groups: Sequence[Group], previous_admin_permissions: set[str]
) -> None:
    """Commit the grants and their markers together with default-group seeding."""
    insert = postgres_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    for flag, permission, rules in _BACKFILLS:
        claim = (
            insert(Settings)
            .values(key=flag, value="true")
            .on_conflict_do_nothing(index_elements=[Settings.key])
            .returning(Settings.key)
        )
        claimed = await session.scalar(claim)
        if claimed is None or permission in previous_admin_permissions:
            continue

        for group in groups:
            if not group.permissions:
                continue
            current = set(group.permissions)
            grants = {grant for trigger, granted in rules if trigger in current for grant in granted}
            if permission == "pipelines:read" and group.name == "Operators":
                grants.update(("pipelines:read", "pipelines:write", "pipelines:run"))
            if missing := sorted(grants - current):
                group.permissions = [*group.permissions, *missing]
                logger.info("Backfilled %s for group '%s'", ", ".join(missing), group.name)
