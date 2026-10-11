"""Cross-database restore must not strip constraints from the shared ORM."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from backend.app.models.location import Location  # noqa: F401
from backend.app.models.storage_ha_sensor import StorageHASensor


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_create", [False, True])
async def test_restore_preserves_global_foreign_key_ddl(tmp_path, fail_create):
    from backend.app.api.routes.settings import _import_sqlite_to_postgres

    source = tmp_path / "source.db"
    with sqlite3.connect(source) as database:
        database.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT)")
    table = StorageHASensor.__table__
    constraints = set(table.foreign_key_constraints)
    before = [str(CreateTable(table).compile(dialect=d)) for d in (sqlite.dialect(), postgresql.dialect())]
    assert all("REFERENCES locations (id) ON DELETE CASCADE" in ddl for ddl in before)
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
        assert set(table.foreign_key_constraints) == constraints
        after = [str(CreateTable(table).compile(dialect=d)) for d in (sqlite.dialect(), postgresql.dialect())]
        assert after == before
        engine.dispose.assert_awaited_once()
    finally:
        # Keep the red control isolated: the old implementation mutates these.
        for constraint in constraints:
            table.append_constraint(constraint)
            constraint._create_rule = None
