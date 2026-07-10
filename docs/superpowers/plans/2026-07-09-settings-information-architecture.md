# Settings Information Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the PrintOps Settings page into the approved domain-based structure while preserving legacy deep links, search jumps, permissions, and existing settings behaviour.

**Architecture:** Add a small navigation/alias layer, then teach Settings search and the Settings page to use canonical domain tabs. Keep the existing `SettingsPage.tsx` components in place for the first implementation pass, moving render blocks by domain without changing backend settings shape or permissions.

**Tech Stack:** React 19, TypeScript, React Router, TanStack Query, react-i18next, Vitest, Testing Library, Vite.

## Global Constraints

- Make `Allgemein` small and predictable.
- Put every setting in exactly one primary location.
- Align Settings with the PrintOps domains without duplicating the main app menu.
- Preserve old deep links such as `?tab=queue`, `?tab=users`, and `?tab=backup`.
- Keep cross-tab Settings search working for every moved card.
- Keep admin/security concerns visibly separate from production and operations.
- No backend settings schema changes.
- No permissions model changes.
- No redesign of individual card internals unless a move requires a heading or label update.
- No change to the main application navigation.
- No online deployment as part of this step.

---

## File Structure

- Create `frontend/src/lib/settingsNavigation.ts`.
  - Owns canonical Settings tab IDs, legacy aliases, labels, icon keys, and helpers for URL/search resolution.
- Create `frontend/src/__tests__/lib/settingsNavigation.test.ts`.
  - Unit-tests canonical tabs, aliases, and tab-to-URL conversion.
- Modify `frontend/src/lib/settingsSearch.ts`.
  - Allows search entries to target canonical Settings tabs.
- Modify `frontend/src/pages/SettingsPage.tsx`.
  - Uses navigation helpers for URL state, tab rail rendering, search jumps, and canonical content grouping.
- Modify `frontend/src/i18n/locales/en.ts`, `frontend/src/i18n/locales/de.ts`, `frontend/src/i18n/locales/es.ts`, `frontend/src/i18n/locales/fr.ts`, `frontend/src/i18n/locales/it.ts`, `frontend/src/i18n/locales/ja.ts`, `frontend/src/i18n/locales/ko.ts`, `frontend/src/i18n/locales/pt-BR.ts`, `frontend/src/i18n/locales/tr.ts`, `frontend/src/i18n/locales/zh-CN.ts`, and `frontend/src/i18n/locales/zh-TW.ts`.
  - Adds parity-safe `settings.tabs.*` labels for the canonical tab names.
- Modify `frontend/src/__tests__/pages/SettingsPage.test.tsx`.
  - Updates tab expectations, adds legacy URL alias coverage, and adds search jump coverage.

---

### Task 1: Add Canonical Settings Navigation Model

**Files:**
- Create: `frontend/src/lib/settingsNavigation.ts`
- Create: `frontend/src/__tests__/lib/settingsNavigation.test.ts`

**Interfaces:**
- Produces:
  - `type CanonicalSettingsTab`
  - `type LegacySettingsTab`
  - `type SettingsTab`
  - `SETTINGS_NAV_ITEMS`
  - `resolveSettingsTab(tabParam: string | null): CanonicalSettingsTab`
  - `canonicalTabToUrlParam(tab: CanonicalSettingsTab): string | null`
  - `settingsTabLabelKey(tab: CanonicalSettingsTab): string`
  - `legacySettingsTabDefaultSubTab(tabParam: string | null): { usersSubTab?: UsersSubTab; queueSubTab?: QueueSubTab }`
- Consumes: no project code beyond shared string literal types.

- [ ] **Step 1: Write the failing navigation tests**

Create `frontend/src/__tests__/lib/settingsNavigation.test.ts`:

```ts
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
```

- [ ] **Step 2: Run the failing tests**

Run:

```powershell
npm.cmd run test -- settingsNavigation.test.ts --run
```

