"""A flushed write must commit or fail before the client sees its HTTP status."""

import asyncio
import io
import json
import zipfile

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core import database
from backend.app.main import app
from backend.app.models.project import Project

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _request(method, path, payload, on_start):
    body = json.dumps(payload).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"test"), (b"content-type", b"application/json")],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }
    pending = True

    async def receive():
        nonlocal pending
        if pending:
            pending = False
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Future()

    chunks = []

    async def send(message):
        if message["type"] == "http.response.start":
            await on_start(message["status"])
        if message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    await app(scope, receive, send)
    return b"".join(chunks)


@pytest.fixture
async def file_database(async_client, tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'http-transactions.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "async_session", sessions)
    monkeypatch.setattr("backend.app.core.auth.async_session", sessions)
    monkeypatch.delitem(app.dependency_overrides, database.get_db)
    try:
        yield engine, sessions
    finally:
        await engine.dispose()


async def test_commit_is_visible_from_another_connection_before_http_success(file_database):
    _engine, sessions = file_database
    project_name = "Committed at response start"
    seen = []

    async def on_start(status):
        assert status == 200
        async with sessions() as db:
            seen.append(await db.scalar(select(Project.name).where(Project.name == project_name)))

    await _request("POST", "/api/v1/projects/", {"name": project_name}, on_start)
    assert seen == [project_name]


async def test_commit_failure_sends_server_error_before_any_success(file_database, monkeypatch):
    engine, sessions = file_database

    class FailingCommit(AsyncSession):
        async def commit(self):
            raise OperationalError("COMMIT", {}, Exception("simulated database failure"))

    monkeypatch.setattr(database, "async_session", async_sessionmaker(engine, class_=FailingCommit))
    statuses = []

    async def on_start(status):
        statuses.append(status)
        async with sessions() as db:
            assert await db.scalar(select(Project.id)) is None

    with pytest.raises(OperationalError):
        await _request("POST", "/api/v1/projects/", {"name": "Rejected at commit"}, on_start)
    assert statuses == [500]


async def test_database_connection_is_released_before_project_stream(file_database):
    engine, sessions = file_database
    async with sessions.begin() as db:
        project = Project(name="Streamed project")
        db.add(project)
        await db.flush()
        project_id = project.id

    async def on_start(status):
        assert status == 200
        assert engine.pool.checkedout() == 0

    body = await _request("GET", f"/api/v1/projects/{project_id}/export", {}, on_start)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert json.loads(archive.read("project.json"))["name"] == "Streamed project"
