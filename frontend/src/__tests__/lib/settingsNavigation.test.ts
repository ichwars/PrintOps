import { describe, expect, it } from 'vitest';
import {
  SETTINGS_NAV_ITEMS,
  canonicalTabToUrlParam,
  legacySettingsTabDefaultAnchor,
  legacySettingsTabDefaultSubTab,
  resolveOrderManagementSubTab,
  resolveSettingsTab,
  settingsTabLabelKey,
} from '../../lib/settingsNavigation';

describe('settingsNavigation', () => {
  it('resolves the canonical business profile order-management subtab', () => {
    expect(resolveOrderManagementSubTab('business-profile')).toBe('business-profile');
    expect(resolveOrderManagementSubTab('documents')).toBe('documents');
    expect(resolveOrderManagementSubTab('calculation')).toBe('calculation');
    expect(resolveOrderManagementSubTab('unknown')).toBeNull();
  });

  it('keeps Allgemein as the default tab without a URL parameter', () => {
    expect(resolveSettingsTab(null)).toBe('general');
    expect(canonicalTabToUrlParam('general')).toBeNull();
  });

  it('resolves canonical tab ids directly', () => {
    expect(resolveSettingsTab('users-security')).toBe('users-security');
    expect(resolveSettingsTab('printers-production')).toBe('printers-production');
    expect(resolveSettingsTab('projects-files')).toBe('projects-files');
    expect(resolveSettingsTab('warehouse-material')).toBe('warehouse-material');
    expect(resolveSettingsTab('orders-calculation')).toBe('orders-calculation');
    expect(resolveSettingsTab('integrations')).toBe('integrations');
    expect(resolveSettingsTab('operations')).toBe('operations');
  });

  it('maps legacy tab ids to canonical domains', () => {
    expect(resolveSettingsTab('queue')).toBe('printers-production');
    expect(resolveSettingsTab('virtual-printer')).toBe('printers-production');
    expect(resolveSettingsTab('failure-detection')).toBe('printers-production');
    expect(resolveSettingsTab('filament')).toBe('warehouse-material');
    expect(resolveSettingsTab('spoolbuddy')).toBe('warehouse-material');
    expect(resolveSettingsTab('plugs')).toBe('integrations');
    expect(resolveSettingsTab('notifications')).toBe('integrations');
    expect(resolveSettingsTab('network')).toBe('integrations');
    expect(resolveSettingsTab('apikeys')).toBe('integrations');
    expect(resolveSettingsTab('users')).toBe('users-security');
    expect(resolveSettingsTab('backup')).toBe('operations');
  });

  it('keeps legacy sub-tab intent after the settings IA consolidation', () => {
    expect(legacySettingsTabDefaultSubTab('users')).toEqual({ usersSubTab: 'users' });
    expect(legacySettingsTabDefaultSubTab('email')).toEqual({ usersSubTab: 'email' });
    expect(legacySettingsTabDefaultSubTab('queue')).toEqual({ printerProductionSubTab: 'print-process' });
    expect(legacySettingsTabDefaultSubTab('virtual-printer')).toEqual({ printerProductionSubTab: 'devices' });
    expect(legacySettingsTabDefaultSubTab('failure-detection')).toEqual({ printerProductionSubTab: 'failure-detection' });
    expect(legacySettingsTabDefaultSubTab('filament')).toEqual({ warehouseMaterialSubTab: 'filament' });
    expect(legacySettingsTabDefaultSubTab('spoolbuddy')).toEqual({ warehouseMaterialSubTab: 'spoolbuddy' });
    expect(legacySettingsTabDefaultSubTab('apikeys')).toEqual({ integrationSubTab: 'api-metrics' });
    expect(legacySettingsTabDefaultSubTab('backup')).toEqual({ operationSubTab: 'backups' });
  });

  it('maps legacy tab ids to their documented default landing anchors', () => {
    expect(legacySettingsTabDefaultAnchor(null)).toBeUndefined();
    expect(legacySettingsTabDefaultAnchor('general')).toBeUndefined();
    expect(legacySettingsTabDefaultAnchor('users')).toBe('card-users');
    expect(legacySettingsTabDefaultAnchor('email')).toBe('card-smtp');
    expect(legacySettingsTabDefaultAnchor('apikeys')).toBe('card-createapi');
    expect(legacySettingsTabDefaultAnchor('queue')).toBe('card-print-options');
    expect(legacySettingsTabDefaultAnchor('virtual-printer')).toBe('card-vp');
    expect(legacySettingsTabDefaultAnchor('failure-detection')).toBe('card-fd-ml');
    expect(legacySettingsTabDefaultAnchor('filament')).toBe('card-filamentchecks');
    expect(legacySettingsTabDefaultAnchor('spoolbuddy')).toBe('card-spoolbuddy');
    expect(legacySettingsTabDefaultAnchor('plugs')).toBe('card-plugs');
    expect(legacySettingsTabDefaultAnchor('notifications')).toBe('card-providers');
    expect(legacySettingsTabDefaultAnchor('network')).toBe('card-externalurl');
    expect(legacySettingsTabDefaultAnchor('backup')).toBe('card-backup');
  });

  it('exposes the approved rail order and label keys', () => {
    expect(SETTINGS_NAV_ITEMS.map((item) => item.id)).toEqual([
      'general',
      'users-security',
      'printers-production',
      'projects-files',
      'warehouse-material',
      'orders-calculation',
      'integrations',
      'operations',
    ]);
    expect(settingsTabLabelKey('printers-production')).toBe('settings.tabs.printersProduction');
  });
});