Working directory: `frontend`

Expected: FAIL because `frontend/src/lib/settingsNavigation.ts` does not exist.

- [ ] **Step 3: Implement the navigation model**

Create `frontend/src/lib/settingsNavigation.ts`:

```ts
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
  { id: 'users-security', labelKey: 'settings.tabs.usersSecurity', fallback: 'Users & Security', icon: 'shield' },
  { id: 'printers-production', labelKey: 'settings.tabs.printersProduction', fallback: 'Printers & Production', icon: 'printer' },
  { id: 'projects-files', labelKey: 'settings.tabs.projectsFiles', fallback: 'Projects & Files', icon: 'fileText' },
  { id: 'warehouse-material', labelKey: 'settings.tabs.warehouseMaterial', fallback: 'Warehouse & Material', icon: 'warehouse' },
  { id: 'orders-calculation', labelKey: 'settings.tabs.ordersCalculation', fallback: 'Orders & Calculation', icon: 'calculator' },
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
  if (!tabParam) return 'general';
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

export function legacySettingsTabDefaultSubTab(tabParam: string | null): { usersSubTab?: UsersSubTab; queueSubTab?: QueueSubTab } {
  if (tabParam === 'email') return { usersSubTab: 'email' };
  if (tabParam === 'queue') return { queueSubTab: 'dispatch' };
  return {};
}
```

- [ ] **Step 4: Run tests to verify the model passes**

Run:

```powershell
npm.cmd run test -- settingsNavigation.test.ts --run
```

Working directory: `frontend`

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add frontend/src/lib/settingsNavigation.ts frontend/src/__tests__/lib/settingsNavigation.test.ts
git commit -m "feat: add settings navigation model"
```

---

### Task 2: Move Settings Search To Canonical Tabs

**Files:**
- Modify: `frontend/src/lib/settingsSearch.ts`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes:
  - `CanonicalSettingsTab` from `frontend/src/lib/settingsNavigation.ts`
  - `settingsTabLabelKey(tab: CanonicalSettingsTab): string`
- Produces:
  - Search entries with canonical `tab` values.
  - Search result subtitles that display canonical tab labels.

- [ ] **Step 1: Write failing search tests for moved entries**

Add these tests inside `describe('general settings', () => { ... })` in `frontend/src/__tests__/pages/SettingsPage.test.tsx`:

```tsx
    it('searches Sidebar in Allgemein after canonical IA changes', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      const search = await screen.findByPlaceholderText('Search settings...');
      await user.type(search, 'Sidebar');

      expect(await screen.findByText('Sidebar')).toBeInTheDocument();
      expect(screen.getByText('General')).toBeInTheDocument();
    });

    it('searches SpoolBuddy in Warehouse & Material', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      const search = await screen.findByPlaceholderText('Search settings...');
      await user.type(search, 'SpoolBuddy');

      expect(await screen.findByText('SpoolBuddy')).toBeInTheDocument();
      expect(screen.getByText('Warehouse & Material')).toBeInTheDocument();
    });

    it('searches Virtual Printer in Printers & Production', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      const search = await screen.findByPlaceholderText('Search settings...');
      await user.type(search, 'Virtual Printer');

      expect(await screen.findByText('Virtual Printer')).toBeInTheDocument();
      expect(screen.getByText('Printers & Production')).toBeInTheDocument();
    });
```

- [ ] **Step 2: Run the failing Settings page tests**

Run:

```powershell
npm.cmd run test -- SettingsPage.test.tsx --run
```

Working directory: `frontend`

Expected: FAIL because search still uses legacy tab subtitles.

- [ ] **Step 3: Update search types**

Replace `SettingsSearchTab` in `frontend/src/lib/settingsSearch.ts` with:

```ts
import type { CanonicalSettingsTab } from './settingsNavigation';

