"""Real WeasyPrint integration coverage for deterministic document output."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import pikepdf
import pytest

from backend.app.services.document_layout_defaults import TEMPLATE_DEFAULTS
from backend.app.services.document_layout_samples import load_sample
from backend.app.services.document_renderer import DocumentRenderer, RenderInput, RenderLimits
from backend.app.services.document_view_model import build_document_view_model

ROOT = Path(__file__).parents[2]
STAGED_WEASYPRINT = (
    ROOT.parent / "installers" / "windows" / "build" / "staging" / "runtime"
    / "weasyprint" / "dist" / "weasyprint.exe"
)


def _renderer(tmp_path: Path) -> DocumentRenderer:
    if not STAGED_WEASYPRINT.exists():
        pytest.skip("pinned WeasyPrint runtime is not staged")
    return DocumentRenderer(
        engine_cli=STAGED_WEASYPRINT,
        cache_dir=tmp_path / "cache",
        artifact_dir=tmp_path / "artifacts",
    )


def _request(template: str = "classic") -> RenderInput:
    return RenderInput(
        view_model=build_document_view_model(load_sample("invoice-de-standard")),
        layout=TEMPLATE_DEFAULTS[template],
        document_timestamp=datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
        correlation_id="deterministic-integration",
        cache_scope="profile:1",
    )


@pytest.mark.parametrize(
    ("template", "expected_mm"),
    [("classic", (210, 297)), ("modern", (215.9, 279.4))],
)
def test_real_pdf_magic_and_page_size(tmp_path, template, expected_mm):
    rendered = _renderer(tmp_path).render_preview(_request(template))
    assert rendered.content.startswith(b"%PDF-")
    with pikepdf.open(io.BytesIO(rendered.content)) as pdf:
        box = pdf.pages[0].MediaBox
        size_mm = tuple(round(float(value) * 25.4 / 72, 1) for value in (box[2], box[3]))
    assert size_mm == expected_mm


def test_uncached_render_is_byte_deterministic(tmp_path):
    renderer = _renderer(tmp_path)
    first = renderer.render_final(_request())
    second = renderer.render_final(_request())
    assert first.sha256 == second.sha256
    assert first.content == second.content


def test_warm_preview_cache_is_below_two_seconds(tmp_path):
    renderer = _renderer(tmp_path)
    renderer.render_preview(_request())
    started = perf_counter()
    cached = renderer.render_preview(_request())
    elapsed = perf_counter() - started
    assert cached.from_cache is True
    assert elapsed <= 2.0


@pytest.mark.slow
def test_ten_page_document_and_long_position_render_within_hard_limit(tmp_path):
    view_model = build_document_view_model(load_sample("invoice-de-standard"))
    base = view_model.positions[0]
    positions = tuple(
        base.model_copy(
            update={
                "position": number,
                "description": f"Position {number}: {base.description}",
            }
        )
        for number in range(1, 81)
    )
    request = _request("compact")
    request = RenderInput(
        view_model=view_model.model_copy(update={"positions": positions}),
        layout=request.layout,
        document_timestamp=request.document_timestamp,
        correlation_id="ten-page-integration",
        cache_scope=request.cache_scope,
    )
    renderer = DocumentRenderer(
        engine_cli=STAGED_WEASYPRINT,
        cache_dir=tmp_path / "cache",
        artifact_dir=tmp_path / "artifacts",
        limits=RenderLimits(timeout_seconds=60, max_pages=12),
    )
    rendered = renderer.render_final(request)
    assert rendered.page_count == 10

    long_position = base.model_copy(
        update={
            "position": 1,
            "description": "Ausführliche technische Beschreibung " * 40,
        }
    )
    long_request = RenderInput(
        view_model=view_model.model_copy(update={"positions": (long_position,)}),
        layout=request.layout,
        document_timestamp=request.document_timestamp,
        correlation_id="long-position-integration",
        cache_scope=request.cache_scope,
    )
    long_render = renderer.render_final(long_request)
    assert long_render.content.startswith(b"%PDF-")
    assert 1 <= long_render.page_count <= 12
