/**
 * Tests for the SettingsPage component.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../utils';
import { SettingsPage } from '../../pages/SettingsPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY, SIDEBAR_ORDER_KEY } from '../../utils/sidebarLayout';
import { setAuthToken } from '../../api/client';

const mockSettings = {
  auto_archive: true,
  save_thumbnails: true,
  capture_finish_photo: true,
  default_filament_cost: 25.0,
  currency: 'USD',
  ams_humidity_good: 40,
  ams_humidity_fair: 60,
  ams_temp_good: 30,
  ams_temp_fair: 35,
  time_format: 'system',
  date_format: 'system',
  mqtt_enabled: false,
  mqtt_host: '',
  mqtt_port: 1883,
  spoolman_enabled: false,
  spoolman_url: '',
  ha_enabled: false,
  ha_url: '',
  ha_token: '',
  check_updates: false,
  check_printer_firmware: false,
  bed_cooled_threshold: 35,
  ftp_retry_enabled: true,
  ftp_retry_count: 3,
  ftp_retry_delay: 2,
  ftp_timeout: 30,
};

const settingsSidebarChildIds = [
  'settings-general',
  'settings-users-security',
  'settings-printers-production',
  'settings-projects-files',
  'settings-warehouse-material',
  'settings-orders-calculation',
  'settings-integrations',
  'settings-operations',
];

async function clickSettingsSearchResult(query: string) {
  const user = userEvent.setup();
  const search = await screen.findByPlaceholderText('Search settings…');
  const searchContainer = search.closest('.relative');
  if (!searchContainer) {
    throw new Error('Expected settings search container');
  }
  await user.clear(search);
  await user.type(search, query);
  const [result] = await within(searchContainer).findAllByRole('button', { name: new RegExp(query, 'i') });
  await user.click(result);
}

type LegacyAliasLandingExpectation = {
  alias: string;
  anchorId: string;
  tabLabel: string;
  subTabLabel?: string;
};

function setSettingsTabUrl(tab: string, extraSearch = '') {
  const search = tab === 'general' ? extraSearch : `?tab=${tab}${extraSearch}`;
  window.history.replaceState({}, '', `/settings${search}`);
}

function navigateSettingsTab(tab: string, extraSearch = '') {
  const search = tab === 'general' ? extraSearch : `?tab=${tab}${extraSearch}`;
  window.history.pushState({}, '', `/settings${search}`);
  window.dispatchEvent(new Event('popstate'));
}

async function expectLegacyAliasLanding({
  alias,
  anchorId,
  subTabLabel,
}: LegacyAliasLandingExpectation) {
  const scrollSpy = vi.spyOn(Element.prototype, 'scrollIntoView');
  window.history.replaceState({}, '', `/settings?tab=${alias}`);

  render(<SettingsPage />);

  const anchor = await waitFor(() => {
    const element = document.getElementById(anchorId);
    expect(element).not.toBeNull();
    return element as HTMLElement;
  });

  await waitFor(() => {
    expect(scrollSpy).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
    expect(anchor).toHaveClass('ring-2', 'ring-bambu-green');
  });

  if (subTabLabel) {
    expect(await screen.findByRole('button', { name: subTabLabel })).toHaveClass('text-bambu-green');
  }

  scrollSpy.mockRestore();
}

describe('SettingsPage', () => {
  beforeEach(() => {
    // BrowserRouter shares window.location across tests; reset it so a tab
    // switch in one test (e.g. clicking "Printers & Production") doesn't carry into
    // sibling tests that expect to land on the default General tab.
    window.history.replaceState({}, '', '/');
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
    vi.mocked(localStorage.clear).mockReset();
    localStorage.clear();
    setAuthToken(null);
    Element.prototype.scrollIntoView = vi.fn();

    server.use(
      http.get('/api/v1/settings/', () => {
        return HttpResponse.json(mockSettings);
      }),
      http.put('/api/v1/settings/', async ({ request }) => {
        const body = await request.json();
        return HttpResponse.json({ ...mockSettings, ...body });
      }),
      http.get('/api/v1/printers/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/smart-plugs/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/notifications/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/api-keys/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/mqtt/status', () => {
        return HttpResponse.json({ enabled: false });
      }),
      http.get('/api/v1/virtual-printer/status', () => {
        return HttpResponse.json({ running: false });
      }),
      http.get('/api/v1/auth/status', () => {
        return HttpResponse.json({ auth_enabled: false, requires_setup: false });
      }),
      http.get('/api/v1/external-links/', () => {
        return HttpResponse.json([]);
      })
    );
  });

  describe('rendering', () => {
    it('defaults canonical order settings to the business profile subtab and loads real profiles', async () => {
      let requestCount = 0;
      server.use(
        http.get('/api/v1/business-profiles/', () => {
          requestCount += 1;
          return HttpResponse.json([
            {
              id: 7,
              name: 'Berlin Print Works',
              legal_name: 'Berlin Print Works GmbH',
              trading_name: null,
              country_code: 'DE',
              default_currency: 'EUR',
              timezone: 'Europe/Berlin',
              default_locale: 'de',
              billing_mode: 'hybrid',
              is_active: true,
              is_default: true,
              version: 1,
              created_at: '2026-07-01T10:00:00Z',
              updated_at: '2026-07-01T10:00:00Z',
              addresses: [],
              tax_identifiers: [],
              bank_accounts: [],
            },
          ]);
        }),
      );
      setSettingsTabUrl('orders-calculation');

      render(<SettingsPage />);

      expect(await screen.findByRole('button', { name: 'Business Profile' })).toHaveClass('text-bambu-green');
      expect((await screen.findAllByText('Berlin Print Works')).length).toBeGreaterThan(0);
      expect(screen.getByText('Default')).toBeInTheDocument();
      expect(requestCount).toBe(1);
    });

    it('opens the explicit business-profile settings URL', async () => {
      server.use(
        http.get('/api/v1/business-profiles/', () => HttpResponse.json([])),
      );
      setSettingsTabUrl('orders-calculation', '&sub=business-profile');

      render(<SettingsPage />);

      expect(await screen.findByRole('button', { name: 'Business Profile' })).toHaveClass('text-bambu-green');
      expect(document.getElementById('card-business-profile')).not.toBeNull();
      expect(document.getElementById('card-business-profile')?.parentElement).toHaveClass('w-full');
      expect(document.getElementById('card-business-profile')?.parentElement).not.toHaveClass('max-w-3xl');
      expect(document.getElementById('card-business-profile')).toHaveClass('rounded-xl', 'border', 'bg-bambu-dark-secondary');
      expect(window.location.search).toContain('sub=business-profile');
    });

    it('opens the document settings URL as its own order-management subtab', async () => {
      setSettingsTabUrl('orders-calculation', '&sub=documents');

      render(<SettingsPage />);

      expect(await screen.findByRole('button', { name: 'Documents' })).toHaveClass('text-bambu-green');
      expect(document.getElementById('card-document-settings')).not.toBeNull();
      expect(screen.getByRole('heading', { name: 'Document settings' })).toBeInTheDocument();
      expect(window.location.search).toContain('sub=documents');
    });

    it('renders the page title', async () => {
      render(<SettingsPage />);

      await waitFor(() => {
        // Use role-based query to avoid conflicts with dropdown options
        expect(screen.getByRole('heading', { name: 'General', level: 1 })).toBeInTheDocument();
        expect(screen.getByText('Manage language, appearance, default views, and personal UI preferences.')).toBeInTheDocument();
      });
    });

    it('uses the active users/security subpage as the page title', async () => {
      const user = userEvent.setup();
      setSettingsTabUrl('users-security');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Authentication', level: 1 })).toBeInTheDocument();
        expect(screen.getByText('Manage local users, groups, roles, sessions, and authentication state.')).toBeInTheDocument();
      });

      await user.click(await screen.findByRole('button', { name: 'Email Authentication' }));

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Email Authentication', level: 1 })).toBeInTheDocument();
        expect(screen.getByText('Configure SMTP delivery and email-based authentication workflows.')).toBeInTheDocument();
      });
    });

    it('uses the active printer/production subpage as the page title', async () => {
      setSettingsTabUrl('printers-production');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Devices', level: 1 })).toBeInTheDocument();
        expect(screen.getByText('Manage default printers, cameras, FTP retry behavior, and virtual printer endpoints.')).toBeInTheDocument();
      });

      navigateSettingsTab('printers-production', '&sub=pipelines');

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Pipelines', level: 1 })).toBeInTheDocument();
        expect(screen.getByText('Manage slicer pipelines, presets, and automated preparation flows.')).toBeInTheDocument();
      });
    });

    it('composes device settings in two desktop columns before the full-width virtual printers area', async () => {
      setSettingsTabUrl('printers-production');
      let updatedSettings: Record<string, unknown> | undefined;
      server.use(
        http.get('/api/v1/equipment/', () => HttpResponse.json([])),
        http.put('/api/v1/settings/', async ({ request }) => {
          updatedSettings = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({ ...mockSettings, ...updatedSettings });
        }),
      );

      render(<SettingsPage />);

      const grid = await screen.findByTestId('device-settings-grid');
      const left = within(grid).getByTestId('device-settings-left-column');
      const right = within(grid).getByTestId('device-settings-right-column');
      const virtualPrinters = document.getElementById('card-vp');

      expect(grid).toHaveClass('xl:grid-cols-2');
      expect(within(left).getByText('FTP Retry')).toBeInTheDocument();
      const ftpRetryGrid = within(left).getByTestId('ftp-retry-fields-grid');
      const ftpRetrySelects = within(ftpRetryGrid).getAllByRole('combobox');

      expect(ftpRetryGrid).toHaveClass('grid-cols-1', 'md:grid-cols-3');
      expect(ftpRetrySelects).toHaveLength(3);
      for (const select of ftpRetrySelects) {
        expect(select.parentElement).toHaveClass('w-full');
      }
      const retryAttempts = ftpRetrySelects[0];
      expect(retryAttempts).toHaveAttribute('aria-expanded', 'false');
      const user = userEvent.setup();
      await user.click(retryAttempts);
      await user.click(screen.getByRole('option', { name: '5 times' }));
      await waitFor(() => {
        expect(updatedSettings).toEqual(expect.objectContaining({ ftp_retry_count: 5 }));
      });
      expect(
        within(ftpRetryGrid).getByText('Increase for printers with weak WiFi'),
      ).toBeInTheDocument();
      expect(within(left).getByRole('heading', { name: 'Printers' })).toBeInTheDocument();
      expect(within(right).getAllByText('Default Printer').length).toBeGreaterThan(0);
      expect(within(right).getByRole('heading', { name: 'Dryers' })).toBeInTheDocument();
      expect(within(right).getByText('External Cameras')).toBeInTheDocument();
      expect(within(grid).getByTestId('device-layout-ftp')).toHaveClass('order-1');
      expect(within(grid).getByTestId('device-layout-default-printer')).toHaveClass('order-2');
      expect(within(grid).getByTestId('device-layout-printers')).toHaveClass('order-3');
      expect(within(grid).getByTestId('device-layout-dryers')).toHaveClass('order-4');
      expect(within(grid).getByTestId('device-layout-camera')).toHaveClass('order-5');
      expect(virtualPrinters).not.toBeNull();
      expect(
        grid.compareDocumentPosition(virtualPrinters as Node) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(grid.contains(virtualPrinters)).toBe(false);
    });

    it('uses the project management subpage as the page title', async () => {
      setSettingsTabUrl('projects-files');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'File Management', level: 1 })).toBeInTheDocument();
        expect(screen.getByText('Manage file handling, archive modes, disk warnings, and project storage rules.')).toBeInTheDocument();
      });
    });

    it('uses the active integration subpage as the page title', async () => {
      setSettingsTabUrl('integrations');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Notifications', level: 1 })).toBeInTheDocument();
      });
      expect(screen.queryByRole('heading', { name: 'Settings' })).not.toBeInTheDocument();
    });

    it('uses API & Metrics title and description for the active integration subpage', async () => {
      setSettingsTabUrl('integrations', '&sub=api-metrics');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'API & Metrics', level: 1 })).toBeInTheDocument();
        expect(screen.getByText('Manage API keys, camera tokens, Prometheus metrics, and the API browser.')).toBeInTheDocument();
      });
    });

    it('keeps canonical settings domains out of the page-level tab row', async () => {
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'General', level: 1 })).toBeInTheDocument();
      });

      expect(screen.queryByRole('button', { name: 'Users & Security' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Printers & Production' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Projects & Files' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Warehouse & Material' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Orders & Calculation' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Integrations' })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Operations' })).not.toBeInTheDocument();
    });

    it('opens Printers & Production from legacy queue tab URL', async () => {
      window.history.replaceState({}, '', '/settings?tab=queue');
      render(<SettingsPage />);

      expect(await screen.findByRole('button', { name: 'Print Process' })).toHaveClass('text-bambu-green');
      expect(await screen.findByText('Default Print Options')).toBeInTheDocument();
    });

    it('opens Warehouse & Material from legacy filament tab URL', async () => {
      window.history.replaceState({}, '', '/settings?tab=filament');
      render(<SettingsPage />);

      expect(await screen.findByText('Filament checks')).toBeInTheDocument();
    });

    it('opens Operations from legacy backup tab URL', async () => {
      window.history.replaceState({}, '', '/settings?tab=backup');
      render(<SettingsPage />);

      expect(await screen.findByRole('button', { name: 'Backups' })).toHaveClass('text-bambu-green');
      expect(await screen.findByText('Git Backup')).toBeInTheDocument();
    });

    it('opens Users & Security email settings from legacy email tab URL', async () => {
      window.history.replaceState({}, '', '/settings?tab=email');
      render(<SettingsPage />);

      expect(await screen.findByRole('button', { name: 'Email Authentication' })).toHaveClass('text-bambu-green');
      expect(await screen.findByText('SMTP Configuration')).toBeInTheDocument();
    });

    it.each([
      { alias: 'users', anchorId: 'card-users', tabLabel: 'Users & Security', subTabLabel: 'Authentication' },
      { alias: 'email', anchorId: 'card-smtp', tabLabel: 'Users & Security', subTabLabel: 'Email Authentication' },
      { alias: 'apikeys', anchorId: 'card-createapi', tabLabel: 'Integrations', subTabLabel: 'API & Metrics' },
      { alias: 'queue', anchorId: 'card-print-options', tabLabel: 'Printers & Production', subTabLabel: 'Print Process' },
      { alias: 'virtual-printer', anchorId: 'card-vp', tabLabel: 'Printers & Production', subTabLabel: 'Devices' },
      { alias: 'failure-detection', anchorId: 'card-fd-ml', tabLabel: 'Printers & Production', subTabLabel: 'Failure Detection' },
      { alias: 'filament', anchorId: 'card-filamentchecks', tabLabel: 'Warehouse & Material', subTabLabel: 'Filament' },
      { alias: 'spoolbuddy', anchorId: 'card-spoolbuddy', tabLabel: 'Warehouse & Material', subTabLabel: 'SpoolBuddy' },
      { alias: 'backup', anchorId: 'card-backup', tabLabel: 'Operations', subTabLabel: 'Backups' },
    ])('scrolls legacy %s URLs to their documented landing cards', async ({ alias, anchorId, tabLabel, subTabLabel }) => {
      await expectLegacyAliasLanding({ alias, anchorId, tabLabel, subTabLabel });
    });
  });

  describe('general settings', () => {
    it('shows date format setting', async () => {
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Date Format')).toBeInTheDocument();
      });
    });

    it('shows time format setting', async () => {
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Time Format')).toBeInTheDocument();
      });
    });

    it('keeps General focused on UI preferences and excludes orders or operations cards', async () => {
      render(<SettingsPage />);

      await waitFor(() => {
        const generalCard = document.getElementById('card-general');
        const appearanceCard = document.getElementById('card-appearance');
        const sidebarCard = document.getElementById('card-sidebar-links');
        const uiPreferencesCard = document.getElementById('card-ui-preferences');

        expect(generalCard).not.toBeNull();
        expect(appearanceCard).not.toBeNull();
        expect(sidebarCard).not.toBeNull();
        expect(uiPreferencesCard).not.toBeNull();
        expect(within(generalCard as HTMLElement).getByText('Language')).toBeInTheDocument();
        expect(within(generalCard as HTMLElement).getByText('Default View')).toBeInTheDocument();
        expect(within(generalCard as HTMLElement).getByText('Date Format')).toBeInTheDocument();
        expect(within(generalCard as HTMLElement).getByText('Time Format')).toBeInTheDocument();
        expect(within(uiPreferencesCard as HTMLElement).getAllByText('Reset UI Preferences').length).toBeGreaterThan(0);
        expect(screen.queryByText('Cost Tracking')).not.toBeInTheDocument();
        expect(screen.queryByText('Updates')).not.toBeInTheDocument();
        expect(screen.queryByText('Default Printer')).not.toBeInTheDocument();
      });
    });

    it('shows preferred slicer setting on Printers & Production', async () => {
      setSettingsTabUrl('printers-production', '&sub=print-process');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Preferred Slicer')).toBeInTheDocument();
      });
    });

    it('shows slicer dropdown with both options on Printers & Production', async () => {
      setSettingsTabUrl('printers-production', '&sub=print-process');
      render(<SettingsPage />);
      const user = userEvent.setup();

      const slicerSelect = await screen.findByRole('combobox', { name: 'Preferred Slicer' });
      expect(slicerSelect).toHaveTextContent('Bambu Studio');
      await user.click(slicerSelect);
      expect(screen.getByRole('option', { name: 'Bambu Studio' })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: 'OrcaSlicer' })).toBeInTheDocument();
    });

    it('shows File Manager on Projects & Files', async () => {
      setSettingsTabUrl('projects-files');
      render(<SettingsPage />);

      await waitFor(() => {
        const card = document.getElementById('card-filemanager');
        expect(screen.getByText('File Manager')).toBeInTheDocument();
        expect(card).not.toBeNull();
        expect(within(card as HTMLElement).getByText('Low Disk Space Warning')).toBeInTheDocument();
      });
    });

    it('opens the explicit legacy calculation settings URL', async () => {
      setSettingsTabUrl('orders-calculation', '&sub=calculation');
      render(<SettingsPage />);

      await waitFor(() => {
        const card = document.getElementById('card-cost');
        expect(screen.getByRole('button', { name: 'Calculation' })).toHaveClass('text-bambu-green');
        expect(screen.getByText('Cost Tracking')).toBeInTheDocument();
        expect(card).not.toBeNull();
        expect(within(card as HTMLElement).getByText('Currency')).toBeInTheDocument();
        expect(window.location.search).toContain('sub=calculation');
      });
    });

    it('does not show File Manager or Cost Tracking in General', async () => {
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Date Format')).toBeInTheDocument();
        expect(document.getElementById('card-filemanager')).toBeNull();
        expect(document.getElementById('card-cost')).toBeNull();
      });
    });

    it('shows device settings in Printers & Production by default', async () => {
      setSettingsTabUrl('printers-production');
      render(<SettingsPage />);

      await waitFor(() => {
        const defaultPrinterCard = document.getElementById('card-default-printer');
        const virtualPrinterCard = document.getElementById('card-vp');

        expect(defaultPrinterCard).not.toBeNull();
        expect(virtualPrinterCard).not.toBeNull();
        expect(document.getElementById('card-print-options')).toBeNull();
        expect(document.getElementById('card-archive')).toBeNull();
        expect(within(defaultPrinterCard as HTMLElement).getAllByText('Default Printer').length).toBeGreaterThan(0);
        expect(within(virtualPrinterCard as HTMLElement).getByText('Setup Required')).toBeInTheDocument();
      });
    });

    it('shows print-process settings in Printers & Production', async () => {
      setSettingsTabUrl('printers-production', '&sub=print-process');
      render(<SettingsPage />);

      await waitFor(() => {
        const printOptionsCard = document.getElementById('card-print-options');
        const archiveCard = document.getElementById('card-archive');

        expect(printOptionsCard).not.toBeNull();
        expect(archiveCard).not.toBeNull();
        expect(document.getElementById('card-default-printer')).toBeNull();
        expect(within(archiveCard as HTMLElement).getByText('Archive Settings')).toBeInTheDocument();
        expect(within(printOptionsCard as HTMLElement).getByText('Default Print Options')).toBeInTheDocument();
      });
    });

    it('shows Filament Checks in Warehouse & Material by default', async () => {
      setSettingsTabUrl('warehouse-material');
      render(<SettingsPage />);

      await waitFor(() => {
        const filamentChecksCard = document.getElementById('card-filamentchecks');

        expect(filamentChecksCard).not.toBeNull();
        expect(document.getElementById('card-spoolbuddy')).toBeNull();
        expect(within(filamentChecksCard as HTMLElement).getByText('Filament checks')).toBeInTheDocument();
      });
    });

    it('shows warehouse number sequences as a dedicated subpage before Filament', async () => {
      server.use(
        http.get('/api/v1/inventory/number-sequences', () => HttpResponse.json([])),
      );
      setSettingsTabUrl('warehouse-material', '&sub=number-sequences');
      render(<SettingsPage />);

      const numberSequencesTab = await screen.findByRole('button', { name: 'Number sequences' });
      const filamentTab = screen.getByRole('button', { name: 'Filament' });
      const tabButtons = screen.getAllByRole('button');

      expect(tabButtons.indexOf(numberSequencesTab)).toBeLessThan(tabButtons.indexOf(filamentTab));
      expect(numberSequencesTab).toHaveClass('text-bambu-green');
      expect(await screen.findByRole('heading', { name: 'Warehouse number sequences' })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Material number sequence' })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Spool number sequence' })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Purchase order number sequence' })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Goods receipt number sequence' })).toBeInTheDocument();
    });

    it('shows SpoolBuddy under its Warehouse & Material subpage', async () => {
      setSettingsTabUrl('warehouse-material', '&sub=spoolbuddy');
      render(<SettingsPage />);

      await waitFor(() => {
        const spoolBuddyCard = document.getElementById('card-spoolbuddy');

        expect(spoolBuddyCard).not.toBeNull();
        expect(screen.getByText('SpoolBuddy devices')).toBeInTheDocument();
      });
    });

    it('shows Operations subpages and defaults to Updates', async () => {
      const user = userEvent.setup();
      setSettingsTabUrl('operations');
      render(<SettingsPage />);

      await waitFor(() => {
        const updatesCard = document.getElementById('card-updates');

        expect(updatesCard).not.toBeNull();
        expect(within(updatesCard as HTMLElement).getByText('Updates')).toBeInTheDocument();
        expect(document.getElementById('card-data')).toBeNull();
        expect(document.getElementById('card-backup')).toBeNull();
      });

      await user.click(screen.getByRole('button', { name: 'Data Management' }));
      expect(await screen.findByText('Backup & Restore')).toBeInTheDocument();
      expect(window.location.search).toContain('sub=data-management');

      await user.click(screen.getByRole('button', { name: 'Backups' }));
      expect(await screen.findByText('Git Backup')).toBeInTheDocument();
      expect(window.location.search).toContain('sub=backups');
    });

    it('shows Bed Cooled Threshold under Printers & Production instead of Integrations', async () => {
      setSettingsTabUrl('integrations');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(document.getElementById('card-providers')).not.toBeNull();
      });
      expect(screen.queryByText('Bed Cooled Threshold')).not.toBeInTheDocument();

      navigateSettingsTab('printers-production', '&sub=print-process');
      const completionRulesCard = await waitFor(() => {
        const card = document.getElementById('card-completion-rules');
        expect(card).not.toBeNull();
        return card as HTMLElement;
      });
      expect(within(completionRulesCard as HTMLElement).getByText('Bed Cooled Threshold')).toBeInTheDocument();
    });

    it('loads storage usage only on the Operations data management subpage', async () => {
      let storageRequests = 0;
      server.use(
        http.get('/api/v1/system/storage-usage', () => {
          storageRequests += 1;
          return HttpResponse.json({
            total_bytes: 1024,
            total_formatted: '1 KB',
            scan_errors: 0,
            categories: [],
            other_breakdown: [],
          });
        }),
      );

      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Date Format')).toBeInTheDocument();
      });
      expect(storageRequests).toBe(0);

      navigateSettingsTab('operations');

      expect(await screen.findByText('Check printer firmware', {}, { timeout: 5000 })).toBeInTheDocument();
      expect(storageRequests).toBe(0);

      await userEvent.click(screen.getByRole('button', { name: 'Data Management' }));

      await waitFor(() => {
        expect(storageRequests).toBe(1);
        expect(screen.getByText('Storage Usage')).toBeInTheDocument();
      });
    });

    it('shows appearance section', async () => {
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Appearance')).toBeInTheDocument();
      });
    });

    it('shows updates section with firmware toggle', async () => {
      setSettingsTabUrl('operations');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Updates', level: 1 })).toBeInTheDocument();
        expect(screen.getByText('Check for updates')).toBeInTheDocument();
        expect(screen.getByText('Check printer firmware')).toBeInTheDocument();
      });
    });

    it('hides a PrintOps sidebar page from Sidebar', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      await screen.findByRole('heading', { name: 'Sidebar' });
      await screen.findAllByText(/Visible in sidebar/);

      vi.mocked(localStorage.setItem).mockClear();
      await user.click((await screen.findAllByLabelText('Hide page'))[0]);

      expect(localStorage.setItem).toHaveBeenCalledWith(SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY, JSON.stringify(['dashboard']));
      expect(screen.getByText(/Hidden from sidebar/)).toBeInTheDocument();
    });

    it('renders PrintOps Sidebar labels and child context instead of translation keys', async () => {
      render(<SettingsPage />);

      const heading = await screen.findByRole('heading', { name: 'Sidebar' });
      const card = heading.closest('#card-sidebar-links') as HTMLElement;
      expect(card).not.toBeNull();
      await within(card).findAllByText(/Visible in sidebar/);

      expect(within(card).getByText('Dashboard')).toBeInTheDocument();
      expect(within(card).getByText('Warehouse')).toBeInTheDocument();
      expect(within(card).getByText('Orders')).toBeInTheDocument();
      expect(within(card).queryByText('printops.nav.dashboard')).not.toBeInTheDocument();
      expect(within(card).queryByText('printops.nav.warehouse')).not.toBeInTheDocument();
      expect(within(card).getAllByText('Child page of Printers · Visible in sidebar').length).toBeGreaterThan(0);
    });

    it('searches Sidebar in Allgemein after canonical IA changes', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      const search = await screen.findByPlaceholderText('Search settings…');
      await user.type(search, 'Sidebar');

      expect((await screen.findAllByText('Sidebar')).length).toBeGreaterThan(0);
      expect(screen.getAllByText('General').length).toBeGreaterThan(0);
    });

    it('searches SpoolBuddy in Warehouse & Material', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      const search = await screen.findByPlaceholderText('Search settings…');
      await user.type(search, 'SpoolBuddy');

      expect((await screen.findAllByText('SpoolBuddy')).length).toBeGreaterThan(0);
      expect(screen.getAllByText('Warehouse & Material').length).toBeGreaterThan(0);
    });

    it('searches Virtual Printer in Printers & Production', async () => {
      const user = userEvent.setup();
      render(<SettingsPage />);

      const search = await screen.findByPlaceholderText('Search settings…');
      await user.type(search, 'Virtual Printer');

      expect((await screen.findAllByText('Virtual Printer')).length).toBeGreaterThan(0);
      expect(screen.getAllByText('Printers & Production').length).toBeGreaterThan(0);
    });

    it('opens the rendered SpoolBuddy pane from search results', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('SpoolBuddy');

      expect(await screen.findByText('SpoolBuddy devices')).toBeInTheDocument();
      expect(document.getElementById('card-spoolbuddy')).not.toBeNull();
    });

    it('opens the rendered Virtual Printer pane from search results', async () => {
      server.use(
        http.get('/api/v1/virtual-printers', () =>
          HttpResponse.json({ printers: [], models: {} }),
        ),
        http.get('/api/v1/virtual-printers/ca-certificate', () =>
          HttpResponse.json({
            pem: '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----',
            fingerprint_sha256: 'aa:bb',
            not_valid_after: '2030-01-01T00:00:00Z',
          }),
        ),
      );

      render(<SettingsPage />);

      await clickSettingsSearchResult('Virtual Printer');

      expect(await screen.findByText('Setup Required')).toBeInTheDocument();
      expect(document.getElementById('card-vp')).not.toBeNull();
    });

    it('opens the rendered Backup pane from search results', async () => {
      server.use(
        http.get('/api/v1/github-backup/config', () => HttpResponse.json(null)),
        http.get('/api/v1/github-backup/logs', () => HttpResponse.json([])),
        http.get('/api/v1/local-backup/status', () =>
          HttpResponse.json({
            enabled: false,
            schedule: 'daily',
            time: '03:00',
            retention: 5,
            path: '',
            default_path: '/backups',
            is_running: false,
            last_backup_at: null,
            last_status: null,
            last_message: null,
            next_run: null,
            timezone: 'UTC',
          }),
        ),
        http.get('/api/v1/local-backup/backups', () => HttpResponse.json([])),
      );

      render(<SettingsPage />);

      await clickSettingsSearchResult('Backup');

      expect(await screen.findByText('Git Backup')).toBeInTheDocument();
      expect(await screen.findByText('Scheduled Backups')).toBeInTheDocument();
      expect(window.location.search).toContain('sub=backups');
      expect(document.getElementById('card-backup')).not.toBeNull();
    });

    it('opens the rendered FTP Retry pane from search results', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('FTP Retry');

      const card = document.getElementById('card-ftpretry');
      expect(await screen.findByRole('button', { name: 'Devices' })).toHaveClass('text-bambu-green');
      expect(await screen.findByText('FTP Retry')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=printers-production');
      expect(card).not.toBeNull();
    });

    it('opens the rendered Prometheus pane from search results', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('Prometheus');

      const card = document.getElementById('card-prometheus');
      expect(await screen.findByText('Prometheus Metrics')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=integrations');
      expect(window.location.search).toContain('sub=api-metrics');
      expect(card).not.toBeNull();
    });

    it('opens the rendered Webhook pane from search results', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('Webhook');

      expect(await screen.findByText('Webhook Endpoints')).toBeInTheDocument();
      expect(await screen.findByText('/api/v1/webhook/status')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=integrations');
      expect(window.location.search).toContain('sub=webhooks');
      expect(document.getElementById('card-webhooks')).not.toBeNull();
    });

    it('opens the rendered API Browser pane from search results', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('API Browser');

      const card = document.getElementById('card-apibrowser');
      expect(await screen.findByText('API Browser')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=integrations');
      expect(window.location.search).toContain('sub=api-metrics');
      expect(card).not.toBeNull();
    });

    it('opens File Manager from search results on its canonical tab', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('File Manager');

      expect(await screen.findByText('File Manager')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=projects-files');
      expect(document.getElementById('card-filemanager')).not.toBeNull();
    });

    it('opens Cost Tracking from search results on its canonical tab', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('Cost Tracking');

      expect(await screen.findByText('Cost Tracking')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=orders-calculation');
      expect(document.getElementById('card-cost')).not.toBeNull();
    });

    it('opens Archive Settings from search results on its canonical tab', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('Archive Settings');

      expect(await screen.findByRole('button', { name: 'Print Process' })).toHaveClass('text-bambu-green');
      expect(await screen.findByText('Archive Settings')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=printers-production');
      expect(document.getElementById('card-archive')).not.toBeNull();
    });

    it('opens Camera from search results on its canonical tab', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('Camera');

      expect(await screen.findByRole('button', { name: 'Devices' })).toHaveClass('text-bambu-green');
      expect(await screen.findByText('External Cameras')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=printers-production');
      expect(document.getElementById('card-camera')).not.toBeNull();
    });

    it('opens Updates from search results on its canonical tab', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('Updates');

      expect(await screen.findByText('Check printer firmware')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=operations');
      expect(document.getElementById('card-updates')).not.toBeNull();
    });

    it('opens Data Management from search results on its canonical tab', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('Data Management');

      expect(await screen.findByText('Clear Notification Logs')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=operations');
      expect(window.location.search).toContain('sub=data-management');
      expect(document.getElementById('card-data')).not.toBeNull();
    });

    it('scrolls to backup when Go to Backup is clicked from Data Management', async () => {
      const user = userEvent.setup();
      setSettingsTabUrl('operations', '&sub=data-management');
      render(<SettingsPage />);

      const goToBackupButton = await screen.findByRole('button', { name: /go to backup/i });
      expect(document.getElementById('card-backup')).toBeNull();
      const scrollIntoViewSpy = vi
        .spyOn(HTMLElement.prototype, 'scrollIntoView')
        .mockImplementation(() => {});

      await user.click(goToBackupButton);

      await waitFor(() => {
        const backupCard = document.getElementById('card-backup');
        expect(backupCard).not.toBeNull();
        expect(scrollIntoViewSpy).toHaveBeenCalled();
        expect(scrollIntoViewSpy).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' });
        expect(backupCard).toHaveClass('ring-2', 'ring-bambu-green');
        expect(window.location.search).toContain('sub=backups');
      });
      scrollIntoViewSpy.mockRestore();
    });

    it('opens Drying from search results on its canonical tab', async () => {
      render(<SettingsPage />);

      await clickSettingsSearchResult('Drying');

      expect(await screen.findByText('Queue Auto-Drying')).toBeInTheDocument();
      expect(window.location.search).toContain('tab=warehouse-material');
      expect(document.getElementById('card-drying')).not.toBeNull();
    });

    it('shows a previously hidden PrintOps sidebar page from Sidebar', async () => {
      vi.mocked(localStorage.getItem).mockImplementation((key) => {
        if (key === SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY) return JSON.stringify(['printers']);
        return null;
      });

      const user = userEvent.setup();
      render(<SettingsPage />);

      await screen.findByRole('heading', { name: 'Sidebar' });
      await screen.findByText(/Hidden from sidebar/);

      vi.mocked(localStorage.setItem).mockClear();
      await user.click(await screen.findByLabelText('Show page'));

      expect(localStorage.setItem).toHaveBeenCalledWith(SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY, JSON.stringify([]));
      expect(screen.getAllByText(/Visible in sidebar/).length).toBeGreaterThan(0);
    });

    it('does not allow Settings to be hidden from Sidebar', async () => {
      render(<SettingsPage />);

      await screen.findByRole('heading', { name: 'Sidebar' });
      await screen.findByText(/Required in sidebar/);

      const settingsVisibilityButton = await screen.findByLabelText('Settings cannot be hidden');
      expect(settingsVisibilityButton).toBeDisabled();
      expect(screen.getByText(/Required in sidebar/)).toBeInTheDocument();
    });

    it('presents external links and PrintOps pages in saved sidebar order', async () => {
      vi.mocked(localStorage.getItem).mockImplementation((key) => {
        if (key === SIDEBAR_ORDER_KEY) return JSON.stringify(['ext-7', 'printers', 'settings']);
        return null;
      });
      server.use(
        http.get('/api/v1/external-links/', () =>
          HttpResponse.json([
            {
              id: 7,
              name: 'Docs',
              url: 'https://docs.example.test',
              icon: 'Link',
              open_in_new_tab: true,
              custom_icon: null,
              sort_order: 0,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          ]),
        ),
      );

      render(<SettingsPage />);

      await screen.findByRole('heading', { name: 'Sidebar' });
      const docs = await screen.findByText('Docs');
      const printers = screen.getAllByText('Printers').find(element => element.closest('[draggable="true"]'));

      expect(printers).toBeDefined();
      expect(docs.compareDocumentPosition(printers) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it('saves mixed Sidebar order when items are dragged', async () => {
      server.use(
        http.get('/api/v1/external-links/', () =>
          HttpResponse.json([
            {
              id: 7,
              name: 'Docs',
              url: 'https://docs.example.test',
              icon: 'Link',
              open_in_new_tab: true,
              custom_icon: null,
              sort_order: 0,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          ]),
        ),
      );

      render(<SettingsPage />);

      await screen.findByRole('heading', { name: 'Sidebar' });
      const docsRow = (await screen.findByText('Docs')).closest('[draggable="true"]');
      const printersRow = screen.getAllByText('Printers')
        .find(element => element.closest('[draggable="true"]'))
        ?.closest('[draggable="true"]');

      expect(docsRow).not.toBeNull();
      expect(printersRow).not.toBeNull();

      vi.mocked(localStorage.setItem).mockClear();
      const dataTransfer = {
        effectAllowed: '',
        dropEffect: '',
        setData: vi.fn(),
      };
      fireEvent.dragStart(docsRow!, { dataTransfer });
      fireEvent.dragOver(printersRow!, { dataTransfer });
      fireEvent.drop(printersRow!, { dataTransfer });

      expect(localStorage.setItem).toHaveBeenCalledWith(
        SIDEBAR_ORDER_KEY,
        JSON.stringify([
          'dashboard',
          'ext-7',
          'printers',
          'archives',
          'queue',
          'profiles',
          'maintenance',
          'projects',
          'files',
          'makerworld',
          'inventory',
          'warehouse-filament',
          'warehouse-parts',
          'warehouse-stock',
          'warehouse-suppliers',
          'orders',
          'orders-offers',
          'orders-calculation',
          'orders-customers',
          'orders-invoice',
          'notifications',
          'settings',
          ...settingsSidebarChildIds,
        ]),
      );
    });

    it('resets Sidebar to all pages first and configured links at the bottom', async () => {
      vi.mocked(localStorage.getItem).mockImplementation((key) => {
        if (key === SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY) return JSON.stringify(['printers', 'dashboard']);
        if (key === SIDEBAR_ORDER_KEY) return JSON.stringify(['ext-7', 'settings', 'printers']);
        return null;
      });
      server.use(
        http.get('/api/v1/external-links/', () =>
          HttpResponse.json([
            {
              id: 7,
              name: 'Docs',
              url: 'https://docs.example.test',
              icon: 'Link',
              open_in_new_tab: true,
              custom_icon: null,
              sort_order: 0,
              created_at: '2026-01-01T00:00:00Z',
              updated_at: '2026-01-01T00:00:00Z',
            },
          ]),
        ),
      );

      const user = userEvent.setup();
      render(<SettingsPage />);

      const heading = await screen.findByRole('heading', { name: 'Sidebar' });
      const card = heading.closest('#card-sidebar-links');
      expect(card).not.toBeNull();
      await screen.findByText('Docs');

      vi.mocked(localStorage.setItem).mockClear();
      await user.click(within(card as HTMLElement).getByRole('button', { name: /reset/i }));

      expect(localStorage.setItem).toHaveBeenCalledWith(SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY, JSON.stringify([]));
      expect(localStorage.setItem).toHaveBeenCalledWith(
        SIDEBAR_ORDER_KEY,
        JSON.stringify([
          'dashboard',
          'printers',
          'archives',
          'queue',
          'profiles',
          'maintenance',
          'projects',
          'files',
          'makerworld',
          'inventory',
          'warehouse-filament',
          'warehouse-parts',
          'warehouse-stock',
          'warehouse-suppliers',
          'orders',
          'orders-offers',
          'orders-calculation',
          'orders-customers',
          'orders-invoice',
          'notifications',
          'settings',
          ...settingsSidebarChildIds,
          'ext-7',
        ]),
      );

      const settingsRow = screen.getAllByText('Settings')
        .find(element => element.closest('[draggable="true"]'))
        ?.closest('[draggable="true"]');
      const docsRow = screen.getByText('Docs').closest('[draggable="true"]');
      expect(settingsRow).not.toBeNull();
      expect(docsRow).not.toBeNull();
      expect(settingsRow!.compareDocumentPosition(docsRow!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(screen.queryByText(/Hidden from sidebar/)).not.toBeInTheDocument();
    });

    it('sets the current Sidebar order as the backend default for settings admins', async () => {
      let defaultSidebarOrderPayload: string | null = null;
      vi.mocked(localStorage.getItem).mockImplementation((key) => {
        if (key === SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY) return JSON.stringify(['dashboard']);
        return null;
      });

      server.use(
        http.get('/api/v1/auth/status', () =>
          HttpResponse.json({ auth_enabled: true, requires_setup: false }),
        ),
        http.get('/api/v1/auth/me', () =>
          HttpResponse.json({
            id: 1,
            username: 'admin',
            role: 'admin',
            is_active: true,
            is_admin: false,
            groups: [{ id: 1, name: 'Administrators' }],
            permissions: ['settings:update'],
            created_at: '2026-01-01T00:00:00Z',
          }),
        ),
        http.get('/api/v1/settings/', () =>
          HttpResponse.json({ ...mockSettings, default_sidebar_order: '' }),
        ),
        http.put('/api/v1/settings/', async ({ request }) => {
          const body = await request.json() as { default_sidebar_order?: string };
          defaultSidebarOrderPayload = body.default_sidebar_order ?? null;
          return HttpResponse.json({ ...mockSettings, ...body });
        }),
      );
      setAuthToken('test-token');

      const user = userEvent.setup();
      render(<SettingsPage />);

      const heading = await screen.findByRole('heading', { name: 'Sidebar' });
      const card = heading.closest('#card-sidebar-links');
      expect(card).not.toBeNull();

      await user.click(within(card as HTMLElement).getByRole('switch', { name: 'Set Default' }));

      await waitFor(() => {
        expect(defaultSidebarOrderPayload).not.toBeNull();
      });
      expect(JSON.parse(defaultSidebarOrderPayload!)).toEqual({
        order: [
          'dashboard',
          'printers',
          'archives',
          'queue',
          'profiles',
          'maintenance',
          'projects',
          'files',
          'makerworld',
          'inventory',
          'warehouse-filament',
          'warehouse-parts',
          'warehouse-stock',
          'warehouse-suppliers',
          'orders',
          'orders-offers',
          'orders-calculation',
          'orders-customers',
          'orders-invoice',
          'notifications',
          'settings',
          ...settingsSidebarChildIds,
        ],
        hiddenSystemItemIds: ['dashboard'],
      });
    });
  });

  describe('update CTA per deployment shape', () => {
    // The update card branches on the deployment shape returned by
    // /updates/check. Each branch is mutually exclusive — verify the right
    // one wins so HA addon users never see the docker-compose snippet
    // (which they can't run from inside an HA addon container) and Docker
    // users never see the in-app Install button (which would no-op).
    const renderWithUpdateCheck = async (
      checkBody: Record<string, unknown>,
    ) => {
      server.use(
        http.get('/api/v1/settings/', () =>
          HttpResponse.json({ ...mockSettings, check_updates: true }),
        ),
        http.get('/api/v1/updates/check', () => HttpResponse.json(checkBody)),
      );
      setSettingsTabUrl('operations');
      render(<SettingsPage />);
      await waitFor(() => {
        expect(screen.getByRole('heading', { name: 'Updates', level: 1 })).toBeInTheDocument();
      });
    };

    it('shows the HA Supervisor message when running as an HA addon', async () => {
      await renderWithUpdateCheck({
        update_available: true,
        current_version: '0.2.4',
        latest_version: '0.2.5',
        release_name: '0.2.5',
        release_notes: '',
        release_url: 'https://example.invalid/r',
        published_at: '2099-01-01T00:00:00Z',
        is_docker: true,
        is_ha_addon: true,
        update_method: 'ha_addon',
      });

      await waitFor(() => {
        expect(
          screen.getByText(/Home Assistant Supervisor/i),
        ).toBeInTheDocument();
      }, { timeout: 5000 });
      // Docker hint must NOT render — HA branch wins.
      expect(screen.queryByText('docker compose pull && docker compose up -d')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /install update/i })).not.toBeInTheDocument();
    });

    it('shows the docker-compose snippet for Docker (non-HA) deployments', async () => {
      await renderWithUpdateCheck({
        update_available: true,
        current_version: '0.2.4',
        latest_version: '0.2.5',
        release_name: '0.2.5',
        release_notes: '',
        release_url: 'https://example.invalid/r',
        published_at: '2099-01-01T00:00:00Z',
        is_docker: true,
        is_ha_addon: false,
        update_method: 'docker',
      });

      await waitFor(() => {
        expect(screen.getByText('docker compose pull && docker compose up -d')).toBeInTheDocument();
      }, { timeout: 5000 });
      expect(screen.queryByText(/Home Assistant Supervisor/i)).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /install update/i })).not.toBeInTheDocument();
    });

    it('shows the installer-download link for Windows installer installs', async () => {
      const downloadUrl =
        'https://github.com/ichwars/PrintOps/releases/download/v0.2.5/printops-0.2.5-windows-x64-setup.exe';
      await renderWithUpdateCheck({
        update_available: true,
        current_version: '0.2.4',
        latest_version: '0.2.5',
        release_name: '0.2.5',
        release_notes: '',
        release_url: 'https://github.com/ichwars/PrintOps/releases/tag/v0.2.5',
        published_at: '2099-01-01T00:00:00Z',
        is_docker: false,
        is_ha_addon: false,
        is_windows_installer: true,
        update_method: 'windows_installer',
        installer_download_url: downloadUrl,
      });

      const link = await screen.findByRole('link', { name: /download installer for v0\.2\.5/i }, { timeout: 5000 });
      expect(link).toHaveAttribute('href', downloadUrl);
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
      // The in-app update button must NOT render — the git-fetch path can't
      // work from an installer payload.
      expect(screen.queryByRole('button', { name: /install update/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/Home Assistant Supervisor/i)).not.toBeInTheDocument();
      expect(screen.queryByText('docker compose pull && docker compose up -d')).not.toBeInTheDocument();
    });
  });

  describe('tabs navigation', () => {
    it('opens Integrations on Notifications by default', async () => {
      setSettingsTabUrl('integrations');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Notifications' })).toHaveClass('text-bambu-green');
        expect(screen.getByText('Add Provider')).toBeInTheDocument();
      });
    });

    it('can switch to Smart Home under Integrations', async () => {
      setSettingsTabUrl('integrations', '&sub=smart-home');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Smart Home' })).toHaveClass('text-bambu-green');
        expect(screen.getByText('MQTT Publishing')).toBeInTheDocument();
        expect(screen.getByText('Home Assistant')).toBeInTheDocument();
      });
    });

    it('can switch to Webhooks under Integrations', async () => {
      setSettingsTabUrl('integrations', '&sub=webhooks');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Webhooks' })).toHaveClass('text-bambu-green');
        expect(screen.getByText('Webhook Endpoints')).toBeInTheDocument();
      });
    });

    it('can switch to Smart Plugs under Integrations', async () => {
      setSettingsTabUrl('integrations', '&sub=smart-plugs');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Smart Plugs' })).toHaveClass('text-bambu-green');
        expect(screen.getByText('Add Smart Plug')).toBeInTheDocument();
      });
    });

    it('can switch to API & Metrics under Integrations', async () => {
      setSettingsTabUrl('integrations', '&sub=api-metrics');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'API & Metrics' })).toHaveClass('text-bambu-green');
        expect(screen.getByText('API Keys')).toBeInTheDocument();
        expect(screen.getByText('Camera API Tokens')).toBeInTheDocument();
        expect(screen.getByText('Prometheus Metrics')).toBeInTheDocument();
        expect(screen.getByText('API Browser')).toBeInTheDocument();
      });
    });

    it('can switch to Warehouse & Material', async () => {
      setSettingsTabUrl('warehouse-material');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('AMS Display Thresholds')).toBeInTheDocument();
      });
    });
  });

  describe('Printers & Production tab', () => {
    it('can switch to Printers & Production', async () => {
      setSettingsTabUrl('printers-production');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Devices' })).toHaveClass('text-bambu-green');
        expect(screen.getAllByText('Default Printer').length).toBeGreaterThan(0);
      });
    });

    it('shows stagger settings on Printers & Production', async () => {
      setSettingsTabUrl('printers-production', '&sub=print-process');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Staggered Start')).toBeInTheDocument();
        expect(screen.getByText('Group size')).toBeInTheDocument();
        expect(screen.getByText('Interval (minutes)')).toBeInTheDocument();
      });
    });

    it('shows auto-drying settings on Warehouse & Material', async () => {
      setSettingsTabUrl('warehouse-material');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Queue Auto-Drying')).toBeInTheDocument();
      });
    });

    it('shows per-filament humidity threshold editor on Warehouse & Material (#1605)', async () => {
      setSettingsTabUrl('warehouse-material');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Humidity Thresholds')).toBeInTheDocument();
        // Default row is unique to the humidity editor (drying presets has no
        // default row), so we can pin it without disambiguating from the
        // adjacent drying-presets table that also lists PLA/ASA/etc.
        expect(screen.getByText('Default (unknown types)')).toBeInTheDocument();
        // Filament rows render in both tables — assert by count instead of
        // a single getByText. 8 default filaments × 2 tables = 16 PLAs etc.
        expect(screen.getAllByText('PLA').length).toBeGreaterThanOrEqual(2);
        expect(screen.getAllByText('ASA').length).toBeGreaterThanOrEqual(2);
      });
    });

    it('shows default print options on Printers & Production', async () => {
      setSettingsTabUrl('printers-production', '&sub=print-process');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('Default Print Options')).toBeInTheDocument();
        expect(screen.getByText('Bed Levelling')).toBeInTheDocument();
        expect(screen.getByText('Flow Calibration')).toBeInTheDocument();
        expect(screen.getByText('Vibration Calibration')).toBeInTheDocument();
        expect(screen.getByText('First Layer Inspection')).toBeInTheDocument();
        expect(screen.getByText('Timelapse')).toBeInTheDocument();
      });
    });

    it('shows default print options description', async () => {
      setSettingsTabUrl('printers-production', '&sub=print-process');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText(/overridden per print in the print dialog/)).toBeInTheDocument();
      });
    });
  });

  describe('Users & Security tab', () => {
    it('can switch to Users & Security for API keys', async () => {
      setSettingsTabUrl('integrations', '&sub=api-metrics');
      render(<SettingsPage />);

      await waitFor(() => {
        // Button text is "Create Key"
        expect(screen.getByText('Create Key')).toBeInTheDocument();
      });
    });
  });

  describe('SpoolBuddy tab badge', () => {
    const baseDevice = {
      id: 1,
      device_id: 'sb-0001',
      hostname: 'sb-kitchen',
      ip_address: '10.0.0.1',
      backend_url: null,
      firmware_version: '1.0.0',
      has_nfc: true,
      has_scale: true,
      tare_offset: 0,
      calibration_factor: 1.0,
      nfc_reader_type: null,
      nfc_connection: null,
      display_brightness: 100,
      display_blank_timeout: 0,
      has_backlight: false,
      last_calibrated_at: null,
      last_seen: new Date().toISOString(),
      pending_command: null,
      nfc_ok: true,
      scale_ok: true,
      uptime_s: 100,
      update_status: null,
      update_message: null,
      system_stats: null,
      online: true,
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
    };

    it('opens SpoolBuddy settings from Warehouse & Material without the removed domain tab', async () => {
      server.use(
        http.get('/api/v1/spoolbuddy/devices', () => {
          return HttpResponse.json([
            { ...baseDevice, id: 1, device_id: 'sb-0001', hostname: 'sb-kitchen', online: true },
            { ...baseDevice, id: 2, device_id: 'sb-0002', hostname: 'sb-ghost', online: false },
          ]);
        })
      );
      setSettingsTabUrl('warehouse-material', '&sub=spoolbuddy');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('SpoolBuddy devices')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Warehouse & Material' })).not.toBeInTheDocument();
      });
    });
  });

  describe('API Keys tab — delete flow', () => {
    // Without setQueryData on success the deleted row stayed visible until a
    // manual reload — invalidateQueries didn't reliably trigger a UI swap on
    // every browser. Pin the synchronous-removal contract here.
    it('removes a deleted key from the list without a page reload', async () => {
      const initialKeys = [
        {
          id: 42,
          name: 'CI deploy key',
          key_prefix: 'bk_abcd1234',
          can_queue: true,
          can_control_printer: false,
          can_read_status: true,
          printer_ids: null,
          enabled: true,
          last_used: null,
          created_at: '2026-01-01T00:00:00Z',
          expires_at: null,
        },
      ];

      let deleteCallCount = 0;
      server.use(
        http.get('/api/v1/api-keys/', () => HttpResponse.json(initialKeys)),
        http.delete('/api/v1/api-keys/:id', ({ params }) => {
          deleteCallCount += 1;
          expect(params.id).toBe('42');
          return HttpResponse.json({ message: 'API key deleted' });
        })
      );

      const user = userEvent.setup();
      setSettingsTabUrl('integrations', '&sub=api-metrics');
      render(<SettingsPage />);

      // Key is listed
      await waitFor(() => {
        expect(screen.getByText('CI deploy key')).toBeInTheDocument();
      });

      // Click the trash button on the row
      const cards = screen.getByText('CI deploy key').closest('.flex.items-center.justify-between');
      expect(cards).not.toBeNull();
      const trashButton = cards!.querySelectorAll('button');
      await user.click(trashButton[trashButton.length - 1]);

      // Confirm the deletion in the modal
      const confirmButton = await screen.findByRole('button', { name: /delete/i });
      await user.click(confirmButton);

      // The deleted key disappears from the list immediately — no manual
      // reload required. setQueryData drops it before any refetch could fire.
      await waitFor(() => {
        expect(screen.queryByText('CI deploy key')).not.toBeInTheDocument();
      });

      expect(deleteCallCount).toBe(1);
    });
  });

  describe('API Keys tab — #1182 cloud access + ownership UI', () => {
    // The list now exposes two new bits of information per row:
    //   - "Cloud" badge when can_access_cloud=true
    //   - "Legacy" badge when user_id IS NULL (created before per-user ownership)
    // These tell the operator at a glance which keys can read /cloud/* data
    // and which keys need to be recreated to gain that capability.
    it('renders the Cloud badge for keys with can_access_cloud=true and the Legacy badge for ownerless keys', async () => {
      const keys = [
        {
          id: 1,
          name: 'cloud-reader',
          key_prefix: 'bk_cloud123',
          user_id: 7,
          can_queue: false,
          can_control_printer: false,
          can_read_status: true,
          can_access_cloud: true,
          printer_ids: null,
          enabled: true,
          last_used: null,
          created_at: '2026-04-30T00:00:00Z',
          expires_at: null,
        },
        {
          id: 2,
          name: 'legacy-key',
          key_prefix: 'bk_legacy01',
          user_id: null,
          can_queue: true,
          can_control_printer: false,
          can_read_status: true,
          can_access_cloud: false,
          printer_ids: null,
          enabled: true,
          last_used: null,
          created_at: '2025-01-01T00:00:00Z',
          expires_at: null,
        },
      ];

      server.use(http.get('/api/v1/api-keys/', () => HttpResponse.json(keys)));

      setSettingsTabUrl('integrations', '&sub=api-metrics');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('cloud-reader')).toBeInTheDocument();
        expect(screen.getByText('legacy-key')).toBeInTheDocument();
      });

      // Cloud-enabled key gets the Cloud badge but NOT the Legacy badge.
      const cloudRow = screen.getByText('cloud-reader').closest('.flex.items-center.justify-between');
      expect(cloudRow).not.toBeNull();
      expect(cloudRow!.textContent).toContain('Cloud');
      expect(cloudRow!.textContent).not.toContain('Legacy');

      // Ownerless key gets Legacy but NOT Cloud (can_access_cloud=false).
      const legacyRow = screen.getByText('legacy-key').closest('.flex.items-center.justify-between');
      expect(legacyRow).not.toBeNull();
      expect(legacyRow!.textContent).toContain('Legacy');
      // Strip the Cloud-flag check by limiting to badge area — the
      // "Allow cloud access" text from the create form isn't visible here.
      expect(legacyRow!.querySelector('.bg-purple-500\\/20')).toBeNull();
    });

    it('passes can_access_cloud through to the create call when the toggle is checked', async () => {
      let posted: { name?: string; can_access_cloud?: boolean } | null = null;

      server.use(
        http.get('/api/v1/api-keys/', () => HttpResponse.json([])),
        http.post('/api/v1/api-keys/', async ({ request }) => {
          posted = (await request.json()) as { name?: string; can_access_cloud?: boolean };
          return HttpResponse.json({
            id: 99,
            key: 'bk_returnedkey',
            name: posted.name,
            key_prefix: 'bk_returne',
            user_id: 1,
            can_queue: true,
            can_control_printer: false,
            can_read_status: true,
            can_access_cloud: posted.can_access_cloud ?? false,
            printer_ids: null,
            enabled: true,
            last_used: null,
            created_at: '2026-05-01T00:00:00Z',
            expires_at: null,
          });
        })
      );

      const user = userEvent.setup();
      setSettingsTabUrl('integrations', '&sub=api-metrics');
      render(<SettingsPage />);

      // Open the create form. With an empty key list the empty-state card
      // shows "Create Your First Key" — click that to open the form.
      const openButton = await screen.findByRole('button', { name: /Create Your First Key/i });
      await user.click(openButton);

      // Tick the new "Allow cloud access" checkbox. The label wraps the
      // input AND a sibling description div, so getByLabelText doesn't
      // resolve via implicit-label traversal — locate via text + closest
      // label, then grab the checkbox from the same scope.
      const cloudLabelText = await screen.findByText(/Allow cloud access/i);
      const cloudLabel = cloudLabelText.closest('label');
      expect(cloudLabel).not.toBeNull();
      const cloudCheckbox = cloudLabel!.querySelector('input[type="checkbox"]') as HTMLInputElement;
      expect(cloudCheckbox).not.toBeNull();
      await user.click(cloudCheckbox);

      // Submit. Two "Create Key" buttons exist once the form is open (header
      // CTA + form footer); the form-footer one is the actual submit and
      // calls the mutation — find it by walking up from the cloud checkbox
      // we just clicked, since both share the same form container.
      const submitButtons = screen.getAllByRole('button', { name: /^Create Key$/i });
      // Footer submit is the one inside the same form section as the
      // checkbox. The header CTA is in a separate flex row.
      const formSubmit = submitButtons.find(
        (b) => b.closest('div')?.contains(cloudCheckbox) || cloudLabel?.parentElement?.parentElement?.contains(b),
      );
      await user.click(formSubmit ?? submitButtons[submitButtons.length - 1]);

      await waitFor(() => {
        expect(posted).not.toBeNull();
        expect(posted!.can_access_cloud).toBe(true);
      });
    });
  });

  describe('API Keys tab — #1356 energy-cost write scope', () => {
    /**
     * The narrowly-scoped settings-write toggle. We pin two contracts here:
     *
     *   1. The "Energy" badge renders for keys that have can_update_energy_cost=true.
     *      Without a visible signal, an operator can't tell which key in their
     *      list is the one their HA automation depends on.
     *   2. The create form sends can_update_energy_cost=true to the backend
     *      when the toggle is checked. The whole point of #1356 is that the
     *      flag must actually be persisted — a UI that drops it silently
     *      would put us right back where the bug started.
     */
    it('renders the Energy badge for keys with can_update_energy_cost=true', async () => {
      const keys = [
        {
          id: 1,
          name: 'tariff-pusher',
          key_prefix: 'bk_tariff01',
          user_id: 7,
          can_queue: false,
          can_control_printer: false,
          can_read_status: true,
          can_access_cloud: false,
          can_update_energy_cost: true,
          printer_ids: null,
          enabled: true,
          last_used: null,
          created_at: '2026-05-15T00:00:00Z',
          expires_at: null,
        },
      ];

      server.use(http.get('/api/v1/api-keys/', () => HttpResponse.json(keys)));

      setSettingsTabUrl('integrations', '&sub=api-metrics');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText('tariff-pusher')).toBeInTheDocument();
      });

      const row = screen.getByText('tariff-pusher').closest('.flex.items-center.justify-between');
      expect(row).not.toBeNull();
      expect(row!.textContent).toContain('Energy');
    });

    it('passes can_update_energy_cost through to the create call when the toggle is checked', async () => {
      let posted: { name?: string; can_update_energy_cost?: boolean } | null = null;

      server.use(
        http.get('/api/v1/api-keys/', () => HttpResponse.json([])),
        http.post('/api/v1/api-keys/', async ({ request }) => {
          posted = (await request.json()) as { name?: string; can_update_energy_cost?: boolean };
          return HttpResponse.json({
            id: 99,
            key: 'bk_returnedkey',
            name: posted.name,
            key_prefix: 'bk_returne',
            user_id: 1,
            can_queue: true,
            can_control_printer: false,
            can_read_status: true,
            can_access_cloud: false,
            can_update_energy_cost: posted.can_update_energy_cost ?? false,
            printer_ids: null,
            enabled: true,
            last_used: null,
            created_at: '2026-05-15T00:00:00Z',
            expires_at: null,
          });
        })
      );

      const user = userEvent.setup();
      setSettingsTabUrl('integrations', '&sub=api-metrics');
      render(<SettingsPage />);

      const openButton = await screen.findByRole('button', { name: /Create Your First Key/i });
      await user.click(openButton);

      const energyLabelText = await screen.findByText(/Update electricity price/i);
      const energyLabel = energyLabelText.closest('label');
      expect(energyLabel).not.toBeNull();
      const energyCheckbox = energyLabel!.querySelector('input[type="checkbox"]') as HTMLInputElement;
      expect(energyCheckbox).not.toBeNull();
      await user.click(energyCheckbox);

      const submitButtons = screen.getAllByRole('button', { name: /^Create Key$/i });
      const formSubmit = submitButtons.find(
        (b) => b.closest('div')?.contains(energyCheckbox) || energyLabel?.parentElement?.parentElement?.contains(b),
      );
      await user.click(formSubmit ?? submitButtons[submitButtons.length - 1]);

      await waitFor(() => {
        expect(posted).not.toBeNull();
        expect(posted!.can_update_energy_cost).toBe(true);
      });
    });
  });

  describe('external camera snapshot URL override (#1177)', () => {
    /**
     * The snapshot URL input only appears for stream camera types where the
     * MJPEG warm-up problem can occur (mjpeg / rtsp / usb). Pure HTTP
     * snapshot sources don't need an override since their stream URL is
     * already a single-frame endpoint.
     */
    const mjpegPrinter = {
      id: 7,
      name: 'go2rtc Cam',
      serial_number: 'TEST123',
      ip_address: '192.168.1.100',
      access_code: 'XXXX',
      model: 'P1S',
      location: null,
      nozzle_count: 1,
      is_active: true,
      auto_archive: true,
      external_camera_url: 'http://192.168.1.61:1984/api/stream.mjpeg?src=printer',
      external_camera_type: 'mjpeg',
      external_camera_enabled: true,
      external_camera_snapshot_url: null,
      camera_rotation: 0,
      plate_detection_enabled: false,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    it('renders the snapshot URL input when camera_type is mjpeg', async () => {
      server.use(
        http.get('/api/v1/printers/', () => HttpResponse.json([mjpegPrinter])),
      );

      setSettingsTabUrl('printers-production');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/api\/frame\.jpeg\?src=printer/)).toBeInTheDocument();
      });
    });

    it('hides the snapshot URL input when camera_type is snapshot (already a single-frame source)', async () => {
      server.use(
        http.get('/api/v1/printers/', () =>
          HttpResponse.json([{ ...mjpegPrinter, external_camera_type: 'snapshot' }]),
        ),
      );

      setSettingsTabUrl('printers-production');
      render(<SettingsPage />);

      // Wait for the live-stream URL placeholder to render so we know the
      // camera section finished mounting before asserting absence of the
      // snapshot input below.
      await waitFor(() => {
        expect(screen.getByPlaceholderText(/Camera URL/i)).toBeInTheDocument();
      });
      expect(screen.queryByPlaceholderText(/api\/frame\.jpeg\?src=printer/)).not.toBeInTheDocument();
    });

    it(
      'PATCHes the printer with external_camera_snapshot_url when the user types into the input',
      async () => {
        const user = userEvent.setup();
        let receivedBody: Record<string, unknown> | null = null;
        server.use(
          http.get('/api/v1/printers/', () => HttpResponse.json([mjpegPrinter])),
          http.patch('/api/v1/printers/7', async ({ request }) => {
            receivedBody = (await request.json()) as Record<string, unknown>;
            return HttpResponse.json({ ...mjpegPrinter, ...receivedBody });
          }),
        );

        setSettingsTabUrl('printers-production');
        render(<SettingsPage />);

        const input = await waitFor(() =>
          screen.getByPlaceholderText(/api\/frame\.jpeg\?src=printer/),
        );
        await user.type(input, 'http://192.168.1.61:1984/api/frame.jpeg?src=printer');

        // Save is debounced by 800ms; assert the PATCH eventually fires with
        // the typed snapshot URL.
        await waitFor(
          () => {
            expect(receivedBody).not.toBeNull();
            expect(receivedBody!.external_camera_snapshot_url).toBe(
              'http://192.168.1.61:1984/api/frame.jpeg?src=printer',
            );
          },
          { timeout: 5000 },
        );
      },
      // Per-test timeout raised to 15s — `user.type()` of a 49-char URL plus
      // the 800ms save debounce fits in 5s locally (~2.3s typical) but blows
      // past it on slow GitHub Actions runners (5000ms timeout was the failure
      // mode on PR #1263).
      15_000,
    );
  });

  describe('theme mode buttons', () => {
    it('renders Dark, Light, and System buttons', async () => {
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Dark' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Light' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'System' })).toBeInTheDocument();
      });
    });

    it('highlights the active mode button with green border', async () => {
      render(<SettingsPage />);
      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'System' })).toBeInTheDocument();
      });

      await user.click(screen.getByRole('button', { name: 'System' }));

      await waitFor(() => {
        const systemBtn = screen.getByRole('button', { name: 'System' });
        expect(systemBtn.className).toContain('border-bambu-green');
      });
    });

    it('clicking a theme button switches mode', async () => {
      localStorage.setItem('theme-mode', 'dark');
      render(<SettingsPage />);
      const user = userEvent.setup();

      await waitFor(() => {
        const darkBtn = screen.getByRole('button', { name: 'Dark' });
        expect(darkBtn.className).toContain('border-bambu-green');
      });

      const lightBtn = screen.getByRole('button', { name: 'Light' });
      await user.click(lightBtn);

      await waitFor(() => {
        expect(lightBtn.className).toContain('border-bambu-green');
      });
    });

    it('shows a toast when theme button is clicked', async () => {
      render(<SettingsPage />);
      const user = userEvent.setup();

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'System' })).toBeInTheDocument();
      });

      await user.click(screen.getByRole('button', { name: 'System' }));

      await waitFor(() => {
        expect(screen.getByText('Settings saved')).toBeInTheDocument();
      });
    });
  });

  // --------------------------------------------------------------------
  // Slicer Pipelines (#1425) — Printers & Production sub-tabs
  // --------------------------------------------------------------------
  describe('workflow sub-tabs (#1425)', () => {
    beforeEach(() => {
      // Endpoints the Pipelines panel calls (#1425).
      server.use(
        http.get('/api/v1/slicer-pipelines/', () => HttpResponse.json({ pipelines: [] })),
        http.get('/api/v1/slicer/presets', () =>
          HttpResponse.json({
            orca_cloud: { printer: [], process: [], filament: [] },
            cloud: { printer: [], process: [], filament: [] },
            local: { printer: [], process: [], filament: [] },
            standard: { printer: [], process: [], filament: [] },
            cloud_status: 'ok',
            orca_cloud_status: 'ok',
          }),
        ),
      );
    });

    it('renders device-management sub-tabs under Printers & Production', async () => {
      setSettingsTabUrl('printers-production');
      render(<SettingsPage />);
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^Devices$/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Print Process/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /^Pipelines$/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /Failure Detection/i })).toBeInTheDocument();
      });
    });

    it('normalizes legacy queue Pipelines URLs to printers-production', async () => {
      const user = userEvent.setup();
      window.history.replaceState({}, '', '/settings?tab=queue');
      render(<SettingsPage />);

      await user.click(await screen.findByRole('button', { name: /^Pipelines$/i }));
      await waitFor(() => {
        expect(screen.getByText(/No pipelines yet/i)).toBeInTheDocument();
        expect(window.location.search).toContain('tab=printers-production');
        expect(window.location.search).toContain('sub=pipelines');
        expect(window.location.search).not.toContain('tab=queue');
      });
    });

    it('clicking Pipelines sub-tab shows the empty-state hint and updates the URL', async () => {
      setSettingsTabUrl('printers-production');
      render(<SettingsPage />);
      const user = userEvent.setup();
      await user.click(await screen.findByRole('button', { name: /^Pipelines$/i }));

      await waitFor(() => {
        expect(screen.getByText(/No pipelines yet/i)).toBeInTheDocument();
        // New clicks write the canonical tab id while preserving the queue sub-tab.
        expect(window.location.search).toContain('tab=printers-production');
        expect(window.location.search).toContain('sub=pipelines');
      });
    });

    it('loads Pipelines from the canonical printers-production URL', async () => {
      window.history.replaceState({}, '', '/settings?tab=printers-production&sub=pipelines');
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByText(/No pipelines yet/i)).toBeInTheDocument();
        expect(window.location.search).toContain('tab=printers-production');
        expect(window.location.search).toContain('sub=pipelines');
      });
    });

    it('clears stale pipelines substate when search jumps back to dispatch content', async () => {
      window.history.replaceState({}, '', '/settings?tab=printers-production&sub=pipelines');
      render(<SettingsPage />);

      await screen.findByText(/No pipelines yet/i);
      await clickSettingsSearchResult('FTP Retry');

      await waitFor(() => {
        expect(screen.getByText('FTP Retry')).toBeInTheDocument();
        expect(window.location.search).toContain('tab=printers-production');
        expect(window.location.search).not.toContain('sub=pipelines');
      });
    });
  });
});