export type SettingsSearchTab = CanonicalSettingsTab;
```

Keep `SettingsSearchSubTab`, `UsersSubTab`, `SettingsSearchEntry`, `registerSettingsSearch`, and `getSettingsSearchEntries` unchanged.

- [ ] **Step 4: Update search registrations in `SettingsPage.tsx`**

Change the registrations so each `tab` uses its canonical target. The exact mapping is:

```ts
registerSettingsSearch({ labelKey: 'settings.general', tab: 'general', keywords: 'language date time format cards', anchor: 'card-general' });
registerSettingsSearch({ labelKey: 'settings.appearance', tab: 'general', keywords: 'theme dark light mode colors', anchor: 'card-appearance' });
registerSettingsSearch({ labelKey: 'externalLinks.sidebarLayout', labelFallback: 'Sidebar', tab: 'general', keywords: 'sidebar layout links pages hide show external custom navigation url add', anchor: 'card-sidebar-links' });

registerSettingsSearch({ labelKey: 'settings.currentUser', tab: 'users-security', subTab: 'users', keywords: 'current user profile password change', anchor: 'card-currentuser' });
registerSettingsSearch({ labelKey: 'settings.users', tab: 'users-security', subTab: 'users', keywords: 'users accounts list', anchor: 'card-users' });
registerSettingsSearch({ labelKey: 'settings.groups', tab: 'users-security', subTab: 'users', keywords: 'groups roles permissions administrators operators viewers', anchor: 'card-groups' });
registerSettingsSearch({ labelKey: 'settings.sessionPolicy.title', labelFallback: 'Session Policy', tab: 'users-security', subTab: 'users', keywords: 'session timeout expiry logout remember me jwt token lifetime', anchor: 'card-session-policy' });
registerSettingsSearch({ labelKey: 'settings.createNewApiKey', tab: 'users-security', keywords: 'api key create permission scope', anchor: 'card-createapi' });
registerSettingsSearch({ labelKey: 'cameraTokens.title', tab: 'users-security', keywords: 'camera token long-lived home assistant frigate kiosk stream', anchor: 'card-camera-tokens' });

registerSettingsSearch({ labelKey: 'settings.archiveSettings', tab: 'printers-production', keywords: 'archive auto save thumbnails captures', anchor: 'card-archive' });
registerSettingsSearch({ labelKey: 'settings.camera', tab: 'printers-production', keywords: 'camera external video stream', anchor: 'card-camera' });
registerSettingsSearch({ labelKey: 'settings.defaultPrintOptions', labelFallback: 'Default Print Options', tab: 'printers-production', keywords: 'print bed leveling flow calibration vibration first layer timelapse', anchor: 'card-print-options' });
registerSettingsSearch({ labelKey: 'settings.tabs.virtualPrinter', tab: 'printers-production', keywords: 'virtual printer proxy archive slicer bambustudio orcaslicer ip bind', anchor: 'card-vp' });
registerSettingsSearch({ labelKey: 'settings.tabs.failureDetection', labelFallback: 'Failure Detection', tab: 'printers-production', keywords: 'failure detection ai ml obico spaghetti detect monitoring', anchor: 'card-fd-ml' });

registerSettingsSearch({ labelKey: 'settings.fileManager', tab: 'projects-files', keywords: 'file manager archive mode disk warning storage', anchor: 'card-filemanager' });

registerSettingsSearch({ labelKey: 'settings.filamentChecks', tab: 'warehouse-material', keywords: 'filament check warning runout remaining', anchor: 'card-filamentchecks' });
registerSettingsSearch({ labelKey: 'settings.tabs.spoolbuddy', tab: 'warehouse-material', keywords: 'spoolbuddy device scale nfc rfid kiosk unregister', anchor: 'card-spoolbuddy' });
registerSettingsSearch({ labelKey: 'settings.filamentTracking', tab: 'warehouse-material', keywords: 'spoolman filament tracking inventory sync remote integration', anchor: 'card-spoolman' });

