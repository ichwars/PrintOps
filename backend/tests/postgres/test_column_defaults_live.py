"""Older PostgreSQL defaults converge without granting permissions or device actions."""

import os
from unittest.mock import patch

import pytest
from sqlalchemy import inspect, select, text

POSTGRES_URL = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="live PostgreSQL test URL not configured")


@pytest.fixture
async def isolated_app_engine():
    from backend.app.core import database

    try:
        yield
    finally:
        await database.engine.dispose()


async def test_legacy_postgres_columns_keep_existing_denials_and_converge(isolated_app_engine):
    from backend.app.core import database, postgres_column_defaults
    from backend.app.models.api_key import APIKey
    from backend.app.models.oidc_provider import OIDCProvider
    from backend.app.models.print_queue import PrintQueueItem
    from backend.app.models.smart_plug import SmartPlug

    assert database.settings.database_url == POSTGRES_URL
    await database.init_db()
    async with database.engine.begin() as conn:
        await conn.exec_driver_sql("""
            ALTER TABLE api_keys ALTER COLUMN can_manage_projects DROP NOT NULL,
            ALTER COLUMN can_manage_projects SET DEFAULT true
        """)
        await conn.exec_driver_sql("ALTER TABLE oidc_providers ALTER COLUMN email_claim DROP NOT NULL")
        await conn.exec_driver_sql("ALTER TABLE print_queue ALTER COLUMN bed_levelling DROP NOT NULL")
        await conn.exec_driver_sql("ALTER TABLE smart_plugs ALTER COLUMN controls_printer_power DROP NOT NULL")

        fixture_keys = [
            {
                "name": "Null grant",
                "key_hash": "fixture-hash-null",
                "key_prefix": "fixture1",
                "can_manage_projects": None,
            },
            {
                "name": "Explicit grant",
                "key_hash": "fixture-hash-true",
                "key_prefix": "fixture2",
                "can_manage_projects": True,
            },
        ]
        key_ids = (await conn.scalars(APIKey.__table__.insert().returning(APIKey.id), fixture_keys)).all()
        fixture_secret = "synthetic"
        oidc_id = await conn.scalar(
            OIDCProvider.__table__.insert()
            .values(
                name="Legacy provider",
                issuer_url="https://example.test/",
                client_id="fixture-client",
                client_secret=fixture_secret,
                auto_link_existing_accounts=True,
                email_claim=None,
                require_email_verified=False,
            )
            .returning(OIDCProvider.id)
        )
        queue_id = await conn.scalar(
            PrintQueueItem.__table__.insert().values(status="pending", bed_levelling=None).returning(PrintQueueItem.id)
        )
        plug_id = await conn.scalar(
            SmartPlug.__table__.insert()
            .values(name="Legacy plug", ip_address="192.0.2.3", controls_printer_power=None)
            .returning(SmartPlug.id)
        )

    await database.init_db()

    async def reject_rewrite(conn, table, desired, _compiler):
        columns = await conn.run_sync(lambda sync: inspect(sync).get_columns(table))
        actual = {column["name"]: column for column in columns}
        changed = [
            (
                column.name,
                default,
                actual.get(column.name, {}).get("default"),
                actual.get(column.name, {}).get("nullable"),
            )
            for column, default in desired
            if not postgres_column_defaults._matches(column, default, actual.get(column.name))
        ]
        raise AssertionError(f"Repeated schema rewrite for {table}: {changed}")

    with patch.object(postgres_column_defaults, "_align_table", side_effect=reject_rewrite):
        await database.init_db()

    async with database.engine.connect() as conn:
        grants = (
            await conn.scalars(select(APIKey.can_manage_projects).where(APIKey.id.in_(key_ids)).order_by(APIKey.id))
        ).all()
        assert grants == [False, True]
        provider = (
            await conn.execute(
                select(OIDCProvider.email_claim, OIDCProvider.auto_link_existing_accounts).where(
                    OIDCProvider.id == oidc_id
                )
            )
        ).one()
        assert provider == ("email", False)
        assert await conn.scalar(select(PrintQueueItem.bed_levelling).where(PrintQueueItem.id == queue_id)) is False
        assert await conn.scalar(select(SmartPlug.controls_printer_power).where(SmartPlug.id == plug_id)) is False
        columns = await conn.run_sync(lambda sync: inspect(sync).get_columns("api_keys"))
        grant = next(column for column in columns if column["name"] == "can_manage_projects")
        assert grant["default"] == "false" and grant["nullable"] is False


