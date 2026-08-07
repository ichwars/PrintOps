import {
  AlertTriangle,
  Bell,
  Building2,
  Database,
  DollarSign,
  Droplets,
  FileText,
  Globe,
  Home,
  ListOrdered,
  Mail,
  PanelsTopLeft,
  Plug,
  Printer,
  QrCode,
  RefreshCw,
  Send,
  Settings as SettingsIcon,
  Shield,
  TrendingUp,
  Users,
  Workflow,
} from 'lucide-react';
import type { UpdateStatus } from '../api/client';
import type { SettingsSearchEntry } from '../lib/settingsSearch';
import {
  SETTINGS_NAV_ITEMS,
  type CanonicalSettingsTab,
  type IntegrationSubTab,
  type OperationSubTab,
  type OrderManagementSubTab,
  type PrinterProductionSubTab,
  type ProjectManagementSubTab,
  type UsersSubTab,
  type WarehouseMaterialSubTab,
} from '../lib/settingsNavigation';

export const STORAGE_CATEGORY_COLORS: Record<string, string> = {
  database: 'bg-blue-600',
  library_files: 'bg-green-500',
  library_thumbnails: 'bg-teal-500',
  library_other: 'bg-emerald-700',
  archive_timelapses: 'bg-red-500',
  archive_thumbnails: 'bg-amber-500',
  archive_files: 'bg-sky-500',
  virtual_printer_uploads: 'bg-purple-500',
  virtual_printer_upload_cache: 'bg-fuchsia-500',
  virtual_printer_certs: 'bg-violet-500',
  virtual_printer_other: 'bg-purple-700',
  downloads: 'bg-cyan-500',
  plate_calibration: 'bg-lime-500',
  logs: 'bg-orange-500',
  other_data: 'bg-yellow-500',
};

export const STORAGE_FALLBACK_COLORS = [
  'bg-blue-500',
  'bg-green-500',
  'bg-yellow-500',
  'bg-red-500',
  'bg-orange-500',
  'bg-teal-500',
  'bg-cyan-500',
  'bg-purple-500',
];

export const getStorageColor = (key: string, index: number) =>
  STORAGE_CATEGORY_COLORS[key] || STORAGE_FALLBACK_COLORS[index % STORAGE_FALLBACK_COLORS.length];

export const settingsSearchTabFallbackLabels = Object.fromEntries(
  SETTINGS_NAV_ITEMS.map((item) => [item.id, item.fallback]),
) as Record<string, string>;

export type SettingsHeaderMeta = {
  labelKey: string;
  fallback: string;
  fallbackDe?: string;
  descriptionKey: string;
  descriptionFallback: string;
  descriptionFallbackDe?: string;
  icon: typeof Bell;
};