registerSettingsSearch({ labelKey: 'settings.costTracking', tab: 'orders-calculation', keywords: 'currency filament cost energy kwh price', anchor: 'card-cost' });

registerSettingsSearch({ labelKey: 'settings.smartPlugs', tab: 'integrations', keywords: 'smart plug energy power automation tapo kasa tplink shelly', anchor: 'card-plugs' });
registerSettingsSearch({ labelKey: 'settings.providers', tab: 'integrations', keywords: 'telegram discord email notification providers webhook', anchor: 'card-providers' });
registerSettingsSearch({ labelKey: 'settings.homeAssistant', tab: 'integrations', keywords: 'home assistant ha hass mqtt integration', anchor: 'card-ha' });

registerSettingsSearch({ labelKey: 'settings.updates', tab: 'operations', keywords: 'updates version firmware beta check', anchor: 'card-updates' });
registerSettingsSearch({ labelKey: 'settings.dataManagement', tab: 'operations', keywords: 'data reset clear logs notifications preferences storage', anchor: 'card-data' });
registerSettingsSearch({ labelKey: 'settings.tabs.backup', tab: 'operations', keywords: 'backup github restore download cloud sync profiles archives', anchor: 'card-backup' });
```

Keep all other existing registrations, but update their `tab` value using the mapping matrix in `docs/superpowers/specs/2026-07-09-settings-information-architecture-design.md`.

- [ ] **Step 5: Update search subtitle rendering**

Import `settingsTabLabelKey` and replace the legacy subtitle expression in `SettingsPage.tsx` with:

```tsx
<p className="text-xs text-bambu-gray">
  {t(settingsTabLabelKey(entry.tab), entry.tab)}
  {entry.subTab ? ` › ${t(`settings.tabs.${entry.subTab}`, entry.subTab)}` : ''}
</p>
```

- [ ] **Step 6: Run tests to verify search passes**

Run:

```powershell
npm.cmd run test -- SettingsPage.test.tsx --run
```

Working directory: `frontend`

Expected: PASS for the new search tests and existing Settings tests that are not intentionally updated in later tasks.

- [ ] **Step 7: Commit Task 2**

```powershell
git add frontend/src/lib/settingsSearch.ts frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/pages/SettingsPage.test.tsx
git commit -m "feat: route settings search to canonical domains"
```

---

### Task 3: Render Canonical Settings Rail And Preserve URL Aliases

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/i18n/locales/en.ts`
- Modify: `frontend/src/i18n/locales/de.ts`
- Modify: `frontend/src/i18n/locales/es.ts`
- Modify: `frontend/src/i18n/locales/fr.ts`
- Modify: `frontend/src/i18n/locales/it.ts`
- Modify: `frontend/src/i18n/locales/ja.ts`
- Modify: `frontend/src/i18n/locales/ko.ts`
- Modify: `frontend/src/i18n/locales/pt-BR.ts`
- Modify: `frontend/src/i18n/locales/tr.ts`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`
- Modify: `frontend/src/i18n/locales/zh-TW.ts`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes:
  - `SETTINGS_NAV_ITEMS`
  - `CanonicalSettingsTab`
  - `QueueSubTab`
  - `UsersSubTab`
  - `canonicalTabToUrlParam`
  - `legacySettingsTabDefaultSubTab`
  - `resolveSettingsTab`
- Produces:
  - `activeTab: CanonicalSettingsTab`
  - canonical URL params for new tab clicks
  - legacy URL params resolving silently to canonical tabs

- [ ] **Step 1: Update tab rendering tests**

Replace the existing `shows settings tabs` test with:

```tsx
    it('shows canonical settings tabs', async () => {
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getAllByText('General').length).toBeGreaterThan(0);
        expect(screen.getByText('Users & Security')).toBeInTheDocument();
        expect(screen.getByText('Printers & Production')).toBeInTheDocument();
        expect(screen.getByText('Projects & Files')).toBeInTheDocument();
        expect(screen.getByText('Warehouse & Material')).toBeInTheDocument();
        expect(screen.getByText('Orders & Calculation')).toBeInTheDocument();
        expect(screen.getByText('Integrations')).toBeInTheDocument();
        expect(screen.getByText('Operations')).toBeInTheDocument();
      });
    });
