from __future__ import annotations

import inspect
import io
import zipfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def test_archive_budget_rejects_high_compression_ratio() -> None:
    from backend.app.utils.archive_budget import ArchiveBudget, ArchiveBudgetError, validate_zip_archive

    payload = _zip_bytes({"Metadata/project_settings.config": b"A" * 4096})
    with (
        zipfile.ZipFile(io.BytesIO(payload), "r") as archive,
        pytest.raises(ArchiveBudgetError, match="compression ratio"),
    ):
        validate_zip_archive(
            archive,
            ArchiveBudget(
                max_members=4,
                max_member_bytes=8192,
                max_total_uncompressed_bytes=8192,
                max_compression_ratio=2,
            ),
        )


def test_archive_budget_rejects_duplicate_normalized_names() -> None:
    from backend.app.utils.archive_budget import ArchiveBudgetError, validate_zip_archive

    payload = _zip_bytes({"Metadata/value": b"one", "Metadata\\value": b"two"})
    with zipfile.ZipFile(io.BytesIO(payload), "r") as archive, pytest.raises(ArchiveBudgetError, match="duplicate"):
        validate_zip_archive(archive)


@pytest.mark.asyncio
async def test_upload_reader_stops_after_limit() -> None:
    from backend.app.utils.archive_budget import ArchiveBudgetError, read_upload_limited

    class Upload:
        def __init__(self) -> None:
            self.stream = io.BytesIO(b"x" * 17)

        async def read(self, size: int = -1) -> bytes:
            return self.stream.read(size)

    with pytest.raises(ArchiveBudgetError, match="upload"):
        await read_upload_limited(Upload(), max_bytes=16, chunk_size=8)


@pytest.mark.asyncio
async def test_timelapse_upload_uses_video_specific_limit(monkeypatch) -> None:
    from backend.app.api.routes import archives as archive_routes
    from backend.app.utils.archive_budget import MAX_TIMELAPSE_UPLOAD_BYTES, MAX_UPLOAD_BYTES

    assert MAX_TIMELAPSE_UPLOAD_BYTES > MAX_UPLOAD_BYTES
    observed: dict[str, object] = {}

    class Upload:
        filename = "long-print.mp4"

    class Service:
        def __init__(self, _db) -> None:
            pass

        async def get_archive(self, archive_id: int):
            assert archive_id == 7
            return object()

        async def attach_timelapse(self, archive_id: int, content: bytes, filename: str) -> bool:
            observed.update(archive_id=archive_id, content=content, filename=filename)
            return True

    async def read_video_upload(_upload, *, max_bytes: int):
        observed["max_bytes"] = max_bytes
        return b"video"

    monkeypatch.setattr(archive_routes, "ArchiveService", Service)
    monkeypatch.setattr(archive_routes, "read_upload_limited", read_video_upload)

    result = await archive_routes.upload_timelapse(7, Upload(), db=object(), _=None)

    assert observed["max_bytes"] == MAX_TIMELAPSE_UPLOAD_BYTES
    assert observed["filename"] == "long-print.mp4"
    assert result == {"status": "attached", "filename": "long-print.mp4"}


def test_safe_archive_basename_removes_both_separator_styles() -> None:
    from backend.app.utils.archive_budget import safe_archive_basename

    assert safe_archive_basename(r"..\..\victim.3mf") == "victim.3mf"
    assert safe_archive_basename("../../victim.3mf") == "victim.3mf"


def test_slicer_metadata_helpers_reject_compression_bombs() -> None:
    from backend.app.services.slicer_3mf_convert import count_plates_in_3mf, extract_source_printer_model

    xml = b'<config><plate><metadata key="plater_id" value="1"/></plate><!--' + b"A" * (1024 * 1024) + b"--></config>"
    assert count_plates_in_3mf(_zip_bytes({"Metadata/model_settings.config": xml})) == 0

    config = b'{"printer_model":"Bambu Lab X1 Carbon","padding":"' + b"A" * (1024 * 1024) + b'"}'
    assert extract_source_printer_model(_zip_bytes({"Metadata/project_settings.config": config})) is None


def test_threemf_xml_helper_rejects_compression_bomb(tmp_path) -> None:
    from backend.app.utils.threemf_tools import extract_print_time_from_3mf

    xml = (
        b'<config><plate><metadata key="prediction" value="123"/></plate><!--' + b"A" * (1024 * 1024) + b"--></config>"
    )
    path = tmp_path / "bomb.3mf"
    path.write_bytes(_zip_bytes({"Metadata/slice_info.config": xml}))
    assert extract_print_time_from_3mf(path) is None


def test_calculation_slice_request_bounds_work_and_rejects_unused_presets() -> None:
    from backend.app.schemas.calculation_project import CalculationSliceRequest

    with pytest.raises(ValidationError):
        CalculationSliceRequest(plate_ids=list(range(65)))
    with pytest.raises(ValidationError):
        CalculationSliceRequest(plate_ids=[1], printer_preset={"unused": "cache churn"})


@pytest.mark.asyncio
async def test_slice_jobs_are_owned_and_cross_user_polling_is_hidden() -> None:
    from backend.app.api.routes.slice_jobs import get_slice_job
    from backend.app.services.slice_dispatch import SliceDispatchService

    service = SliceDispatchService()

    async def run(_job_id: int) -> dict:
        return {"ok": True}

    job = await service.enqueue(
        kind="library_file",
        source_id=10,
        source_name="model.3mf",
        owner_id=7,
        run=run,
    )
    assert job.owner_id == 7

    import backend.app.api.routes.slice_jobs as routes

    previous = routes.slice_dispatch
    routes.slice_dispatch = service
    try:
        with pytest.raises(HTTPException) as exc:
            await get_slice_job(job.id, auth_result=(SimpleNamespace(id=8), False))
        assert exc.value.status_code == 404
    finally:
        routes.slice_dispatch = previous


@pytest.mark.asyncio
async def test_archive_mutation_route_applies_ownership_gate() -> None:
    from backend.app.api.routes.archives import delete_timelapse

    archive = SimpleNamespace(id=1, deleted_at=None, created_by_id=7, timelapse_path="timelapse.mp4")

    class Result:
        def scalar_one_or_none(self):
            return archive

    class DB:
        async def execute(self, _query):
            return Result()

    with pytest.raises(HTTPException) as exc:
        await delete_timelapse(1, db=DB(), auth_result=(SimpleNamespace(id=8), False))
    assert exc.value.status_code == 404


def test_pending_archive_routes_declare_queue_all_and_archive_authority() -> None:
    from backend.app.api.routes.pending_uploads import archive_all_pending, archive_pending_upload

    for route in (archive_all_pending, archive_pending_upload):
        parameters = inspect.signature(route).parameters
        assert "queue_authority" in parameters
        assert "archive_authority" in parameters


def test_support_log_redaction_covers_headers_query_and_secret_paths() -> None:
    from backend.app.services.log_reader import sanitize_log_content

    content = (
        "Authorization: Bearer eyJ-secret\n"
        "GET https://plug.local/api/super-secret/cm?token=abc123&mode=on\n"
        "api_key = clear-text-key"
    )
    sanitized = sanitize_log_content(content)
    assert "eyJ-secret" not in sanitized
    assert "super-secret" not in sanitized
    assert "abc123" not in sanitized
    assert "clear-text-key" not in sanitized
