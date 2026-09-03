import { useTranslation } from 'react-i18next';
import { ApiError } from '../../../api/client/core';

const en = {
  title: 'Lexware Office', readonly: 'Read only: Lexware → PrintOps',
  setupConnection: 'Set up connection', previewAction: 'Preview', recordName: 'Name', actions: 'Action',
  selectPage: 'Select new customers on this page', clearSelection: 'Clear selection', approvalNote: 'Import only after your review',
  cancel: 'Cancel', previewHelp: 'Choose the fields you want to import into PrintOps.', selectedFieldsOnly: 'Only selected fields will change in PrintOps.',
  intro: 'External data refreshes automatically every 15 minutes. Local customers and articles change only after you review and accept an import.',
  permission: 'You do not have permission to manage accounting integrations.',
  profilePermission: 'Reading business profiles requires additional permissions. Existing connections remain available below.',
  loading: 'Loading…', retry: 'Retry', emptyProfiles: 'Create an active business profile before connecting Lexware.',
  profile: 'Business profile', selectProfile: 'Select a business profile', key: 'Lexware API key',
  keyHelp: 'The key is sent only to PrintOps and stored encrypted on the server. It is never shown again.',
  test: 'Test connection', testing: 'Testing connection…', save: 'Save connection', saved: 'Connection saved.',
  organization: 'Lexware organization', expectedOrganization: 'The organization must match the existing connection.',
  wrongOrganization: 'This key belongs to a different organization. The existing connection cannot be reassigned.',
  connectedProfiles: 'Connections', noConnections: 'No Lexware connections yet.', replaceKey: 'Replace key / reconnect',
  pause: 'Pause sync', resume: 'Resume sync', disconnect: 'Disconnect', sync: 'Refresh now',
  disconnected: 'Disconnected', paused: 'Paused', queued: 'Queued', running: 'Sync in progress', idle: 'Ready',
  success: 'Up to date', failed: 'Sync incomplete', unknown: 'Unknown status',
  lastSuccess: 'Last complete sync', lastAttempt: 'Last attempt', never: 'Not yet',
  stale: 'The last successful data remains visible. An incomplete sync does not mean the source is empty.',
  disconnectHelp: 'Disconnecting removes the key and stops new syncs. Imported local data and external evidence are retained.',
  inactive: 'These saved snapshots are no longer being updated.',
  changed: 'Connection updated.', queuedMessage: 'Refresh queued.', disconnectedMessage: 'Disconnected. Saved data was retained.',
  contacts: 'Customers', articles: 'Articles', resourcePermission: 'You do not have permission to read customers or inventory.',
  search: 'Search external data', filter: 'Record status', all: 'All records', new: 'Not linked', linked: 'Linked', archived: 'Archived',
  noResources: 'No saved external records yet. Run a complete refresh to fetch data.', noMatches: 'No matching records.',
  sourceNumber: 'Lexware number', externalId: 'Lexware ID', updated: 'Snapshot updated', review: 'Review import',
  select: 'Select', selected: 'selected', reviewSelected: 'Review selected new customers',
  batchHelp: 'Only unlinked, non-archived customers can be selected together. Review every preview before accepting.',
  close: 'Close preview', preview: 'Import preview', original: 'Original source: Lexware', local: 'Current local data: PrintOps',
  field: 'Field', accept: 'Accept selected fields', import: 'Import selected fields', importing: 'Importing…',
  link: 'Link without changing fields',
  imported: 'Import completed.', partial: 'Some records were imported before an error. Completed records will not be imported again.',
  noChanges: 'No field changes to import.', chooseFields: 'Select the fields you want to import.',
  shared: 'Shared customer: changes affect accounts in these business profiles:',
  preserve: 'New customers adopt the selected Lexware customer number. For existing customers, select the number explicitly to replace it in this business profile. Notes, tags and unselected fields are preserved.',
  customer_number: 'Customer number',
  customerNumberConflict: 'This customer number is already assigned in this business profile. Review the local target or keep the local number by leaving it unselected.',
  archivedWarning: 'Archived in Lexware. No local record is deleted or deactivated automatically.',
  archivedImport: 'Archived Lexware records cannot be imported.', reconnectImport: 'Reconnect Lexware before importing saved data.',
  target: 'Local target', createNew: 'Create a new local record', targetSearch: 'Search local targets',
  noTargets: 'No local targets found.', targetHelp: 'A matching name is only a suggestion. Select the intended record explicitly.',
  linkedTarget: 'Existing local link', previous: 'Previous', next: 'Next',
  refreshPreview: 'Refresh preview', stalePreview: 'The source or local record changed. Refresh the preview and review it again.',
  identity: 'Name and identity', addresses: 'Billing and delivery addresses', contactFields: 'Contact details',
  tax_identifiers: 'Tax identifiers', name: 'Name', description: 'Description', sale_price: 'Sale price', tax_rate: 'Tax rate',
  articleOptions: 'Confirm local article setup', sku: 'Local article number', kind: 'Article kind',
  choose: 'Select…', finished: 'Finished product', trade: 'Merchandise', service: 'Service',
  unit: 'Confirmed local unit', stockSource: 'Stock source', own: 'Own goods inventory', material: 'Existing material inventory', none: 'No inventory (service)',
  materialTarget: 'Existing material', materialSearch: 'Search materials', sourceUnit: 'Lexware unit',
  currentUnit: 'Current local unit', confirmUnit: 'I confirm that one Lexware unit corresponds to one local unit.',
  unitBasisHelp: 'Import uses a 1:1 basis, including the sale price per unit. No conversion is performed and the local unit is not changed. Do not import if the units are not equivalent.',
  articleHelp: 'Choose the kind and unit explicitly. Sale prices never become purchase costs. Services cannot hold stock.',
  materialHelp: 'The existing material remains the only stock source. Its unit must match the selected article unit.',
  missingOptions: 'Complete the article number, kind, unit and stock source before importing.',
  requiredIdentity: 'A new customer requires name and identity; a new article requires its name.',
  externalType: 'Lexware article type', product: 'Product', unsupportedType: 'This Lexware article type is not supported for import.',
  permissionImport: 'You do not have permission to import into this local target.',
  error: 'The request failed. Please try again.', forbidden: 'Permission denied. Check your PrintOps permissions and Lexware key scopes.',
  conflict: 'The operation conflicts with existing data. Check the organization, profile and local target.',
  rateLimited: 'Too many requests. Wait before trying again.', unavailable: 'Lexware is unavailable or the request could not be completed.',
  validation: 'The data could not be accepted. Check the selected fields, target and required article options.',
  authError: 'Authentication failed. Check your session and Lexware key.',
};