```

Add legacy URL tests:

```tsx
    it('opens Printers & Production from legacy queue tab URL', async () => {
      window.history.replaceState({}, '', '/settings?tab=queue');
      render(<SettingsPage />);

      expect(await screen.findByText('Printers & Production')).toHaveClass('text-bambu-green');
    });

    it('opens Warehouse & Material from legacy filament tab URL', async () => {
      window.history.replaceState({}, '', '/settings?tab=filament');
      render(<SettingsPage />);

      expect(await screen.findByText('Warehouse & Material')).toHaveClass('text-bambu-green');
    });

    it('opens Operations from legacy backup tab URL', async () => {
      window.history.replaceState({}, '', '/settings?tab=backup');
      render(<SettingsPage />);

      expect(await screen.findByText('Operations')).toHaveClass('text-bambu-green');
    });

    it('opens Users & Security email settings from legacy email tab URL', async () => {
      window.history.replaceState({}, '', '/settings?tab=email');
      render(<SettingsPage />);

      expect(await screen.findByText('Users & Security')).toHaveClass('text-bambu-green');
      expect(await screen.findByText('Email Authentication')).toHaveClass('text-bambu-green');
    });
```

- [ ] **Step 2: Run failing Settings page tests**

Run:

```powershell
npm.cmd run test -- SettingsPage.test.tsx --run
```

Working directory: `frontend`

Expected: FAIL because canonical rail labels are not rendered yet.

- [ ] **Step 3: Update `SettingsPage.tsx` imports and state**

Add imports:

```ts
import {
  SETTINGS_NAV_ITEMS,
  canonicalTabToUrlParam,
  legacySettingsTabDefaultSubTab,
  resolveSettingsTab,
  type CanonicalSettingsTab,
  type QueueSubTab,
  type UsersSubTab,
} from '../lib/settingsNavigation';
```

Remove the local `validTabs` and `TabType` declarations.

Replace initial tab/sub-tab setup with:

```ts
  const tabParam = searchParams.get('tab');
  const initialTab = resolveSettingsTab(tabParam);
  const legacySubTabs = legacySettingsTabDefaultSubTab(tabParam);
  const [activeTab, setActiveTab] = useState<CanonicalSettingsTab>(initialTab);
  const [usersSubTab, setUsersSubTab] = useState<UsersSubTab>(legacySubTabs.usersSubTab ?? 'users');
  const initialQueueSub: QueueSubTab =
    tabParam === 'queue' && searchParams.get('sub') === 'pipelines'
      ? 'pipelines'
      : legacySubTabs.queueSubTab ?? 'dispatch';
  const [queueSubTab, setQueueSubTab] = useState<QueueSubTab>(initialQueueSub);
```

Replace `handleTabChange` with:

```ts
  const handleTabChange = (tab: CanonicalSettingsTab) => {
    setActiveTab(tab);
    if (tab !== 'users-security') {
      setUsersSubTab('users');
    }
    if (tab !== 'printers-production') {
      setQueueSubTab('dispatch');
      searchParams.delete('sub');
    }

    const urlTab = canonicalTabToUrlParam(tab);
    if (urlTab) {
      searchParams.set('tab', urlTab);
    } else {
      searchParams.delete('tab');
    }
    setSearchParams(searchParams, { replace: true });
  };