export const SETTINGS_SECTION_HEADERS: Record<CanonicalSettingsTab, SettingsHeaderMeta> = {
  general: {
    labelKey: 'settings.tabs.general',
    fallback: 'General',
    descriptionKey: 'settings.sectionDescriptions.general',
    descriptionFallback: 'Manage language, appearance, default views, and personal UI preferences.',
    descriptionFallbackDe: 'Sprache, Darstellung, Standardansichten und persönliche UI-Einstellungen verwalten.',
    icon: SettingsIcon,
  },
  'users-security': {
    labelKey: 'settings.tabs.usersSecurity',
    fallback: 'Users & Security',
    descriptionKey: 'settings.sectionDescriptions.usersSecurity',
    descriptionFallback: 'Manage users, authentication, identity providers, and security controls.',
    descriptionFallbackDe: 'Benutzer, Authentifizierung, Identitätsanbieter und Sicherheitsfunktionen verwalten.',
    icon: Shield,
  },
  'printers-production': {
    labelKey: 'settings.tabs.printersProduction',
    fallback: 'Printers & Production',
    fallbackDe: 'Geräteverwaltung',
    descriptionKey: 'settings.sectionDescriptions.printersProduction',
    descriptionFallback: 'Configure print defaults, production flows, virtual printers, and printer support features.',
    descriptionFallbackDe: 'Druckstandards, Produktionsabläufe, virtuelle Drucker und Druckerfunktionen konfigurieren.',
    icon: Printer,
  },
  'projects-files': {
    labelKey: 'settings.tabs.projectsFiles',
    fallback: 'Projects & Files',
    fallbackDe: 'Projektverwaltung',
    descriptionKey: 'settings.sectionDescriptions.projectsFiles',
    descriptionFallback: 'Manage file handling, external folders, project links, and storage rules.',
    descriptionFallbackDe: 'Dateiverwaltung, externe Ordner, Projektverknüpfungen und Speicherregeln verwalten.',
    icon: FileText,
  },
  'warehouse-material': {
    labelKey: 'settings.tabs.warehouseMaterial',
    fallback: 'Warehouse & Material',
    fallbackDe: 'Lagerverwaltung',
    descriptionKey: 'settings.sectionDescriptions.warehouseMaterial',
    descriptionFallback: 'Manage filament checks, Spoolman, material catalogs, and warehouse-related defaults.',
    descriptionFallbackDe: 'Filamentprüfungen, Spoolman, Materialkataloge und lagerbezogene Standards verwalten.',
    icon: Database,
  },
  'orders-calculation': {
    labelKey: 'settings.tabs.ordersCalculation',
    fallback: 'Orders & Calculation',
    fallbackDe: 'Auftragsverwaltung',
    descriptionKey: 'settings.sectionDescriptions.ordersCalculation',
    descriptionFallback: 'Configure currency, cost tracking, and calculation defaults for commercial workflows.',
    descriptionFallbackDe: 'Währung, Kostenverfolgung und Kalkulationsstandards für kaufmännische Abläufe konfigurieren.',
    icon: DollarSign,
  },
  integrations: {
    labelKey: 'settings.tabs.integrations',
    fallback: 'Integrations',
    descriptionKey: 'settings.sectionDescriptions.integrations',
    descriptionFallback: 'Connect PrintOps to notifications, automation, smart home, and API services.',
    descriptionFallbackDe: 'PrintOps mit Benachrichtigungen, Automatisierung, Smart Home und API-Diensten verbinden.',
    icon: Plug,
  },
  operations: {
    labelKey: 'settings.tabs.operations',
    fallback: 'Operations',
    descriptionKey: 'settings.sectionDescriptions.operations',
    descriptionFallback: 'Manage updates, data cleanup, backups, and operational maintenance tasks.',
    descriptionFallbackDe: 'Updates, Datenbereinigung, Sicherungen und betriebliche Wartungsaufgaben verwalten.',
    icon: Database,
  },
};

export const USER_SECURITY_SUB_TABS: Record<UsersSubTab, SettingsHeaderMeta> = {
  users: {
    labelKey: 'settings.tabs.users',
    fallback: 'Authentication',
    descriptionKey: 'settings.userSecuritySubTabDescriptions.users',
    descriptionFallback: 'Manage local users, groups, roles, sessions, and authentication state.',
    descriptionFallbackDe: 'Lokale Benutzer, Gruppen, Rollen, Sitzungen und Authentifizierungsstatus verwalten.',
    icon: Users,
  },
  email: {
    labelKey: 'settings.tabs.emailAuth',
    fallback: 'Email Authentication',
    descriptionKey: 'settings.userSecuritySubTabDescriptions.email',
    descriptionFallback: 'Configure SMTP delivery and email-based authentication workflows.',
    descriptionFallbackDe: 'SMTP-Versand und E-Mail-basierte Authentifizierungsabläufe konfigurieren.',
    icon: Mail,
  },
  ldap: {
    labelKey: 'settings.tabs.ldap',
    fallback: 'LDAP',
    descriptionKey: 'settings.userSecuritySubTabDescriptions.ldap',
    descriptionFallback: 'Connect directory authentication and map LDAP groups to PrintOps roles.',
    descriptionFallbackDe: 'Verzeichnisanmeldung anbinden und LDAP-Gruppen PrintOps-Rollen zuordnen.',
    icon: Shield,
  },
  twofa: {
    labelKey: 'settings.tabs.twoFa',
    fallback: 'Two-Factor Auth',
    descriptionKey: 'settings.userSecuritySubTabDescriptions.twofa',
    descriptionFallback: 'Manage TOTP, email OTP, and linked two-factor methods.',
    descriptionFallbackDe: 'TOTP, E-Mail-OTP und verknüpfte Zwei-Faktor-Methoden verwalten.',
    icon: Shield,
  },
  oidc: {
    labelKey: 'settings.tabs.oidc',
    fallback: 'SSO / OIDC',
    descriptionKey: 'settings.userSecuritySubTabDescriptions.oidc',
    descriptionFallback: 'Configure SSO/OIDC identity providers and login behavior.',
    descriptionFallbackDe: 'SSO/OIDC-Identitätsanbieter und Anmeldeverhalten konfigurieren.',
    icon: Globe,
  },
  security: {
    labelKey: 'settings.tabs.security',
    fallback: 'Security',
    descriptionKey: 'settings.userSecuritySubTabDescriptions.security',
    descriptionFallback: 'Review security posture, session rules, and authentication safeguards.',
    descriptionFallbackDe: 'Sicherheitsstatus, Sitzungsregeln und Authentifizierungsschutz prüfen.',
    icon: Shield,
  },
};

