import { useTranslation } from 'react-i18next';

const en = {
  type_invoice: 'Invoice', type_creditnote: 'Credit note', type_quotation: 'Quotation', type_orderconfirmation: 'Order confirmation',
  type_salesinvoice: 'Sales voucher', type_salescreditnote: 'Sales credit voucher', type_purchaseinvoice: 'Purchase invoice',
  type_purchasecreditnote: 'Purchase credit note', type_downpaymentinvoice: 'Down payment invoice', type_deliverynote: 'Delivery note',
  status_open: 'Open', status_paid: 'Paid', status_paidoff: 'Settled', status_overdue: 'Overdue', status_draft: 'Draft',
  status_unchecked: 'Unchecked', status_voided: 'Voided', status_final: 'Final', status_transferred: 'Transferred',
  status_sepadebit: 'SEPA debit', status_accepted: 'Accepted', status_rejected: 'Rejected',
  status_openRevenue: 'Open receivable', status_openExpense: 'Open payable',
  title: 'Lexware documents', description: 'External originals and voucher-related finance. Read only in Lexware.',
  financeTitle: 'Separate Lexware finance', financeNote: 'Not a bank balance. Linked PrintOps documents, drafts, voided vouchers and unknown payment data are excluded from these totals. Local payments are unchanged.',
  loading: 'Loading…', retry: 'Retry', error: 'Could not load Lexware data.', empty: 'No Lexware documents. Connect and synchronize Lexware in Settings.',
  denied: 'You do not have permission to read documents.', search: 'Search number or contact', allTypes: 'All document types',
  profile: 'Business profile', allProfiles: 'All profiles', type: 'Type', number: 'Original number', contact: 'Contact', date: 'Date',
  status: 'Status', total: 'Gross amount', open: 'Open amount', details: 'Details', close: 'Close', source: 'Source', updated: 'Snapshot updated',
  previous: 'Previous', next: 'Next', count: 'Documents', unsupported: 'Unsupported type — not imported into finance',
  stale: 'Not updating — showing the last stored snapshot', missing: 'Missing from latest full sync — retained as evidence',
  unknown: 'Unknown', notApplicable: 'Not applicable', balanced: 'Settled (not necessarily a bank payment)', due: 'Due date', overdue: 'Overdue',
  receivables: 'Open receivables', payables: 'Open payables', credits: 'Credit notes reduce the corresponding open balance.',
  linked: 'Linked documents excluded', unknownCount: 'Unknown payment data', excluded: 'Excluded documents',
  payments: 'Payment and settlement items', noPayments: 'No payment items reported.', paymentKind: 'Kind', amount: 'Amount',
  bank_payment: 'Bank payment', cash_payment: 'Cash payment', manual_payment: 'Manual payment / private deposit',
  credit_offset: 'Credit note offset', cash_discount: 'Cash discount', write_off: 'Write-off', dunning_costs: 'Dunning costs',
  currency_conversion: 'Currency conversion', originals: 'Original files', noFiles: 'No original available in the snapshot.',
  download: 'Download original', cached: 'Stored locally; included in full backups', uncached: 'Fetch and cache (max. 10 MiB)',
  linkTitle: 'Manual PrintOps linkage', linkNote: 'Choose the same transaction. Only issued financial documents with matching type, profile, currency and gross amount can be linked. No local payments are overwritten.',
  selectLocal: 'Choose a local document', link: 'Link document', unlink: 'Remove link', localId: 'Linked PrintOps document',
  localLoading: 'Loading local documents…', localEmpty: 'No local documents available in this profile.',
  actionError: 'The action failed. Reload and check the document or connection.', conflict: 'The document changed. Reload it before retrying.',
  financeDenied: 'Financial details and original files require payment read permission.', archived: 'Archived', refresh: 'Reload snapshots',
};
const de: typeof en = {
  type_invoice: 'Rechnung', type_creditnote: 'Rechnungskorrektur', type_quotation: 'Angebot', type_orderconfirmation: 'Auftragsbestätigung',
  type_salesinvoice: 'Verkaufsbeleg', type_salescreditnote: 'Verkaufsgutschrift', type_purchaseinvoice: 'Eingangsrechnung',
  type_purchasecreditnote: 'Einkaufsgutschrift', type_downpaymentinvoice: 'Abschlagsrechnung', type_deliverynote: 'Lieferschein',
  status_open: 'Offen', status_paid: 'Bezahlt', status_paidoff: 'Ausgeglichen', status_overdue: 'Überfällig', status_draft: 'Entwurf',
  status_unchecked: 'Ungeprüft', status_voided: 'Storniert', status_final: 'Abgeschlossen', status_transferred: 'Überwiesen',
  status_sepadebit: 'SEPA-Lastschrift', status_accepted: 'Angenommen', status_rejected: 'Abgelehnt',
  status_openRevenue: 'Offene Forderung', status_openExpense: 'Offene Verbindlichkeit',
  title: 'Lexware-Belege', description: 'Externe Originale und belegbezogene Finanzen. Ausschließlich lesender Zugriff auf Lexware.',
  financeTitle: 'Separate Lexware-Finanzübersicht', financeNote: 'Kein Bankkontostand. Zugeordnete PrintOps-Belege, Entwürfe, Stornos und unbekannte Zahlungsdaten sind aus diesen Summen ausgeschlossen. Lokale Zahlungen bleiben unverändert.',
  loading: 'Wird geladen…', retry: 'Erneut versuchen', error: 'Lexware-Daten konnten nicht geladen werden.', empty: 'Keine Lexware-Belege. Lexware unter Einstellungen verbinden und synchronisieren.',
  denied: 'Keine Berechtigung zum Lesen von Belegen.', search: 'Nummer oder Kontakt suchen', allTypes: 'Alle Belegarten',
  profile: 'Unternehmensprofil', allProfiles: 'Alle Profile', type: 'Art', number: 'Originalnummer', contact: 'Kontakt', date: 'Datum',
  status: 'Status', total: 'Bruttobetrag', open: 'Offener Betrag', details: 'Details', close: 'Schließen', source: 'Quelle', updated: 'Datenstand',
  previous: 'Zurück', next: 'Weiter', count: 'Belege', unsupported: 'Nicht unterstützte Art — nicht in Finanzen übernommen',
  stale: 'Keine Aktualisierung — letzter gespeicherter Stand', missing: 'Fehlt im letzten vollständigen Abruf — als Nachweis erhalten',
  unknown: 'Unbekannt', notApplicable: 'Nicht anwendbar', balanced: 'Ausgeglichen (nicht zwingend Bankzahlung)', due: 'Fälligkeit', overdue: 'Überfällig',
  receivables: 'Offene Forderungen', payables: 'Offene Verbindlichkeiten', credits: 'Gutschriften mindern den jeweiligen offenen Saldo.',
  linked: 'Zugeordnete Belege ausgeschlossen', unknownCount: 'Unbekannte Zahlungsdaten', excluded: 'Ausgeschlossene Belege',
  payments: 'Zahlungen und Verrechnungen', noPayments: 'Keine Zahlungspositionen gemeldet.', paymentKind: 'Art', amount: 'Betrag',
  bank_payment: 'Bankzahlung', cash_payment: 'Kassenzahlung', manual_payment: 'Manuelle Zahlung / Privateinlage',
  credit_offset: 'Gutschriftverrechnung', cash_discount: 'Skonto', write_off: 'Ausbuchung', dunning_costs: 'Mahnkosten',
  currency_conversion: 'Währungsdifferenz', originals: 'Originaldateien', noFiles: 'Kein Original im Datenstand verfügbar.',
  download: 'Original herunterladen', cached: 'Lokal gespeichert; in Vollbackups enthalten', uncached: 'Abrufen und sichern (max. 10 MiB)',
  linkTitle: 'Manuelle PrintOps-Zuordnung', linkNote: 'Denselben Geschäftsvorfall auswählen. Finanzbelege müssen ausgestellt sein und in Art, Profil, Währung und Bruttobetrag übereinstimmen. Lokale Zahlungen werden nicht überschrieben.',
  selectLocal: 'Lokalen Beleg auswählen', link: 'Beleg zuordnen', unlink: 'Zuordnung entfernen', localId: 'Zugeordneter PrintOps-Beleg',
  localLoading: 'Lokale Belege werden geladen…', localEmpty: 'Keine lokalen Belege in diesem Profil vorhanden.',
  actionError: 'Aktion fehlgeschlagen. Beleg neu laden und Verbindung prüfen.', conflict: 'Der Beleg wurde geändert. Vor einem neuen Versuch neu laden.',
  financeDenied: 'Finanzdetails und Originaldateien erfordern Leserechte für Zahlungen.', archived: 'Archiviert', refresh: 'Datenstand neu laden',
};

export function useLexwareDocumentLabels() {
  const { i18n } = useTranslation();
  return (i18n.resolvedLanguage || i18n.language || 'en').startsWith('de') ? de : en;
}
export type LexwareDocumentLabels = typeof en;

export function documentCodeLabel(labels: LexwareDocumentLabels, kind: 'type' | 'status', value: string) {
  return (labels as Record<string, string>)[`${kind}_${value}`] ?? value;
}

export function displayMoney(value: string | null | undefined, currency: string, unknown: string) {
  // Keep exact decimal strings from the server, including values beyond JS safe integer precision.
  return value == null ? unknown : `${value} ${currency}`;
}