```

Update `handleQueueSubTabChange` signature to:

```ts
  const handleQueueSubTabChange = (sub: QueueSubTab) => {
```

- [ ] **Step 4: Replace hardcoded rail buttons**

Create an icon map inside `SettingsPage.tsx` near the render block:

```tsx
  const settingsNavIcons = {
    settings: SettingsIcon,
    shield: Shield,
    printer: Printer,
    fileText: FileText,
    warehouse: Home,
    calculator: DollarSign,
    plug: Plug,
    database: Database,
  } as const;
```

Replace the current hardcoded `<nav>` button list with:

```tsx
      <nav className="flex flex-wrap gap-1 border-b border-bambu-dark-tertiary lg:flex-col lg:flex-nowrap lg:gap-0 lg:border-b-0 lg:border-r lg:w-56 lg:flex-shrink-0 lg:self-start lg:sticky lg:top-4">
        {SETTINGS_NAV_ITEMS.map((item) => {
          const Icon = settingsNavIcons[item.icon];
          return (
            <button
              key={item.id}
              onClick={() => handleTabChange(item.id)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px lg:border-b-0 lg:border-l-2 lg:-ml-px lg:mb-0 lg:justify-start flex items-center gap-2 ${
                activeTab === item.id
                  ? 'text-bambu-green border-bambu-green'
                  : 'text-bambu-gray hover:text-gray-900 dark:hover:text-white border-transparent'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t(item.labelKey, item.fallback)}
            </button>
          );
        })}
      </nav>
```

- [ ] **Step 5: Add locale labels**

Add these keys under `settings.tabs` in `frontend/src/i18n/locales/en.ts`:

```ts
      usersSecurity: 'Users & Security',
      printersProduction: 'Printers & Production',
      projectsFiles: 'Projects & Files',
      warehouseMaterial: 'Warehouse & Material',
      ordersCalculation: 'Orders & Calculation',
      integrations: 'Integrations',
      operations: 'Operations',
```

Add these keys under `settings.tabs` in `frontend/src/i18n/locales/de.ts`:

```ts
      usersSecurity: 'Benutzer & Sicherheit',
      printersProduction: 'Drucker & Produktion',
      projectsFiles: 'Projekte & Dateien',
      warehouseMaterial: 'Lager & Material',
      ordersCalculation: 'Aufträge & Kalkulation',
      integrations: 'Integrationen',
      operations: 'Betrieb',
```

Add translated equivalents for the same seven keys to every other locale file listed in this task. The parity script requires identical leaf key sets across all locale files.

- [ ] **Step 6: Run tests and i18n parity**

Run:

```powershell
npm.cmd run test -- SettingsPage.test.tsx settingsNavigation.test.ts --run
npm.cmd run check:i18n
```

Working directory: `frontend`

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

```powershell
git add frontend/src/pages/SettingsPage.tsx frontend/src/i18n/locales frontend/src/__tests__/pages/SettingsPage.test.tsx
git commit -m "feat: render canonical settings navigation"
```

---

### Task 4: Move Settings Content Into Approved Domains

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes:
  - canonical `activeTab`
  - existing card anchors such as `card-sidebar-links`, `card-vp`, and `card-backup`
- Produces:
  - domain-rendered Settings content where each card appears once.

- [ ] **Step 1: Add domain content tests**

Add tests to `frontend/src/__tests__/pages/SettingsPage.test.tsx`:

```tsx
    it('keeps Allgemein focused on basic preferences and sidebar', async () => {
      render(<SettingsPage />);

      expect(await screen.findByText('General')).toBeInTheDocument();
      expect(await screen.findByRole('heading', { name: 'Appearance' })).toBeInTheDocument();
      expect(await screen.findByRole('heading', { name: 'Sidebar' })).toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Cost Tracking' })).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Updates' })).not.toBeInTheDocument();
    });

    it('shows production settings in Printers & Production', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      await user.click(await screen.findByText('Printers & Production'));

      expect(await screen.findByRole('heading', { name: 'Archive Settings' })).toBeInTheDocument();
      expect(await screen.findByRole('heading', { name: 'Default Print Options' })).toBeInTheDocument();
      expect(await screen.findByText('Virtual Printer')).toBeInTheDocument();
    });

    it('shows material settings in Warehouse & Material', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      await user.click(await screen.findByText('Warehouse & Material'));

      expect(await screen.findByRole('heading', { name: 'Filament Checks' })).toBeInTheDocument();
      expect(await screen.findByText('SpoolBuddy')).toBeInTheDocument();
    });

    it('shows backup settings in Operations', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      await user.click(await screen.findByText('Operations'));

      expect(await screen.findByText('Backup')).toBeInTheDocument();
      expect(await screen.findByRole('heading', { name: 'Updates' })).toBeInTheDocument();
    });