export const PRINTER_PRODUCTION_SUB_TABS: Record<PrinterProductionSubTab, SettingsHeaderMeta> = {
  devices: {
    labelKey: 'settings.tabs.deviceManagementDevices',
    fallback: 'Devices',
    fallbackDe: 'Geräte',
    descriptionKey: 'settings.printerProductionSubTabDescriptions.devices',
    descriptionFallback: 'Manage default printers, cameras, FTP retry behavior, and virtual printer endpoints.',
    descriptionFallbackDe: 'Standarddrucker, Kameras, FTP-Wiederholungen und virtuelle Drucker-Endpunkte verwalten.',
    icon: Printer,
  },
  'print-process': {
    labelKey: 'settings.tabs.deviceManagementPrintProcess',
    fallback: 'Print Process',
    fallbackDe: 'Druckprozess',
    descriptionKey: 'settings.printerProductionSubTabDescriptions.printProcess',
    descriptionFallback: 'Configure print defaults, archiving, queue behavior, G-code, slicer, and completion rules.',
    descriptionFallbackDe: 'Druckstandards, Archivierung, Warteschlangenverhalten, G-Code, Slicer und Abschlussregeln konfigurieren.',
    icon: ListOrdered,
  },
  pipelines: {
    labelKey: 'settings.tabs.queuePipelines',
    fallback: 'Pipelines',
    descriptionKey: 'settings.printerProductionSubTabDescriptions.pipelines',
    descriptionFallback: 'Manage slicer pipelines, presets, and automated preparation flows.',
    descriptionFallbackDe: 'Slicer-Pipelines, Profile und automatische Vorbereitungsabläufe verwalten.',
    icon: Workflow,
  },
  'failure-detection': {
    labelKey: 'settings.tabs.failureDetection',
    fallback: 'Failure Detection',
    fallbackDe: 'Fehlererkennung',
    descriptionKey: 'settings.printerProductionSubTabDescriptions.failureDetection',
    descriptionFallback: 'Configure AI failure monitoring, per-printer detection behavior, status, and history.',
    descriptionFallbackDe: 'KI-Fehlererkennung, druckerspezifisches Erkennungsverhalten, Status und Verlauf konfigurieren.',
    icon: AlertTriangle,
  },
};

export const PRINTER_PRODUCTION_SUB_TAB_ITEMS: Array<{ id: PrinterProductionSubTab; meta: SettingsHeaderMeta }> = [
  { id: 'devices', meta: PRINTER_PRODUCTION_SUB_TABS.devices },
  { id: 'print-process', meta: PRINTER_PRODUCTION_SUB_TABS['print-process'] },
  { id: 'pipelines', meta: PRINTER_PRODUCTION_SUB_TABS.pipelines },
  { id: 'failure-detection', meta: PRINTER_PRODUCTION_SUB_TABS['failure-detection'] },
];

export const PROJECT_MANAGEMENT_SUB_TABS: Record<ProjectManagementSubTab, SettingsHeaderMeta> = {
  files: {
    labelKey: 'settings.tabs.projectManagementFiles',
    fallback: 'File Management',
    fallbackDe: 'Dateiverwaltung',
    descriptionKey: 'settings.projectManagementSubTabDescriptions.files',
    descriptionFallback: 'Manage file handling, archive modes, disk warnings, and project storage rules.',
    descriptionFallbackDe: 'Dateiverwaltung, Archivmodi, Speicherwarnungen und Projektspeicher-Regeln verwalten.',
    icon: FileText,
  },
};

