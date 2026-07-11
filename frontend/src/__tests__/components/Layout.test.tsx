/**
 * Tests for the Layout component.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fireEvent, waitFor } from '@testing-library/react';
import { render } from '../utils';
import { Layout } from '../../components/Layout';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY, SIDEBAR_ORDER_KEY } from '../../utils/sidebarLayout';
import { setAuthToken } from '../../api/client';

const sidebarLink = (href: string) =>
  document.querySelector(`aside a[href="${href}"]`);

const sidebarMenuButton = (id: string) =>
  document.querySelector(`aside button[aria-controls="sidebar-submenu-${id}"]`) as HTMLButtonElement | null;

function expandSidebarMenu(id: string) {
  const button = sidebarMenuButton(id);
  expect(button).toBeInTheDocument();
  if (button?.getAttribute('aria-expanded') === 'false') {
    fireEvent.click(button);
  }
  return button;
}

describe('Layout', () => {
  beforeEach(() => {
    window.history.replaceState({}, '', '/');
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
    vi.mocked(localStorage.clear).mockReset();
    localStorage.clear();
    setAuthToken(null);
    server.use(
      http.get('/api/v1/printers/', () => {
        return HttpResponse.json([
          { id: 1, name: 'X1 Carbon', model: 'X1C', enabled: true },
        ]);
      }),
      http.get('/api/v1/printers/:id/status', () => {
        return HttpResponse.json({
          connected: true,
          state: 'IDLE',
        });
      }),
      http.get('/api/v1/version', () => {
        return HttpResponse.json({ version: '0.1.6', build: 'test' });
      }),
      http.get('/api/v1/settings/', () => {
        return HttpResponse.json({
          check_updates: false,
          check_printer_firmware: false,
          auto_archive: true,
        });
      }),
      http.get('/api/v1/external-links/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/smart-plugs/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/support/debug-logging', () => {
        return HttpResponse.json({ enabled: false });
      }),
      http.get('/api/v1/queue/', () => {
        return HttpResponse.json([]);
      }),
      http.get('/api/v1/pending-uploads/count', () => {
        return HttpResponse.json({ count: 0 });
      }),
      http.get('/api/v1/updates/check', () => {
        return HttpResponse.json({ update_available: false });
      }),
      http.get('/api/v1/auth/status', () => {
        return HttpResponse.json({ auth_enabled: false, requires_setup: false });
      }),
      http.get('/api/v1/printers/developer-mode-warnings', () => {
        return HttpResponse.json([]);
      })
    );
  });

  describe('rendering', () => {
    it('renders the sidebar', async () => {
      render(<Layout />);

      // Layout renders as a flex container with sidebar
      await waitFor(() => {
        const sidebar = document.querySelector('aside');
        expect(sidebar).toBeInTheDocument();
      });
    });

    it('renders navigation links', async () => {
      render(<Layout />);

      await waitFor(() => {
        // Navigation links should be present
        const links = document.querySelectorAll('a');
        expect(links.length).toBeGreaterThan(0);
      });
    });
  });

  describe('navigation', () => {
    it('has navigation items', async () => {
      render(<Layout />);

      await waitFor(() => {
        // Should have multiple navigation links
        const navLinks = document.querySelectorAll('a[href]');
        expect(navLinks.length).toBeGreaterThan(0);
      });
    });

    it('includes settings link', async () => {
      render(<Layout />);

      await waitFor(() => {
        // Settings link should exist (route /settings)
        const settingsLink = document.querySelector('a[href="/settings"]');
        expect(settingsLink).toBeInTheDocument();
      });
    });

    it('hides system nav items stored in sidebar layout preferences', async () => {
      vi.mocked(localStorage.getItem).mockImplementation((key) => {
        if (key === SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY) return JSON.stringify(['printers']);
        return null;
      });

      render(<Layout />);

      await waitFor(() => {
        const sidebar = document.querySelector('aside');
        expect(sidebar).toBeInTheDocument();
        expect(sidebarMenuButton('inventory')).toBeInTheDocument();
      });

      expandSidebarMenu('inventory');
      expect(sidebarLink('/warehouse')).toBeInTheDocument();
      expect(sidebarLink('/printers')).toBeNull();
      expect(sidebarMenuButton('printers')).toBeNull();
    });

    it('applies admin default sidebar hidden state with the default order', async () => {
      const storage: Record<string, string> = {};
      vi.mocked(localStorage.getItem).mockImplementation((key) => storage[key] ?? null);
      vi.mocked(localStorage.setItem).mockImplementation((key, value) => {
        storage[key] = value;
      });
      server.use(
        http.get('/api/v1/settings/default-sidebar-order', () =>
          HttpResponse.json({
            default_sidebar_order: JSON.stringify({
              order: ['inventory', 'printers', 'settings'],
              hiddenSystemItemIds: ['printers'],
            }),
          }),
        ),
      );

      render(<Layout />);

      await waitFor(() => {
        const sidebar = document.querySelector('aside');
        expect(sidebar).toBeInTheDocument();
        expect(sidebarMenuButton('inventory')).toBeInTheDocument();
      });

      expandSidebarMenu('inventory');
      expect(sidebarLink('/warehouse')).toBeInTheDocument();

      await waitFor(() => {
        expect(sidebarLink('/printers')).toBeNull();
        expect(sidebarMenuButton('printers')).toBeNull();
        expect(localStorage.setItem).toHaveBeenCalledWith(SIDEBAR_ORDER_KEY, JSON.stringify(['inventory', 'printers', 'settings']));
        expect(localStorage.setItem).toHaveBeenCalledWith(SIDEBAR_HIDDEN_SYSTEM_ITEMS_KEY, JSON.stringify(['printers']));
      });
    });

    it('keeps grouped nav submenus collapsed until their main item is clicked', async () => {
      render(<Layout />);

      await waitFor(() => {
        expect(sidebarMenuButton('printers')).toBeInTheDocument();
        expect(sidebarMenuButton('printers')).toHaveAttribute('aria-expanded', 'false');
        expect(sidebarMenuButton('projects')).toHaveAttribute('aria-expanded', 'false');
      });

      expect(sidebarLink('/queue')).toBeNull();

      fireEvent.click(sidebarMenuButton('printers')!);

      await waitFor(() => {
        expect(sidebarMenuButton('printers')).toHaveAttribute('aria-expanded', 'true');
        expect(sidebarLink('/queue')).toBeInTheDocument();
      });

      fireEvent.click(sidebarMenuButton('projects')!);

      await waitFor(() => {
        expect(sidebarMenuButton('printers')).toHaveAttribute('aria-expanded', 'false');
        expect(sidebarMenuButton('projects')).toHaveAttribute('aria-expanded', 'true');
        expect(sidebarLink('/queue')).toBeNull();
        expect(sidebarLink('/files')).toBeInTheDocument();
      });

      fireEvent.click(sidebarMenuButton('printers')!);

      await waitFor(() => {
        expect(sidebarMenuButton('printers')).toHaveAttribute('aria-expanded', 'true');
        expect(sidebarMenuButton('projects')).toHaveAttribute('aria-expanded', 'false');
        expect(sidebarLink('/queue')).toBeInTheDocument();
        expect(sidebarLink('/files')).toBeNull();
      });

      fireEvent.click(sidebarMenuButton('printers')!);

      await waitFor(() => {
        expect(sidebarMenuButton('printers')).toHaveAttribute('aria-expanded', 'false');
        expect(sidebarLink('/queue')).toBeNull();
      });
    });

    it('shows settings domains as Settings submenu links', async () => {
      window.history.replaceState({}, '', '/settings?tab=integrations');
      render(<Layout />);

      await waitFor(() => {
        expect(sidebarMenuButton('settings')).toHaveAttribute('aria-expanded', 'true');
        expect(sidebarLink('/settings')).toBeInTheDocument();
        expect(sidebarLink('/settings')).not.toHaveClass('bg-bambu-green');
        expect(sidebarLink('/settings?tab=users-security')).toBeInTheDocument();
        expect(sidebarLink('/settings?tab=printers-production')).toBeInTheDocument();
        expect(sidebarLink('/settings?tab=projects-files')).toBeInTheDocument();
        expect(sidebarLink('/settings?tab=warehouse-material')).toBeInTheDocument();
        expect(sidebarLink('/settings?tab=orders-calculation')).toBeInTheDocument();
        expect(sidebarLink('/settings?tab=integrations')).toHaveClass('bg-bambu-green');
        expect(sidebarLink('/settings?tab=operations')).toBeInTheDocument();
      });
    });
  });

  describe('version display', () => {
    it('shows version info', async () => {
      render(<Layout />);

      await waitFor(() => {
        // Version info is displayed in sidebar
        expect(document.body).toBeInTheDocument();
      });
    });
  });

  describe('theme toggle', () => {
    it('has theme toggle button', async () => {
      render(<Layout />);

      await waitFor(() => {
        // Theme toggle should be present
        const buttons = document.querySelectorAll('button');
        expect(buttons.length).toBeGreaterThan(0);
      });
    });

    it('cycles through dark → light → system → dark', async () => {
      localStorage.setItem('theme-mode', 'dark');
      render(<Layout />);

      await waitFor(() => {
        // In dark mode, title should say "Switch to light mode"
        const btn = document.querySelector('button[title="Switch to light mode"]');
        expect(btn).toBeInTheDocument();
      });

      // Click to go from dark → light
      const lightBtn = document.querySelector('button[title="Switch to light mode"]')!;
      lightBtn.click();

      await waitFor(() => {
        // In light mode, title should say "Switch to system mode"
        const btn = document.querySelector('button[title="Switch to system mode"]');
        expect(btn).toBeInTheDocument();
      });

      // Click to go from light → system
      const systemBtn = document.querySelector('button[title="Switch to system mode"]')!;
      systemBtn.click();

      await waitFor(() => {
        // In system mode, title should say "Switch to dark mode"
        const btn = document.querySelector('button[title="Switch to dark mode"]');
        expect(btn).toBeInTheDocument();
      });

      // Click to go from system → dark
      const darkBtn = document.querySelector('button[title="Switch to dark mode"]')!;
      darkBtn.click();

      await waitFor(() => {
        // Back to dark mode
        const btn = document.querySelector('button[title="Switch to light mode"]');
        expect(btn).toBeInTheDocument();
      });
    });
  });

  describe('plate detection alert modal', () => {
    it('shows modal when plate-not-empty event is dispatched', async () => {
      render(<Layout />);

      // Dispatch the plate-not-empty event
      window.dispatchEvent(
        new CustomEvent('plate-not-empty', {
          detail: {
            printer_id: 1,
            printer_name: 'Test Printer',
            message: 'Objects detected on build plate',
          },
        })
      );

      await waitFor(() => {
        // Modal should appear with "Print Paused!" text
        expect(document.body.textContent).toContain('Print Paused!');
        expect(document.body.textContent).toContain('Test Printer');
      });
    });

    it('closes modal when I Understand button is clicked', async () => {
      render(<Layout />);

      // Dispatch the plate-not-empty event
      window.dispatchEvent(
        new CustomEvent('plate-not-empty', {
          detail: {
            printer_id: 1,
            printer_name: 'Test Printer',
            message: 'Objects detected on build plate',
          },
        })
      );

      await waitFor(() => {
        expect(document.body.textContent).toContain('Print Paused!');
      });

      // Click the "I Understand" button
      const button = document.querySelector('button');
      if (button && button.textContent?.includes('I Understand')) {
        button.click();
      }

      // Find and click the "I Understand" button by searching all buttons
      const buttons = document.querySelectorAll('button');
      buttons.forEach((btn) => {
        if (btn.textContent?.includes('I Understand')) {
          btn.click();
        }
      });

      await waitFor(() => {
        // Modal should be closed
        expect(document.body.textContent).not.toContain('Print Paused!');
      });
    });
  });

  describe('developer mode warning banner', () => {
    it('shows warning banner when printers lack developer mode', async () => {
      server.use(
        http.get('/api/v1/printers/developer-mode-warnings', () => {
          return HttpResponse.json([
            { printer_id: 1, name: 'X1 Carbon' },
          ]);
        })
      );

      render(<Layout />);

      await waitFor(() => {
        expect(document.body.textContent).toContain('Developer LAN mode is not enabled on');
        expect(document.body.textContent).toContain('X1 Carbon');
      });
    });

    it('shows multiple printer names in warning banner', async () => {
      server.use(
        http.get('/api/v1/printers/developer-mode-warnings', () => {
          return HttpResponse.json([
            { printer_id: 1, name: 'X1 Carbon' },
            { printer_id: 2, name: 'P1S' },
          ]);
        })
      );

      render(<Layout />);

      await waitFor(() => {
        expect(document.body.textContent).toContain('X1 Carbon');
        expect(document.body.textContent).toContain('P1S');
      });
    });

    it('hides warning banner when no printers lack developer mode', async () => {
      // Default handler returns empty array
      render(<Layout />);

      await waitFor(() => {
        const sidebar = document.querySelector('aside');
        expect(sidebar).toBeInTheDocument();
      });

      // Banner should not be present
      expect(document.body.textContent).not.toContain('Developer LAN mode is not enabled on');
    });

    it('shows how to enable link in warning banner', async () => {
      server.use(
        http.get('/api/v1/printers/developer-mode-warnings', () => {
          return HttpResponse.json([
            { printer_id: 1, name: 'X1 Carbon' },
          ]);
        })
      );

      render(<Layout />);

      await waitFor(() => {
        expect(document.body.textContent).toContain('How to enable');
        const link = document.querySelector('a[href*="enable-developer-mode"]');
        expect(link).toBeInTheDocument();
      });
    });
  });

  describe('update banner suppression for HA addon', () => {
    // HA Supervisor surfaces its own update notification natively in the HA
    // UI, so the in-app banner would be duplicate noise that links to a page
    // that just says "update via HA". Suppress it for HA addon deployments.
    it('hides the update-available banner when running as an HA addon', async () => {
      server.use(
        http.get('/api/v1/updates/check', () => {
          return HttpResponse.json({
            update_available: true,
            current_version: '0.2.4',
            latest_version: '0.2.5',
            is_docker: true,
            is_ha_addon: true,
            update_method: 'ha_addon',
          });
        }),
      );

      render(<Layout />);

      await waitFor(() => {
        const sidebar = document.querySelector('aside');
        expect(sidebar).toBeInTheDocument();
      });

      expect(document.body.textContent).not.toContain('Update available');
    });

    it('still shows the update-available banner for plain Docker deployments', async () => {
      server.use(
        http.get('/api/v1/updates/check', () => {
          return HttpResponse.json({
            update_available: true,
            current_version: '0.2.4',
            latest_version: '0.2.5',
            is_docker: true,
            is_ha_addon: false,
            update_method: 'docker',
          });
        }),
      );

      render(<Layout />);

      await waitFor(() => {
        expect(document.body.textContent).toContain('0.2.5');
      });
    });
  });

  describe('MakerWorld sidebar permission gate (#1175)', () => {
    // The MakerWorld sidebar entry was visible to every authenticated user
    // regardless of group permissions because Layout's `navPermissions` map
    // had no entry for `makerworld`. Backend routes already gated on
    // `makerworld:view`, so users without the permission saw the entry,
    // clicked, and got 403'd by every API call inside the page. The fix
    // adds `makerworld: 'makerworld:view'` to the map so the entry is
    // hidden when the permission is absent — same shape as every other
    // sidebar entry.
    const enableAuthWithUser = (permissions: string[]) => {
      server.use(
        http.get('/api/v1/auth/status', () =>
          HttpResponse.json({ auth_enabled: true, requires_setup: false }),
        ),
        http.get('/api/v1/auth/me', () =>
          HttpResponse.json({
            id: 1,
            username: 'tester',
            role: 'user',
            is_active: true,
            is_admin: false,
            groups: [{ id: 2, name: 'Standard Users' }],
            permissions,
            created_at: '2026-01-01T00:00:00Z',
          }),
        ),
      );
      // AuthProvider needs a token to fetch /auth/me; the value isn't
      // validated by the mocked server.
      setAuthToken('test-token');
    };

    const findMakerWorldNavLink = () => {
      // Sidebar nav links use react-router's `to` prop, which renders as a
      // plain `<a href="/makerworld">`. Match on the href so the test isn't
      // coupled to whatever locale string is rendered.
      return document.querySelector('aside a[href="/makerworld"]');
    };

    it('hides the MakerWorld nav entry when the user lacks makerworld:view', async () => {
      // Standard user without the MakerWorld permission. Projects is granted
      // only so the grouped Projects menu can be expanded; the gate remains
      // per-entry and MakerWorld must not render.
      enableAuthWithUser(['projects:read', 'library:read', 'archives:read', 'queue:read']);

      render(<Layout />);

      await waitFor(() => {
        // Wait for the auth resolution + sidebar render. Some other nav
        // entry confirms the sidebar finished mounting.
        const sidebar = document.querySelector('aside');
        expect(sidebar).toBeInTheDocument();
        expect(sidebarMenuButton('projects')).toBeInTheDocument();
      });

      expandSidebarMenu('projects');
      expect(sidebarLink('/files')).toBeInTheDocument();
      expect(findMakerWorldNavLink()).toBeNull();
    });

    it('shows the MakerWorld nav entry when the user has makerworld:view', async () => {
      enableAuthWithUser([
        'projects:read',
        'library:read',
        'archives:read',
        'queue:read',
        'makerworld:view',
      ]);

      render(<Layout />);

      await waitFor(() => {
        expect(sidebarMenuButton('projects')).toBeInTheDocument();
      });

      expandSidebarMenu('projects');

      await waitFor(() => {
        expect(findMakerWorldNavLink()).toBeInTheDocument();
      });
    });
  });

  describe('Sidebar gate accepts granular read tiers (#1755)', () => {
    // Default Operators group is seeded with `*:read_own` only — never the
    // legacy `*:read`. Previously the sidebar gate checked the legacy alone,
    // so Archives / Queue / Files were hidden from every non-admin even
    // though the underlying API endpoints accepted their requests. These
    // tests pin that the gate accepts ANY of the three tiers (legacy /
    // _own / _all) for the three resources that ship granular variants.
    const enableAuthWithUser = (permissions: string[]) => {
      server.use(
        http.get('/api/v1/auth/status', () =>
          HttpResponse.json({ auth_enabled: true, requires_setup: false }),
        ),
        http.get('/api/v1/auth/me', () =>
          HttpResponse.json({
            id: 1,
            username: 'tester',
            role: 'user',
            is_active: true,
            is_admin: false,
            groups: [{ id: 2, name: 'Operators' }],
            permissions,
            created_at: '2026-01-01T00:00:00Z',
          }),
        ),
      );
      setAuthToken('test-token');
    };

    it('shows Files in the sidebar when the user only has library:read_own', async () => {
      enableAuthWithUser(['projects:read', 'library:read_own']);

      render(<Layout />);

      await waitFor(() => {
        expect(document.querySelector('aside')).toBeInTheDocument();
        expect(sidebarMenuButton('projects')).toBeInTheDocument();
      });

      expandSidebarMenu('projects');

      await waitFor(() => {
        expect(sidebarLink('/files')).toBeInTheDocument();
      });
    });

    it('shows Files in the sidebar when the user only has library:read_all', async () => {
      enableAuthWithUser(['projects:read', 'library:read_all']);

      render(<Layout />);

      await waitFor(() => {
        expect(sidebarMenuButton('projects')).toBeInTheDocument();
      });

      expandSidebarMenu('projects');

      await waitFor(() => {
        expect(sidebarLink('/files')).toBeInTheDocument();
      });
    });

    it('shows Archives in the sidebar when the user only has archives:read_own', async () => {
      enableAuthWithUser(['archives:read_own']);

      render(<Layout />);

      await waitFor(() => {
        expect(sidebarMenuButton('printers')).toBeInTheDocument();
      });

      expandSidebarMenu('printers');

      await waitFor(() => {
        expect(sidebarLink('/archives')).toBeInTheDocument();
      });
    });

    it('shows Queue in the sidebar when the user only has queue:read_own', async () => {
      enableAuthWithUser(['queue:read_own']);

      render(<Layout />);

      await waitFor(() => {
        expect(sidebarMenuButton('printers')).toBeInTheDocument();
      });

      expandSidebarMenu('printers');

      await waitFor(() => {
        expect(sidebarLink('/queue')).toBeInTheDocument();
      });
    });

    it('still hides Files when the user has none of the three read tiers', async () => {
      enableAuthWithUser(['printers:read']);

      render(<Layout />);

      await waitFor(() => {
        expect(document.querySelector('aside')).toBeInTheDocument();
      });

      expect(sidebarLink('/files')).toBeNull();
      expect(sidebarLink('/archives')).toBeNull();
      expect(sidebarLink('/queue')).toBeNull();
    });
  });

  describe('Order management sidebar permissions', () => {
    const enableAuthWithUser = (permissions: string[], isAdmin = false) => {
      server.use(
        http.get('/api/v1/auth/status', () =>
          HttpResponse.json({ auth_enabled: true, requires_setup: false }),
        ),
        http.get('/api/v1/auth/me', () =>
          HttpResponse.json({
            id: 1,
            username: 'order-user',
            role: isAdmin ? 'admin' : 'user',
            is_active: true,
            is_admin: isAdmin,
            groups: [],
            permissions,
            created_at: '2026-01-01T00:00:00Z',
          }),
        ),
      );
      setAuthToken('test-token');
    };

    it('shows the order parent and Customers only to a customers reader', async () => {
      enableAuthWithUser(['customers:read']);

      render(<Layout />);

      await waitFor(() => expect(sidebarMenuButton('orders')).toBeInTheDocument());
      expandSidebarMenu('orders');

      expect(sidebarLink('/orders')).toBeInTheDocument();
      expect(sidebarLink('/orders/customers')).toBeInTheDocument();
      expect(sidebarLink('/orders/calculation')).toBeNull();
      expect(sidebarLink('/orders/offers')).toBeNull();
      expect(sidebarLink('/orders/invoices')).toBeNull();
    });

    it('shows the order parent and Calculation but not Customers to a calculations reader', async () => {
      enableAuthWithUser(['calculations:read']);

      render(<Layout />);

      await waitFor(() => expect(sidebarMenuButton('orders')).toBeInTheDocument());
      expandSidebarMenu('orders');

      expect(sidebarLink('/orders')).toBeInTheDocument();
      expect(sidebarLink('/orders/calculation')).toBeInTheDocument();
      expect(sidebarLink('/orders/customers')).toBeNull();
      expect(sidebarLink('/orders/offers')).toBeNull();
      expect(sidebarLink('/orders/invoices')).toBeNull();
    });

    it('hides order navigation without an order read permission while keeping Settings gated independently', async () => {
      enableAuthWithUser(['settings:read']);

      render(<Layout />);

      await waitFor(() => expect(sidebarMenuButton('settings')).toBeInTheDocument());
      expect(sidebarMenuButton('orders')).toBeNull();
      expect(sidebarLink('/orders')).toBeNull();
      expect(sidebarLink('/settings')).toBeInTheDocument();
    });

    it('keeps order navigation open for administrators', async () => {
      enableAuthWithUser([], true);

      render(<Layout />);

      await waitFor(() => expect(sidebarMenuButton('orders')).toBeInTheDocument());
      expandSidebarMenu('orders');
      expect(sidebarLink('/orders/customers')).toBeInTheDocument();
      expect(sidebarLink('/orders/calculation')).toBeInTheDocument();
    });
  });
});
