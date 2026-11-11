import logging

import pytest
from sqlalchemy import select

from backend.app.core.auth import create_access_token
from backend.app.core.filament_color_migration import migrate_silk_plus_colors
from backend.app.core.permissions import Permission
from backend.app.models.color_catalog import ColorCatalogEntry
from backend.app.models.group import Group
from backend.app.models.settings import Settings
from backend.app.models.spool import Spool
from backend.app.models.user import User
from backend.app.services.color_catalog_lookup import resolve_bambu_color
from backend.tests.integration.test_media_tokens import _admin_token
from backend.tests.integration.test_reprint_archive_lifecycle import quiet_start  # noqa: F401


async def test_silk_plus_migration_changes_only_shipped_defaults_and_unnamed_rfid(db_session):
    rows = [
        ColorCatalogEntry(
            manufacturer="Bambu Lab", color_name="Titan Gray", hex_color="#5F6367", material="PLA Silk", is_default=True
        ),
        ColorCatalogEntry(
            manufacturer="Bambu Lab", color_name="Custom silver", hex_color="#C8C8C8", material="PLA Silk"
        ),
    ]
    spools = [
        Spool(
            material="PLA",
            subtype="Silk+",
            brand="Bambu Lab",
            color_name=name,
            rgba="5F6367FF",
            data_origin="rfid_auto",
        )
        for name in (None, "My gray")
    ]
    db_session.add_all([*rows, *spools])
    await db_session.flush()
    conn = await db_session.connection()
    await migrate_silk_plus_colors(conn)
    await migrate_silk_plus_colors(conn)

    color = await resolve_bambu_color(db_session, "5F6367FF", "PLA Silk+")
    assert color is not None and color.name == "Titan Gray"
    assert list(await db_session.scalars(select(ColorCatalogEntry.material).order_by(ColorCatalogEntry.id))) == [
        "PLA Silk+",
        "PLA Silk",
    ]
    assert list(await db_session.scalars(select(Spool.color_name).order_by(Spool.id))) == ["Titan Gray", "My gray"]


async def test_default_printer_setting_is_hidden_from_users_outside_its_scope(
    async_client, db_session, printer_factory
):
    first, second = await printer_factory(), await printer_factory()
    admin = await _admin_token(async_client, "ui_default_printer")
    db_session.add_all(
        [
            Settings(key="default_printer_id", value=str(second.id)),
            User(
                username="limited_default_printer",
                allowed_printer_ids=[first.id],
                groups=[Group(name="Printer reader", permissions=[Permission.PRINTERS_READ.value])],
            ),
        ]
    )
    await db_session.commit()

    async def visible_default(token):
        result = await async_client.get("/api/v1/settings/ui-flags", headers={"Authorization": f"Bearer {token}"})
        assert result.status_code == 200, result.text
        return result.json()["default_printer_id"]

    assert await visible_default(admin) == second.id
    assert await visible_default(create_access_token({"sub": "limited_default_printer"})) is None


async def test_null_mandatory_archive_fields_are_ignored_and_notes_can_be_cleared(
    async_client, archive_factory, printer_factory
):
    printer = await printer_factory()
    archive = await archive_factory(printer.id, notes="Notes", quantity=4, is_favorite=True)
    result = await async_client.patch(
        f"/api/v1/archives/{archive.id}", json={"quantity": None, "is_favorite": None, "notes": None}
    )
    assert result.status_code == 200, result.text
    assert result.json()["quantity"] == 4 and result.json()["is_favorite"] is True
    assert result.json()["notes"] is None


@pytest.mark.parametrize(
    ("global_enabled", "printer_enabled", "reason"),
    [(False, True, "global auto-archive"), (True, False, "auto-archive for printer")],
)
async def test_archive_switch_skips_external_jobs_but_tracks_dispatched_jobs(
    quiet_start, db_session, printer_factory, archive_factory, caplog, global_enabled, printer_enabled, reason
):
    from backend.app import main
    from backend.app.models.archive import PrintArchive

    printer = await printer_factory(auto_archive=printer_enabled)
    db_session.add(Settings(key="auto_archive", value=str(global_enabled).lower()))
    await db_session.commit()

    with caplog.at_level(logging.INFO, logger="backend.app.main"):
        await main.on_print_start(printer.id, {"filename": "external.gcode.3mf", "subtask_id": "ext"})
    assert reason in caplog.text
    assert list(await db_session.scalars(select(PrintArchive.id))) == []

    archive = await archive_factory(printer.id, with_run=False, filename="expected.gcode.3mf", status="archived")
    main.register_expected_print(printer.id, archive.filename, archive.id)
    await main.on_print_start(printer.id, {"filename": archive.filename, "subtask_id": "expected"})
    await db_session.refresh(archive)
    assert archive.status == "printing"
