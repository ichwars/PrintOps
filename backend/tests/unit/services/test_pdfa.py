"""PDF/A-3u metadata, letterhead and structural validation tests."""

from __future__ import annotations

import io
from datetime import datetime, timezone

import pikepdf
import pytest

from backend.app.services.pdfa import (
    PdfaError,
    inspect_pdfa3u,
    merge_letterheads,
    prepare_pdfa3u,
)


def _pdf(*, pages: int = 1, size=(595.2756, 841.8898), color=b"0 0 1 rg") -> bytes:
    target = io.BytesIO()
    with pikepdf.new() as pdf:
        for _ in range(pages):
            page = pdf.add_blank_page(page_size=size)
            page.Contents = pdf.make_stream(color + b" 10 10 20 20 re f")
        pdf.save(target, static_id=True)
    return target.getvalue()


def _page_contents(page: pikepdf.Page) -> bytes:
    contents = page.Contents
    if isinstance(contents, pikepdf.Array):
        return b"\n".join(stream.read_bytes() for stream in contents)
    return contents.read_bytes()


def test_prepare_adds_pdfa3u_output_intent_and_accessibility_metadata():
    prepared = prepare_pdfa3u(
        _pdf(),
        language="de",
        timestamp=datetime(2026, 7, 23, 12, tzinfo=timezone.utc),
        document_id="a" * 64,
    )
    with pikepdf.open(io.BytesIO(prepared)) as pdf:
        metadata = pdf.open_metadata()
        assert metadata["pdfaid:part"] == "3"
        assert metadata["pdfaid:conformance"] == "U"
        assert metadata["xmpMM:DocumentID"] == f"urn:sha256:{'a' * 64}"
        assert str(pdf.Root.Lang) == "de-DE"
        assert bool(pdf.Root.MarkInfo.Marked) is True
        assert bool(pdf.Root.ViewerPreferences.DisplayDocTitle) is True
        intent = pdf.Root.OutputIntents[0]
        assert intent.S == "/GTS_PDFA1"
        assert int(intent.DestOutputProfile.N) == 3
        assert len(intent.DestOutputProfile.read_bytes()) > 1000

    report = inspect_pdfa3u(prepared)
    assert report.valid is True
    assert report.findings == ()


def test_missing_pdfa_structure_returns_concrete_findings():
    report = inspect_pdfa3u(_pdf())
    assert report.valid is False
    assert {finding.code for finding in report.findings} >= {
        "PDFA_XMP_MISSING",
        "PDFA_OUTPUT_INTENT_MISSING",
        "PDFA_LANGUAGE_MISSING",
    }


def test_letterhead_is_merged_below_foreground_on_first_and_following_pages():
    merged = merge_letterheads(
        _pdf(pages=2, color=b"0 0 1 rg"),
        first=_pdf(color=b"1 0 0 rg"),
        following=_pdf(color=b"0 1 0 rg"),
    )
    with pikepdf.open(io.BytesIO(merged)) as pdf:
        first = _page_contents(pdf.pages[0])
        following = _page_contents(pdf.pages[1])
        assert first.find(b"1 0 0 rg") < first.find(b"0 0 1 rg")
        assert following.find(b"0 1 0 rg") < following.find(b"0 0 1 rg")


def test_letterhead_page_box_mismatch_is_rejected():
    with pytest.raises(PdfaError) as caught:
        merge_letterheads(_pdf(), first=_pdf(size=(612, 792)))
    assert caught.value.code == "PDFA_LETTERHEAD_PAGE_MISMATCH"
