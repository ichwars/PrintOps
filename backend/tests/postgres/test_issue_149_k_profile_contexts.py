"""Live PostgreSQL migration and cross-database restore for stored flow contexts."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from backend.app.core.spool_k_profile_migration import migrate_spool_k_profile_contexts
from backend.app.models.spool_k_profile import SpoolKProfile
from backend.app.models.spoolman_k_profile import SpoolmanKProfile
from backend.tests.unit.test_spool_k_context_migration_149 import _legacy_schema

POSTGRES_TEST_URL = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not POSTGRES_TEST_URL, reason="live PostgreSQL test URL not configured"),
]


@pytest.fixture
async def scoped_postgres():
    # Own a schema per test: existing startup fixtures in public remain intact.
    schema = f"issue149_{uuid4().hex}"
    admin = create_async_engine(POSTGRES_TEST_URL)
    async with admin.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_async_engine(POSTGRES_TEST_URL, connect_args={"server_settings": {"search_path": schema}})
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await admin.dispose()


@pytest.mark.parametrize("legacy_type", [None, "hardened_steel", "HS00_0.4"])
@pytest.mark.parametrize("constraint_name", [None, "uq_spoolman_k_profile"])
async def test_old_unique_migration_preserves_ids_legacy_fk_and_both_flows(
    scoped_postgres, legacy_type, constraint_name
):
    async with scoped_postgres.begin() as conn:
        await _legacy_schema(conn, constraint_name, legacy_type)
        before = {
            table: (await conn.execute(text(f"SELECT * FROM {table} ORDER BY id"))).all()
            for table in ("spool_k_profile", "spoolman_k_profile")
        }
        for model in (SpoolKProfile, SpoolmanKProfile):
            await conn.run_sync(lambda sync, model=model: model.__table__.create(sync, checkfirst=True))
        await migrate_spool_k_profile_contexts(conn)
        await migrate_spool_k_profile_contexts(conn)
        for table, rows in before.items():
            assert (await conn.execute(text(f"SELECT * FROM {table} ORDER BY id"))).all() == rows
            key = "spool_id" if table == "spool_k_profile" else "spoolman_spool_id"
            for flow in ["HH"] if legacy_type == "HS00_0.4" else ["HS", "HH"]:
                await conn.execute(
                    text(
                        f"INSERT INTO {table} ({key},printer_id,extruder,nozzle_diameter,nozzle_type,k_value,cali_idx) "
                        "VALUES (1,1,0,'0.4',:flow,0.04,5)"
                    ),
                    {"flow": flow},
                )
            with pytest.raises(IntegrityError):
                async with conn.begin_nested():
                    await conn.execute(
                        text(
                            f"INSERT INTO {table} ({key},printer_id,extruder,nozzle_diameter,nozzle_type,k_value,cali_idx) "
                            "VALUES (1,1,0,'0.4','HH07_0.4',0.05,5)"
                        )
                    )
        await conn.execute(text("DELETE FROM printers WHERE id=1"))
        for table in before:
            assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0


async def test_portable_sqlite_import_retains_flow_indices_and_legacy_rows(tmp_path, monkeypatch):
    """Uses the dedicated test DB's public schema, as the actual restore does.

    This test intentionally replaces only the database explicitly supplied via
    PRINTOPS_POSTGRES_TEST_URL. All device services remain disconnected.
    """
    from backend.app.api.routes.settings import _import_sqlite_to_postgres
    from backend.app.core import database
    from backend.app.models.printer import Printer
    from backend.app.models.spool import Spool

    source = tmp_path / "source.db"
    source_engine = create_async_engine(f"sqlite+aiosqlite:///{source}")
    async with source_engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    async with AsyncSession(source_engine, expire_on_commit=False) as db:
        printer = Printer(
            name="P2S", model="P2S", serial_number="TEST_FLOW", ip_address="127.0.0.1", access_code="test-only"
        )
        spool = Spool(material="PLA", k_profiles=[])
        db.add_all([printer, spool])
        await db.flush()
        for model, key in [(SpoolKProfile, "spool_id"), (SpoolmanKProfile, "spoolman_spool_id")]:
            for flow in [None, "hardened_steel", "HS", "HH"]:
                db.add(
                    model(
                        **{key: spool.id},
                        printer_id=printer.id,
                        nozzle_type=flow,
                        nozzle_diameter="0.4",
                        extruder=0,
                        cali_idx=5,
                        k_value=0.03,
                        setting_id="PTEST",
                    )
                )
        await db.commit()
        expected = {}
        for model in (SpoolKProfile, SpoolmanKProfile):
            expected[model.__tablename__] = [
                (row.id, row.nozzle_type, row.cali_idx, row.setting_id)
                for row in (await db.scalars(select(model).order_by(model.id))).all()
            ]
    await source_engine.dispose()
    target = create_async_engine(POSTGRES_TEST_URL)
    monkeypatch.setattr(database, "_create_engine", lambda: target)
    try:
        await _import_sqlite_to_postgres(source, POSTGRES_TEST_URL)
        async with target.begin() as conn:
            await migrate_spool_k_profile_contexts(conn)
            await migrate_spool_k_profile_contexts(conn)
            for table, rows in expected.items():
                actual = (
                    await conn.execute(text(f"SELECT id,nozzle_type,cali_idx,setting_id FROM {table} ORDER BY id"))
                ).all()
                assert actual == rows
                index = (
                    await conn.execute(
                        text("SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND indexname=:name"),
                        {"name": f"uq_{table}_context"},
                    )
                ).scalar_one()
                assert "UNIQUE INDEX" in index and "nozzle_type" in index
                # Restore sets sequences above the retained IDs; same-flow writes
                # fail on context rather than being silently duplicated.
                key = "spool_id" if table == "spool_k_profile" else "spoolman_spool_id"
                with pytest.raises(IntegrityError):
                    async with conn.begin_nested():
                        await conn.execute(
                            text(
                                f"INSERT INTO {table} ({key},printer_id,extruder,nozzle_diameter,nozzle_type,k_value) "
                                "VALUES (1,1,0,'0.4','HS07_0.4',0.05)"
                            )
                        )
            await conn.execute(text("DELETE FROM printers WHERE serial_number='TEST_FLOW'"))
            for table in expected:
                assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0
    finally:
        await target.dispose()
