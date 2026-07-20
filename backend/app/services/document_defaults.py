"""Validated defaults and idempotent seeding for document configuration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import insert, select

from backend.app.models.business_profile import BusinessProfile
from backend.app.models.document_configuration import (
    DocumentBasicPolicy,
    DocumentConfiguration,
    DocumentContentPolicy,
    DocumentTextBlock,
    DunningPolicy,
    EInvoicePolicy,
    PaymentPolicy,
    TaxPolicy,
)
from backend.app.models.settings import Settings
from backend.app.services.document_catalog import (
    DOCUMENT_CAPABILITIES,
    PLACEHOLDERS,
    TEXT_BLOCK_PURPOSES,
    DocumentType,
    EInvoiceRequirement,
)

DEFAULTS_DIRECTORY = Path(__file__).resolve().parent.parent / "resources" / "document_defaults"
SUPPORTED_LANGUAGES = ("de", "en")
LEGACY_SETTING_KEYS = (
    "orders.offer_validity_days",
    "orders.payment_term_days",
    "orders.default_order_status",
    "orders.offer_default_text",
    "orders.invoice_default_text",
    "orders.pdf_footer_text",
    "orders.include_calculation_data",
    "orders.use_payment_term_in_invoice_text",
)
_PLACEHOLDER_PATTERN = re.compile(r"\{([A-Z][A-Z0-9_]*)\}")


class DocumentDefaultsError(RuntimeError):
    """Raised when committed defaults violate the document catalog contract."""


def load_document_defaults(language: str) -> dict[str, Any]:
    if language not in SUPPORTED_LANGUAGES:
        raise DocumentDefaultsError(f"Unsupported document-default language: {language}")

    path = DEFAULTS_DIRECTORY / f"{language}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentDefaultsError(f"Cannot load document defaults from {path}: {exc}") from exc

    expected_types = {document_type.value for document_type in DocumentType}
    actual_types = set(payload.get("documents", {}))
    if actual_types != expected_types:
        missing = sorted(expected_types - actual_types)
        unexpected = sorted(actual_types - expected_types)
        raise DocumentDefaultsError(
            f"Invalid {language} document-default catalog; missing={missing}, unexpected={unexpected}"
        )

    if payload.get("language") != language:
        raise DocumentDefaultsError(f"Document-default language mismatch in {path}")

    allowed_purposes = set(TEXT_BLOCK_PURPOSES)
    resource_purposes = {"intro", "closing", "payment_terms"}
    if not resource_purposes <= allowed_purposes:
        invalid = sorted(resource_purposes - allowed_purposes)
        raise DocumentDefaultsError(f"Invalid text purposes in {path}: {invalid}")

    allowed_placeholders = set(PLACEHOLDERS)
    for document_type, document_defaults in payload["documents"].items():
        for field in ("subject", "intro", "closing"):
            value = document_defaults.get(field)
            if not isinstance(value, str) or not value.strip():
                raise DocumentDefaultsError(f"Missing {field} default for {language}/{document_type}")
            invalid = sorted(set(_PLACEHOLDER_PATTERN.findall(value)) - allowed_placeholders)
            if invalid:
                raise DocumentDefaultsError(
                    f"Invalid placeholders in {language}/{document_type}/{field}: {invalid}"
                )

    payment_terms = payload.get("payment_terms")
    if not isinstance(payment_terms, str) or not payment_terms.strip():
        raise DocumentDefaultsError(f"Missing payment_terms default for {language}")
    invalid = sorted(set(_PLACEHOLDER_PATTERN.findall(payment_terms)) - allowed_placeholders)
    if invalid:
        raise DocumentDefaultsError(f"Invalid placeholders in {language}/payment_terms: {invalid}")

    return payload


def _legacy_int(settings: dict[str, str], key: str, fallback: int) -> int:
    raw = settings.get(key)
    if raw is None:
        return fallback
    try:
        value = int(raw)
    except ValueError as exc:
        raise DocumentDefaultsError(f"Legacy setting {key} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise DocumentDefaultsError(f"Legacy setting {key} must not be negative")
    return value


def _legacy_bool(settings: dict[str, str], key: str, fallback: bool) -> bool:
    raw = settings.get(key)
    if raw is None:
        return fallback
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise DocumentDefaultsError(f"Legacy setting {key} must be boolean, got {raw!r}")


async def seed_document_configurations(conn) -> None:
    """Seed complete bilingual version-one drafts without overwriting existing rows."""

    defaults_by_language = {language: load_document_defaults(language) for language in SUPPORTED_LANGUAGES}
    settings_result = await conn.execute(select(Settings.key, Settings.value).where(Settings.key.in_(LEGACY_SETTING_KEYS)))
    legacy_settings = dict(settings_result.all())
    profile_rows = (await conn.execute(select(BusinessProfile.id, BusinessProfile.default_currency))).all()

    for profile_id, default_currency in profile_rows:
        for language, resource in defaults_by_language.items():
            defaults = resource["defaults"]
            for document_type in DocumentType:
                existing_id = await conn.scalar(
                    select(DocumentConfiguration.id)
                    .where(
                        DocumentConfiguration.business_profile_id == profile_id,
                        DocumentConfiguration.document_type == document_type.value,
                        DocumentConfiguration.language == language,
                    )
                    .limit(1)
                )
                if existing_id is not None:
                    continue

                configuration_id = (
                    await conn.execute(
                        insert(DocumentConfiguration)
                        .values(
                            business_profile_id=profile_id,
                            document_type=document_type.value,
                            language=language,
                            version=1,
                            status="draft",
                            lock_version=1,
                        )
                        .returning(DocumentConfiguration.id)
                    )
                ).scalar_one()

                capability = DOCUMENT_CAPABILITIES[document_type]
                document_defaults = resource["documents"][document_type.value]
                validity_days = defaults["validity_days"] if document_type is DocumentType.QUOTATION else None
                payment_term_days = defaults["payment_term_days"]
                include_calculation_data = defaults["include_calculation_data"]
                use_payment_term_in_invoice_text = defaults["use_payment_term_in_invoice_text"]

                if language == "de":
                    if document_type is DocumentType.QUOTATION:
                        validity_days = _legacy_int(
                            legacy_settings,
                            "orders.offer_validity_days",
                            validity_days,
                        )
                    payment_term_days = _legacy_int(
                        legacy_settings,
                        "orders.payment_term_days",
                        payment_term_days,
                    )
                    include_calculation_data = _legacy_bool(
                        legacy_settings,
                        "orders.include_calculation_data",
                        include_calculation_data,
                    )
                    use_payment_term_in_invoice_text = _legacy_bool(
                        legacy_settings,
                        "orders.use_payment_term_in_invoice_text",
                        use_payment_term_in_invoice_text,
                    )

                await conn.execute(
                    insert(DocumentBasicPolicy).values(
                        configuration_id=configuration_id,
                        subject=document_defaults["subject"],
                        validity_days=validity_days,
                        date_rule="issue_date",
                        rounding_mode="half_up",
                        reference_requirements={},
                        allowed_successors=sorted(successor.value for successor in capability.allowed_successors),
                    )
                )
                await conn.execute(
                    insert(PaymentPolicy).values(
                        configuration_id=configuration_id,
                        payment_term_days=payment_term_days,
                        currency=default_currency,
                        due_date_basis="issue_date",
                        payment_methods=[],
                        early_payment_rules=[],
                        prepayment_percent=0,
                        installment_enabled=False,
                        use_term_in_invoice_text=use_payment_term_in_invoice_text,
                    )
                )
                await conn.execute(
                    insert(DunningPolicy).values(
                        configuration_id=configuration_id,
                        enabled=document_type is DocumentType.DUNNING_NOTICE,
                        annual_interest_rate=0,
                        flat_fee=0,
                    )
                )
                await conn.execute(
                    insert(DocumentContentPolicy).values(
                        configuration_id=configuration_id,
                        include_calculation_data=include_calculation_data,
                        visible_content={},
                    )
                )
                await conn.execute(
                    insert(TaxPolicy).values(
                        configuration_id=configuration_id,
                        allowed_cases=[],
                        decision_rules={},
                        allow_override=False,
                    )
                )
                await conn.execute(
                    insert(EInvoicePolicy).values(
                        configuration_id=configuration_id,
                        requirement=(
                            EInvoiceRequirement.RULE_REQUIRED.value
                            if capability.einvoice
                            else EInvoiceRequirement.OPTIONAL.value
                        ),
                        recipient_requirements={},
                    )
                )

                text_values = {
                    "intro": document_defaults["intro"],
                    "closing": document_defaults["closing"],
                }
                if capability.has_payment_terms:
                    text_values["payment_terms"] = resource["payment_terms"]
                if language == "de" and document_type is DocumentType.QUOTATION:
                    text_values["closing"] = legacy_settings.get(
                        "orders.offer_default_text",
                        text_values["closing"],
                    )
                if language == "de" and document_type is DocumentType.INVOICE:
                    text_values["closing"] = legacy_settings.get(
                        "orders.invoice_default_text",
                        text_values["closing"],
                    )
                if language == "de" and legacy_settings.get("orders.pdf_footer_text"):
                    text_values["footer"] = legacy_settings["orders.pdf_footer_text"]

                await conn.execute(
                    insert(DocumentTextBlock),
                    [
                        {
                            "configuration_id": configuration_id,
                            "purpose": purpose,
                            "body": body,
                            "position": position,
                        }
                        for position, (purpose, body) in enumerate(text_values.items())
                    ],
                )