export const PROJECT_MANAGEMENT_SUB_TAB_ITEMS: Array<{ id: ProjectManagementSubTab; meta: SettingsHeaderMeta }> = [
  { id: 'files', meta: PROJECT_MANAGEMENT_SUB_TABS.files },
];

export const WAREHOUSE_MATERIAL_SUB_TABS: Record<WarehouseMaterialSubTab, SettingsHeaderMeta> = {
  'number-sequences': {
    labelKey: 'settings.tabs.warehouseNumberSequences',
    fallback: 'Number sequences',
    fallbackDe: 'Nummernkreise',
    descriptionKey: 'settings.warehouseMaterialSubTabDescriptions.numberSequences',
    descriptionFallback: 'Manage global number sequences for materials, spools, purchase orders, and goods receipts.',
    descriptionFallbackDe: 'Globale Nummernkreise für Material, Spulen, Bestellungen und Wareneingänge verwalten.',
    icon: ListOrdered,
  },
  filament: {
    labelKey: 'settings.tabs.warehouseFilament',
    fallback: 'Filament',
    descriptionKey: 'settings.warehouseMaterialSubTabDescriptions.filament',
    descriptionFallback: 'Manage drying presets, Spoolman tracking, filament checks, mapping, and AMS display thresholds.',
    descriptionFallbackDe: 'Trocknungsprofile, Spoolman-Verfolgung, Filamentprüfungen, Zuordnung und AMS-Anzeigeschwellen verwalten.',
    icon: Droplets,
  },
  'small-parts': {
    labelKey: 'settings.tabs.warehouseSmallParts',
    fallback: 'Material',
    fallbackDe: 'Material',
    descriptionKey: 'settings.warehouseMaterialSubTabDescriptions.smallParts',
    descriptionFallback: 'Manage material categories, units, shared locations, and stock defaults.',
    descriptionFallbackDe: 'Materialkategorien, Einheiten, gemeinsame Lagerorte und Bestandsstandards verwalten.',
    icon: Database,
  },
  catalogs: {
    labelKey: 'settings.tabs.warehouseCatalogs',
    fallback: 'Catalogs',
    fallbackDe: 'Kataloge',
    descriptionKey: 'settings.warehouseMaterialSubTabDescriptions.catalogs',
    descriptionFallback: 'Manage spool and color catalogs used for inventory and label workflows.',
    descriptionFallbackDe: 'Spulen- und Farbkataloge für Lager- und Label-Abläufe verwalten.',
    icon: Database,
  },
  spoolbuddy: {
    labelKey: 'settings.tabs.spoolbuddy',
    fallback: 'SpoolBuddy',
    descriptionKey: 'settings.warehouseMaterialSubTabDescriptions.spoolbuddy',
    descriptionFallback: 'Manage SpoolBuddy kiosks, NFC readers, scales, calibration, and device registration.',
    descriptionFallbackDe: 'SpoolBuddy-Kioske, NFC-Leser, Waagen, Kalibrierung und Geräteregistrierung verwalten.',
    icon: QrCode,
  },
};

export const WAREHOUSE_MATERIAL_SUB_TAB_ITEMS: Array<{ id: WarehouseMaterialSubTab; meta: SettingsHeaderMeta }> = [
  { id: 'number-sequences', meta: WAREHOUSE_MATERIAL_SUB_TABS['number-sequences'] },
  { id: 'filament', meta: WAREHOUSE_MATERIAL_SUB_TABS.filament },
  { id: 'small-parts', meta: WAREHOUSE_MATERIAL_SUB_TABS['small-parts'] },
  { id: 'catalogs', meta: WAREHOUSE_MATERIAL_SUB_TABS.catalogs },
  { id: 'spoolbuddy', meta: WAREHOUSE_MATERIAL_SUB_TABS.spoolbuddy },
];

