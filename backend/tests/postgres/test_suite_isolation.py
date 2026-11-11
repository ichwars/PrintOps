"""The opt-in fixture uses the PostgreSQL engine without sharing app state."""

import os

import pytest
from sqlalchemy import text

from backend.app.core import database

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_POSTGRES_URL"), reason="PostgreSQL suite is opt-in")


async def test_app_and_fixture_databases_are_distinct_and_use_utc(test_engine):
    async with database.engine.connect() as app_connection, test_engine.connect() as fixture:
        app_name = await app_connection.scalar(text("SELECT current_database()"))
        fixture_name = await fixture.scalar(text("SELECT current_database()"))
        assert app_name.startswith("printops_test_") and app_name.endswith("_app")
        assert fixture_name == app_name.removesuffix("_app") + "_fixtures"
        assert await fixture.scalar(text("SHOW timezone")) == "UTC"
    await database.engine.dispose()
