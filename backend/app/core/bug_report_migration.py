"""Remove contact information kept by older bug report submissions."""

from sqlalchemy import update

from backend.app.models.bug_report import BugReport


async def clear_bug_report_contacts(conn) -> None:
    await conn.execute(update(BugReport).where(BugReport.reporter_email.is_not(None)).values(reporter_email=None))