```

- [ ] **Step 2: Run failing content tests**

Run:

```powershell
npm.cmd run test -- SettingsPage.test.tsx --run
```

Working directory: `frontend`

Expected: FAIL because content is still grouped by legacy tabs.

- [ ] **Step 3: Update top-level content conditions**

In `SettingsPage.tsx`, replace legacy conditions using this canonical mapping:

```tsx
{activeTab === 'general' && (
  <>
    {/* card-general without default printer */}
    {/* card-appearance */}
    {/* card-sidebar-links */}
    {/* reset UI preferences portion split from card-data */}
  </>
)}

{activeTab === 'users-security' && (
  <>
    {/* users sub-tab navigation */}
    {/* API keys cards: card-createapi, card-camera-tokens */}
  </>
)}

{activeTab === 'printers-production' && (
  <>
    {/* default printer moved from card-general */}
    {/* card-archive */}
    {/* card-camera */}
    {/* card-ftpretry */}
    {/* card-print-options */}
    {/* card-plate */}
    {/* card-temp-fan-presets */}
    {/* card-staggered */}
    {/* card-preheat */}
    {/* card-gcode */}
    {/* card-pipelines */}
    {/* card-slicer */}
    {/* card-vp */}
    {/* card-failure-detection */}
  </>
)}

{activeTab === 'projects-files' && (
  <>
    {/* card-filemanager */}
  </>
)}

{activeTab === 'warehouse-material' && (
  <>
    {/* card-drying */}
    {/* card-filamentchecks */}
    {/* card-printmodal */}
    {/* card-amsthresholds */}
    {/* card-spoolman */}
    {/* card-spool-catalog */}
    {/* card-color-catalog */}
    {/* card-spoolbuddy */}
  </>
)}

{activeTab === 'orders-calculation' && (
  <>
    {/* card-cost */}
  </>
)}

{activeTab === 'integrations' && (
  <>
    {/* card-plugs */}
    {/* card-providers */}
    {/* card-templates */}
    {/* card-externalurl */}
    {/* card-ha */}
    {/* card-mqtt */}
    {/* card-webhooks */}
    {/* card-apibrowser */}
  </>
)}

{activeTab === 'operations' && (
  <>
    {/* storage/log portions of card-data */}
    {/* card-updates */}
    {/* card-prometheus */}
    {/* card-backup */}
  </>
)}
```

When moving JSX, keep the existing card IDs unchanged so search anchors and tests remain stable.

- [ ] **Step 4: Split mixed cards**

Split `card-general` into:

```tsx
<Card id="card-general">
  {/* language, default view, date format, time format */}
</Card>
```

Move the existing default-printer select into a new card in `printers-production`:

```tsx
<Card id="card-default-printer">
  <CardHeader>
    <h2 className="text-lg font-semibold text-white flex items-center gap-2">
      <Printer className="w-5 h-5 text-bambu-green" />
      {t('settings.defaultPrinter')}
    </h2>
  </CardHeader>
  <CardContent>
    {/* move the existing default printer select here unchanged */}
  </CardContent>
</Card>
```

Split `card-data` into:

```tsx
<Card id="card-ui-preferences">
  <CardHeader>
    <h2 className="text-lg font-semibold text-white">{t('settings.uiPreferences', 'UI Preferences')}</h2>
  </CardHeader>
  <CardContent>
    {/* move reset UI preferences here */}
  </CardContent>
