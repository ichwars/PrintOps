"""A restart keeps permission removals while older versions still get their upgrade grants."""

import pytest
from sqlalchemy import delete, select

from backend.app.core.database import seed_default_groups
from backend.app.core.permissions import ALL_PERMISSIONS
from backend.app.models.group import Group
from backend.app.models.settings import Settings

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_CASES = [
    (
        "_backfill_446_clear_plate_permission_done",
        "printers:clear_plate",
        ["printers:control"],
        {"printers:clear_plate"},
    ),
    (
        "_backfill_1099_makerworld_permissions_done",
        "makerworld:view",
        ["library:upload"],
        {"makerworld:view", "makerworld:import"},
    ),
    (
        "_backfill_1184_forecast_permissions_done",
        "inventory:forecast_read",
        ["inventory:read", "inventory:update"],
        {"inventory:forecast_read", "inventory:forecast_write"},
    ),
    (
        "_backfill_1425_pipeline_permissions_done",
        "pipelines:read",
        ["library:read_own"],
        {"pipelines:read"},
    ),
]


@pytest.mark.parametrize(("flag", "representative", "original", "grants"), _CASES)
@pytest.mark.parametrize("previously_shipped", [True, False])
async def test_grants_are_migrated_only_when_the_installed_version_needs_them(
    async_client, db_session, flag, representative, original, grants, previously_shipped
):
    admin = await db_session.scalar(select(Group).where(Group.name == "Administrators"))
    custom = Group(name="Custom workshop", permissions=original)
    db_session.add(custom)
    await db_session.execute(delete(Settings).where(Settings.key == flag))
    if not previously_shipped:
        admin.permissions = [permission for permission in admin.permissions if permission != representative]
    await db_session.commit()

    await seed_default_groups()

    await db_session.refresh(custom)
    expected = set(original) if previously_shipped else set(original) | grants
    assert set(custom.permissions) == expected
    assert await db_session.scalar(select(Settings.value).where(Settings.key == flag)) == "true"
    await db_session.refresh(admin)
    assert set(ALL_PERMISSIONS) <= set(admin.permissions)

    custom.permissions = original
    await db_session.commit()
    await seed_default_groups()
    await seed_default_groups()

    await db_session.refresh(custom)
    assert custom.permissions == original


async def test_reset_preserves_the_permission_migration_markers(async_client, db_session):
    response = await async_client.post("/api/v1/settings/reset")
    assert response.status_code == 200, response.text
    flags = await db_session.scalars(select(Settings.key).where(Settings.key.in_([case[0] for case in _CASES])))
    assert set(flags) == {case[0] for case in _CASES}
