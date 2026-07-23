"""Structural PDF/A-3u, custom font and letterhead renderer integration."""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path

import pikepdf
import pytest

from backend.app.services.document_layout_defaults import TEMPLATE_DEFAULTS
from backend.app.services.document_layout_samples import load_sample
from backend.app.services.document_renderer import DocumentRenderer, RenderInput
from backend.app.services.document_view_model import build_document_view_model
from backend.app.services.pdfa import inspect_pdfa3u
from backend.app.services.verapdf import VeraPdfRunner

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "document_layouts"
WEASYPRINT = (
    ROOT.parent / "installers" / "windows" / "build" / "staging" / "runtime"
    / "weasyprint" / "dist" / "weasyprint.exe"
)
VERAPDF = ROOT.parent / "installers" / "windows" / "build" / "staging" / "runtime" / "verapdf" / "verapdf.bat"


def _renderer(tmp_path: Path) -> DocumentRenderer:
    if not WEASYPRINT.exists():
        pytest.skip("pinned WeasyPrint runtime is not staged")
    return DocumentRenderer(
        engine_cli=WEASYPRINT,
        cache_dir=tmp_path / "cache",
        artifact_dir=tmp_path / "artifacts",
        validator=False,
    )


def _input(layout=None, *, assets=None, roles=None) -> RenderInput:
    return RenderInput(
        view_model=build_document_view_model(load_sample("invoice-de-standard")),
        layout=layout or TEMPLATE_DEFAULTS["classic"],
        document_timestamp=datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
        correlation_id="pdfa-conformance",
        cache_scope="profile:1",
        assets=assets or {},
        asset_roles=roles or {},
    )


def test_renderer_produces_structurally_valid_pdfa3u_with_unicode_fonts(tmp_path):
    rendered = _renderer(tmp_path).render_final(_input())
    report = inspect_pdfa3u(rendered.content)
    assert report.valid is True
    assert report.fonts_checked > 0
    with pikepdf.open(io.BytesIO(rendered.content)) as pdf:
        assert pdf.pdf_version == "1.7"
        assert len(pdf.pages) == rendered.page_count
        assert str(pdf.Root.Lang) == "de-DE"


def test_custom_font_is_resolved_only_from_registered_asset(tmp_path):
    font = (FIXTURES / "test-font.ttf").read_bytes()
    digest = hashlib.sha256(font).hexdigest()
    layout = TEMPLATE_DEFAULTS["classic"].model_copy(
        update={
            "typography": TEMPLATE_DEFAULTS["classic"].typography.model_copy(
                update={"font_family": "Bitstream Vera Sans"}
            )
        }
    )
    rendered = _renderer(tmp_path).render_final(
        _input(layout, assets={digest: font}, roles={"font_regular": digest})
    )
    report = inspect_pdfa3u(rendered.content)
    assert report.valid is True
    with pikepdf.open(io.BytesIO(rendered.content)) as pdf:
        base_fonts = {
            str(font_object.BaseFont)
            for page in pdf.pages
            for font_object in page.Resources.get("/Font", {}).values()
        }
    assert any("Bitstream-Vera-Sans" in name for name in base_fonts)


def test_first_and_following_letterhead_are_applied_as_backgrounds(tmp_path):
    first = (FIXTURES / "letterhead-a4.pdf").read_bytes()
    first_digest = hashlib.sha256(first).hexdigest()
    layout = TEMPLATE_DEFAULTS["classic"].model_copy(
        update={
            "page": TEMPLATE_DEFAULTS["classic"].page.model_copy(
                update={
                    "use_first_page_letterhead": True,
                    "use_following_page_letterhead": True,
                }
            )
        }
    )
    rendered = _renderer(tmp_path).render_final(
        _input(
            layout,
            assets={first_digest: first},
            roles={
                "letterhead_first": first_digest,
                "letterhead_following": first_digest,
            },
        )
    )
    assert rendered.page_count >= 2
    assert inspect_pdfa3u(rendered.content).valid is True


@pytest.mark.requires_verapdf
def test_real_verapdf_accepts_final_pdfa3u_and_rejects_invalid_fixture(tmp_path):
    if not VERAPDF.exists():
        pytest.skip("pinned veraPDF runtime is not staged")
    runner = VeraPdfRunner(cli_path=VERAPDF, report_dir=tmp_path / "reports")
    renderer = DocumentRenderer(
        engine_cli=WEASYPRINT,
        cache_dir=tmp_path / "cache",
        artifact_dir=tmp_path / "artifacts",
        validator=runner,
    )
    rendered = renderer.render_final(_input())
    assert rendered.validation_status == "valid"
    assert rendered.validation_report is not None
    assert rendered.validation_report.compliant is True
    assert rendered.validation_report.findings == []

    invalid = runner.validate(
        (FIXTURES / "letterhead-a4.pdf").read_bytes(),
        correlation_id="invalid-pdfa",
    )
    assert invalid.compliant is False
    assert invalid.findings
    assert invalid.findings[0].external_rule_id.startswith("ISO 19005-3:2012#")
