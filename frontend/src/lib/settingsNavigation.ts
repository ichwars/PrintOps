export type CanonicalSettingsTab =
  | 'general'
  | 'users-security'
  | 'printers-production'
  | 'projects-files'
  | 'warehouse-material'
  | 'orders-calculation'
  | 'integrations'
  | 'operations';

export type LegacySettingsTab =
  | 'plugs'
  | 'notifications'
  | 'queue'
  | 'filament'
  | 'network'
  | 'apikeys'
  | 'virtual-printer'
  | 'spoolbuddy'
  | 'failure-detection'
  | 'users'
  | 'backup'
  | 'email';

export type SettingsTab = CanonicalSettingsTab | LegacySettingsTab;

export type UsersSubTab = 'users' | 'email' | 'ldap' | 'oidc' | 'twofa' | 'security';

export type PrinterProductionSubTab = 'devices' | 'print-process' | 'pipelines' | 'failure-detection';

export type ProjectManagementSubTab = 'files';

export type WarehouseMaterialSubTab = 'filament' | 'catalogs' | 'spoolbuddy';

export type OrderManagementSubTab = 'business-profile' | 'calculation';

export type IntegrationSubTab = 'notifications' | 'webhooks' | 'smart-home' | 'smart-plugs' | 'api-metrics';

export type OperationSubTab = 'updates' | 'data-management' | 'backups';

type SettingsNavIcon =
  | 'settings'
  | 'shield'
  | 'printer'
  | 'fileText'
  | 'warehouse'
  | 'calculator'
  | 'plug'
  | 'database';

export interface SettingsNavItem {
  id: CanonicalSettingsTab;
  labelKey: string;
  fallback: string;
  icon: SettingsNavIcon;
}

export const SETTINGS_NAV_ITEMS: SettingsNavItem[] = [
  { id: 'general', labelKey: 'settings.tabs.general', fallback: 'General', icon: 'settings' },
  {
    id: 'users-security',
    labelKey: 'settings.tabs.usersSecurity',
    fallback: 'Users & Security',
    icon: 'shield',
  },
  {
    id: 'printers-production',
    labelKey: 'settings.tabs.printersProduction',
    fallback: 'Printers & Production',
    icon: 'printer',
  },
  {
    id: 'projects-files',
    labelKey: 'settings.tabs.projectsFiles',
    fallback: 'Projects & Files',
    icon: 'fileText',
  },
  {
    id: 'warehouse-material',
    labelKey: 'settings.tabs.warehouseMaterial',
    fallback: 'Warehouse & Material',
    icon: 'warehouse',
  },
  {
    id: 'orders-calculation',
    labelKey: 'settings.tabs.ordersCalculation',
    fallback: 'Orders & Calculation',
    icon: 'calculator',
  },
  { id: 'integrations', labelKey: 'settings.tabs.integrations', fallback: 'Integrations', icon: 'plug' },
  { id: 'operations', labelKey: 'settings.tabs.operations', fallback: 'Operations', icon: 'database' },
];

const CANONICAL_TABS = new Set<CanonicalSettingsTab>(SETTINGS_NAV_ITEMS.map((item) => item.id));

const LEGACY_TAB_ALIASES: Record<LegacySettingsTab, CanonicalSettingsTab> = {
  plugs: 'integrations',
  notifications: 'integrations',
  queue: 'printers-production',
  filament: 'warehouse-material',
  network: 'integrations',
  apikeys: 'integrations',
  'virtual-printer': 'printers-production',
  spoolbuddy: 'warehouse-material',
  'failure-detection': 'printers-production',
  users: 'users-security',
  backup: 'operations',
  email: 'users-security',
};

const LEGACY_TAB_DEFAULT_SUBTABS: Partial<Record<LegacySettingsTab, {
  usersSubTab?: UsersSubTab;
  printerProductionSubTab?: PrinterProductionSubTab;
  projectManagementSubTab?: ProjectManagementSubTab;
  warehouseMaterialSubTab?: WarehouseMaterialSubTab;
  orderManagementSubTab?: OrderManagementSubTab;
  integrationSubTab?: IntegrationSubTab;
  operationSubTab?: OperationSubTab;
}>> = {
  users: { usersSubTab: 'users' },
  email: { usersSubTab: 'email' },
  queue: { printerProductionSubTab: 'print-process' },
  'virtual-printer': { printerProductionSubTab: 'devices' },
  'failure-detection': { printerProductionSubTab: 'failure-detection' },
  filament: { warehouseMaterialSubTab: 'filament' },
  spoolbuddy: { warehouseMaterialSubTab: 'spoolbuddy' },
  notifications: { integrationSubTab: 'notifications' },
  network: { integrationSubTab: 'smart-home' },
  plugs: { integrationSubTab: 'smart-plugs' },
  apikeys: { integrationSubTab: 'api-metrics' },
  backup: { operationSubTab: 'backups' },
};

const LEGACY_TAB_DEFAULT_ANCHORS: Partial<Record<LegacySettingsTab, string>> = {
  users: 'card-users',
  email: 'card-smtp',
  apikeys: 'card-createapi',
  queue: 'card-print-options',
  'virtual-printer': 'card-vp',
  'failure-detection': 'card-fd-ml',
  filament: 'card-filamentchecks',
  spoolbuddy: 'card-spoolbuddy',
  plugs: 'card-plugs',
  notifications: 'card-providers',
  network: 'card-externalurl',
  backup: 'card-backup',
};

export function resolveSettingsTab(tabParam: string | null): CanonicalSettingsTab {
  if (!tabParam) {
    return 'general';
  }

  if (CANONICAL_TABS.has(tabParam as CanonicalSettingsTab)) {
    return tabParam as CanonicalSettingsTab;
  }

  return LEGACY_TAB_ALIASES[tabParam as LegacySettingsTab] ?? 'general';
}

export function canonicalTabToUrlParam(tab: CanonicalSettingsTab): string | null {
  return tab === 'general' ? null : tab;
}

export function settingsTabLabelKey(tab: CanonicalSettingsTab): string {
  return SETTINGS_NAV_ITEMS.find((item) => item.id === tab)?.labelKey ?? 'settings.tabs.general';
}

export function resolveOrderManagementSubTab(value: string | null): OrderManagementSubTab | null {
  return value === 'business-profile' || value === 'calculation' ? value : null;
}

export function legacySettingsTabDefaultSubTab(tabParam: string | null): {
  usersSubTab?: UsersSubTab;
  printerProductionSubTab?: PrinterProductionSubTab;
  projectManagementSubTab?: ProjectManagementSubTab;
  warehouseMaterialSubTab?: WarehouseMaterialSubTab;
  orderManagementSubTab?: OrderManagementSubTab;
  integrationSubTab?: IntegrationSubTab;
  operationSubTab?: OperationSubTab;
} {
  if (!tabParam) {
    return {};
  }

  return LEGACY_TAB_DEFAULT_SUBTABS[tabParam as LegacySettingsTab] ?? {};
}

export function legacySettingsTabDefaultAnchor(tabParam: string | null): string | undefined {
  if (!tabParam) {
    return undefined;
  }

  return LEGACY_TAB_DEFAULT_ANCHORS[tabParam as LegacySettingsTab];
}
