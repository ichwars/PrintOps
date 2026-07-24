"""Versioned, relational document layout aggregate and immutable evidence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    inspect,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class ImmutableLayoutError(RuntimeError):
    """Raised when versioned layout evidence would be rewritten."""


def _scope_key(document_type: str | None, language: str | None) -> str:
    return f"{document_type or '*'}|{language or '*'}"


class DocumentLayoutConfiguration(Base):
    __tablename__ = "document_layout_configurations"
    __table_args__ = (
        UniqueConstraint(
            "business_profile_id",
            "scope_key",
            "version",
            name="uq_document_layout_scope_version",
        ),
        CheckConstraint(
            "language IS NULL OR document_type IS NOT NULL",
            name="ck_document_layout_language_requires_type",
        ),
        CheckConstraint(
            "status IN ('draft','scheduled','active','superseded','withdrawn')",
            name="ck_document_layout_status",
        ),
        CheckConstraint("orientation = 'portrait'", name="ck_document_layout_portrait"),
        CheckConstraint("page_format IN ('A4','Letter')", name="ck_document_layout_page_format"),
        CheckConstraint(
            "template_key IN ('classic','modern','compact')",
            name="ck_document_layout_template",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"),
        index=True,
    )
    document_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scope_key: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    template_key: Mapped[str] = mapped_column(String(16), default="classic")
    page_format: Mapped[str] = mapped_column(String(16), default="A4")
    orientation: Mapped[str] = mapped_column(String(16), default="portrait")
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    renderer_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validator_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="pending")
    validation_report: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    page_rules: Mapped[LayoutPageRules | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    typography_rules: Mapped[LayoutTypographyRules | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    header_rules: Mapped[LayoutHeaderRules | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    title_rules: Mapped[LayoutTitleRules | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    position_rules: Mapped[LayoutPositionRules | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    totals_rules: Mapped[LayoutTotalsRules | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    technical_rules: Mapped[LayoutTechnicalRules | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    notes_rules: Mapped[LayoutNotesRules | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    footer_rules: Mapped[LayoutFooterRules | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    asset_links: Mapped[list[DocumentLayoutAssetLink]] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", lazy="selectin"
    )
    publication: Mapped[DocumentLayoutPublication | None] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )
    audit_receipts: Mapped[list[DocumentLayoutAuditReceipt]] = relationship(
        back_populates="configuration", cascade="all, delete-orphan", lazy="selectin"
    )
    preview_jobs: Mapped[list[DocumentPreviewJob]] = relationship(back_populates="configuration")
class LayoutPageRules(Base):
    __tablename__ = "layout_page_rules"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), primary_key=True
    )
    margin_top_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("18"))
    margin_right_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("18"))
    margin_bottom_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("18"))
    margin_left_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("18"))
    first_page_content_top_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("45"))
    following_page_content_top_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("20"))
    use_first_page_letterhead: Mapped[bool] = mapped_column(Boolean, default=False)
    use_following_page_letterhead: Mapped[bool] = mapped_column(Boolean, default=False)
    reuse_first_letterhead: Mapped[bool] = mapped_column(Boolean, default=False)
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="page_rules")


class LayoutTypographyRules(Base):
    __tablename__ = "layout_typography_rules"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), primary_key=True
    )
    font_family: Mapped[str] = mapped_column(String(128), default="Noto Sans")
    base_size_pt: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal("10"))
    table_size_pt: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal("9"))
    metadata_size_pt: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal("8"))
    heading_scale: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.40"))
    line_height: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.35"))
    paragraph_spacing_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("3"))
    accent_color: Mapped[str] = mapped_column(String(7), default="#5A6C60")
    text_color: Mapped[str] = mapped_column(String(7), default="#111111")
    muted_color: Mapped[str] = mapped_column(String(7), default="#666666")
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="typography_rules")


class LayoutHeaderRules(Base):
    __tablename__ = "layout_header_rules"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), primary_key=True
    )
    show_logo: Mapped[bool] = mapped_column(Boolean, default=True)
    logo_width_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("22"))
    logo_alignment: Mapped[str] = mapped_column(String(16), default="left")
    show_company_details: Mapped[bool] = mapped_column(Boolean, default=True)
    show_sender_line: Mapped[bool] = mapped_column(Boolean, default=True)
    recipient_window: Mapped[str] = mapped_column(String(16), default="left")
    recipient_top_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("45"))
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="header_rules")


class LayoutTitleRules(Base):
    __tablename__ = "layout_title_rules"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), primary_key=True
    )
    show_title: Mapped[bool] = mapped_column(Boolean, default=True)
    show_document_number: Mapped[bool] = mapped_column(Boolean, default=True)
    show_issue_date: Mapped[bool] = mapped_column(Boolean, default=True)
    show_service_date: Mapped[bool] = mapped_column(Boolean, default=True)
    show_due_date: Mapped[bool] = mapped_column(Boolean, default=True)
    show_customer_number: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_alignment: Mapped[str] = mapped_column(String(16), default="right")
    title_spacing_mm: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("6"))
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="title_rules")


class LayoutPositionRules(Base):
    __tablename__ = "layout_position_rules"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), primary_key=True
    )
    table_style: Mapped[str] = mapped_column(String(16), default="standard")
    show_position_number: Mapped[bool] = mapped_column(Boolean, default=True)
    show_description: Mapped[bool] = mapped_column(Boolean, default=True)
    show_quantity: Mapped[bool] = mapped_column(Boolean, default=True)
    show_unit: Mapped[bool] = mapped_column(Boolean, default=True)
    show_unit_price: Mapped[bool] = mapped_column(Boolean, default=True)
    show_net_amount: Mapped[bool] = mapped_column(Boolean, default=False)
    show_tax_rate: Mapped[bool] = mapped_column(Boolean, default=False)
    show_total: Mapped[bool] = mapped_column(Boolean, default=True)
    show_secondary_description: Mapped[bool] = mapped_column(Boolean, default=True)
    repeat_header: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="position_rules")


class LayoutTotalsRules(Base):
    __tablename__ = "layout_totals_rules"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), primary_key=True
    )
    show_subtotal: Mapped[bool] = mapped_column(Boolean, default=True)
    show_discount: Mapped[bool] = mapped_column(Boolean, default=True)
    show_tax_breakdown: Mapped[bool] = mapped_column(Boolean, default=True)
    show_gross_total: Mapped[bool] = mapped_column(Boolean, default=True)
    show_prepayments: Mapped[bool] = mapped_column(Boolean, default=True)
    show_payment_terms: Mapped[bool] = mapped_column(Boolean, default=True)
    show_bank_details: Mapped[bool] = mapped_column(Boolean, default=True)
    totals_alignment: Mapped[str] = mapped_column(String(16), default="right")
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="totals_rules")


class LayoutTechnicalRules(Base):
    __tablename__ = "layout_technical_rules"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    show_printer: Mapped[bool] = mapped_column(Boolean, default=True)
    show_plate: Mapped[bool] = mapped_column(Boolean, default=True)
    show_material: Mapped[bool] = mapped_column(Boolean, default=True)
    show_print_time: Mapped[bool] = mapped_column(Boolean, default=True)
    show_weight: Mapped[bool] = mapped_column(Boolean, default=True)
    show_file_name: Mapped[bool] = mapped_column(Boolean, default=False)
    placement: Mapped[str] = mapped_column(String(16), default="position")
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="technical_rules")


class LayoutNotesRules(Base):
    __tablename__ = "layout_notes_rules"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), primary_key=True
    )
    show_intro_text: Mapped[bool] = mapped_column(Boolean, default=True)
    show_outro_text: Mapped[bool] = mapped_column(Boolean, default=True)
    show_payment_note: Mapped[bool] = mapped_column(Boolean, default=True)
    show_legal_note: Mapped[bool] = mapped_column(Boolean, default=True)
    intro_placement: Mapped[str] = mapped_column(String(16), default="before_positions")
    outro_placement: Mapped[str] = mapped_column(String(16), default="after_totals")
    keep_with_next: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="notes_rules")


class LayoutFooterRules(Base):
    __tablename__ = "layout_footer_rules"

    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    column_layout: Mapped[str] = mapped_column(String(16), default="three")
    show_company_data: Mapped[bool] = mapped_column(Boolean, default=True)
    show_tax_data: Mapped[bool] = mapped_column(Boolean, default=True)
    show_bank_data: Mapped[bool] = mapped_column(Boolean, default=True)
    show_alternative_payment: Mapped[bool] = mapped_column(Boolean, default=True)
    show_additional_notes: Mapped[bool] = mapped_column(Boolean, default=False)
    show_page_numbers: Mapped[bool] = mapped_column(Boolean, default=True)
    page_number_format: Mapped[str] = mapped_column(String(64), default="Seite {page}/{pages}")
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="footer_rules")


class DocumentLayoutAsset(Base):
    __tablename__ = "document_layout_assets"
    __table_args__ = (
        UniqueConstraint("business_profile_id", "sha256", name="uq_document_layout_asset_hash"),
        CheckConstraint(
            "asset_type IN ('logo','letterhead_first','letterhead_following','font')",
            name="ck_document_layout_asset_type",
        ),
        CheckConstraint(
            "preflight_status IN ('pending','valid','invalid')",
            name="ck_document_layout_asset_preflight",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"), index=True
    )
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    preflight_status: Mapped[str] = mapped_column(String(16), default="pending")
    preflight_report: Mapped[dict] = mapped_column(JSON, default=dict)
    pdf_width_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    pdf_height_mm: Mapped[Decimal | None] = mapped_column(Numeric(7, 2), nullable=True)
    pdf_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    font_family: Mapped[str | None] = mapped_column(String(255), nullable=True)
    font_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    font_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    font_glyph_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    font_embedding_allowed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    first_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    links: Mapped[list[DocumentLayoutAssetLink]] = relationship(back_populates="asset")


class DocumentLayoutAssetLink(Base):
    __tablename__ = "document_layout_asset_links"
    __table_args__ = (
        UniqueConstraint("configuration_id", "role", name="uq_document_layout_asset_role"),
        CheckConstraint(
            "role IN ('logo','letterhead_first','letterhead_following','font_regular',"
            "'font_bold','font_italic','font_bold_italic')",
            name="ck_document_layout_asset_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_assets.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="asset_links")
    asset: Mapped[DocumentLayoutAsset] = relationship(back_populates="links")


class DocumentLayoutPublication(Base):
    __tablename__ = "document_layout_publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="RESTRICT"), unique=True, index=True
    )
    effective_sha256: Mapped[str] = mapped_column(String(64), index=True)
    asset_receipts: Mapped[dict] = mapped_column(JSON, default=dict)
    renderer_version: Mapped[str] = mapped_column(String(128))
    validator_version: Mapped[str] = mapped_column(String(128))
    validation_status: Mapped[str] = mapped_column(String(32))
    validation_report: Mapped[dict] = mapped_column(JSON, default=dict)
    published_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="publication")


class DocumentLayoutAuditReceipt(Base):
    __tablename__ = "document_layout_audit_receipts"
    __table_args__ = (
        UniqueConstraint("configuration_id", "edit_session_id", name="uq_layout_audit_edit_session"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    edit_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_field_paths: Mapped[list] = mapped_column(JSON, default=list)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    before_lock_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_lock_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="audit_receipts")


class DocumentPreviewJob(Base):
    __tablename__ = "document_preview_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','ready','failed','expired')",
            name="ck_document_preview_job_status",
        ),
        CheckConstraint("source_type IN ('sample','document')", name="ck_document_preview_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid4())
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    business_profile_id: Mapped[int] = mapped_column(
        ForeignKey("business_profiles.id", ondelete="RESTRICT"), index=True
    )
    configuration_id: Mapped[int] = mapped_column(
        ForeignKey("document_layout_configurations.id", ondelete="RESTRICT"), index=True
    )
    layout_lock_version: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(16))
    source_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cache_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    result_storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    findings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    configuration: Mapped[DocumentLayoutConfiguration] = relationship(back_populates="preview_jobs")


RULE_MODELS = (
    LayoutPageRules,
    LayoutTypographyRules,
    LayoutHeaderRules,
    LayoutTitleRules,
    LayoutPositionRules,
    LayoutTotalsRules,
    LayoutTechnicalRules,
    LayoutNotesRules,
    LayoutFooterRules,
)


def _set_scope_key(_mapper, _connection, target: DocumentLayoutConfiguration) -> None:
    target.scope_key = _scope_key(target.document_type, target.language)


def _reject_published_layout_change(_mapper, _connection, target) -> None:
    state = inspect(target)
    status_history = state.attrs.status.history
    original_status = status_history.deleted[0] if status_history.deleted else target.status
    if original_status != "draft" and not getattr(target, "_allow_layout_lifecycle_mutation", False):
        raise ImmutableLayoutError(f"published {type(target).__name__} is immutable")


def _configuration_status(connection, configuration_id: int) -> str | None:
    return connection.execute(
        select(DocumentLayoutConfiguration.status).where(
            DocumentLayoutConfiguration.id == configuration_id
        )
    ).scalar_one_or_none()


def _reject_rule_change(_mapper, connection, target) -> None:
    if getattr(target, "_allow_layout_lifecycle_mutation", False):
        return
    status = _configuration_status(connection, target.configuration_id)
    if status != "draft":
        raise ImmutableLayoutError(f"published {type(target).__name__} is immutable")
    raise ImmutableLayoutError("draft layout rules may only be changed by the lifecycle service")


def _reject_used_asset_change(_mapper, connection, target: DocumentLayoutAsset) -> None:
    if getattr(target, "_allow_layout_asset_mutation", False):
        return
    used = target.first_used_at is not None or connection.execute(
        select(DocumentLayoutAssetLink.id)
        .join(
            DocumentLayoutConfiguration,
            DocumentLayoutConfiguration.id == DocumentLayoutAssetLink.configuration_id,
        )
        .where(
            DocumentLayoutAssetLink.asset_id == target.id,
            DocumentLayoutConfiguration.status != "draft",
        )
        .limit(1)
    ).first()
    if used:
        raise ImmutableLayoutError("an asset used by a published layout is immutable")


def _reject_asset_link_change(_mapper, connection, target: DocumentLayoutAssetLink) -> None:
    if getattr(target, "_allow_layout_lifecycle_mutation", False):
        return
    if _configuration_status(connection, target.configuration_id) != "draft":
        raise ImmutableLayoutError("published layout asset links are immutable")


def _reject_receipt_change(_mapper, _connection, target) -> None:
    raise ImmutableLayoutError(f"{type(target).__name__} is append-only")


event.listen(DocumentLayoutConfiguration, "before_insert", _set_scope_key)
event.listen(DocumentLayoutConfiguration, "before_update", _set_scope_key)
event.listen(DocumentLayoutConfiguration, "before_update", _reject_published_layout_change)
event.listen(DocumentLayoutConfiguration, "before_delete", _reject_published_layout_change)
for _rule_model in RULE_MODELS:
    event.listen(_rule_model, "before_update", _reject_rule_change)
    event.listen(_rule_model, "before_delete", _reject_rule_change)
event.listen(DocumentLayoutAsset, "before_update", _reject_used_asset_change)
event.listen(DocumentLayoutAsset, "before_delete", _reject_used_asset_change)
event.listen(DocumentLayoutAssetLink, "before_update", _reject_asset_link_change)
event.listen(DocumentLayoutAssetLink, "before_delete", _reject_asset_link_change)
event.listen(DocumentLayoutPublication, "before_update", _reject_receipt_change)
event.listen(DocumentLayoutPublication, "before_delete", _reject_receipt_change)
event.listen(DocumentLayoutAuditReceipt, "before_update", _reject_receipt_change)
event.listen(DocumentLayoutAuditReceipt, "before_delete", _reject_receipt_change)
