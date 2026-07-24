"""Security and semantic structure tests for internal PDF templates."""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from backend.app.services.document_layout_defaults import TEMPLATE_DEFAULTS
from backend.app.services.document_layout_samples import load_all_samples, load_sample
from backend.app.services.document_templates import render_document_html
from backend.app.services.document_view_model import build_document_view_model

FIXTURES = Path(__file__).parents[2] / "fixtures" / "document_layouts"


@pytest.mark.parametrize("template_key", ["classic", "modern", "compact"])
def test_every_template_renders_every_document_type_and_language(template_key):
    layout = TEMPLATE_DEFAULTS[template_key]
    for snapshot in load_all_samples().values():
        html = render_document_html(build_document_view_model(snapshot), layout)
        assert f"template-{template_key}" in html
        assert snapshot.number in html
        assert '<table class="positions' in html
        assert '<section class="totals-block">' in html or snapshot.document_type == "delivery_note"


def test_markup_is_autoescaped_and_never_becomes_script_or_style():
    snapshot = load_sample("invoice-de-standard")
    hostile = "<script>alert(1)</script><style>body{display:none}</style>"
    line = snapshot.lines[0].model_copy(update={"description": hostile})
    snapshot = snapshot.model_copy(update={"lines": (line, *snapshot.lines[1:])})
    html = render_document_html(build_document_view_model(snapshot), TEMPLATE_DEFAULTS["classic"])
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert html.count("<script") == 0
    assert html.count("<style") == 1


def test_templates_contain_no_external_resources_or_inline_scripts():
    html = render_document_html(
        build_document_view_model(load_sample("invoice-de-standard")),
        TEMPLATE_DEFAULTS["modern"],
    )
    assert not re.search(r"(?:src|href)=[\"'](?:https?:|file:|//)", html, re.IGNORECASE)
    assert "<script" not in html.lower()
    assert "url(" not in html.lower()


def test_print_rules_cover_pagination_invariants():
    html = render_document_html(
        build_document_view_model(load_sample("invoice-de-standard")),
        TEMPLATE_DEFAULTS["compact"],
    )
    for rule in (
        "display: table-header-group",
        "display: table-footer-group",
        "break-inside: avoid",
        "counter(pages)",
        "overflow-wrap: anywhere",
    ):
        assert rule in html


def test_css_values_are_closed_and_invalid_font_falls_back():
    layout = TEMPLATE_DEFAULTS["classic"].model_copy(
        update={
            "typography": TEMPLATE_DEFAULTS["classic"].typography.model_copy(
                update={"font_family": "x';background:url(file:///etc/passwd)"}
            )
        }
    )
    html = render_document_html(build_document_view_model(load_sample("invoice-de-standard")), layout)
    assert "font-family:'Noto Sans'" in html
    assert "file:///" not in html


def test_typography_controls_change_the_rendered_pdf_css():
    layout = TEMPLATE_DEFAULTS["classic"].model_copy(
        update={
            "typography": TEMPLATE_DEFAULTS["classic"].typography.model_copy(
                update={"table_size_pt": Decimal("13"), "paragraph_spacing_mm": Decimal("6")}
            )
        }
    )

    html = render_document_html(build_document_view_model(load_sample("invoice-de-standard")), layout)

    assert "--table-size:13pt" in html
    assert "--paragraph-spacing:6mm" in html
    assert "font-size: var(--table-size)" in html
    assert "margin-bottom: var(--paragraph-spacing)" in html


def test_position_table_header_is_single_line_and_visually_separated():
    html = render_document_html(
        build_document_view_model(load_sample("invoice-de-standard")),
        TEMPLATE_DEFAULTS["classic"],
    )

    assert ".positions .number { width: 12mm; }" in html
    assert ".positions thead th" in html
    assert "white-space: nowrap" in html
    assert "background: #f2f4f3" in html
    assert "border-bottom: 1.5px solid var(--accent)" in html


def test_normalized_html_snapshots_are_stable():
    expected = json.loads((FIXTURES / "template-html-sha256.json").read_text(encoding="utf-8"))
    view_model = build_document_view_model(load_sample("invoice-de-standard"))
    actual = {}
    for template_key, layout in TEMPLATE_DEFAULTS.items():
        html = render_document_html(view_model, layout)
        normalized = re.sub(r">\s+<", "><", html).strip().encode("utf-8")
        actual[template_key] = hashlib.sha256(normalized).hexdigest()
    assert actual == expected
