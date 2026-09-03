import { useTranslation } from 'react-i18next';

const en = {
  title: 'Warehouse goods', subtitle: 'Sales articles, physical stock and reservations managed in PrintOps.',
  search: 'Search articles', all: 'All', active: 'Active', archived: 'Archived', low: 'Below minimum stock',
  create: 'New article', edit: 'Edit article', save: 'Save', close: 'Close', cancel: 'Cancel', archive: 'Archive article',
  restore: 'Restore article', loading: 'Loading…', empty: 'No articles match these filters.', noRead: 'You do not have permission to read warehouse articles.',
  error: 'Could not load warehouse data.', retry: 'Retry', previous: 'Previous', next: 'Next',
  sku: 'Article number', name: 'Name', description: 'Description', kind: 'Article kind',
  articleDetails: 'Article', stock: 'Stock', prices: 'Prices', projectLinks: 'Project reference',
  finished: 'Finished product', trade: 'Trade goods', service: 'Service', unit: 'Local unit',
  sale: 'Net selling price (EUR)', cost: 'Unit / production cost (EUR)', tax: 'Tax rate (%)', minimum: 'Minimum stock',
  source: 'Stock source', own: 'Own warehouse stock', material: 'Existing material', none: 'No stock',
  choose: 'Please select', materialSearch: 'Search material', materialLink: 'Open material management',
  materialNote: 'This article uses the existing material stock. Bookings and reservations stay in material management.',
  serviceNote: 'Services have no stock or reservations.', frozen: 'Unit, kind and stock source are locked after the first stock entry.',
  project: 'Project ID (optional)', revision: 'Calculation revision ID (optional)',
  physical: 'Physical', reserved: 'Reserved', available: 'Available', location: 'Location', destination: 'Destination',
  history: 'Movement history', noHistory: 'No movements yet.', booking: 'Stock movement', quantity: 'Quantity', reason: 'Reason',
  opening: 'Opening balance', receipt: 'Receipt', issue: 'Free issue', transfer: 'Transfer', correction: 'Inventory correction (delta)',
  reservation: 'Reservation', release: 'Release reservation', reserved_issue: 'Issue reserved stock', counter: 'Counter-entry',
  book: 'Post movement', order: 'Order ID (optional)', reservationSelect: 'Open reservation',
  counterNote: 'A counter-entry reverses the selected movement without deleting history. Current stock constraints still apply.',
  quantityNote: 'Use a negative delta for inventory reductions. Stock and available quantity cannot be negative.',
  noLocations: 'Create a storage location in material or filament management before booking.',
  noUnits: 'Create or activate a unit in material settings first.', updated: 'Updated', actor: 'User', localActor: 'Local / API',
  archiveNote: 'Archiving retains the complete journal and is only possible with no stock or reservations.',
};
const de: typeof en = {
  title: 'Warenlager', subtitle: 'Verkaufsartikel, physischer Bestand und Reservierungen in PrintOps.',
  search: 'Artikel suchen', all: 'Alle', active: 'Aktiv', archived: 'Archiviert', low: 'Unter Mindestbestand',
  create: 'Neuer Artikel', edit: 'Artikel bearbeiten', save: 'Speichern', close: 'Schließen', cancel: 'Abbrechen', archive: 'Artikel archivieren',
  restore: 'Artikel reaktivieren', loading: 'Wird geladen …', empty: 'Keine Artikel für diese Filter.', noRead: 'Keine Berechtigung zum Lesen des Warenlagers.',
  error: 'Lagerdaten konnten nicht geladen werden.', retry: 'Erneut versuchen', previous: 'Zurück', next: 'Weiter',
  sku: 'Artikelnummer', name: 'Bezeichnung', description: 'Beschreibung', kind: 'Artikelart',
  articleDetails: 'Artikel', stock: 'Bestand', prices: 'Preise', projectLinks: 'Projektbezug',
  finished: 'Fertigprodukt', trade: 'Handelsware', service: 'Dienstleistung', unit: 'Lokale Einheit',
  sale: 'Verkaufspreis netto (EUR)', cost: 'Einstands- / Herstellkosten (EUR)', tax: 'Steuersatz (%)', minimum: 'Mindestbestand',
  source: 'Bestandsquelle', own: 'Eigener Warenbestand', material: 'Bestehendes Material', none: 'Kein Bestand',
  choose: 'Bitte auswählen', materialSearch: 'Material suchen', materialLink: 'Materialverwaltung öffnen',
  materialNote: 'Dieser Artikel nutzt den vorhandenen Materialbestand. Buchungen und Reservierungen bleiben in der Materialverwaltung.',
  serviceNote: 'Dienstleistungen haben keine Bestände oder Reservierungen.', frozen: 'Einheit, Artikelart und Bestandsquelle sind nach der ersten Buchung gesperrt.',
  project: 'Projekt-ID (optional)', revision: 'Kalkulationsrevision-ID (optional)',
  physical: 'Physisch', reserved: 'Reserviert', available: 'Verfügbar', location: 'Lagerort', destination: 'Ziellagerort',
  history: 'Bewegungshistorie', noHistory: 'Noch keine Buchungen.', booking: 'Lagerbewegung', quantity: 'Menge', reason: 'Grund',
  opening: 'Anfangsbestand', receipt: 'Wareneingang', issue: 'Freier Warenausgang', transfer: 'Umbuchung', correction: 'Inventurkorrektur (Differenz)',
  reservation: 'Reservierung', release: 'Reservierung freigeben', reserved_issue: 'Reservierte Ware ausgeben', counter: 'Gegenbuchung',
  book: 'Bewegung buchen', order: 'Auftrags-ID (optional)', reservationSelect: 'Offene Reservierung',
  counterNote: 'Die Gegenbuchung macht die gewählte Bewegung nachvollziehbar rückgängig. Aktuelle Bestandsgrenzen gelten weiterhin.',
  quantityNote: 'Bestandsminderungen als negative Differenz buchen. Physische und verfügbare Mengen dürfen nicht negativ werden.',
  noLocations: 'Vor der Buchung einen Lagerort in der Material- oder Filamentverwaltung anlegen.',
  noUnits: 'Zuerst eine Einheit in den Materialeinstellungen anlegen oder aktivieren.', updated: 'Aktualisiert', actor: 'Nutzer', localActor: 'Lokal / API',
  archiveNote: 'Archivieren erhält die gesamte Historie und ist nur ohne Bestand oder Reservierungen möglich.',
};

export function useWarehouseCopy() {
  const { i18n } = useTranslation();
  return (i18n.resolvedLanguage ?? i18n.language).startsWith('de') ? de : en;
}

export const warehouseQuantity = (value: string) => Number(value).toLocaleString(undefined, { maximumFractionDigits: 6 });
