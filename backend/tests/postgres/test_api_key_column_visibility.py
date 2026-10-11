"""Migration guards must inspect the api_keys table resolved by search_path."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core import database


async def test_api_key_column_guard_respects_visible_table_and_fallback(monkeypatch):
    dsn = os.environ.get("PRINTOPS_POSTGRES_TEST_URL")
    if not dsn:
        pytest.skip("Set PRINTOPS_POSTGRES_TEST_URL to an isolated PostgreSQL test database")
    monkeypatch.setattr(database, "is_sqlite", lambda: False)
    engine = create_async_engine(dsn)
    primary = "api_keys_primary_" + uuid4().hex
    fallback = "api_keys_fallback_" + uuid4().hex
    try:
        async with engine.begin() as conn:
            for schema in (primary, fallback):
                await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
            await conn.execute(text(f'CREATE TABLE "{primary}".api_keys (can_manage_library BOOLEAN)'))
            await conn.execute(
                text(f'CREATE TABLE "{fallback}".api_keys (can_manage_library BOOLEAN, fallback_only BOOLEAN)')
            )
            await conn.execute(text(f'SET LOCAL search_path TO "{primary}", "{fallback}"'))
            assert not await database._api_keys_column_exists(conn, "fallback_only")
            assert await database._api_keys_column_exists(conn, "can_manage_library")
            await conn.execute(text(f'DROP TABLE "{primary}".api_keys'))
            assert await database._api_keys_column_exists(conn, "fallback_only")
            assert not await database._api_keys_column_exists(conn, "missing_column")
    finally:
        async with engine.begin() as conn:
            for schema in (primary, fallback):
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await engine.dispose()