export const ORDER_MANAGEMENT_SUB_TABS: Record<OrderManagementSubTab, SettingsHeaderMeta> = {
  'business-profile': {
    labelKey: 'settings.tabs.orderManagementBusinessProfile',
    fallback: 'Business Profile',
    fallbackDe: 'Unternehmensprofil',
    descriptionKey: 'settings.orderManagementSubTabDescriptions.businessProfile',
    descriptionFallback: 'Manage the company details used to issue commercial documents.',
    descriptionFallbackDe: 'Unternehmensdaten für die Ausstellung kaufmännischer Dokumente verwalten.',
    icon: Building2,
  },
  documents: {
    labelKey: 'settings.tabs.orderManagementDocuments',
    fallback: 'Documents',
    fallbackDe: 'Dokumente',
    descriptionKey: 'settings.orderManagementSubTabDescriptions.documents',
    descriptionFallback: 'Configure versioned document rules, payment terms, tax handling, and electronic invoices.',
    descriptionFallbackDe: 'Versionierte Dokumentregeln, Zahlungsbedingungen, Steuerbehandlung und E-Rechnungen konfigurieren.',
    icon: FileText,
  },
  'format-preview': {
    labelKey: 'settings.tabs.orderManagementFormatPreview',
    fallback: 'Format & Preview',
    fallbackDe: 'Format & Vorschau',
    descriptionKey: 'settings.orderManagementSubTabDescriptions.formatPreview',
    descriptionFallback: 'Design versioned PDF layouts, verify real previews, and control publishing readiness.',
    descriptionFallbackDe: 'Versionierte PDF-Layouts gestalten, echte Vorschauen prüfen und die Freigabebereitschaft steuern.',
    icon: PanelsTopLeft,
  },
  calculation: {
    labelKey: 'settings.tabs.orderManagementCalculation',
    fallback: 'Calculation',
    fallbackDe: 'Kalkulation',
    descriptionKey: 'settings.orderManagementSubTabDescriptions.calculation',
    descriptionFallback: 'Configure currency, cost tracking, and calculation defaults for commercial workflows.',
    descriptionFallbackDe: 'Währung, Kostenverfolgung und Kalkulationsstandards für kaufmännische Abläufe konfigurieren.',
    icon: DollarSign,
  },
};

export const ORDER_MANAGEMENT_SUB_TAB_ITEMS: Array<{ id: OrderManagementSubTab; meta: SettingsHeaderMeta }> = [
  { id: 'business-profile', meta: ORDER_MANAGEMENT_SUB_TABS['business-profile'] },
  { id: 'documents', meta: ORDER_MANAGEMENT_SUB_TABS.documents },
  { id: 'format-preview', meta: ORDER_MANAGEMENT_SUB_TABS['format-preview'] },
  { id: 'calculation', meta: ORDER_MANAGEMENT_SUB_TABS.calculation },
];

export const UPDATE_STATUS_FALLBACK_LABELS: Record<UpdateStatus['status'], string> = {
  idle: 'Idle',
  checking: 'Checking',
  downloading: 'Downloading',
  installing: 'Installing',
  complete: 'Complete',
  error: 'Error',
};

export const legacySearchTabByAnchor: Record<string, string> = {
  'card-general': 'general',
  'card-appearance': 'general',
  'card-ui-preferences': 'general',
  'card-sidebar-links': 'general',
  'card-default-printer': 'printers-production',
  'card-archive': 'printers-production',
  'card-camera': 'printers-production',
  'card-cost': 'orders-calculation',
  'card-document-settings': 'orders-calculation',
  'card-document-layout-settings': 'orders-calculation',
  'card-filemanager': 'projects-files',
  'card-updates': 'operations',
  'card-data': 'operations',
  'card-plugs': 'plugs',
  'card-providers': 'notifications',
  'card-templates': 'notifications',
  'card-print-options': 'queue',
  'card-temp-fan-presets': 'queue',
  'card-staggered': 'queue',
  'card-plate': 'queue',
  'card-gcode': 'queue',
  'card-slicer': 'queue',
  'card-drying': 'warehouse-material',
  'card-warehouse-number-sequences': 'warehouse-material',
  'card-preheat': 'queue',
  'card-pipelines': 'queue',
  'card-filamentchecks': 'filament',
  'card-printmodal': 'filament',
  'card-amsthresholds': 'filament',
  'card-spoolman': 'filament',
  'card-spool-catalog': 'filament',
  'card-color-catalog': 'filament',
  'card-externalurl': 'network',
  'card-ftpretry': 'printers-production',
  'card-ha': 'network',
  'card-mqtt': 'network',
  'card-prometheus': 'integrations',
  'card-createapi': 'integrations',
  'card-webhooks': 'integrations',
  'card-apibrowser': 'integrations',
  'card-camera-tokens': 'integrations',
  'card-vp': 'virtual-printer',
  'card-spoolbuddy': 'spoolbuddy',
  'card-fd-ml': 'failure-detection',
  'card-fd-perprinter': 'failure-detection',
  'card-fd-status': 'failure-detection',
  'card-fd-history': 'failure-detection',
  'card-failure-detection': 'failure-detection',
  'card-currentuser': 'users',
  'card-users': 'users',
  'card-groups': 'users',
  'card-session-policy': 'users',
  'card-smtp': 'users',
  'card-smtp-config': 'users',
  'card-email-advanced-auth': 'users',
  'card-email-test': 'users',
  'card-ldap': 'users',
  'card-ldap-server': 'users',
  'card-ldap-toggle': 'users',
  'card-2fa-totp': 'users',
  'card-2fa-emailotp': 'users',
  'card-2fa-linked': 'users',
  'card-oidc': 'users',
  'card-oidc-empty': 'users',
  'card-mfa-encryption': 'users',
  'card-backup': 'backup',
  'card-backup-github': 'backup',
  'card-backup-history': 'backup',
  'card-backup-local': 'backup',
  'card-backup-scheduled': 'backup',
};

