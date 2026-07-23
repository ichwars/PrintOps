"""Complete immutable system and template defaults for every layout field."""

from __future__ import annotations

from types import MappingProxyType

from backend.app.schemas.document_layout import (
    EffectiveDocumentLayout,
    FooterRulesDraft,
    FooterRulesEffective,
    HeaderRulesDraft,
    HeaderRulesEffective,
    NotesRulesDraft,
    NotesRulesEffective,
    PageRulesDraft,
    PageRulesEffective,
    PositionRulesDraft,
    PositionRulesEffective,
    TechnicalRulesDraft,
    TechnicalRulesEffective,
    TitleRulesDraft,
    TitleRulesEffective,
    TotalsRulesDraft,
    TotalsRulesEffective,
    TypographyRulesDraft,
    TypographyRulesEffective,
)
from backend.app.services.document_layout_catalog import (
    RENDERER_VERSION,
    TEMPLATE_VERSIONS,
    VALIDATOR_VERSION,
)


def _effective(model_type, draft):
    return model_type.model_validate(draft.model_dump())


def _layout(
    template_key: str,
    *,
    page: PageRulesDraft,
    typography: TypographyRulesDraft,
    header: HeaderRulesDraft,
    title: TitleRulesDraft,
    positions: PositionRulesDraft,
    totals: TotalsRulesDraft,
    technical: TechnicalRulesDraft,
    notes: NotesRulesDraft,
    footer: FooterRulesDraft,
) -> EffectiveDocumentLayout:
    return EffectiveDocumentLayout(
        schema_version=1,
        template_version=TEMPLATE_VERSIONS[template_key],
        renderer_version=RENDERER_VERSION,
        validator_version=VALIDATOR_VERSION,
        page=_effective(PageRulesEffective, page),
        typography=_effective(TypographyRulesEffective, typography),
        header=_effective(HeaderRulesEffective, header),
        title=_effective(TitleRulesEffective, title),
        positions=_effective(PositionRulesEffective, positions),
        totals=_effective(TotalsRulesEffective, totals),
        technical=_effective(TechnicalRulesEffective, technical),
        notes=_effective(NotesRulesEffective, notes),
        footer=_effective(FooterRulesEffective, footer),
    )


CLASSIC_DEFAULT = _layout(
    "classic",
    page=PageRulesDraft(template_key="classic"),
    typography=TypographyRulesDraft(accent_color="#5A6C60"),
    header=HeaderRulesDraft(logo_alignment="left", recipient_window="left"),
    title=TitleRulesDraft(metadata_alignment="right"),
    positions=PositionRulesDraft(table_style="standard"),
    totals=TotalsRulesDraft(totals_alignment="right"),
    technical=TechnicalRulesDraft(placement="position"),
    notes=NotesRulesDraft(),
    footer=FooterRulesDraft(column_layout="three"),
)

MODERN_DEFAULT = _layout(
    "modern",
    page=PageRulesDraft(
        template_key="modern",
        page_format="Letter",
        margin_top_mm="16",
        margin_right_mm="16",
        margin_bottom_mm="16",
        margin_left_mm="16",
        first_page_content_top_mm="42",
    ),
    typography=TypographyRulesDraft(
        base_size_pt="10.5",
        heading_scale="1.55",
        accent_color="#2563EB",
        paragraph_spacing_mm="4",
    ),
    header=HeaderRulesDraft(logo_alignment="right", recipient_window="left"),
    title=TitleRulesDraft(metadata_alignment="right", title_spacing_mm="8"),
    positions=PositionRulesDraft(table_style="spacious", show_net_amount=True),
    totals=TotalsRulesDraft(totals_alignment="right"),
    technical=TechnicalRulesDraft(placement="notes"),
    notes=NotesRulesDraft(intro_placement="before_title"),
    footer=FooterRulesDraft(column_layout="two"),
)

COMPACT_DEFAULT = _layout(
    "compact",
    page=PageRulesDraft(
        template_key="compact",
        margin_top_mm="10",
        margin_right_mm="10",
        margin_bottom_mm="10",
        margin_left_mm="10",
        first_page_content_top_mm="36",
        following_page_content_top_mm="14",
    ),
    typography=TypographyRulesDraft(
        base_size_pt="8.5",
        table_size_pt="7.5",
        metadata_size_pt="7",
        heading_scale="1.25",
        line_height="1.15",
        paragraph_spacing_mm="1.5",
        accent_color="#374151",
    ),
    header=HeaderRulesDraft(logo_width_mm="16", recipient_window="left"),
    title=TitleRulesDraft(title_spacing_mm="3"),
    positions=PositionRulesDraft(table_style="compact", show_secondary_description=False),
    totals=TotalsRulesDraft(),
    technical=TechnicalRulesDraft(),
    notes=NotesRulesDraft(),
    footer=FooterRulesDraft(column_layout="three"),
)

SYSTEM_DEFAULT = CLASSIC_DEFAULT
TEMPLATE_DEFAULTS = MappingProxyType(
    {
        "classic": CLASSIC_DEFAULT,
        "modern": MODERN_DEFAULT,
        "compact": COMPACT_DEFAULT,
    }
)