const de: typeof en = {
  title: 'Lexware Office', readonly: 'Nur lesend: Lexware → PrintOps',
  setupConnection: 'Verbindung einrichten', previewAction: 'Vorschau', recordName: 'Name', actions: 'Aktion',
  selectPage: 'Neue Kunden auf dieser Seite auswählen', clearSelection: 'Auswahl aufheben', approvalNote: 'Übernahme erst nach deiner Prüfung',
  cancel: 'Abbrechen', previewHelp: 'Wähle die Felder, die du in PrintOps übernehmen möchtest.', selectedFieldsOnly: 'Nur ausgewählte Felder werden in PrintOps geändert.',
  intro: 'Externe Daten werden automatisch alle 15 Minuten aktualisiert. Lokale Kunden und Artikel ändern sich erst nach Prüfung und Übernahme einer Vorschau.',
  permission: 'Dir fehlt die Berechtigung zum Verwalten von Buchhaltungsintegrationen.',
  profilePermission: 'Zum Lesen von Unternehmensprofilen sind zusätzliche Rechte erforderlich. Vorhandene Verbindungen bleiben unten verfügbar.',
  loading: 'Wird geladen…', retry: 'Erneut versuchen', emptyProfiles: 'Lege vor der Verbindung ein aktives Unternehmensprofil an.',
  profile: 'Unternehmensprofil', selectProfile: 'Unternehmensprofil auswählen', key: 'Lexware-API-Schlüssel',
  keyHelp: 'Der Schlüssel wird nur an PrintOps gesendet und serverseitig verschlüsselt gespeichert. Er wird nicht erneut angezeigt.',
  test: 'Verbindung testen', testing: 'Verbindung wird getestet…', save: 'Verbindung speichern', saved: 'Verbindung gespeichert.',
  organization: 'Lexware-Organisation', expectedOrganization: 'Die Organisation muss zur vorhandenen Verbindung passen.',
  wrongOrganization: 'Dieser Schlüssel gehört zu einer anderen Organisation. Die vorhandene Verbindung kann nicht neu zugeordnet werden.',
  connectedProfiles: 'Verbindungen', noConnections: 'Noch keine Lexware-Verbindungen.', replaceKey: 'Schlüssel ersetzen / neu verbinden',
  pause: 'Abruf pausieren', resume: 'Abruf fortsetzen', disconnect: 'Verbindung trennen', sync: 'Jetzt aktualisieren',
  disconnected: 'Getrennt', paused: 'Pausiert', queued: 'Eingereiht', running: 'Abruf läuft', idle: 'Bereit',
  success: 'Aktuell', failed: 'Abruf unvollständig', unknown: 'Unbekannter Status',
  lastSuccess: 'Letzter vollständiger Abruf', lastAttempt: 'Letzter Versuch', never: 'Noch nicht',
  stale: 'Die letzten erfolgreichen Daten bleiben sichtbar. Ein unvollständiger Abruf bedeutet keinen leeren Quellbestand.',
  disconnectHelp: 'Beim Trennen wird der Schlüssel entfernt und neue Abrufe werden gestoppt. Übernommene lokale Daten und externe Nachweise bleiben erhalten.',
  inactive: 'Diese gespeicherten Daten werden nicht mehr aktualisiert.',
  changed: 'Verbindung aktualisiert.', queuedMessage: 'Aktualisierung eingereiht.', disconnectedMessage: 'Verbindung getrennt. Gespeicherte Daten bleiben erhalten.',
  contacts: 'Kunden', articles: 'Artikel', resourcePermission: 'Dir fehlen Leserechte für Kunden und Lager.',
  search: 'Externe Daten suchen', filter: 'Datensatzstatus', all: 'Alle Datensätze', new: 'Nicht verknüpft', linked: 'Verknüpft', archived: 'Archiviert',
  noResources: 'Noch keine externen Datensätze gespeichert. Starte einen vollständigen Abruf.', noMatches: 'Keine passenden Datensätze.',
  sourceNumber: 'Lexware-Nummer', externalId: 'Lexware-ID', updated: 'Stand der Quelldaten', review: 'Übernahme prüfen',
  select: 'Auswählen', selected: 'ausgewählt', reviewSelected: 'Ausgewählte neue Kunden prüfen',
  batchHelp: 'Nur unverknüpfte, nicht archivierte Kunden können gemeinsam ausgewählt werden. Prüfe jede Vorschau vor der Übernahme.',
  close: 'Vorschau schließen', preview: 'Übernahmevorschau', original: 'Originalquelle: Lexware', local: 'Aktuelle lokale Daten: PrintOps',
  field: 'Feld', accept: 'Ausgewählte Felder übernehmen', import: 'Ausgewählte Felder importieren', importing: 'Wird übernommen…',
  link: 'Ohne Feldänderungen verknüpfen',
  imported: 'Übernahme abgeschlossen.', partial: 'Einige Datensätze wurden vor einem Fehler übernommen. Abgeschlossene Datensätze werden nicht erneut importiert.',
  noChanges: 'Keine Feldänderungen zur Übernahme.', chooseFields: 'Wähle die zu übernehmenden Felder aus.',
  shared: 'Gemeinsam genutzter Kunde: Änderungen betreffen Konten in diesen Unternehmensprofilen:',
  preserve: 'Neue Kunden erhalten die ausgewählte Lexware-Kundennummer. Bei bestehenden Kunden musst du die Nummer ausdrücklich auswählen, um sie in diesem Unternehmensprofil zu ersetzen. Notizen, Tags und nicht ausgewählte Felder bleiben erhalten.',
  customer_number: 'Kundennummer',
  customerNumberConflict: 'Diese Kundennummer ist im Unternehmensprofil bereits vergeben. Prüfe das lokale Ziel oder behalte die lokale Nummer, indem du das Feld nicht auswählst.',
  archivedWarning: 'In Lexware archiviert. Lokale Datensätze werden nicht automatisch gelöscht oder deaktiviert.',
  archivedImport: 'Archivierte Lexware-Datensätze können nicht übernommen werden.', reconnectImport: 'Verbinde Lexware erneut, bevor du gespeicherte Daten übernimmst.',
  target: 'Lokales Ziel', createNew: 'Neuen lokalen Datensatz anlegen', targetSearch: 'Lokale Ziele suchen',
  noTargets: 'Keine lokalen Ziele gefunden.', targetHelp: 'Ein gleicher Name ist nur ein Hinweis. Wähle den gewünschten Datensatz ausdrücklich aus.',
  linkedTarget: 'Vorhandene lokale Verknüpfung', previous: 'Zurück', next: 'Weiter',
  refreshPreview: 'Vorschau erneuern', stalePreview: 'Quelldaten oder lokale Daten haben sich geändert. Erneuere und prüfe die Vorschau.',
  identity: 'Name und Identität', addresses: 'Rechnungs- und Lieferadressen', contactFields: 'Kontaktdaten',
  tax_identifiers: 'Steuerkennungen', name: 'Name', description: 'Beschreibung', sale_price: 'Verkaufspreis', tax_rate: 'Steuersatz',
  articleOptions: 'Lokalen Artikel bestätigen', sku: 'Lokale Artikelnummer', kind: 'Artikelart',
  choose: 'Auswählen…', finished: 'Fertigprodukt', trade: 'Handelsware', service: 'Dienstleistung',
  unit: 'Bestätigte lokale Einheit', stockSource: 'Bestandsquelle', own: 'Eigener Warenbestand', material: 'Vorhandener Materialbestand', none: 'Kein Bestand (Dienstleistung)',
  materialTarget: 'Vorhandenes Material', materialSearch: 'Materialien suchen', sourceUnit: 'Lexware-Einheit',
  currentUnit: 'Aktuelle lokale Einheit', confirmUnit: 'Ich bestätige, dass eine Lexware-Einheit einer lokalen Einheit entspricht.',
  unitBasisHelp: 'Die Übernahme erfolgt auf 1:1-Basis, auch für den Verkaufspreis je Einheit. Es erfolgt keine Umrechnung und die lokale Einheit bleibt unverändert. Übernimm die Daten nicht, wenn die Einheiten nicht gleichwertig sind.',
  articleHelp: 'Bestätige Artikelart und Einheit ausdrücklich. Verkaufspreise werden niemals zu Einstandspreisen. Dienste können keinen Bestand erhalten.',
  materialHelp: 'Das vorhandene Material bleibt die einzige Bestandsquelle. Seine Einheit muss zur ausgewählten Artikeleinheit passen.',
  missingOptions: 'Vervollständige Artikelnummer, Art, Einheit und Bestandsquelle vor der Übernahme.',
  requiredIdentity: 'Neue Kunden benötigen Name und Identität; neue Artikel benötigen ihren Namen.',
  externalType: 'Lexware-Artikelart', product: 'Produkt', unsupportedType: 'Diese Lexware-Artikelart wird nicht zur Übernahme unterstützt.',
  permissionImport: 'Dir fehlt die Berechtigung zur Übernahme in dieses lokale Ziel.',
  error: 'Die Anfrage ist fehlgeschlagen. Bitte erneut versuchen.', forbidden: 'Zugriff verweigert. Prüfe deine PrintOps-Rechte und die Freigaben des Lexware-Schlüssels.',
  conflict: 'Die Aktion steht im Konflikt mit vorhandenen Daten. Prüfe Organisation, Profil und lokales Ziel.',
  rateLimited: 'Zu viele Anfragen. Warte vor einem erneuten Versuch.', unavailable: 'Lexware ist nicht erreichbar oder die Anfrage konnte nicht abgeschlossen werden.',
  validation: 'Die Daten konnten nicht übernommen werden. Prüfe Felder, Ziel und die erforderlichen Artikeloptionen.',
  authError: 'Anmeldung fehlgeschlagen. Prüfe deine Sitzung und den Lexware-Schlüssel.',
};

export type LexwareMessages = typeof en;

export function useLexwareMessages() {
  const { i18n } = useTranslation();
  return { text: i18n.language.startsWith('de') ? de : en, locale: i18n.language };
}

// Never render credential request errors verbatim: provider errors can contain secrets.
export function lexwareError(error: unknown, text: LexwareMessages, preview = false): string {
  if (!(error instanceof ApiError)) return text.error;
  if (error.code === 'customer_number_conflict') return text.customerNumberConflict;
  if (error.status === 409) return preview ? text.stalePreview : text.conflict;
  if (error.status === 403) return text.forbidden;
  if (error.status === 401) return text.authError;
  if (error.status === 429) return text.rateLimited;
  if (error.status === 422 || error.status === 400) return text.validation;
  if (error.status >= 500) return text.unavailable;
  return text.error;
}

export function formatLexwareDate(value: string | null, locale: string, empty: string) {
  if (!value) return empty;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? empty : date.toLocaleString(locale);
}