export function resolveLegacySearchTab(entry: SettingsSearchEntry): string {
  return legacySearchTabByAnchor[entry.anchor] ?? 'general';
}

export const INTEGRATION_SUB_TABS: Array<{
  id: IntegrationSubTab;
  labelKey: string;
  fallback: string;
  fallbackDe?: string;
  descriptionKey: string;
  descriptionFallback: string;
  descriptionFallbackDe?: string;
  icon: typeof Bell;
}> = [
  {
    id: 'notifications',
    labelKey: 'settings.tabs.notifications',
    fallback: 'Notifications',
    descriptionKey: 'settings.integrationSubTabDescriptions.notifications',
    descriptionFallback: 'Manage notification providers, templates, and delivery logs.',
    descriptionFallbackDe: 'Benachrichtigungskanäle, Vorlagen und Versandprotokolle verwalten.',
    icon: Bell,
  },
  {
    id: 'webhooks',
    labelKey: 'settings.tabs.webhooks',
    fallback: 'Webhooks',
    descriptionKey: 'settings.integrationSubTabDescriptions.webhooks',
    descriptionFallback: 'Review webhook endpoints for external automation and API-driven workflows.',
    descriptionFallbackDe: 'Webhook-Endpunkte für externe Automatisierungen und API-Abläufe prüfen.',
    icon: Send,
  },
  {
    id: 'smart-home',
    labelKey: 'settings.tabs.smartHome',
    fallback: 'Smart Home',
    descriptionKey: 'settings.integrationSubTabDescriptions.smartHome',
    descriptionFallback: 'Configure Home Assistant, MQTT publishing, and the external PrintOps URL.',
    descriptionFallbackDe: 'Home Assistant, MQTT-Veröffentlichung und externe PrintOps-URL konfigurieren.',
    icon: Home,
  },
  {
    id: 'smart-plugs',
    labelKey: 'settings.tabs.smartPlugs',
    fallback: 'Smart Plugs',
    descriptionKey: 'settings.integrationSubTabDescriptions.smartPlugs',
    descriptionFallback: 'Manage smart plugs, switching, reachability, and energy readings.',
    descriptionFallbackDe: 'Smart Plugs, Schaltzustände, Erreichbarkeit und Energieverbrauch verwalten.',
    icon: Plug,
  },
  {
    id: 'api-metrics',
    labelKey: 'settings.tabs.apiMetrics',
    fallback: 'API & Metrics',
    fallbackDe: 'API & Metriken',
    descriptionKey: 'settings.integrationSubTabDescriptions.apiMetrics',
    descriptionFallback: 'Manage API keys, camera tokens, Prometheus metrics, and the API browser.',
    descriptionFallbackDe: 'API-Schlüssel, Kamera-Tokens, Prometheus-Metriken und den API-Browser verwalten.',
    icon: TrendingUp,
  },
];

