"""Immutable closed catalog for the document layout renderer."""

from __future__ import annotations

from types import MappingProxyType

from backend.app.services.document_catalog import DocumentType

RENDERER_VERSION = "weasyprint-69.0+pikepdf-10.10.0"
VALIDATOR_VERSION = "verapdf-1.30.2"
SUPPORTED_LANGUAGES = ("de", "en")
SUPPORTED_DOCUMENT_TYPES = tuple(document_type.value for document_type in DocumentType)
LAYOUT_SECTION_KEYS = (
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
PAGE_FORMATS_MM = MappingProxyType(
    {
        "A4": (210, 297),
        "Letter": (215.9, 279.4),
    }
)
TEMPLATE_VERSIONS = MappingProxyType(
    {
        "classic": "1.0.0",
        "modern": "1.0.0",
        "compact": "1.0.0",
    }
)
TEMPLATE_DESCRIPTIONS = MappingProxyType(
    {
        "classic": "Klassische Geschäftskorrespondenz mit ruhigem Tabellenraster.",
        "modern": "Akzentbetontes Layout mit klarer Metadatenspalte.",
        "compact": "Platzsparendes Layout für umfangreiche Positionstabellen.",
    }
)
