"""Closed catalog, strict DTO and complete-default contracts for layouts."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.app.schemas.document_layout import (
    EffectiveDocumentLayout,
    PageRulesDraft,
    PreviewRequest,
    TypographyRulesDraft,
    TypographyRulesPatch,
)
from backend.app.services.document_catalog import DocumentType
from backend.app.services.document_layout_catalog import (
    LAYOUT_SECTION_KEYS,
    PAGE_FORMATS_MM,
    RENDERER_VERSION,
    SUPPORTED_DOCUMENT_TYPES,
    SUPPORTED_LANGUAGES,
    TEMPLATE_DESCRIPTIONS,
    TEMPLATE_VERSIONS,
    VALIDATOR_VERSION,
)
from backend.app.services.document_layout_defaults import SYSTEM_DEFAULT, TEMPLATE_DEFAULTS

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "document_layouts"


def test_catalog_is_closed_complete_and_versioned():
    assert tuple(TEMPLATE_DEFAULTS) == ("classic", "modern", "compact")
    assert tuple(TEMPLATE_VERSIONS) == ("classic", "modern", "compact")
    assert tuple(TEMPLATE_DESCRIPTIONS) == ("classic", "modern", "compact")
    assert set(PAGE_FORMATS_MM) == {"A4", "Letter"}
    assert SUPPORTED_LANGUAGES == ("de", "en")
    assert set(SUPPORTED_DOCUMENT_TYPES) == {document_type.value for document_type in DocumentType}
    assert RENDERER_VERSION == "weasyprint-69.0+pikepdf-10.10.0"
    assert VALIDATOR_VERSION == "verapdf-1.30.2"
    assert LAYOUT_SECTION_KEYS == (
        "page",
        "typography",
        "header",
        "title",
        "positions",
        "totals",
        "technical",
        "notes",
        "footer",
    )


@pytest.mark.parametrize("margin", (Decimal("3.99"), Decimal("30.01")))
def test_page_contract_enforces_portrait_and_printable_margins(margin):
    with pytest.raises(ValidationError):
        PageRulesDraft(margin_top_mm=margin)
    with pytest.raises(ValidationError):
        PageRulesDraft(orientation="landscape")


@pytest.mark.parametrize("size", (Decimal("6.9"), Decimal("16.1")))
def test_typography_contract_enforces_size_and_hex_colors(size):
    with pytest.raises(ValidationError):
        TypographyRulesDraft(base_size_pt=size)
    with pytest.raises(ValidationError):
        TypographyRulesDraft(accent_color="green")


def test_patch_distinguishes_omitted_field_from_removed_override():
    omitted = TypographyRulesPatch()
    removed = TypographyRulesPatch(accent_color=None)

    assert "accent_color" not in omitted.model_fields_set
    assert "accent_color" in removed.model_fields_set
    assert removed.accent_color is None


def test_public_contracts_reject_unknown_fields_and_preview_payloads():
    with pytest.raises(ValidationError):
        PageRulesDraft(css="body { display: none }")
    with pytest.raises(ValidationError):
        PreviewRequest(
            layout_id=1,
            layout_lock_version=2,
            source_kind="sample",
            source_id="invoice-de-standard",
            document_content={"unsafe": "payload"},
        )
    with pytest.raises(ValidationError):
        PreviewRequest(
            layout_id=1,
            layout_lock_version=2,
            source_kind="document",
            source_id="not-an-id",
        )


def test_every_template_default_is_complete_and_contains_no_css_keys():
    assert isinstance(SYSTEM_DEFAULT, EffectiveDocumentLayout)
    for template_key, effective in TEMPLATE_DEFAULTS.items():
        payload = effective.model_dump(mode="json")
        assert set(LAYOUT_SECTION_KEYS) <= set(payload)
        assert payload["page"]["template_key"] == template_key
        serialized = json.dumps(payload).lower()
        assert "css" not in serialized


@pytest.mark.parametrize(
    "fixture_name",
    ("effective-classic-a4.json", "effective-modern-letter.json"),
)
def test_effective_fixtures_are_complete_and_do_not_default_missing_sections(fixture_name):
    fixture = FIXTURE_DIR / fixture_name
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    effective = EffectiveDocumentLayout.model_validate(payload)
    assert effective.model_dump(mode="json") == payload
    assert effective == TEMPLATE_DEFAULTS[payload["page"]["template_key"]]

    for section in LAYOUT_SECTION_KEYS:
        incomplete = dict(payload)
        incomplete.pop(section)
        with pytest.raises(ValidationError):
            EffectiveDocumentLayout.model_validate(incomplete)