</Card>
```

and:

```tsx
<Card id="card-data">
  <CardHeader>
    <h2 className="text-lg font-semibold text-white">{t('settings.dataManagement')}</h2>
  </CardHeader>
  <CardContent>
    {/* keep clear notification logs, storage usage, and backup/restore controls here */}
  </CardContent>
</Card>
```

- [ ] **Step 5: Ensure conditional queries still run in the correct tabs**

Update query `enabled` guards:

```ts
enabled: activeTab === 'integrations' && !!smartPlugs && smartPlugs.length > 0,
enabled: activeTab === 'operations',
```

Use `activeTab === 'integrations'` for Smart Plug energy data and `activeTab === 'operations'` for storage usage.

- [ ] **Step 6: Run content tests**

Run:

```powershell
npm.cmd run test -- SettingsPage.test.tsx --run
```

Working directory: `frontend`

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```powershell
git add frontend/src/pages/SettingsPage.tsx frontend/src/__tests__/pages/SettingsPage.test.tsx
git commit -m "feat: group settings by PrintOps domains"
```

---

### Task 5: Final Verification And Local Review Prep

**Files:**
- Modify: `frontend/src/__tests__/pages/SettingsPage.test.tsx`

**Interfaces:**
- Consumes:
  - completed canonical Settings UI
- Produces:
  - verified local build/test state
  - clear browser review instructions for the user

- [ ] **Step 1: Run targeted Settings tests**

Run:

```powershell
npm.cmd run test -- SettingsPage.test.tsx settingsNavigation.test.ts --run
```

Working directory: `frontend`

Expected: PASS.

- [ ] **Step 2: Run i18n parity**

Run:

```powershell
npm.cmd run check:i18n
```

Working directory: `frontend`

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run:

```powershell
npm.cmd run build
```

Working directory: `frontend`

Expected: PASS with Vite production build artifacts generated.

- [ ] **Step 4: Start or refresh the local server**

Use the already running local PrintOps server at `http://127.0.0.1:8000/settings`. Refresh the browser after `npm.cmd run build` completes. If the browser still shows stale assets, stop implementation and report that the local server needs a restart before visual review.

Expected: `http://127.0.0.1:8000/settings` loads the canonical Settings rail.

- [ ] **Step 5: Manual browser smoke check**

In the local browser, verify:

```text
/settings opens Allgemein.
/settings?tab=queue opens Drucker & Produktion.
/settings?tab=filament opens Lager & Material.
/settings?tab=backup opens Betrieb.
/settings?tab=email opens Benutzer & Sicherheit and selects Email Authentication.
Search "Sidebar" shows Allgemein.
Search "SpoolBuddy" shows Lager & Material.
Search "Backup" shows Betrieb.
Search "Virtual Printer" shows Drucker & Produktion.
```

- [ ] **Step 6: Commit verification fixes**

If tests or smoke checks require small fixes, commit them:

```powershell
git add frontend/src/pages/SettingsPage.tsx frontend/src/lib/settingsNavigation.ts frontend/src/lib/settingsSearch.ts frontend/src/i18n/locales frontend/src/__tests__/pages/SettingsPage.test.tsx frontend/src/__tests__/lib/settingsNavigation.test.ts
git commit -m "test: verify settings information architecture"
```

Skip this commit only if Task 5 produces no file changes.

---

## Self-Review

- Spec coverage: every approved canonical tab, legacy alias, search requirement, i18n requirement, and local verification step is covered by a task.
- Placeholder scan: the plan contains no open placeholder tokens and no undefined task target.
- Type consistency: `CanonicalSettingsTab`, `UsersSubTab`, and `QueueSubTab` are defined in Task 1 and consumed by later tasks with the same names.
- Scope check: this remains one implementation unit because it changes one Settings page, one navigation helper, one search registry, locale labels, and Settings-focused tests.
