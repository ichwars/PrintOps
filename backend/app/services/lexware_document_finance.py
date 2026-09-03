"""Conservative decimal projections for voucher-related finance, not bank balances."""

from datetime import date
from decimal import Decimal, InvalidOperation

from backend.app.models.lexware_documents import LexwareDocument
from backend.app.schemas.lexware_documents import LexwareDocumentFinanceRead, LexwarePaymentItemRead

FINANCIAL_TYPES = {"invoice", "creditnote", "salesinvoice", "salescreditnote", "purchaseinvoice", "purchasecreditnote"}
FINAL_STATUSES = {"open", "paid", "paidoff", "overdue", "transferred", "sepadebit"}
PAYMENT_CATEGORIES = {
    "partPaymentFinancialTransaction": "bank_payment",
    "partPaymentCashBox": "cash_payment",
    "manualPayment": "manual_payment",
    "partPaymentCreditNote": "credit_offset",
    "cashDiscount": "cash_discount",
    "irrecoverableReceivable": "write_off",
    "dunningCosts": "dunning_costs",
    "currencyConversion": "currency_conversion",
}


def money(value) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or abs(amount) >= Decimal("10000000000000000"):
            return None
        return amount.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def iso_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def payment_is_complete(payload: dict | None, currency: str) -> bool:
    if not isinstance(payload, dict):
        return False
    amount = money(payload.get("openAmount"))
    items = payload.get("paymentItems")
    if (
        amount is None
        or amount < 0
        or payload.get("currency") != currency
        or payload.get("paymentStatus") not in {"balanced", "openRevenue", "openExpense"}
        or not isinstance(items, list)
    ):
        return False
    if payload["paymentStatus"] == "balanced" and amount != 0:
        return False
    return all(
        isinstance(item, dict)
        and money(item.get("amount")) is not None
        and item.get("currency") == currency
        and isinstance(item.get("paymentItemType"), str)
        for item in items
    )


def project_finance(document: LexwareDocument, today: date | None = None) -> LexwareDocumentFinanceRead:
    today = today or date.today()
    is_financial = document.voucher_type in FINANCIAL_TYPES
    credit = document.voucher_type in {"creditnote", "salescreditnote", "purchasecreditnote"}
    direction = (
        ("payable" if document.voucher_type.startswith("purchase") else "receivable") if is_financial else "none"
    )
    payment = document.payment
    payload = payment.payload if payment else None
    state = payment.state if payment else "unknown"
    if state == "known" and not payment_is_complete(payload, document.currency):
        state = "unknown"
    if state == "known" and (
        payload.get("voucherType", document.voucher_type) != document.voucher_type
        or payload.get("voucherStatus", document.voucher_status) != document.voucher_status
    ):
        # The voucher may have changed between detail and payment GETs. Do not combine two states.
        state = "unknown"
    if not is_financial or document.voucher_status in {"draft", "unchecked", "voided"}:
        state = "not_applicable"
    open_amount = money(payload.get("openAmount")) if state == "known" else None
    items = []
    if state == "known":
        items = [
            LexwarePaymentItemRead(
                item_type=item["paymentItemType"],
                category=PAYMENT_CATEGORIES.get(item["paymentItemType"], "unknown"),
                amount=money(item["amount"]),
                currency=item["currency"],
                posting_date=iso_date(item.get("postingDate")),
            )
            for item in payload["paymentItems"]
        ]
    if not document.supported:
        reason = "unsupported_type"
    elif not document.in_latest_sync:
        reason = "missing_from_latest_sync"
    elif document.local_document_id is not None:
        reason = "linked_local_document"
    elif not is_financial:
        reason = "not_financial"
    elif document.voucher_status not in FINAL_STATUSES:
        reason = "voided" if document.voucher_status == "voided" else "not_final"
    elif state != "known":
        reason = "unknown_payment"
    else:
        reason = None
    return LexwareDocumentFinanceRead(
        currency=document.currency,
        total_amount=document.total_amount,
        open_amount=open_amount,
        payment_state=state,
        payment_status=payload.get("paymentStatus") if state == "known" else None,
        direction=direction,
        credit=credit,
        overdue=(document.due_date < today and open_amount > 0)
        if document.due_date and open_amount is not None
        else None,
        included_in_totals=reason is None,
        exclusion_reason=reason,
        payment_items=items,
    )
