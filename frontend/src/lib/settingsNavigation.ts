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

export type QueueSubTab = 'dispatch' | 'pipelines';

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
  apikeys: 'users-security',
  'virtual-printer': 'printers-production',
  spoolbuddy: 'warehouse-material',
  'failure-detection': 'printers-production',
  users: 'users-security',
  backup: 'operations',
  email: 'users-security',
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

export function legacySettingsTabDefaultSubTab(tabParam: string | null): {
  usersSubTab?: UsersSubTab;
  queueSubTab?: QueueSubTab;
} {
  if (tabParam === 'email') return { usersSubTab: 'email' };
  if (tabParam === 'queue') return { queueSubTab: 'dispatch' };
  return {};
}
