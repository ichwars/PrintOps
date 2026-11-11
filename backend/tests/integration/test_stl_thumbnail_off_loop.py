"""Every library entry point dispatches STL rendering to its dedicated worker."""

import contextlib
import io
import struct
import threading
import zipfile

import pytest
from httpx import AsyncClient

from backend.app.api.routes import library


def _binary_stl(triangles: int = 8) -> bytes:
    """A binary STL comfortably above MIN_USABLE_STL_BYTES."""
    header = b"PrintOps test".ljust(80, b"\0")
    body = b""
    for i in range(triangles):
        body += struct.pack("<12fH", 0, 0, 1, 0, 0, i, 1, 0, i, 0, 1, i, 0)
    return header + struct.pack("<I", triangles) + body


@pytest.fixture
def render_threads(monkeypatch):
    """Record the thread every thumbnail render runs in."""
    seen: list[int] = []

    def fake(_stl_path, _thumbnails_dir, size=256):
        seen.append(threading.get_ident())
        # Their own worker, not the shared pool every other to_thread call uses.
        assert threading.current_thread().name.startswith("stl-thumbnail")
        return None

    monkeypatch.setattr(library, "generate_stl_thumbnail", fake)
    return seen


@pytest.mark.asyncio
@pytest.mark.integration
async def test_an_upload_renders_off_the_loop(async_client: AsyncClient, render_threads):
    loop_thread = threading.get_ident()
    resp = await async_client.post(
        "/api/v1/library/files", files={"file": ("part.stl", _binary_stl(), "application/octet-stream")}
    )

    assert resp.status_code == 200, resp.text
    assert render_threads and loop_thread not in render_threads


@pytest.mark.asyncio
@pytest.mark.integration
async def test_a_zip_of_stls_renders_off_the_loop(async_client: AsyncClient, render_threads):
    loop_thread = threading.get_ident()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.stl", _binary_stl())
        zf.writestr("b.stl", _binary_stl())

    resp = await async_client.post(
        "/api/v1/library/files/extract-zip", files={"file": ("models.zip", buf.getvalue(), "application/zip")}
    )

    assert resp.status_code == 200, resp.text
    assert len(render_threads) == 2 and loop_thread not in render_threads


@pytest.mark.asyncio
@pytest.mark.integration
async def test_a_batch_renders_off_the_loop(async_client: AsyncClient, render_threads):
    upload = await async_client.post(
        "/api/v1/library/files",
        files={"file": ("part.stl", _binary_stl(), "application/octet-stream")},
        params={"generate_stl_thumbnails": "false"},
    )
    assert upload.status_code == 200, upload.text
    loop_thread = threading.get_ident()

    resp = await async_client.post("/api/v1/library/generate-stl-thumbnails", json={"all_missing": True})

    assert resp.status_code == 200, resp.text
    assert render_threads and loop_thread not in render_threads


@pytest.mark.asyncio
@pytest.mark.integration
async def test_an_external_folder_backfill_renders_off_the_loop(
    async_client: AsyncClient, db_session, render_threads, monkeypatch
):
    upload = await async_client.post(
        "/api/v1/library/files",
        files={"file": ("part.stl", _binary_stl(), "application/octet-stream")},
        params={"generate_stl_thumbnails": "false"},
    )
    assert upload.status_code == 200, upload.text
    folder = await async_client.post("/api/v1/library/folders", json={"name": "ext"})
    from backend.app.models.library import LibraryFile

    row = await db_session.get(LibraryFile, upload.json()["id"])
    row.folder_id = folder.json()["id"]
    await db_session.commit()

    @contextlib.asynccontextmanager
    async def session():
        yield db_session

    monkeypatch.setattr(library, "async_session", session)
    loop_thread = threading.get_ident()

    await library._backfill_external_stl_thumbnails([folder.json()["id"]])

    assert render_threads and loop_thread not in render_threads
