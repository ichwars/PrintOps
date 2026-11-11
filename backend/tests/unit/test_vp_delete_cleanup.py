"""Test virtual printer deletion using the actual pending upload rows."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from backend.app.models.pending_upload import PendingUpload
from backend.app.models.virtual_printer import VirtualPrinter
from backend.app.services.virtual_printer import virtual_printer_manager


@pytest.mark.asyncio
@pytest.mark.parametrize("with_uploads", [True, False])
async def test_delete_vp_marks_only_its_pending_uploads_discarded(
    async_client, db_session, tmp_path, monkeypatch, with_uploads
):
    db_session.add(VirtualPrinter(id=1, name="Remove"))
    original_status = {}
    for vp_id, status in ((1, "pending"), (1, "archived"), (12, "pending")):
        if not with_uploads:
            continue
        upload_dir = tmp_path / "uploads" / str(vp_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        name = f"{vp_id}-{status}.3mf"
        upload = upload_dir / name
        upload.write_bytes(b"fixture")
        original_status[name] = status
        db_session.add(PendingUpload(filename=name, file_path=str(upload), file_size=7, status=status))
    await db_session.commit()

    remove_instance = AsyncMock()
    monkeypatch.setattr(virtual_printer_manager, "remove_instance", remove_instance)
    monkeypatch.setattr(virtual_printer_manager, "sync_from_db", AsyncMock())
    monkeypatch.setattr(virtual_printer_manager, "_base_dir", tmp_path)
    response = await async_client.delete("/api/v1/virtual-printers/1")
    assert response.status_code == 200
    remove_instance.assert_awaited_once_with(1)
    assert not (tmp_path / "uploads" / "1").exists()
    assert await db_session.scalar(select(VirtualPrinter.id)) is None

    if with_uploads:
        original_status["1-pending.3mf"] = "discarded"
        assert (tmp_path / "uploads" / "12" / "12-pending.3mf").read_bytes() == b"fixture"
    assert (
        dict((await db_session.execute(select(PendingUpload.filename, PendingUpload.status))).all()) == original_status
    )


@pytest.mark.asyncio
async def test_in_flight_review_upload_cannot_create_pending_row_for_deleted_vp(db_session, tmp_path):
    from contextlib import asynccontextmanager

    from backend.app.services.virtual_printer.manager import VirtualPrinterInstance

    @asynccontextmanager
    async def session_factory():
        yield db_session

    instance = VirtualPrinterInstance(
        vp_id=41,
        name="Deleted virtual printer",
        mode="review",
        model="C12",
        access_code="12345678",
        serial_suffix="391800041",
        base_dir=tmp_path,
        session_factory=session_factory,
    )
    file_path = tmp_path / "late.3mf"
    file_path.write_bytes(b"fixture")
    await instance._queue_file(file_path, "192.0.2.10")
    assert not file_path.exists()
    assert await db_session.scalar(select(PendingUpload.id)) is None
