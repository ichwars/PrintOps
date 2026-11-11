from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from backend.app.core.bug_report_migration import clear_bug_report_contacts
from backend.app.models.bug_report import BugReport
from backend.app.services.sensor_history_settings import history_cutoff


@pytest.mark.parametrize("key", ["ams_history_retention_days", "printer_sensor_history_retention_days"])
async def test_retention_settings_require_at_least_one_day(async_client, key):
    response = await async_client.put("/api/v1/settings/", json={key: 0})
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(("value", "days"), [("0", 1), ("-3", 1), ("90", 90), ("bad", 30), (None, 30)])
def test_old_retention_settings_have_a_safe_cutoff(value, days):
    now = datetime(2026, 11, 11)
    assert history_cutoff(now, value, 30) == now - timedelta(days=days)


async def test_existing_bug_report_contact_is_cleared_repeatably(db_session):
    report = BugReport(description="Example issue", status="failed", reporter_email="sample@example.invalid")
    db_session.add(report)
    await db_session.flush()
    connection = await db_session.connection()
    await clear_bug_report_contacts(connection)
    await clear_bug_report_contacts(connection)
    assert await db_session.scalar(select(BugReport.reporter_email).where(BugReport.id == report.id)) is None
