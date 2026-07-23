"""Boundary and failure-contract tests for the shared document renderer."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pikepdf
import pytest

from backend.app.services.document_layout_defaults import TEMPLATE_DEFAULTS
from backend.app.services.document_layout_samples import load_sample
from backend.app.services.document_renderer import (
    DocumentRenderer,
    DocumentRendererError,
    RenderInput,
    RenderLimits,
)
from backend.app.services.document_view_model import build_document_view_model
from backend.app.services.verapdf import PdfaValidationReport, VeraPdfUnavailable


def _request(**changes) -> RenderInput:
    values = {
        "view_model": build_document_view_model(load_sample("invoice-de-standard")),
        "layout": TEMPLATE_DEFAULTS["classic"],
        "document_timestamp": datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
        "correlation_id": "renderer-unit-test",
        "cache_scope": "profile:1",
    }
    values.update(changes)
    return RenderInput(**values)


def _pdf(page_count: int = 1) -> bytes:
    target = io.BytesIO()
    with pikepdf.new() as pdf:
        for _ in range(page_count):
            pdf.add_blank_page(page_size=(595.2756, 841.8898))
        pdf.save(target, static_id=True)
    return target.getvalue()


def test_preview_and_final_use_same_pipeline(tmp_path):
    calls: list[str] = []

    def engine(_html: str, _workspace: Path, mode: str) -> bytes:
        calls.append(mode)
        return _pdf()

    renderer = DocumentRenderer(
        cache_dir=tmp_path / "cache",
        artifact_dir=tmp_path / "artifacts",
        engine=engine,
        validator=False,
    )
    preview = renderer.render_preview(_request())
    final = renderer.render_final(_request())

    assert preview.content.startswith(b"%PDF-")
    assert final.content.startswith(b"%PDF-")
    assert calls == ["preview", "final"]
    assert preview.mode == "preview"
    assert final.mode == "final"


def test_cache_hit_is_authorized_every_time(tmp_path):
    authorizations: list[str] = []
    engine_calls = 0

    def authorize(scope: str) -> bool:
        authorizations.append(scope)
        return True

    def engine(_html: str, _workspace: Path, _mode: str) -> bytes:
        nonlocal engine_calls
        engine_calls += 1
        return _pdf()

    renderer = DocumentRenderer(
        cache_dir=tmp_path / "cache",
        cache_authorizer=authorize,
        engine=engine,
    )
    renderer.render_preview(_request())
    cached = renderer.render_preview(_request())

    assert cached.from_cache is True
    assert engine_calls == 1
    assert authorizations == ["profile:1"]


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (TimeoutError(), "RENDER_TIMEOUT"),
        (MemoryError(), "RENDER_MEMORY_LIMIT"),
        (OSError("engine exploded"), "RENDER_ENGINE_FAILED"),
    ],
)
def test_engine_failures_have_stable_public_codes(tmp_path, exception, code):
    def engine(_html: str, _workspace: Path, _mode: str) -> bytes:
        raise exception

    renderer = DocumentRenderer(cache_dir=tmp_path / "cache", engine=engine)
    with pytest.raises(DocumentRendererError) as caught:
        renderer.render_preview(_request())
    assert caught.value.code == code
    assert "engine exploded" not in str(caught.value)


def test_page_and_output_limits_are_hard_failures(tmp_path):
    renderer = DocumentRenderer(
        cache_dir=tmp_path / "cache",
        limits=RenderLimits(max_pages=12, max_output_bytes=128),
        engine=lambda *_: _pdf(13),
    )
    with pytest.raises(DocumentRendererError) as caught:
        renderer.render_preview(_request())
    assert caught.value.code in {"RENDER_PAGE_LIMIT", "RENDER_ENGINE_FAILED"}


def test_unregistered_resource_urls_are_rejected_before_engine(tmp_path):
    renderer = DocumentRenderer(
        cache_dir=tmp_path / "cache",
        engine=lambda *_: pytest.fail("engine must not run"),
    )
    with pytest.raises(DocumentRendererError) as caught:
        renderer._validate_resource_access('<img src="file:///etc/passwd">')
    assert caught.value.code == "RENDER_ASSET_UNAVAILABLE"


def test_worker_workspace_is_removed_after_failure(tmp_path):
    workspaces: list[Path] = []

    def engine(_html: str, workspace: Path, _mode: str) -> bytes:
        workspaces.append(workspace)
        (workspace / "partial.pdf").write_bytes(b"partial")
        raise TimeoutError

    renderer = DocumentRenderer(cache_dir=tmp_path / "cache", engine=engine)
    with pytest.raises(DocumentRendererError):
        renderer.render_preview(_request())
    assert workspaces and not workspaces[0].exists()


def test_preview_warns_but_final_blocks_when_validator_is_unavailable(tmp_path):
    def unavailable(*_args, **_kwargs):
        raise VeraPdfUnavailable("PDF_VALIDATOR_UNAVAILABLE")

    renderer = DocumentRenderer(
        cache_dir=tmp_path / "cache",
        artifact_dir=tmp_path / "artifacts",
        engine=lambda *_: _pdf(),
        validator=SimpleNamespace(validate=unavailable),
    )
    preview = renderer.render_preview(_request())
    assert preview.validation_status == "unvalidated"
    assert preview.warnings == ("PDF_VALIDATOR_UNAVAILABLE",)
    with pytest.raises(DocumentRendererError):
        renderer.render_final(_request())
    assert list((tmp_path / "artifacts").rglob("*.pdf")) == []


def test_final_artifact_is_persisted_only_after_compliant_validation(tmp_path):
    report = PdfaValidationReport(
        compliant=True,
        validator_version="1.30.2",
        findings=[],
        raw_report_sha256="a" * 64,
    )
    renderer = DocumentRenderer(
        cache_dir=tmp_path / "cache",
        artifact_dir=tmp_path / "artifacts",
        engine=lambda *_: _pdf(),
        validator=SimpleNamespace(validate=lambda *_args, **_kwargs: report),
    )
    rendered = renderer.render_final(_request())
    assert rendered.validation_status == "valid"
    assert rendered.validation_report == report
    assert rendered.artifact_path and rendered.artifact_path.is_file()
