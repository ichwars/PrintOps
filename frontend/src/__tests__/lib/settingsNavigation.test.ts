import { describe, expect, it } from 'vitest';
import {
  SETTINGS_NAV_ITEMS,
  canonicalTabToUrlParam,
  legacySettingsTabDefaultSubTab,
  resolveSettingsTab,
  settingsTabLabelKey,
} from '../../lib/settingsNavigation';

describe('settingsNavigation', () => {
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
    expect(resolveSettingsTab('apikeys')).toBe('users-security');
    expect(resolveSettingsTab('users')).toBe('users-security');
    expect(resolveSettingsTab('backup')).toBe('operations');
  });

  it('keeps legacy email and queue sub-tab intent', () => {
    expect(legacySettingsTabDefaultSubTab('email')).toEqual({ usersSubTab: 'email' });
    expect(legacySettingsTabDefaultSubTab('queue')).toEqual({ queueSubTab: 'dispatch' });
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
