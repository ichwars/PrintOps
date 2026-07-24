"""Strict internal Jinja renderer and closed CSS mapping for document templates."""

from __future__ import annotations

import re
from importlib import resources

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from backend.app.schemas.document_layout import EffectiveDocumentLayout
from backend.app.services.document_view_model import DocumentViewModel

_TEMPLATE_PACKAGE = "backend.app.templates.documents"
_TEMPLATES = frozenset({"classic", "modern", "compact"})
_SAFE_FONT = re.compile(r"^[A-Za-z0-9 _-]{1,128}$")


def _css_variables(layout: EffectiveDocumentLayout) -> dict[str, str]:
    page = layout.page
    typography = layout.typography
    font = typography.font_family if _SAFE_FONT.fullmatch(typography.font_family) else "Noto Sans"
    return {
        "page-size": page.page_format,
        "margin-top": f"{page.margin_top_mm}mm",
        "margin-right": f"{page.margin_right_mm}mm",
        "margin-bottom": f"{page.margin_bottom_mm}mm",
        "margin-left": f"{page.margin_left_mm}mm",
        "first-content-top": f"{page.first_page_content_top_mm}mm",
        "font-family": font,
        "base-size": f"{typography.base_size_pt}pt",
        "table-size": f"{typography.table_size_pt}pt",
        "metadata-size": f"{typography.metadata_size_pt}pt",
        "heading-scale": str(typography.heading_scale),
        "line-height": str(typography.line_height),
        "paragraph-spacing": f"{typography.paragraph_spacing_mm}mm",
        "accent": typography.accent_color,
        "text-color": typography.text_color,
        "muted-color": typography.muted_color,
    }


def render_document_html(
    document: DocumentViewModel,
    layout: EffectiveDocumentLayout,
) -> str:
    template_key = layout.page.template_key
    if template_key not in _TEMPLATES:
        raise ValueError("unknown internal document template")
    template_root = resources.files(_TEMPLATE_PACKAGE)
    environment = Environment(
        loader=FileSystemLoader(str(template_root)),
        undefined=StrictUndefined,
        autoescape=select_autoescape(enabled_extensions=("html",), default_for_string=True),
        enable_async=False,
    )
    template = environment.get_template(f"{template_key}.html")
    return template.render(
        document=document.model_dump(mode="python"),
        layout=layout.model_dump(mode="python"),
        css_variables=_css_variables(layout),
    )
