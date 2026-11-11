"""Provision independent app and fixture databases for opt-in PostgreSQL tests."""

import asyncio
import atexit
import logging
import os
from uuid import uuid4

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)


async def _manage_databases(server: URL, databases: list[str], *, create: bool) -> None:
    engine = create_async_engine(server, isolation_level="AUTOCOMMIT", poolclass=NullPool, hide_parameters=True)
    created: list[str] = []
    try:
        async with engine.connect() as connection:
            try:
                for name in databases:
                    if create:
                        await connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
                        created.append(name)
                    else:
                        await connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            except BaseException:
                for name in created:
                    await connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
                raise
    finally:
        await engine.dispose()


def local_postgres_url(raw_url: str) -> URL:
    try:
        server = make_url(raw_url)
    except ArgumentError:
        raise RuntimeError("Invalid PostgreSQL test URL") from None
    address_options = {"host", "port", "database", "dbname", "user", "password", "dsn"}
    if (
        server.drivername != "postgresql+asyncpg"
        or server.host not in ("127.0.0.1", "::1", "localhost")
        or address_options.intersection(server.query)
    ):
        raise RuntimeError("The PostgreSQL test URL must point to a local PostgreSQL test instance")
    return server


def configure_postgres_suite() -> str | None:
    """Return the fixture URL and configure the app URL before its settings load."""
    raw_url = os.environ.get("TEST_POSTGRES_URL")
    if not raw_url:
        return None
    server = local_postgres_url(raw_url)

    prefix = f"printops_test_{uuid4().hex}"
    app_name, fixture_name = f"{prefix}_app", f"{prefix}_fixtures"
    databases = [app_name, fixture_name]
    try:
        asyncio.run(_manage_databases(server, databases, create=True))
    except Exception as error:
        raise RuntimeError(f"Could not create PostgreSQL test databases ({type(error).__name__})") from None

    def cleanup():
        try:
            asyncio.run(_manage_databases(server, databases, create=False))
        except Exception as error:
            logger.warning("Could not remove the temporary PostgreSQL databases (%s)", type(error).__name__)

    atexit.register(cleanup)
    os.environ["DATABASE_URL"] = server.set(database=app_name).render_as_string(hide_password=False)
    return server.set(database=fixture_name).render_as_string(hide_password=False)