export const OPERATION_SUB_TABS: Array<{
  id: OperationSubTab;
  labelKey: string;
  fallback: string;
  fallbackDe?: string;
  descriptionKey: string;
  descriptionFallback: string;
  descriptionFallbackDe?: string;
  icon: typeof Bell;
}> = [
  {
    id: 'updates',
    labelKey: 'settings.tabs.operationUpdates',
    fallback: 'Updates',
    descriptionKey: 'settings.operationSubTabDescriptions.updates',
    descriptionFallback: 'Manage PrintOps update checks, beta channels, and printer firmware monitoring.',
    descriptionFallbackDe: 'PrintOps-Updateprüfungen, Beta-Kanäle und Drucker-Firmware-Überwachung verwalten.',
    icon: RefreshCw,
  },
  {
    id: 'data-management',
    labelKey: 'settings.tabs.operationDataManagement',
    fallback: 'Data Management',
    descriptionKey: 'settings.operationSubTabDescriptions.dataManagement',
    descriptionFallback: 'Review storage usage, clear local records, and route backup or restore tasks.',
    descriptionFallbackDe: 'Speichernutzung prüfen, lokale Daten bereinigen und Backup- oder Wiederherstellungsaufgaben steuern.',
    icon: Database,
  },
  {
    id: 'backups',
    labelKey: 'settings.tabs.operationBackups',
    fallback: 'Backups',
    descriptionKey: 'settings.operationSubTabDescriptions.backups',
    descriptionFallback: 'Manage local and GitHub backups, restore archives, schedules, and backup history.',
    descriptionFallbackDe: 'Lokale und GitHub-Backups, Wiederherstellungsarchive, Zeitpläne und Backup-Verlauf verwalten.',
    icon: Shield,
  },
];

export const INTEGRATION_SUB_TAB_IDS = new Set<IntegrationSubTab>(INTEGRATION_SUB_TABS.map((item) => item.id));
export const OPERATION_SUB_TAB_IDS = new Set<OperationSubTab>(OPERATION_SUB_TABS.map((item) => item.id));
export const PRINTER_PRODUCTION_SUB_TAB_IDS = new Set<PrinterProductionSubTab>(
  PRINTER_PRODUCTION_SUB_TAB_ITEMS.map((item) => item.id),
);
export const PROJECT_MANAGEMENT_SUB_TAB_IDS = new Set<ProjectManagementSubTab>(
  PROJECT_MANAGEMENT_SUB_TAB_ITEMS.map((item) => item.id),
);
export const WAREHOUSE_MATERIAL_SUB_TAB_IDS = new Set<WarehouseMaterialSubTab>(
  WAREHOUSE_MATERIAL_SUB_TAB_ITEMS.map((item) => item.id),
);
export function resolveIntegrationSubTab(value: string | null): IntegrationSubTab | null {
  return INTEGRATION_SUB_TAB_IDS.has(value as IntegrationSubTab) ? value as IntegrationSubTab : null;
}

export function integrationSubTabUrlParam(subTab: IntegrationSubTab): string | null {
  return subTab === 'notifications' ? null : subTab;
}

export function resolveOperationSubTab(value: string | null): OperationSubTab | null {
  return OPERATION_SUB_TAB_IDS.has(value as OperationSubTab) ? value as OperationSubTab : null;
}

export function operationSubTabUrlParam(subTab: OperationSubTab): string | null {
  return subTab === 'updates' ? null : subTab;
}

export function resolvePrinterProductionSubTab(value: string | null): PrinterProductionSubTab | null {
  return PRINTER_PRODUCTION_SUB_TAB_IDS.has(value as PrinterProductionSubTab)
    ? value as PrinterProductionSubTab
    : null;
}

export function printerProductionSubTabUrlParam(subTab: PrinterProductionSubTab): string | null {
  return subTab === 'devices' ? null : subTab;
}

export function resolveProjectManagementSubTab(value: string | null): ProjectManagementSubTab | null {
  return PROJECT_MANAGEMENT_SUB_TAB_IDS.has(value as ProjectManagementSubTab)
    ? value as ProjectManagementSubTab
    : null;
}

export function projectManagementSubTabUrlParam(subTab: ProjectManagementSubTab): string | null {
  return subTab === 'files' ? null : subTab;
}

export function resolveWarehouseMaterialSubTab(value: string | null): WarehouseMaterialSubTab | null {
  return WAREHOUSE_MATERIAL_SUB_TAB_IDS.has(value as WarehouseMaterialSubTab)
    ? value as WarehouseMaterialSubTab
    : null;
}

export function warehouseMaterialSubTabUrlParam(subTab: WarehouseMaterialSubTab): string | null {
  return subTab === 'filament' ? null : subTab;
}

export function orderManagementSubTabUrlParam(subTab: OrderManagementSubTab): string | null {
  return subTab === 'business-profile' ? null : subTab;
}
