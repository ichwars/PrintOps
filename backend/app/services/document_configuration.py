"""Lifecycle and field-level inheritance for document configuration."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.customer import CustomerAccount
from backend.app.models.document_configuration import (
    ConfigurationPublication,
    DocumentBasicPolicy,
    DocumentConfiguration,
    DocumentContentPolicy,
    DocumentTextBlock,
    DunningPolicy,
    DunningStage,
    EInvoicePolicy,
    PaymentPolicy,
    TaxPolicy,
)
from backend.app.schemas.document_configuration import (
    BankAssignmentDraft,
    BasicPolicyDraft,
    ContentPolicyDraft,
    CreateConfigurationCommand,
    DocumentConfigurationDraft,
    DocumentTextBlockDraft,
    DunningPolicyDraft,
    DunningStageDraft,
    EffectiveBasicPolicy,
    EffectiveContentPolicy,
    EffectiveDocumentPolicy,
    EffectiveEInvoicePolicy,
    EffectivePaymentPolicy,
    EffectiveTaxPolicy,
    EffectiveTextBlock,
    InstallmentDraft,
    PaymentPolicyDraft,
    SourcedValue,
)
from backend.app.services.document_catalog import DOCUMENT_CAPABILITIES, DocumentType, EInvoiceRequirement
from backend.app.services.document_defaults import load_document_defaults
from backend.app.services.document_policy_validation import ConfigurationNotReady, validate_policy
from backend.app.services.order_errors import InvalidStateConflictError, ResourceNotFoundError, VersionConflictError


def _configuration_options():
    return (
        selectinload(DocumentConfiguration.basic_policy),
        selectinload(DocumentConfiguration.payment_policy),
        selectinload(DocumentConfiguration.dunning_policy).selectinload(DunningPolicy.stages),
        selectinload(DocumentConfiguration.text_blocks),
        selectinload(DocumentConfiguration.content_policy),
        selectinload(DocumentConfiguration.tax_policy),
        selectinload(DocumentConfiguration.einvoice_policy),
        selectinload(DocumentConfiguration.publication),
    )


async def _load_configuration(
    session: AsyncSession,
    configuration_id: int,
    *,
    populate_existing: bool = False,
) -> DocumentConfiguration:
    statement = (
        select(DocumentConfiguration)
        .where(DocumentConfiguration.id == configuration_id)
        .options(*_configuration_options())
        .execution_options(populate_existing=populate_existing)
    )
    configuration = await session.scalar(statement)
    if configuration is None:
        raise ResourceNotFoundError(f"Document configuration {configuration_id} was not found")
    return configuration


async def load_configuration(session: AsyncSession, configuration_id: int) -> DocumentConfiguration:
    return await _load_configuration(session, configuration_id)


def _copy_child(child: Any, model_type: type, excluded: set[str]) -> Any:
    if child is None:
        return None
    values = {
        column.name: deepcopy(getattr(child, column.name))
        for column in child.__table__.columns
        if column.name not in excluded
    }
    return model_type(**values)


async def create_draft(
    session: AsyncSession,
    command: CreateConfigurationCommand,
    actor_id: int | None,
) -> DocumentConfiguration:
    profile = await session.get(BusinessProfile, command.business_profile_id)
    if profile is None:
        raise ResourceNotFoundError(f"Business profile {command.business_profile_id} was not found")

    highest_version = await session.scalar(
        select(func.max(DocumentConfiguration.version)).where(
            DocumentConfiguration.business_profile_id == command.business_profile_id,
            DocumentConfiguration.document_type == command.document_type.value,
            DocumentConfiguration.language == command.language,
        )
    )
    resource_language = command.language if command.language in {"de", "en"} else command.language.split("-", 1)[0]
    defaults = load_document_defaults(resource_language)
    document_defaults = defaults["documents"][command.document_type.value]
    capability = DOCUMENT_CAPABILITIES[command.document_type]

    configuration = DocumentConfiguration(
        business_profile_id=command.business_profile_id,
        document_type=command.document_type.value,
        language=command.language,
        version=(highest_version or 0) + 1,
        status="draft",
        lock_version=1,
        change_reason=command.change_reason,
        created_by_id=actor_id,
    )
    configuration.basic_policy = DocumentBasicPolicy(
        subject=document_defaults["subject"],
        validity_days=(defaults["defaults"]["validity_days"] if command.document_type is DocumentType.QUOTATION else None),
        allowed_successors=sorted(successor.value for successor in capability.allowed_successors),
    )
    configuration.payment_policy = PaymentPolicy(
        payment_term_days=defaults["defaults"]["payment_term_days"],
        currency=profile.default_currency,
        use_term_in_invoice_text=defaults["defaults"]["use_payment_term_in_invoice_text"],
    )
    configuration.dunning_policy = DunningPolicy(enabled=command.document_type is DocumentType.DUNNING_NOTICE)
    configuration.content_policy = DocumentContentPolicy(
        include_calculation_data=defaults["defaults"]["include_calculation_data"]
    )
    configuration.tax_policy = TaxPolicy()
    configuration.einvoice_policy = EInvoicePolicy(
        requirement=(
            EInvoiceRequirement.RULE_REQUIRED.value if capability.einvoice else EInvoiceRequirement.OPTIONAL.value
        )
    )
    text_values = {
        "intro": document_defaults["intro"],
        "closing": document_defaults["closing"],
    }
    if capability.has_payment_terms:
        text_values["payment_terms"] = defaults["payment_terms"]
    configuration.text_blocks = [
        DocumentTextBlock(purpose=purpose, body=body, position=position)
        for position, (purpose, body) in enumerate(text_values.items())
    ]
    session.add(configuration)
    await session.flush()
    return await _load_configuration(session, configuration.id, populate_existing=True)


async def clone_version(session: AsyncSession, configuration_id: int, actor_id: int | None) -> DocumentConfiguration:
    source = await _load_configuration(session, configuration_id)
    highest_version = await session.scalar(
        select(func.max(DocumentConfiguration.version)).where(
            DocumentConfiguration.business_profile_id == source.business_profile_id,
            DocumentConfiguration.document_type == source.document_type,
            DocumentConfiguration.language == source.language,
        )
    )
    clone = DocumentConfiguration(
        business_profile_id=source.business_profile_id,
        document_type=source.document_type,
        language=source.language,
        version=(highest_version or source.version) + 1,
        status="draft",
        lock_version=1,
        change_reason=None,
        created_by_id=actor_id,
    )
    clone.basic_policy = _copy_child(source.basic_policy, DocumentBasicPolicy, {"configuration_id"})
    clone.payment_policy = _copy_child(source.payment_policy, PaymentPolicy, {"configuration_id"})
    clone.dunning_policy = _copy_child(source.dunning_policy, DunningPolicy, {"configuration_id"})
    if clone.dunning_policy is not None and source.dunning_policy is not None:
        clone.dunning_policy.stages = [
            _copy_child(stage, DunningStage, {"id", "dunning_policy_id"}) for stage in source.dunning_policy.stages
        ]
    clone.content_policy = _copy_child(source.content_policy, DocumentContentPolicy, {"configuration_id"})
    clone.tax_policy = _copy_child(source.tax_policy, TaxPolicy, {"configuration_id"})
    clone.einvoice_policy = _copy_child(source.einvoice_policy, EInvoicePolicy, {"configuration_id"})
    clone.text_blocks = [
        _copy_child(block, DocumentTextBlock, {"id", "configuration_id"}) for block in source.text_blocks
    ]
    session.add(clone)
    await session.flush()
    return clone


async def update_draft(
    session: AsyncSession,
    configuration_id: int,
    expected_version: int,
    patch: dict[str, Any],
    actor_id: int | None,
) -> DocumentConfiguration:
    result = await session.execute(
        update(DocumentConfiguration)
        .where(
            DocumentConfiguration.id == configuration_id,
            DocumentConfiguration.status == "draft",
            DocumentConfiguration.lock_version == expected_version,
        )
        .values(lock_version=expected_version + 1)
        .returning(DocumentConfiguration.id)
    )
    if result.scalar_one_or_none() is None:
        existing = await session.get(DocumentConfiguration, configuration_id)
        if existing is None:
            raise ResourceNotFoundError(f"Document configuration {configuration_id} was not found")
        if existing.status != "draft":
            raise InvalidStateConflictError("Only draft document configurations can be updated")
        raise VersionConflictError(f"Document configuration {configuration_id} changed concurrently")

    configuration = await _load_configuration(session, configuration_id, populate_existing=True)
    section_targets = {
        "basic": configuration.basic_policy,
        "payment": configuration.payment_policy,
        "dunning": configuration.dunning_policy,
        "content": configuration.content_policy,
        "tax": configuration.tax_policy,
        "einvoice": configuration.einvoice_policy,
    }
    for section, values in patch.items():
        if section == "change_reason":
            configuration.change_reason = str(values) if values is not None else None
            continue
        if section == "text_blocks":
            configuration.text_blocks = [DocumentTextBlock(**deepcopy(item)) for item in values]
            continue
        target = section_targets.get(section)
        if target is None or not isinstance(values, dict):
            raise InvalidStateConflictError(f"Unsupported document configuration patch section: {section}")
        values = deepcopy(values)
        if section == "dunning" and "stages" in values:
            target.stages = [DunningStage(**DunningStageDraft.model_validate(item).model_dump()) for item in values.pop("stages")]
        if section == "payment":
            discount_days = values.pop("discount_days", None)
            discount_percent = values.pop("discount_percent", None)
            if discount_days is not None or discount_percent is not None:
                current_rule = target.early_payment_rules[0] if target.early_payment_rules else {}
                target.early_payment_rules = [
                    {
                        "days": discount_days if discount_days is not None else current_rule.get("days", 0),
                        "percent": str(
                            discount_percent if discount_percent is not None else current_rule.get("percent", "0")
                        ),
                    }
                ]
            if "installments" in values:
                target.installments = [
                    {
                        "percent": str(InstallmentDraft.model_validate(item).percent),
                        "due_days": InstallmentDraft.model_validate(item).due_days,
                    }
                    for item in values.pop("installments")
                ]
            if "bank_assignments" in values:
                assignments = [BankAssignmentDraft.model_validate(item) for item in values.pop("bank_assignments")]
                defaults = [assignment for assignment in assignments if assignment.is_default]
                target.bank_account_id = defaults[0].bank_account_id if len(defaults) == 1 else None
        column_names = {column.name for column in target.__table__.columns}
        for field, value in values.items():
            if field not in column_names or field in {"configuration_id", "id"}:
                raise InvalidStateConflictError(f"Unsupported field {section}.{field}")
            setattr(target, field, deepcopy(value))

    await session.flush()
    configuration.validation_findings = validate_policy(_as_policy_draft(configuration))
    return configuration


async def publish(
    session: AsyncSession,
    configuration_id: int,
    expected_version: int,
    effective_from: date,
    reason: str,
    actor_id: int | None,
    rule_versions: dict[str, str],
) -> DocumentConfiguration:
    target = await _load_configuration(session, configuration_id)
    findings = validate_policy(_as_policy_draft(target))
    blockers = tuple(finding for finding in findings if finding.severity == "blocker")
    if blockers:
        raise ConfigurationNotReady(blockers)
    versions = (
        await session.scalars(
            select(DocumentConfiguration)
            .where(
                DocumentConfiguration.business_profile_id == target.business_profile_id,
                DocumentConfiguration.document_type == target.document_type,
                DocumentConfiguration.language == target.language,
            )
            .with_for_update()
        )
    ).all()
    if any(version.status == "scheduled" and version.id != target.id for version in versions):
        raise InvalidStateConflictError("A scheduled configuration already exists for this document context")

    new_status = "active" if effective_from <= date.today() else "scheduled"
    result = await session.execute(
        update(DocumentConfiguration)
        .where(
            DocumentConfiguration.id == configuration_id,
            DocumentConfiguration.status == "draft",
            DocumentConfiguration.lock_version == expected_version,
        )
        .values(
            status=new_status,
            effective_from=effective_from,
            change_reason=reason,
            published_by_id=actor_id,
            published_at=datetime.now(timezone.utc),
            lock_version=expected_version + 1,
        )
        .returning(DocumentConfiguration.id)
    )
    if result.scalar_one_or_none() is None:
        if target.status != "draft":
            raise InvalidStateConflictError("Only draft document configurations can be published")
        raise VersionConflictError(f"Document configuration {configuration_id} changed concurrently")

    if new_status == "active":
        for version in versions:
            if version.id != target.id and version.status == "active":
                version.status = "superseded"

    target = await _load_configuration(session, configuration_id, populate_existing=True)
    target.publication = ConfigurationPublication(
        validation_status="passed",
        validation_errors=[],
        rule_versions=deepcopy(rule_versions),
        published_at=target.published_at,
    )
    await session.flush()
    return target


async def withdraw_scheduled(
    session: AsyncSession,
    configuration_id: int,
    expected_version: int,
    reason: str,
    actor_id: int | None,
) -> DocumentConfiguration:
    result = await session.execute(
        update(DocumentConfiguration)
        .where(
            DocumentConfiguration.id == configuration_id,
            DocumentConfiguration.status == "scheduled",
            DocumentConfiguration.lock_version == expected_version,
        )
        .values(
            status="draft",
            effective_from=None,
            change_reason=reason,
            published_by_id=None,
            published_at=None,
            lock_version=expected_version + 1,
        )
        .returning(DocumentConfiguration.id)
    )
    if result.scalar_one_or_none() is None:
        existing = await session.get(DocumentConfiguration, configuration_id)
        if existing is None:
            raise ResourceNotFoundError(f"Document configuration {configuration_id} was not found")
        if existing.status != "scheduled":
            raise InvalidStateConflictError("Only scheduled configurations can be withdrawn")
        raise VersionConflictError(f"Document configuration {configuration_id} changed concurrently")
    configuration = await _load_configuration(session, configuration_id, populate_existing=True)
    if configuration.publication is not None:
        await session.delete(configuration.publication)
        configuration.publication = None
    await session.flush()
    return configuration


def _as_policy_draft(configuration: DocumentConfiguration) -> DocumentConfigurationDraft:
    basic = configuration.basic_policy
    payment = configuration.payment_policy
    dunning = configuration.dunning_policy
    content = configuration.content_policy
    if basic is None or payment is None or dunning is None or content is None:
        raise InvalidStateConflictError(f"Document configuration {configuration.id} has incomplete policy rows")

    discount_rule = payment.early_payment_rules[0] if payment.early_payment_rules else {}
    installments = payment.installments or []
    return DocumentConfigurationDraft(
        document_type=DocumentType(configuration.document_type),
        language=configuration.language,
        basic=BasicPolicyDraft(
            subject=basic.subject,
            validity_days=basic.validity_days,
            date_rule=basic.date_rule,
            rounding_mode=basic.rounding_mode,
            reference_requirements=deepcopy(basic.reference_requirements),
            allowed_successors=[DocumentType(item) for item in basic.allowed_successors],
        ),
        payment=PaymentPolicyDraft(
            payment_term_days=payment.payment_term_days,
            currency=payment.currency,
            due_date_basis=payment.due_date_basis,
            payment_methods=deepcopy(payment.payment_methods),
            discount_days=discount_rule.get("days", 0),
            discount_percent=discount_rule.get("percent", "0"),
            installments=[InstallmentDraft.model_validate(item) for item in installments],
            prepayment_percent=payment.prepayment_percent,
            installment_enabled=payment.installment_enabled,
            bank_account_id=payment.bank_account_id,
            bank_assignments=(
                [BankAssignmentDraft(bank_account_id=payment.bank_account_id, is_default=True)]
                if payment.bank_account_id is not None
                else []
            ),
            use_term_in_invoice_text=payment.use_term_in_invoice_text,
        ),
        dunning=DunningPolicyDraft(
            enabled=dunning.enabled,
            annual_interest_rate=dunning.annual_interest_rate,
            flat_fee=dunning.flat_fee,
            stages=[
                DunningStageDraft(
                    level=stage.level,
                    wait_days=stage.wait_days,
                    fee=stage.fee,
                    charge_interest=stage.charge_interest,
                    new_due_days=stage.new_due_days,
                    body=stage.body,
                    escalation_hint=stage.escalation_hint,
                )
                for stage in dunning.stages
            ],
        ),
        content=ContentPolicyDraft(
            include_calculation_data=content.include_calculation_data,
            visible_content=deepcopy(content.visible_content),
        ),
        text_blocks=[
            DocumentTextBlockDraft(
                purpose=block.purpose,
                body=block.body,
                condition=deepcopy(block.condition),
                position=block.position,
            )
            for block in configuration.text_blocks
        ],
    )


def to_draft_schema(configuration: DocumentConfiguration) -> DocumentConfigurationDraft:
    return _as_policy_draft(configuration)


def _value(value: Any, source: str, *, overridable: bool = True) -> SourcedValue:
    return SourcedValue(value=value, source=source, overridable=overridable)


async def resolve_effective(
    session: AsyncSession,
    profile_id: int,
    customer_id: int | None,
    document_type: str,
    language: str,
    document_overrides: dict[str, Any],
) -> EffectiveDocumentPolicy:
    base_statement = (
        select(DocumentConfiguration)
        .where(
            DocumentConfiguration.business_profile_id == profile_id,
            DocumentConfiguration.document_type == document_type,
            DocumentConfiguration.language == language,
        )
        .options(*_configuration_options())
    )
    configuration = await session.scalar(
        base_statement.where(
            DocumentConfiguration.status == "active",
            DocumentConfiguration.effective_from <= date.today(),
        ).order_by(DocumentConfiguration.effective_from.desc(), DocumentConfiguration.version.desc())
    )
    if configuration is None:
        configuration = await session.scalar(
            base_statement.where(DocumentConfiguration.status == "draft").order_by(DocumentConfiguration.version.desc())
        )
    if configuration is None:
        raise ResourceNotFoundError(
            f"No document configuration exists for profile={profile_id}, type={document_type}, language={language}"
        )
    if not all(
        (
            configuration.basic_policy,
            configuration.payment_policy,
            configuration.content_policy,
            configuration.tax_policy,
            configuration.einvoice_policy,
        )
    ):
        raise InvalidStateConflictError(f"Document configuration {configuration.id} is incomplete")

    profile = await session.get(BusinessProfile, profile_id)
    if profile is None:
        raise ResourceNotFoundError(f"Business profile {profile_id} was not found")
    customer_account = None
    if customer_id is not None:
        customer_account = await session.scalar(
            select(CustomerAccount).where(
                CustomerAccount.customer_id == customer_id,
                CustomerAccount.business_profile_id == profile_id,
                CustomerAccount.is_active.is_(True),
            )
        )

    basic = configuration.basic_policy
    payment = configuration.payment_policy
    content = configuration.content_policy
    tax = configuration.tax_policy
    einvoice = configuration.einvoice_policy
    assert basic is not None and payment is not None and content is not None and tax is not None and einvoice is not None

    payment_term_value = payment.payment_term_days
    payment_term_source = "configuration"
    currency_value = payment.currency or profile.default_currency
    currency_source = "configuration" if payment.currency else "business_profile"
    if customer_account is not None:
        payment_term_value = customer_account.payment_term_days
        payment_term_source = "customer"
        currency_value = customer_account.preferred_currency
        currency_source = "customer"
    payment_overrides = document_overrides.get("payment", {})
    if "payment_term_days" in payment_overrides:
        payment_term_value = payment_overrides["payment_term_days"]
        payment_term_source = "document"
    if "currency" in payment_overrides:
        currency_value = payment_overrides["currency"]
        currency_source = "document"

    basic_overrides = document_overrides.get("basic", {})
    content_overrides = document_overrides.get("content", {})
    tax_overrides = document_overrides.get("tax", {})
    einvoice_overrides = document_overrides.get("einvoice", {})

    def sourced_field(model: Any, field: str, overrides: dict[str, Any], *, overridable: bool = True):
        if field in overrides:
            return _value(overrides[field], "document", overridable=overridable)
        return _value(deepcopy(getattr(model, field)), "configuration", overridable=overridable)

    text_overrides = document_overrides.get("text_blocks", {})
    return EffectiveDocumentPolicy(
        configuration_id=configuration.id,
        configuration_version=configuration.version,
        basic=EffectiveBasicPolicy(
            subject=sourced_field(basic, "subject", basic_overrides),
            validity_days=sourced_field(basic, "validity_days", basic_overrides),
            date_rule=sourced_field(basic, "date_rule", basic_overrides),
            rounding_mode=sourced_field(basic, "rounding_mode", basic_overrides),
        ),
        payment=EffectivePaymentPolicy(
            payment_term_days=_value(payment_term_value, payment_term_source),
            currency=_value(currency_value, currency_source),
            due_date_basis=sourced_field(payment, "due_date_basis", payment_overrides),
            payment_methods=sourced_field(payment, "payment_methods", payment_overrides),
            early_payment_rules=sourced_field(payment, "early_payment_rules", payment_overrides),
            prepayment_percent=_value(str(payment_overrides.get("prepayment_percent", payment.prepayment_percent)), "document" if "prepayment_percent" in payment_overrides else "configuration"),
            installment_enabled=sourced_field(payment, "installment_enabled", payment_overrides),
            bank_account_id=sourced_field(payment, "bank_account_id", payment_overrides),
            use_term_in_invoice_text=sourced_field(payment, "use_term_in_invoice_text", payment_overrides),
        ),
        content=EffectiveContentPolicy(
            include_calculation_data=sourced_field(content, "include_calculation_data", content_overrides),
            visible_content=sourced_field(content, "visible_content", content_overrides),
        ),
        tax=EffectiveTaxPolicy(
            allowed_cases=sourced_field(tax, "allowed_cases", tax_overrides, overridable=False),
            decision_rules=sourced_field(tax, "decision_rules", tax_overrides, overridable=False),
            allow_override=sourced_field(tax, "allow_override", tax_overrides, overridable=False),
        ),
        einvoice=EffectiveEInvoicePolicy(
            requirement=sourced_field(einvoice, "requirement", einvoice_overrides),
            en16931_version=sourced_field(einvoice, "en16931_version", einvoice_overrides, overridable=False),
            cius_name=sourced_field(einvoice, "cius_name", einvoice_overrides, overridable=False),
            cius_version=sourced_field(einvoice, "cius_version", einvoice_overrides, overridable=False),
            syntax=sourced_field(einvoice, "syntax", einvoice_overrides),
            zugferd_profile=sourced_field(einvoice, "zugferd_profile", einvoice_overrides),
            process_identifier=sourced_field(einvoice, "process_identifier", einvoice_overrides),
            seller_identifier=sourced_field(einvoice, "seller_identifier", einvoice_overrides),
            seller_identifier_scheme=sourced_field(einvoice, "seller_identifier_scheme", einvoice_overrides),
            default_payment_method=sourced_field(einvoice, "default_payment_method", einvoice_overrides),
            bank_account_id=sourced_field(einvoice, "bank_account_id", einvoice_overrides),
            recipient_requirements=sourced_field(einvoice, "recipient_requirements", einvoice_overrides),
        ),
        text_blocks=[
            EffectiveTextBlock(
                purpose=block.purpose,
                body=_value(text_overrides.get(block.purpose, block.body), "document" if block.purpose in text_overrides else "configuration"),
                condition=deepcopy(block.condition),
                position=block.position,
            )
            for block in configuration.text_blocks
        ],
    )
