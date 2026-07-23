"""Pure layout resolver receipts and patch-map contracts."""

from __future__ import annotations

from backend.app.services.document_layout_defaults import TEMPLATE_DEFAULTS
from backend.app.services.document_layouts import PATCH_TARGETS, canonical_effective_sha256


def test_patch_map_contains_every_public_patch_field():
    assert "page.template_key" in PATCH_TARGETS
    assert "page.margin_top_mm" in PATCH_TARGETS
    assert "typography.accent_color" in PATCH_TARGETS
    assert "header.show_logo" in PATCH_TARGETS
    assert "positions.show_total" in PATCH_TARGETS
    assert "footer.show_page_numbers" in PATCH_TARGETS


def test_effective_hash_is_canonical_and_stable():
    layout = TEMPLATE_DEFAULTS["classic"]
    assert canonical_effective_sha256(layout) == canonical_effective_sha256(
        layout.model_validate_json(layout.model_dump_json())
    )
