"""Deterministic validation contracts for document policies and text rendering."""

from backend.app.schemas.document_configuration import (
    BankAssignmentDraft,
    BasicPolicyDraft,
    ContentPolicyDraft,
    DocumentConfigurationDraft,
    DocumentTextBlockDraft,
    DunningPolicyDraft,
    DunningStageDraft,
    EInvoicePolicyDraft,
    InstallmentDraft,
    PaymentPolicyDraft,
    TaxPolicyDraft,
)
from backend.app.services.document_policy_validation import render_text_blocks, validate_policy


def policy(**overrides) -> DocumentConfigurationDraft:
    payment = PaymentPolicyDraft(
        payment_term_days=14,
        currency="EUR",
        discount_days=7,
        discount_percent="2.00",
        installments=[],
        bank_assignments=[BankAssignmentDraft(bank_account_id=1, is_default=True)],
    )
    text_blocks = [
        DocumentTextBlockDraft(purpose="intro", body="Invoice {DOCUMENT_NUMBER}", position=0),
        DocumentTextBlockDraft(purpose="closing", body="Pay by {DUE_DATE}", position=1),
        DocumentTextBlockDraft(purpose="payment_terms", body="Payment in 14 days", position=2),
    ]
    data = {
        "document_type": "invoice",
        "language": "de",
        "basic": BasicPolicyDraft(subject="Invoice {DOCUMENT_NUMBER}"),
        "payment": payment,
        "dunning": DunningPolicyDraft(enabled=False, annual_interest_rate="0", flat_fee="0", stages=[]),
        "content": ContentPolicyDraft(),
        "tax": TaxPolicyDraft(),
        "einvoice": EInvoicePolicyDraft(),
        "text_blocks": text_blocks,
    }
    data.update(overrides)
    return DocumentConfigurationDraft.model_validate(data)


def test_policy_rejects_discount_after_due_date():
    invalid_payment = policy().payment.model_copy(update={"discount_days": 30})
    findings = validate_policy(policy(payment=invalid_payment))

    assert [(item.code, item.field_path) for item in findings] == [
        ("discount_after_due_date", "payment.discount_days")
    ]


def test_installment_percentages_must_total_one_hundred():
    invalid_payment = policy().payment.model_copy(
        update={
            "installments": [
                InstallmentDraft(percent="40.00", due_days=7),
                InstallmentDraft(percent="40.00", due_days=30),
            ]
        }
    )

    findings = validate_policy(policy(payment=invalid_payment))

    assert any(item.code == "installments_total_invalid" for item in findings)


def test_unknown_or_unavailable_placeholder_is_blocking():
    invalid_blocks = [
        *policy().text_blocks[:-2],
        DocumentTextBlockDraft(
            purpose="closing",
            body="Pay {QUOTATION_VALID_UNTIL} to {UNKNOWN}",
            position=1,
        ),
        policy().text_blocks[-1],
    ]

    findings = validate_policy(policy(text_blocks=invalid_blocks))

    assert {item.code for item in findings} == {"placeholder_not_available", "placeholder_unknown"}


def test_dunning_stages_are_unique_ordered_and_non_negative():
    invalid_dunning = DunningPolicyDraft(
        enabled=True,
        annual_interest_rate="-1.00",
        flat_fee="-2.00",
        stages=[
            DunningStageDraft(level=2, wait_days=7, fee="1.00", new_due_days=7),
            DunningStageDraft(level=2, wait_days=5, fee="-1.00", new_due_days=7),
        ],
    )

    findings = validate_policy(policy(dunning=invalid_dunning))

    assert {
        "dunning_interest_negative",
        "dunning_fee_negative",
        "dunning_stage_level_duplicate",
        "dunning_stage_order_invalid",
        "dunning_stage_fee_negative",
    } <= {item.code for item in findings}


def test_payment_documents_require_exactly_one_default_bank_assignment():
    missing_bank = policy().payment.model_copy(update={"bank_assignments": []})
    two_defaults = policy().payment.model_copy(
        update={
            "bank_assignments": [
                BankAssignmentDraft(bank_account_id=1, is_default=True),
                BankAssignmentDraft(bank_account_id=2, is_default=True),
            ]
        }
    )

    assert {item.code for item in validate_policy(policy(payment=missing_bank))} == {"default_bank_missing"}
    assert {item.code for item in validate_policy(policy(payment=two_defaults))} == {"default_bank_multiple"}


def test_render_text_blocks_replaces_available_values_in_position_order():
    rendered = render_text_blocks(
        list(reversed(policy().text_blocks)),
        {"DOCUMENT_NUMBER": "RE-1001", "DUE_DATE": "31.07.2026"},
        "invoice",
    )

    assert [item.purpose for item in rendered] == ["intro", "closing", "payment_terms"]
    assert rendered[0].body == "Invoice RE-1001"
    assert rendered[1].body == "Pay by 31.07.2026"
