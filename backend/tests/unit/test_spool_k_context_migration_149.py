"""Portable flow indices and lossless startup/backup migration coverage."""

import sqlite3
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import MetaData, UniqueConstraint, text
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.schema import CreateIndex, CreateTable

from backend.app.core.spool_k_profile_migration import migrate_spool_k_profile_contexts
from backend.app.models.spool_k_profile import SpoolKProfile
from backend.app.models.spoolman_k_profile import SpoolmanKProfile


@pytest.mark.parametrize("model", [SpoolKProfile, SpoolmanKProfile])
@pytest.mark.parametrize("dialect", [sqlite.dialect(), postgresql.dialect()])
def test_metadata_flow_identity_has_explicit_prefixes_and_unknown_null(model, dialect):
    index = next(iter(model.__table__.indexes))
    ddl = str(CreateIndex(index).compile(dialect=dialect))
    assert "UNIQUE INDEX" in ddl and "nozzle_type" in ddl
    assert "'HS'" in ddl and "'HH'" in ddl and "ELSE" not in ddl
    # Existing columns retain their FK/CASCADE and metadata shape for restore.
    assert "ON DELETE CASCADE" in str(CreateTable(model.__table__).compile(dialect=dialect))


async def _legacy_schema(conn, constraint_name=None, nozzle_type=None):
    await conn.execute(text("CREATE TABLE printers (id INTEGER PRIMARY KEY)"))
    await conn.execute(text("CREATE TABLE spool (id INTEGER PRIMARY KEY)"))
    await conn.execute(text("INSERT INTO printers VALUES (1)"))
    await conn.execute(text("INSERT INTO spool VALUES (1)"))
    for model in (SpoolKProfile, SpoolmanKProfile):
        metadata = MetaData()
        for fk in model.__table__.foreign_keys:
            fk.column.table.to_metadata(metadata)
        table = model.__table__.to_metadata(metadata)
        if model is SpoolmanKProfile:
            table.append_constraint(
                UniqueConstraint("spoolman_spool_id", "printer_id", "extruder", "nozzle_diameter", name=constraint_name)
            )
        await conn.execute(CreateTable(table))
        key = "spool_id" if model is SpoolKProfile else "spoolman_spool_id"
        await conn.execute(
            text(
                f"INSERT INTO {table.name} (id,{key},printer_id,extruder,nozzle_diameter,nozzle_type,k_value,cali_idx,setting_id) "
                "VALUES (11,1,1,0,'0.4',:type,0.02,5,'PLEGACY')"
            ),
            {"type": nozzle_type},
        )
    # Local storage historically allowed ambiguous unknown rows. Retain them,
    # so the strict resolver can continue to reject ambiguity without data loss.
    await conn.execute(
        text(
            "INSERT INTO spool_k_profile (id,spool_id,printer_id,extruder,nozzle_diameter,nozzle_type,k_value,cali_idx) "
            "VALUES (12,1,1,0,'0.4','stainless_steel',0.03,5)"
        )
    )
    await conn.execute(text("CREATE INDEX ix_spoolman_k_profile_spool ON spoolman_k_profile (spoolman_spool_id)"))


