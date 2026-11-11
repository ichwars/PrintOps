"""Background timelapse edits are cancellable and keep the selected source revision."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.core.auth import create_access_token, generate_api_key
from backend.app.core.config import settings
from backend.app.models.api_key import APIKey
from backend.app.models.settings import Settings
from backend.app.models.user import User
from backend.app.services import timelapse_jobs
from backend.app.services.timelapse_processor import TimelapseProcessor

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture
async def source(archive_factory, printer_factory):
    printer = await printer_factory()
    path = settings.base_dir / "archives" / "timelapse-editor" / "original.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"original")
    archive = await archive_factory(printer.id, timelapse_path=str(path.relative_to(settings.base_dir)))
    yield archive.id, path
    await timelapse_jobs.cancel_all()


def _start(archive_id, path):
    url = f"/api/v1/archives/{archive_id}/timelapse"
    return url, {"source_version": timelapse_jobs.source_version(path), "save_mode": "replace", "trim_end": "4"}


async def test_job_can_be_cancelled_and_retried(async_client, source):
    archive_id, path = source
    url, form = _start(archive_id, path)
    running = asyncio.Event()
    cancelled = asyncio.Event()

    async def process(_self, *, output_path, on_progress, **_):
        output_path.write_bytes(b"partial")
        on_progress(0.3)
        running.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with (
        patch.object(TimelapseProcessor, "__init__", lambda self, input_path: None),
        patch.object(
            TimelapseProcessor,
            "process",
            process,
        ),
    ):
        result = await async_client.post(f"{url}/process?background=true", data=form)
        assert result.status_code == 202, result.text
        job_id = result.json()["job_id"]
        await asyncio.wait_for(running.wait(), 3)
        polled = await async_client.get(f"{url}/job")
        assert polled.json()["progress"] == pytest.approx(0.3)
        conflicting = await async_client.post(f"{url}/process?background=true", data=form)
        assert conflicting.status_code == 409
        stop = await async_client.delete(f"{url}/job/{job_id}")
        assert stop.status_code == 200 and stop.json()["status"] == "cancelled", stop.text
    assert cancelled.is_set()
    assert path.read_bytes() == b"original"
    assert not list(path.parent.glob(".timelapse-edit-*"))

    async def complete(_self, *, output_path, **_):
        output_path.write_bytes(b"edited")
        return True

    with (
        patch.object(TimelapseProcessor, "__init__", lambda self, input_path: None),
        patch.object(
            TimelapseProcessor,
            "process",
            complete,
        ),
    ):
        completed = await async_client.post(f"{url}/process", data=form)
    assert completed.status_code == 200 and completed.json()["status"] == "completed", completed.text
    assert path.read_bytes() == b"edited"


async def test_source_revision_rejects_stale_editor_and_mid_encode_replacement(async_client, source):
    archive_id, path = source
    url, form = _start(archive_id, path)
    encode_ready = asyncio.Event()
    encode_finish = asyncio.Event()

    async def process(_self, *, output_path, **_):
        encode_ready.set()
        await encode_finish.wait()
        output_path.write_bytes(b"our edit")
        return True

    info = {"duration": 4, "width": 32, "height": 32, "fps": 25, "codec": "h264", "file_size": 8, "has_audio": False}
    with (
        patch.object(TimelapseProcessor, "__init__", lambda self, input_path: None),
        patch.object(TimelapseProcessor, "get_info", AsyncMock(return_value=info)),
        patch.object(TimelapseProcessor, "process", process),
    ):
        snapshot = await async_client.get(f"{url}/info")
        assert snapshot.status_code == 200 and snapshot.json()["source_version"] == form["source_version"]
        stale = await async_client.post(f"{url}/process?background=true", data={**form, "source_version": "old"})
        assert stale.status_code == 409
        accepted = await async_client.post(f"{url}/process?background=true", data=form)
        assert accepted.status_code == 202
        await asyncio.wait_for(encode_ready.wait(), 3)
        path.write_bytes(b"replacement from another producer")
        encode_finish.set()
        job = timelapse_jobs.get_job(archive_id, ("appliance", 0))
        assert job is not None and job.task is not None
        await asyncio.wait_for(job.task, 3)
        failed = await async_client.get(f"{url}/job")
        assert failed.json()["status"] == "failed" and "changed" in failed.json()["message"]
    assert path.read_bytes() == b"replacement from another producer"


async def test_job_routes_require_archive_edit_credentials(async_client, db_session, source):
    archive_id, path = source
    url, form = _start(archive_id, path)
    user = User(username="timelapse-auth-test")
    db_session.add_all([user, Settings(key="auth_enabled", value="true")])
    key, key_hash, prefix = generate_api_key()
    revoked, revoked_hash, revoked_prefix = generate_api_key()
    db_session.add_all(
        [
            APIKey(name="Read only", key_hash=key_hash, key_prefix=prefix, can_manage_archives=False),
            APIKey(name="Revoked", key_hash=revoked_hash, key_prefix=revoked_prefix, enabled=False),
        ]
    )
    await db_session.commit()
    expired = create_access_token({"sub": user.username}, expires_delta=timedelta(seconds=-60))
    for headers, expected in (
        ({}, 401),
        ({"X-API-Key": "invalid"}, 401),
        ({"X-API-Key": key}, 403),
        ({"X-API-Key": revoked}, 401),
        ({"Authorization": f"Bearer {expired}"}, 401),
    ):
        assert (await async_client.get(f"{url}/job", headers=headers)).status_code == expected
        assert (await async_client.delete(f"{url}/job/random", headers=headers)).status_code == expected
        assert (
            await async_client.post(f"{url}/process?background=true", data=form, headers=headers)
        ).status_code == expected
