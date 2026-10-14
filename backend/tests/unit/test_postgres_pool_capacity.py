"""Startup capacity diagnostics; fake only the external PostgreSQL boundary."""

import asyncio
import importlib
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.core import database
from backend.app.core.config import Settings


class FakeEngine:
    def __init__(self, row=("100", "3", "0"), *, error=None, dialect="postgresql", stall=False):
        self.dialect = SimpleNamespace(name=dialect)
        self.row = row
        self.error = error
        self.stall = stall
        self.queries = []
        self.closed = False

    @asynccontextmanager
    async def connect(self):
        try:
            if self.error:
                raise self.error
            yield self
        finally:
            self.closed = True

    async def execute(self, statement):
        self.queries.append(str(statement))
        if self.stall:
            await asyncio.Event().wait()
        return SimpleNamespace(one=lambda: self.row)


def install_engine(monkeypatch, engine, size=20, overflow=20):
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "_pool_config", {"pool_size": size, "max_overflow": overflow})


async def probe():
    module = importlib.import_module("backend.app.core.postgres_pool_capacity")
    await module.check_pool_fits_server()


@pytest.mark.parametrize(
    "row,size,overflow,warns",
    [
        (("100", "3", "0"), 20, 20, False),
        (("43", "3", "0"), 20, 20, False),
        (("42", "3", "0"), 20, 20, True),
        (("100", "3", "0"), 20, 78, True),
        (("43", "3", "1"), 20, 20, True),
        (("43", "3", None), 20, 20, False),
        (("20", "0", None), 20, 0, False),
    ],
)
async def test_configured_ceiling_and_known_reserved_slots(monkeypatch, caplog, row, size, overflow, warns):
    engine = FakeEngine(row)
    install_engine(monkeypatch, engine, size, overflow)
    with caplog.at_level(logging.WARNING):
        await probe()
    assert bool(caplog.records) is warns
    assert engine.closed
    assert engine.queries == [
        "SELECT current_setting('max_connections'), "
        "current_setting('superuser_reserved_connections'), "
        "current_setting('reserved_connections', true)"
    ]
    if warns:
        assert f"pool_size {size} + max_overflow {overflow}" in caplog.text
        assert "per worker" in caplog.text
        assert "DB_POOL_SIZE" in caplog.text and "DB_MAX_OVERFLOW" in caplog.text
        assert "other clients" in caplog.text


async def test_sqlite_never_checks_out_a_probe_connection(monkeypatch, caplog):
    engine = FakeEngine(dialect="sqlite", error=AssertionError("must not connect"))
    install_engine(monkeypatch, engine)
    await probe()
    assert not engine.closed
    assert not engine.queries
    assert not caplog.records


@pytest.mark.parametrize(
    "row",
    [
        (None, "3", "0"),
        ("secret://credential", "3", "0"),
        ("-1", "3", "0"),
        ("0", "0", "0"),
        ("100", "-3", "0"),
        ("100", "3", "bad"),
        ("100", None, "0"),
        ("3", "3", "0"),
        ("100", "3", "9" * 10000),
        (True, "3", "0"),
        (100.5, "3", "0"),
        (),
    ],
)
async def test_malformed_limits_warn_without_leaking_values(monkeypatch, caplog, row):
    install_engine(monkeypatch, FakeEngine(row))
    await probe()
    assert len(caplog.records) == 1
    assert "could not" in caplog.text.lower()
    assert "secret" not in caplog.text and "999999" not in caplog.text
    assert len(caplog.records[0].getMessage()) < 300
    assert caplog.records[0].exc_info is None


@pytest.mark.parametrize("error", [PermissionError("secret://password"), OSError("secret://password")])
async def test_restricted_or_unavailable_probe_is_warning_only(monkeypatch, caplog, error):
    install_engine(monkeypatch, FakeEngine(error=error))
    await probe()
    assert len(caplog.records) == 1
    assert "secret" not in caplog.text
    assert caplog.records[0].exc_info is None


async def test_slow_probe_is_bounded_and_releases_connection(monkeypatch, caplog):
    module = importlib.import_module("backend.app.core.postgres_pool_capacity")
    monkeypatch.setattr(module, "_PROBE_TIMEOUT_SECONDS", 0.01)
    engine = FakeEngine(stall=True)
    install_engine(monkeypatch, engine)
    await asyncio.wait_for(probe(), timeout=1)
    assert engine.closed
    assert len(caplog.records) == 1


async def test_process_cancellation_is_not_swallowed(monkeypatch):
    install_engine(monkeypatch, FakeEngine(error=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await probe()


class StartupReached(BaseException):
    pass


async def test_lifespan_continues_after_failed_probe(monkeypatch, caplog):
    from backend.app import main

    events = []

    async def initialized():
        events.append("initialized")

    @asynccontextmanager
    async def next_startup_session():
        events.append("continued")
        raise StartupReached
        yield

    monkeypatch.setattr(main, "init_db", initialized)
    monkeypatch.setattr(main, "async_session", next_startup_session)
    install_engine(monkeypatch, FakeEngine(error=OSError("secret://password")))
    with pytest.raises(StartupReached):
        async with main.lifespan(main.app):
            pass
    assert events == ["initialized", "continued"]
    assert any("PostgreSQL" in r.getMessage() for r in caplog.records)
    assert "secret" not in caplog.text


async def test_lifespan_does_not_swallow_migration_errors(monkeypatch):
    from backend.app import main

    async def migration_failed():
        raise RuntimeError("migration failed")

    monkeypatch.setattr(main, "init_db", migration_failed)
    engine = FakeEngine()
    install_engine(monkeypatch, engine)
    with pytest.raises(RuntimeError, match="migration failed"):
        async with main.lifespan(main.app):
            pass
    assert not engine.queries


@pytest.mark.parametrize("sqlite,overflow", [(True, 200), (False, 20)])
def test_existing_defaults_and_overrides_remain_dialect_aware(monkeypatch, sqlite, overflow):
    monkeypatch.setattr(database, "is_sqlite", lambda: sqlite)
    for name in ("db_pool_size", "db_max_overflow", "db_pool_timeout", "db_pool_recycle"):
        monkeypatch.setattr(database.settings, name, None)
    config = database._resolve_pool_kwargs()
    assert config["pool_size"] == 20 and config["max_overflow"] == overflow
    monkeypatch.setattr(database.settings, "db_pool_size", 7)
    monkeypatch.setattr(database.settings, "db_max_overflow", 0)
    monkeypatch.setattr(database.settings, "db_pool_timeout", 9)
    config = database._resolve_pool_kwargs()
    assert config["pool_size"] == 7 and config["max_overflow"] == 0 and config["pool_timeout"] == 9


@pytest.mark.parametrize("field,value", [("db_pool_size", 0), ("db_max_overflow", -1), ("db_pool_timeout", 0)])
def test_existing_invalid_pool_settings_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value})