@pytest.mark.asyncio
@pytest.mark.parametrize("constraint_name", [None, "uq_spoolman_k_profile"])
@pytest.mark.parametrize("legacy_type", [None, "hardened_steel", "HS00_0.4"])
async def test_legacy_migration_is_transactional_idempotent_and_preserves_rows(constraint_name, legacy_type):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            await _legacy_schema(conn, constraint_name, legacy_type)
            before = {
                table: (await conn.execute(text(f"SELECT * FROM {table} ORDER BY id"))).all()
                for table in ("spool_k_profile", "spoolman_k_profile")
            }
            # Same ordering as startup/restore: create_all does not alter old UNIQUE.
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
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_migration_error_rolls_back_old_unique_rebuild(monkeypatch):
    import backend.app.core.spool_k_profile_migration as migration

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as conn:
            await _legacy_schema(conn, "uq_spoolman_k_profile")
            original = migration._rebuild_sqlite

            async def fail_after_copy(conn, table):
                await original(conn, table)
                raise RuntimeError("injected migration failure")

            monkeypatch.setattr(migration, "_rebuild_sqlite", fail_after_copy)
            with pytest.raises(RuntimeError, match="injected"):
                await migrate_spool_k_profile_contexts(conn)
            sql = (
                await conn.execute(text("SELECT sql FROM sqlite_master WHERE name='spoolman_k_profile'"))
            ).scalar_one()
            assert "uq_spoolman_k_profile" in sql
            assert (
                await conn.execute(text("SELECT setting_id FROM spoolman_k_profile WHERE id=11"))
            ).scalar_one() == "PLEGACY"
            assert (
                await conn.execute(
                    text("SELECT count(*) FROM sqlite_master WHERE name='spoolman_k_profile_context_v2'")
                )
            ).scalar_one() == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_sqlite_backup_restore_keeps_both_flows_and_unknown_legacy(tmp_path):
    backup = tmp_path / "backup.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{backup}")
    try:
        async with engine.begin() as conn:
            await _legacy_schema(conn)
            await migrate_spool_k_profile_contexts(conn)
            for table, key in [("spool_k_profile", "spool_id"), ("spoolman_k_profile", "spoolman_spool_id")]:
                for flow in ["HS", "HH"]:
                    await conn.execute(
                        text(
                            f"INSERT INTO {table} ({key},printer_id,extruder,nozzle_diameter,nozzle_type,k_value,cali_idx) "
                            "VALUES (1,1,0,'0.4',:flow,0.04,5)"
                        ),
                        {"flow": flow},
                    )
    finally:
        await engine.dispose()
    with sqlite3.connect(backup) as source:
        dump = "\n".join(source.iterdump())
    restored = tmp_path / "restored.db"
    with sqlite3.connect(restored) as target:
        target.executescript(dump)
    engine = create_async_engine(f"sqlite+aiosqlite:///{restored}")
    try:
        async with engine.begin() as conn:
            await migrate_spool_k_profile_contexts(conn)
            for table in ("spool_k_profile", "spoolman_k_profile"):
                values = (await conn.execute(text(f"SELECT nozzle_type, cali_idx FROM {table} ORDER BY id"))).all()
                assert (None, 5) in values and ("HS", 5) in values and ("HH", 5) in values
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_plan_drops_only_the_old_unique_and_uses_portable_index(monkeypatch):
    import backend.app.core.spool_k_profile_migration as migration

    @asynccontextmanager
    async def savepoint():
        yield

    from types import SimpleNamespace

    conn = SimpleNamespace(
        dialect=postgresql.dialect(), run_sync=AsyncMock(), execute=AsyncMock(), begin_nested=savepoint
    )
    monkeypatch.setattr(
        migration,
        "_unique_constraints",
        AsyncMock(
            return_value=[
                {
                    "name": "legacy unique name",
                    "column_names": ["spoolman_spool_id", "printer_id", "extruder", "nozzle_diameter"],
                },
                {"name": "unrelated", "column_names": ["id"]},
            ]
        ),
    )
    await migrate_spool_k_profile_contexts(conn)
    sql = [str(call.args[0].compile(dialect=conn.dialect)) for call in conn.execute.await_args_list]
    assert any('DROP CONSTRAINT "legacy unique name"' in statement for statement in sql)
    assert all("unrelated" not in statement for statement in sql)
    assert sum("CREATE UNIQUE INDEX IF NOT EXISTS" in statement for statement in sql) == 2
    assert all("PRAGMA" not in statement and "AUTOINCREMENT" not in statement for statement in sql)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_create", [False, True])
async def test_cross_database_restore_keeps_shared_k_profile_metadata(tmp_path, fail_create):
    from unittest.mock import MagicMock, patch

    from backend.app.api.routes.settings import _import_sqlite_to_postgres
    from backend.app.core.database import Base

    source = tmp_path / "empty.db"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    tables = [SpoolKProfile.__table__, SpoolmanKProfile.__table__]
    before = [
        str(CreateTable(table).compile(dialect=dialect))
        for table in tables
        for dialect in (sqlite.dialect(), postgresql.dialect())
    ]
    assert all("ON DELETE CASCADE" in ddl for ddl in before)
    originals = [(table, set(table.constraints)) for table in Base.metadata.tables.values()]
    connection = MagicMock()
    connection.execute = AsyncMock()
    connection.run_sync = AsyncMock(side_effect=RuntimeError("create failed") if fail_create else None)
    transaction = MagicMock()
    transaction.__aenter__ = AsyncMock(return_value=connection)
    transaction.__aexit__ = AsyncMock(return_value=False)
    engine = MagicMock()
    engine.begin.return_value = transaction
    engine.dispose = AsyncMock()
    try:
        with patch("backend.app.core.database._create_engine", return_value=engine):
            if fail_create:
                with pytest.raises(RuntimeError, match="create failed"):
                    await _import_sqlite_to_postgres(source, "postgresql+asyncpg://unused/test")
            else:
                await _import_sqlite_to_postgres(source, "postgresql+asyncpg://unused/test")
        after = [
            str(CreateTable(table).compile(dialect=dialect))
            for table in tables
            for dialect in (sqlite.dialect(), postgresql.dialect())
        ]
        assert after == before
    finally:
        for table, constraints in originals:
            table.constraints.update(constraints)
            for constraint in table.foreign_key_constraints:
                constraint._create_rule = None


@pytest.mark.asyncio
async def test_duplicate_reported_flow_backup_is_rejected_before_destination_changes(tmp_path):
    from unittest.mock import MagicMock, patch

    from backend.app.api.routes.settings import _import_sqlite_to_postgres

    source = tmp_path / "ambiguous.db"
    with sqlite3.connect(source) as db:
        db.execute(
            "CREATE TABLE spool_k_profile (spool_id INTEGER, printer_id INTEGER, extruder INTEGER, "
            "nozzle_diameter TEXT, nozzle_type TEXT)"
        )
        db.executemany("INSERT INTO spool_k_profile VALUES (1,1,0,'0.4',?)", [("HS00_0.4",), ("HS07_0.4",)])
    engine = MagicMock()
    engine.dispose = AsyncMock()
    with (
        patch("backend.app.core.database._create_engine", return_value=engine),
        pytest.raises(ValueError, match="ambiguous.*reported flow"),
    ):
        await _import_sqlite_to_postgres(source, "postgresql+asyncpg://unused/test")
    engine.begin.assert_not_called()
    engine.dispose.assert_awaited_once()
