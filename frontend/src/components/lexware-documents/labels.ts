import { useTranslation } from 'react-i18next';

export function useLexwareDocumentLabels() {
  const { t } = useTranslation();
  return t('orders.runtimeDomain.lexwareDocuments', { returnObjects: true }) as unknown as LexwareDocumentLabels;
}
export type LexwareDocumentLabels = { "type_invoice": string; "type_creditnote": string; "type_quotation": string; "type_orderconfirmation": string; "type_salesinvoice": string; "type_salescreditnote": string; "type_purchaseinvoice": string; "type_purchasecreditnote": string; "type_downpaymentinvoice": string; "type_deliverynote": string; "status_open": string; "status_paid": string; "status_paidoff": string; "status_overdue": string; "status_draft": string; "status_unchecked": string; "status_voided": string; "status_final": string; "status_transferred": string; "status_sepadebit": string; "status_accepted": string; "status_rejected": string; "status_openRevenue": string; "status_openExpense": string; "title": string; "description": string; "financeTitle": string; "financeNote": string; "loading": string; "retry": string; "error": string; "empty": string; "denied": string; "search": string; "allTypes": string; "profile": string; "allProfiles": string; "type": string; "number": string; "contact": string; "date": string; "status": string; "total": string; "open": string; "details": string; "close": string; "source": string; "updated": string; "previous": string; "next": string; "count": string; "unsupported": string; "stale": string; "missing": string; "unknown": string; "notApplicable": string; "balanced": string; "due": string; "overdue": string; "receivables": string; "payables": string; "credits": string; "linked": string; "unknownCount": string; "excluded": string; "payments": string; "noPayments": string; "paymentKind": string; "amount": string; "bank_payment": string; "cash_payment": string; "manual_payment": string; "credit_offset": string; "cash_discount": string; "write_off": string; "dunning_costs": string; "currency_conversion": string; "originals": string; "noFiles": string; "download": string; "cached": string; "uncached": string; "linkTitle": string; "linkNote": string; "selectLocal": string; "link": string; "unlink": string; "localId": string; "localLoading": string; "localEmpty": string; "actionError": string; "conflict": string; "financeDenied": string; "archived": string; "refresh": string; };

export function documentCodeLabel(labels: LexwareDocumentLabels, kind: 'type' | 'status', value: string) {
  return (labels as Record<string, string>)[`${kind}_${value}`] ?? value;
}

export function displayMoney(value: string | null | undefined, currency: string, unknown: string) {
  // Keep exact decimal strings from the server, including values beyond JS safe integer precision.
  return value == null ? unknown : `${value} ${currency}`;
}
