"""Check project links before writing archive files for a pending upload."""

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.models.archive import PrintArchive
from backend.app.models.pending_upload import PendingUpload
from backend.app.models.project import Project
from backend.tests.unit.test_issue_131_archive_recovery import _make_3mf

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def pending_upload(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "base_dir", tmp_path)
    monkeypatch.setattr(settings, "archive_dir", tmp_path / "archive")
    source = tmp_path / "part.3mf"
    _make_3mf(source)
    pending = PendingUpload(filename=source.name, file_path=str(source), file_size=source.stat().st_size)
    db_session.add(pending)
    await db_session.commit()
    return pending.id, source


async def test_unknown_project_leaves_upload_pending_and_creates_no_archive(async_client, db_session, pending_upload):
    upload_id, source = pending_upload
    response = await async_client.post(f"/api/v1/pending-uploads/{upload_id}/archive", json={"project_id": 9999})

    assert response.status_code == 400
    assert response.json()["detail"] == "Project not found"
    assert source.is_file()
    assert not settings.archive_dir.exists()
    assert (await db_session.execute(select(PrintArchive.id))).first() is None
    row = await db_session.execute(
        select(PendingUpload.status, PendingUpload.project_id).where(PendingUpload.id == upload_id)
    )
    assert row.one() == ("pending", None)


@pytest.mark.parametrize("requested_project", ["known", 0, None])
async def test_archive_and_pending_upload_store_the_same_project(
    async_client, db_session, pending_upload, requested_project
):
    upload_id, source = pending_upload
    if requested_project == "known":
        project = Project(name="Print project")
        db_session.add(project)
        await db_session.commit()
        requested_project = project.id

    response = await async_client.post(
        f"/api/v1/pending-uploads/{upload_id}/archive", json={"project_id": requested_project}
    )

    assert response.status_code == 200, response.text
    assert not source.exists()
    assert len(list(settings.archive_dir.rglob("*.3mf"))) == 1
    expected = requested_project or None
    archive = await db_session.execute(select(PrintArchive.project_id).where(PrintArchive.id == response.json()["id"]))
    pending = await db_session.execute(
        select(PendingUpload.status, PendingUpload.project_id).where(PendingUpload.id == upload_id)
    )
    assert archive.scalar_one() == expected
    assert pending.one() == ("archived", expected)
