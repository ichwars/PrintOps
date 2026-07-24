"""Strict public contracts for typed commercial-document layouts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TemplateKey = Literal["classic", "modern", "compact"]
PageFormat = Literal["A4", "Letter"]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
Margin = Annotated[Decimal, Field(ge=4, le=30)]
FontSize = Annotated[Decimal, Field(ge=7, le=16)]
SourceLevel = Literal["system", "profile", "document_type", "language"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ImmutableModel(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class ValueSource(ImmutableModel):
    level: SourceLevel
    configuration_id: int | None = Field(default=None, gt=0)
    version: int | None = Field(default=None, ge=1)


class PageRulesDraft(StrictModel):
    template_key: TemplateKey = "classic"
    page_format: PageFormat = "A4"
    orientation: Literal["portrait"] = "portrait"
    margin_top_mm: Margin = Decimal("18")
    margin_right_mm: Margin = Decimal("18")
    margin_bottom_mm: Margin = Decimal("18")
    margin_left_mm: Margin = Decimal("18")
    first_page_content_top_mm: Annotated[Decimal, Field(ge=10, le=90)] = Decimal("45")
    following_page_content_top_mm: Annotated[Decimal, Field(ge=10, le=60)] = Decimal("20")
    use_first_page_letterhead: bool = False
    use_following_page_letterhead: bool = False
    reuse_first_letterhead: bool = False


class PageRulesPatch(StrictModel):
    template_key: TemplateKey | None = None
    page_format: PageFormat | None = None
    orientation: Literal["portrait"] | None = None
    margin_top_mm: Margin | None = None
    margin_right_mm: Margin | None = None
    margin_bottom_mm: Margin | None = None
    margin_left_mm: Margin | None = None
    first_page_content_top_mm: Annotated[Decimal, Field(ge=10, le=90)] | None = None
    following_page_content_top_mm: Annotated[Decimal, Field(ge=10, le=60)] | None = None
    use_first_page_letterhead: bool | None = None
    use_following_page_letterhead: bool | None = None
    reuse_first_letterhead: bool | None = None


class PageRulesEffective(ImmutableModel):
    template_key: TemplateKey
    page_format: PageFormat
    orientation: Literal["portrait"]
    margin_top_mm: Margin
    margin_right_mm: Margin
    margin_bottom_mm: Margin
    margin_left_mm: Margin
    first_page_content_top_mm: Annotated[Decimal, Field(ge=10, le=90)]
    following_page_content_top_mm: Annotated[Decimal, Field(ge=10, le=60)]
    use_first_page_letterhead: bool
    use_following_page_letterhead: bool
    reuse_first_letterhead: bool


class PageRulesSources(ImmutableModel):
    template_key: ValueSource
    page_format: ValueSource
    orientation: ValueSource
    margin_top_mm: ValueSource
    margin_right_mm: ValueSource
    margin_bottom_mm: ValueSource
    margin_left_mm: ValueSource
    first_page_content_top_mm: ValueSource
    following_page_content_top_mm: ValueSource
    use_first_page_letterhead: ValueSource
    use_following_page_letterhead: ValueSource
    reuse_first_letterhead: ValueSource


class PageRulesSourcedValue(ImmutableModel):
    value: PageRulesEffective
    sources: PageRulesSources


class TypographyRulesDraft(StrictModel):
    font_family: str = Field(default="Noto Sans", min_length=1, max_length=128)
    base_size_pt: FontSize = Decimal("10")
    table_size_pt: Annotated[Decimal, Field(ge=7, le=14)] = Decimal("9")
    metadata_size_pt: Annotated[Decimal, Field(ge=7, le=12)] = Decimal("8")
    heading_scale: Annotated[Decimal, Field(ge=1.1, le=2)] = Decimal("1.4")
    line_height: Annotated[Decimal, Field(ge=1, le=2)] = Decimal("1.35")
    paragraph_spacing_mm: Annotated[Decimal, Field(ge=0, le=12)] = Decimal("3")
    accent_color: HexColor = "#5A6C60"
    text_color: HexColor = "#111111"
    muted_color: HexColor = "#666666"


class TypographyRulesPatch(StrictModel):
    font_family: Annotated[str, Field(min_length=1, max_length=128)] | None = None
    base_size_pt: FontSize | None = None
    table_size_pt: Annotated[Decimal, Field(ge=7, le=14)] | None = None
    metadata_size_pt: Annotated[Decimal, Field(ge=7, le=12)] | None = None
    heading_scale: Annotated[Decimal, Field(ge=1.1, le=2)] | None = None
    line_height: Annotated[Decimal, Field(ge=1, le=2)] | None = None
    paragraph_spacing_mm: Annotated[Decimal, Field(ge=0, le=12)] | None = None
    accent_color: HexColor | None = None
    text_color: HexColor | None = None
    muted_color: HexColor | None = None


class TypographyRulesEffective(ImmutableModel):
    font_family: str = Field(min_length=1, max_length=128)
    base_size_pt: FontSize
    table_size_pt: Annotated[Decimal, Field(ge=7, le=14)]
    metadata_size_pt: Annotated[Decimal, Field(ge=7, le=12)]
    heading_scale: Annotated[Decimal, Field(ge=1.1, le=2)]
    line_height: Annotated[Decimal, Field(ge=1, le=2)]
    paragraph_spacing_mm: Annotated[Decimal, Field(ge=0, le=12)]
    accent_color: HexColor
    text_color: HexColor
    muted_color: HexColor


class TypographyRulesSources(ImmutableModel):
    font_family: ValueSource
    base_size_pt: ValueSource
    table_size_pt: ValueSource
    metadata_size_pt: ValueSource
    heading_scale: ValueSource
    line_height: ValueSource
    paragraph_spacing_mm: ValueSource
    accent_color: ValueSource
    text_color: ValueSource
    muted_color: ValueSource


class TypographyRulesSourcedValue(ImmutableModel):
    value: TypographyRulesEffective
    sources: TypographyRulesSources


class HeaderRulesDraft(StrictModel):
    show_logo: bool = True
    logo_width_mm: Annotated[Decimal, Field(ge=8, le=80)] = Decimal("22")
    logo_alignment: Literal["left", "center", "right"] = "left"
    show_company_details: bool = True
    show_sender_line: bool = True
    recipient_window: Literal["left", "right"] = "left"
    recipient_top_mm: Annotated[Decimal, Field(ge=30, le=90)] = Decimal("45")


class HeaderRulesPatch(StrictModel):
    show_logo: bool | None = None
    logo_width_mm: Annotated[Decimal, Field(ge=8, le=80)] | None = None
    logo_alignment: Literal["left", "center", "right"] | None = None
    show_company_details: bool | None = None
    show_sender_line: bool | None = None
    recipient_window: Literal["left", "right"] | None = None
    recipient_top_mm: Annotated[Decimal, Field(ge=30, le=90)] | None = None


class HeaderRulesEffective(ImmutableModel):
    show_logo: bool
    logo_width_mm: Annotated[Decimal, Field(ge=8, le=80)]
    logo_alignment: Literal["left", "center", "right"]
    show_company_details: bool
    show_sender_line: bool
    recipient_window: Literal["left", "right"]
    recipient_top_mm: Annotated[Decimal, Field(ge=30, le=90)]


class HeaderRulesSources(ImmutableModel):
    show_logo: ValueSource
    logo_width_mm: ValueSource
    logo_alignment: ValueSource
    show_company_details: ValueSource
    show_sender_line: ValueSource
    recipient_window: ValueSource
    recipient_top_mm: ValueSource


class HeaderRulesSourcedValue(ImmutableModel):
    value: HeaderRulesEffective
    sources: HeaderRulesSources


class TitleRulesDraft(StrictModel):
    show_title: bool = True
    show_document_number: bool = True
    show_issue_date: bool = True
    show_service_date: bool = True
    show_due_date: bool = True
    show_customer_number: bool = True
    metadata_alignment: Literal["left", "right"] = "right"
    title_spacing_mm: Annotated[Decimal, Field(ge=0, le=20)] = Decimal("6")


class TitleRulesPatch(StrictModel):
    show_title: bool | None = None
    show_document_number: bool | None = None
    show_issue_date: bool | None = None
    show_service_date: bool | None = None
    show_due_date: bool | None = None
    show_customer_number: bool | None = None
    metadata_alignment: Literal["left", "right"] | None = None
    title_spacing_mm: Annotated[Decimal, Field(ge=0, le=20)] | None = None


class TitleRulesEffective(ImmutableModel):
    show_title: bool
    show_document_number: bool
    show_issue_date: bool
    show_service_date: bool
    show_due_date: bool
    show_customer_number: bool
    metadata_alignment: Literal["left", "right"]
    title_spacing_mm: Annotated[Decimal, Field(ge=0, le=20)]


class TitleRulesSources(ImmutableModel):
    show_title: ValueSource
    show_document_number: ValueSource
    show_issue_date: ValueSource
    show_service_date: ValueSource
    show_due_date: ValueSource
    show_customer_number: ValueSource
    metadata_alignment: ValueSource
    title_spacing_mm: ValueSource


class TitleRulesSourcedValue(ImmutableModel):
    value: TitleRulesEffective
    sources: TitleRulesSources


class PositionRulesDraft(StrictModel):
    table_style: Literal["compact", "standard", "spacious"] = "standard"
    show_position_number: bool = True
    show_description: bool = True
    show_quantity: bool = True
    show_unit: bool = True
    show_unit_price: bool = True
    show_net_amount: bool = False
    show_tax_rate: bool = False
    show_total: bool = True
    show_secondary_description: bool = True
    repeat_header: bool = True


class PositionRulesPatch(StrictModel):
    table_style: Literal["compact", "standard", "spacious"] | None = None
    show_position_number: bool | None = None
    show_description: bool | None = None
    show_quantity: bool | None = None
    show_unit: bool | None = None
    show_unit_price: bool | None = None
    show_net_amount: bool | None = None
    show_tax_rate: bool | None = None
    show_total: bool | None = None
    show_secondary_description: bool | None = None
    repeat_header: bool | None = None


class PositionRulesEffective(ImmutableModel):
    table_style: Literal["compact", "standard", "spacious"]
    show_position_number: bool
    show_description: bool
    show_quantity: bool
    show_unit: bool
    show_unit_price: bool
    show_net_amount: bool
    show_tax_rate: bool
    show_total: bool
    show_secondary_description: bool
    repeat_header: bool


class PositionRulesSources(ImmutableModel):
    table_style: ValueSource
    show_position_number: ValueSource
    show_description: ValueSource
    show_quantity: ValueSource
    show_unit: ValueSource
    show_unit_price: ValueSource
    show_net_amount: ValueSource
    show_tax_rate: ValueSource
    show_total: ValueSource
    show_secondary_description: ValueSource
    repeat_header: ValueSource


class PositionRulesSourcedValue(ImmutableModel):
    value: PositionRulesEffective
    sources: PositionRulesSources


class TotalsRulesDraft(StrictModel):
    show_subtotal: bool = True
    show_discount: bool = True
    show_tax_breakdown: bool = True
    show_gross_total: bool = True
    show_prepayments: bool = True
    show_payment_terms: bool = True
    show_bank_details: bool = True
    totals_alignment: Literal["left", "right"] = "right"


class TotalsRulesPatch(StrictModel):
    show_subtotal: bool | None = None
    show_discount: bool | None = None
    show_tax_breakdown: bool | None = None
    show_gross_total: bool | None = None
    show_prepayments: bool | None = None
    show_payment_terms: bool | None = None
    show_bank_details: bool | None = None
    totals_alignment: Literal["left", "right"] | None = None


class TotalsRulesEffective(ImmutableModel):
    show_subtotal: bool
    show_discount: bool
    show_tax_breakdown: bool
    show_gross_total: bool
    show_prepayments: bool
    show_payment_terms: bool
    show_bank_details: bool
    totals_alignment: Literal["left", "right"]


class TotalsRulesSources(ImmutableModel):
    show_subtotal: ValueSource
    show_discount: ValueSource
    show_tax_breakdown: ValueSource
    show_gross_total: ValueSource
    show_prepayments: ValueSource
    show_payment_terms: ValueSource
    show_bank_details: ValueSource
    totals_alignment: ValueSource


class TotalsRulesSourcedValue(ImmutableModel):
    value: TotalsRulesEffective
    sources: TotalsRulesSources


class TechnicalRulesDraft(StrictModel):
    enabled: bool = True
    show_printer: bool = True
    show_plate: bool = True
    show_material: bool = True
    show_print_time: bool = True
    show_weight: bool = True
    show_file_name: bool = False
    placement: Literal["position", "notes"] = "position"


class TechnicalRulesPatch(StrictModel):
    enabled: bool | None = None
    show_printer: bool | None = None
    show_plate: bool | None = None
    show_material: bool | None = None
    show_print_time: bool | None = None
    show_weight: bool | None = None
    show_file_name: bool | None = None
    placement: Literal["position", "notes"] | None = None


class TechnicalRulesEffective(ImmutableModel):
    enabled: bool
    show_printer: bool
    show_plate: bool
    show_material: bool
    show_print_time: bool
    show_weight: bool
    show_file_name: bool
    placement: Literal["position", "notes"]


class TechnicalRulesSources(ImmutableModel):
    enabled: ValueSource
    show_printer: ValueSource
    show_plate: ValueSource
    show_material: ValueSource
    show_print_time: ValueSource
    show_weight: ValueSource
    show_file_name: ValueSource
    placement: ValueSource


class TechnicalRulesSourcedValue(ImmutableModel):
    value: TechnicalRulesEffective
    sources: TechnicalRulesSources


class NotesRulesDraft(StrictModel):
    show_intro_text: bool = True
    show_outro_text: bool = True
    show_payment_note: bool = True
    show_legal_note: bool = True
    intro_placement: Literal["before_title", "before_positions"] = "before_positions"
    outro_placement: Literal["after_positions", "after_totals"] = "after_totals"
    keep_with_next: bool = True


class NotesRulesPatch(StrictModel):
    show_intro_text: bool | None = None
    show_outro_text: bool | None = None
    show_payment_note: bool | None = None
    show_legal_note: bool | None = None
    intro_placement: Literal["before_title", "before_positions"] | None = None
    outro_placement: Literal["after_positions", "after_totals"] | None = None
    keep_with_next: bool | None = None


class NotesRulesEffective(ImmutableModel):
    show_intro_text: bool
    show_outro_text: bool
    show_payment_note: bool
    show_legal_note: bool
    intro_placement: Literal["before_title", "before_positions"]
    outro_placement: Literal["after_positions", "after_totals"]
    keep_with_next: bool


class NotesRulesSources(ImmutableModel):
    show_intro_text: ValueSource
    show_outro_text: ValueSource
    show_payment_note: ValueSource
    show_legal_note: ValueSource
    intro_placement: ValueSource
    outro_placement: ValueSource
    keep_with_next: ValueSource


class NotesRulesSourcedValue(ImmutableModel):
    value: NotesRulesEffective
    sources: NotesRulesSources


class FooterRulesDraft(StrictModel):
    enabled: bool = True
    column_layout: Literal["one", "two", "three"] = "three"
    show_company_data: bool = True
    show_tax_data: bool = True
    show_bank_data: bool = True
    show_alternative_payment: bool = True
    show_additional_notes: bool = False
    show_page_numbers: bool = True
    page_number_format: str = Field(default="Seite {page}/{pages}", min_length=1, max_length=64)


class FooterRulesPatch(StrictModel):
    enabled: bool | None = None
    column_layout: Literal["one", "two", "three"] | None = None
    show_company_data: bool | None = None
    show_tax_data: bool | None = None
    show_bank_data: bool | None = None
    show_alternative_payment: bool | None = None
    show_additional_notes: bool | None = None
    show_page_numbers: bool | None = None
    page_number_format: Annotated[str, Field(min_length=1, max_length=64)] | None = None


class FooterRulesEffective(ImmutableModel):
    enabled: bool
    column_layout: Literal["one", "two", "three"]
    show_company_data: bool
    show_tax_data: bool
    show_bank_data: bool
    show_alternative_payment: bool
    show_additional_notes: bool
    show_page_numbers: bool
    page_number_format: str = Field(min_length=1, max_length=64)


class FooterRulesSources(ImmutableModel):
    enabled: ValueSource
    column_layout: ValueSource
    show_company_data: ValueSource
    show_tax_data: ValueSource
    show_bank_data: ValueSource
    show_alternative_payment: ValueSource
    show_additional_notes: ValueSource
    show_page_numbers: ValueSource
    page_number_format: ValueSource


class FooterRulesSourcedValue(ImmutableModel):
    value: FooterRulesEffective
    sources: FooterRulesSources


class EffectiveDocumentLayout(ImmutableModel):
    schema_version: int = Field(ge=1)
    template_version: str = Field(min_length=1, max_length=32)
    renderer_version: str = Field(min_length=1, max_length=128)
    validator_version: str = Field(min_length=1, max_length=128)
    page: PageRulesEffective
    typography: TypographyRulesEffective
    header: HeaderRulesEffective
    title: TitleRulesEffective
    positions: PositionRulesEffective
    totals: TotalsRulesEffective
    technical: TechnicalRulesEffective
    notes: NotesRulesEffective
    footer: FooterRulesEffective


class SourcedDocumentLayout(ImmutableModel):
    effective: EffectiveDocumentLayout
    page: PageRulesSourcedValue
    typography: TypographyRulesSourcedValue
    header: HeaderRulesSourcedValue
    title: TitleRulesSourcedValue
    positions: PositionRulesSourcedValue
    totals: TotalsRulesSourcedValue
    technical: TechnicalRulesSourcedValue
    notes: NotesRulesSourcedValue
    footer: FooterRulesSourcedValue


class LayoutScope(ImmutableModel):
    business_profile_id: int = Field(gt=0)
    document_type: str | None = Field(default=None, max_length=32)
    language: Literal["de", "en"] | None = None

    @model_validator(mode="after")
    def language_requires_document_type(self) -> LayoutScope:
        if self.language is not None and self.document_type is None:
            raise ValueError("language scope requires document_type")
        return self


class CreateLayoutRequest(StrictModel):
    scope: LayoutScope
    template_key: TemplateKey = "classic"
    reason: str = Field(min_length=3, max_length=1000)


class CloneLayoutRequest(StrictModel):
    source_layout_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)


class PatchLayoutRequest(StrictModel):
    expected_lock_version: int = Field(ge=1)
    edit_session_id: str = Field(min_length=8, max_length=64)
    page: PageRulesPatch | None = None
    typography: TypographyRulesPatch | None = None
    header: HeaderRulesPatch | None = None
    title: TitleRulesPatch | None = None
    positions: PositionRulesPatch | None = None
    totals: TotalsRulesPatch | None = None
    technical: TechnicalRulesPatch | None = None
    notes: NotesRulesPatch | None = None
    footer: FooterRulesPatch | None = None


class PublishLayoutRequest(StrictModel):
    expected_lock_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)
    effective_from: datetime | None = None


class WithdrawLayoutRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=1000)


class LayoutSummary(ImmutableModel):
    id: int
    scope: LayoutScope
    version: int
    status: Literal["draft", "scheduled", "active", "superseded", "withdrawn"]
    lock_version: int
    effective_from: datetime | None
    created_at: datetime
    updated_at: datetime


class LayoutAssetMetadata(ImmutableModel):
    id: int
    business_profile_id: int
    asset_type: Literal["logo", "letterhead_first", "letterhead_following", "font"]
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preflight_status: Literal["pending", "valid", "invalid"]
    preflight_report: dict
    created_at: datetime


class AssetUploadRequest(StrictModel):
    business_profile_id: int = Field(gt=0)
    asset_type: Literal["logo", "letterhead_first", "letterhead_following", "font"]
    original_name: str = Field(min_length=1, max_length=255)
    declared_mime_type: str = Field(min_length=3, max_length=128)
    declared_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    font_embedding_rights_confirmed: bool = False


class AssetLinkRequest(StrictModel):
    asset_id: int = Field(gt=0)
    role: Literal[
        "logo",
        "letterhead_first",
        "letterhead_following",
        "font_regular",
        "font_bold",
        "font_italic",
        "font_bold_italic",
    ]


class PreviewRequest(StrictModel):
    layout_id: int = Field(gt=0)
    layout_lock_version: int = Field(gt=0)
    source_kind: Literal["sample", "document"]
    source_id: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_source_reference(self) -> PreviewRequest:
        if self.source_kind == "document" and (
            not self.source_id.isascii()
            or not self.source_id.isdecimal()
            or int(self.source_id) <= 0
        ):
            raise ValueError("document source_id must be a positive decimal identifier")
        return self


class PreviewJobResponse(ImmutableModel):
    public_id: str
    status: Literal["queued", "running", "ready", "failed", "expired"]
    layout_id: int
    lock_version: int
    expires_at: datetime
    result_sha256: str | None = None


class LayoutFinding(ImmutableModel):
    code: str = Field(min_length=1, max_length=128)
    severity: Literal["info", "warning", "blocker"]
    field_path: str | None = None
    message_key: str = Field(min_length=1, max_length=160)
    message: str
    correction_hint: str | None = None
    external_rule_id: str | None = Field(default=None, max_length=160)


class LayoutReadinessReport(ImmutableModel):
    ready: bool
    findings: tuple[LayoutFinding, ...]
    renderer_version: str
    validator_version: str


class LayoutAuditReceiptSchema(ImmutableModel):
    id: int
    layout_id: int
    event_type: str
    edit_session_id: str | None
    reason: str | None
    changed_field_paths: tuple[str, ...]
    actor_id: int | None
    first_seen_at: datetime
    last_seen_at: datetime


class ExternalRenderRequest(StrictModel):
    document_snapshot_id: int = Field(gt=0)
    published_layout_id: int | None = Field(default=None, gt=0)
    zugferd_artifact_id: int | None = Field(default=None, gt=0)
    xrechnung_artifact_id: int | None = Field(default=None, gt=0)
    idempotency_id: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def one_einvoice_reference(self) -> ExternalRenderRequest:
        if self.zugferd_artifact_id is not None and self.xrechnung_artifact_id is not None:
            raise ValueError("ZUGFeRD and XRechnung artifact references are mutually exclusive")
        return self


class ExternalRenderResponse(ImmutableModel):
    artifact_id: int
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    validation_status: Literal["valid", "invalid", "unvalidated"]
    content_type: str
    correlation_id: str