async def test_legacy_postgres_types_preserve_tray_data_and_float_values(isolated_app_engine):
    from backend.app.core import database
    from backend.app.models.active_print_session import ActivePrintSession
    from backend.app.models.active_print_spoolman import ActivePrintSpoolman
    from backend.app.models.archive import PrintArchive
    from backend.app.models.printer import Printer
    from backend.app.models.smart_plug import SmartPlug
    from backend.app.models.spool import Spool

    assert database.settings.database_url == POSTGRES_URL
    await database.init_db()
    async with database.engine.begin() as conn:
        await conn.exec_driver_sql("SET extra_float_digits = 0")
        await conn.exec_driver_sql("""
            ALTER TABLE active_print_spoolman ALTER COLUMN tray_remain_start TYPE text USING tray_remain_start::text
        """)
        await conn.exec_driver_sql("""
            ALTER TABLE active_print_sessions ALTER COLUMN spool_change_log TYPE text USING spool_change_log::text
        """)
        await conn.exec_driver_sql("ALTER TABLE spool ALTER COLUMN weight_used_baseline TYPE real")
        await conn.exec_driver_sql("ALTER TABLE smart_plugs ALTER COLUMN rest_energy_total_multiplier TYPE real")
        printer_id = await conn.scalar(
            Printer.__table__.insert()
            .values(name="Legacy printer", serial_number="TEST-346-347", ip_address="192.0.2.7", access_code="FIXTURE1")
            .returning(Printer.id)
        )
        await conn.execute(
            Spool.__table__.insert().values(material="PLA", note="Legacy float", weight_used_baseline=0.001)
        )
        await conn.execute(
            SmartPlug.__table__.insert().values(
                name="Legacy energy multiplier", ip_address="192.0.2.6", rest_energy_total_multiplier=0.0000001234567
            )
        )
        await conn.execute(
            text("""
                INSERT INTO active_print_sessions (printer_id, print_name, started_at, tray_now_at_start, spool_change_log)
                VALUES (:printer, 'Legacy print', CURRENT_TIMESTAMP, -1, :changes)
            """),
            {"printer": printer_id, "changes": '[{"slot":0,"weight":17}]'},
        )
        tray_ids = []
        for index, snapshot in enumerate(('{"0-0":{"remain":80}}', '{"0-0":NaN}')):
            filename = f"fixture-{index}.3mf"
            archive_id = await conn.scalar(
                PrintArchive.__table__.insert()
                .values(printer_id=printer_id, filename=filename, file_path=filename, file_size=1)
                .returning(PrintArchive.id)
            )
            tray_ids.append(
                await conn.scalar(
                    text("""
                    INSERT INTO active_print_spoolman (printer_id, archive_id, ams_trays, tray_remain_start)
                    VALUES (:printer, :archive, '{}', :snapshot) RETURNING id
                """),
                    {"printer": printer_id, "archive": archive_id, "snapshot": snapshot},
                )
            )

    await database.init_db()
    await database.init_db()

    async with database.engine.connect() as conn:
        assert await conn.scalar(text("SHOW extra_float_digits")) == "0"
        snapshots = (
            await conn.scalars(
                select(ActivePrintSpoolman.tray_remain_start)
                .where(ActivePrintSpoolman.id.in_(tray_ids))
                .order_by(ActivePrintSpoolman.id)
            )
        ).all()
        assert snapshots == [{"0-0": {"remain": 80}}, None]
        changes = await conn.scalar(
            select(ActivePrintSession.spool_change_log).where(ActivePrintSession.printer_id == printer_id)
        )
        assert changes == [{"slot": 0, "weight": 17}]
        assert await conn.scalar(select(Spool.weight_used_baseline).where(Spool.note == "Legacy float")) == 0.001
        multiplier = await conn.scalar(
            select(SmartPlug.rest_energy_total_multiplier).where(SmartPlug.name == "Legacy energy multiplier")
        )
        assert multiplier == 0.0000001234567
