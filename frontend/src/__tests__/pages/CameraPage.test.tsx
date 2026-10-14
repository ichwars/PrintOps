/**
 * Tests for the CameraPage component.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, screen, waitFor, fireEvent, render as rtlRender } from '@testing-library/react';
import { CameraPage } from '../../pages/CameraPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '../../contexts/ThemeContext';
import { ToastProvider } from '../../contexts/ToastContext';
import { AuthProvider } from '../../contexts/AuthContext';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../i18n';
import { setAuthToken } from '../../api/client';

// Mock navigator.sendBeacon which isn't available in jsdom
vi.stubGlobal('navigator', {
  ...navigator,
  sendBeacon: vi.fn().mockReturnValue(true),
});

const mockPrinter = {
  id: 1,
  name: 'X1 Carbon',
  ip_address: '192.168.1.100',
  serial_number: '00M09A350100001',
  access_code: '12345678',
  model: 'X1C',
  enabled: true,
};

// Custom render for CameraPage which needs specific route params
function renderCameraPage(printerId: number, search = '') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return rtlRender(
    <QueryClientProvider client={queryClient}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={[`/cameras/${printerId}${search}`]}>
          <AuthProvider>
            <ThemeProvider>
              <ToastProvider>
                <Routes>
                  <Route path="/cameras/:printerId" element={<CameraPage />} />
                </Routes>
              </ToastProvider>
            </ThemeProvider>
          </AuthProvider>
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>
  );
}

describe('CameraPage', () => {
  const originalTitle = document.title;

  beforeEach(() => {
    const storage = new Map<string, string>();
    vi.mocked(localStorage.getItem).mockImplementation(key => storage.get(key) ?? null);
    vi.mocked(localStorage.setItem).mockImplementation((key, value) => { storage.set(key, value); });
    vi.mocked(localStorage.removeItem).mockImplementation(key => { storage.delete(key); });
    server.use(
      http.get('/api/v1/printers/:id', () => {
        return HttpResponse.json(mockPrinter);
      }),
      http.get('/api/v1/printers/:id/status', () => {
        return HttpResponse.json({
          connected: true,
          state: 'IDLE',
          progress: 0,
        });
      }),
      http.post('/api/v1/printers/:id/camera/stop', () => {
        return HttpResponse.json({ success: true });
      }),
      http.get('/api/v1/printers/:id/camera/status', () => {
        return HttpResponse.json({ active: true, stalled: false });
      })
    );
  });

  afterEach(() => {
    document.title = originalTitle;
    setAuthToken(null);
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
  });

  describe('per-printer camera preference', () => {
    const preferenceKey = 'printops:camera-view:v2:http%3A%2F%2Flocalhost%3A3000:appliance:printer:00M09A350100001';

    it('updates the camera window title when the interface language changes', async () => {
      try {
        await i18n.changeLanguage('nl');
        const view = renderCameraPage(1);
        await waitFor(() => expect(document.title).toBe('X1 Carbon - Cameraweergave'));
        await act(() => i18n.changeLanguage('en'));
        await waitFor(() => expect(document.title).toBe('X1 Carbon - Camera View'));
        view.unmount();
        expect(document.title).toBe('PrintOps');
      } finally {
        await i18n.changeLanguage('en');
      }
    });

    it('opens the saved snapshot without starting a live player', async () => {
      localStorage.setItem(preferenceKey, JSON.stringify({ version: 1, mode: 'snapshot' }));
      renderCameraPage(1);

      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
      });
      expect(document.querySelector('video')).toBeNull();
      expect(screen.getByRole('button', { name: 'Snapshot' })).toHaveAttribute('aria-pressed', 'true');
    });

    it('waits for the signed-in identity before opening its saved snapshot', async () => {
      localStorage.setItem('printops:camera-view:v2:http%3A%2F%2Flocalhost%3A3000:user:account-1:printer:00M09A350100001', '{"version":1,"mode":"snapshot"}');
      setAuthToken('preference-test-token', 'session');
      let resolveIdentity!: () => void;
      let identityRequested = false;
      const identity = new Promise<void>(resolve => { resolveIdentity = resolve; });
      server.use(
        http.get('*/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
        http.get('*/api/v1/auth/me', async () => {
          identityRequested = true;
          await identity;
          return HttpResponse.json({ id: 1, sub: 'account-1', username: 'admin', role: 'admin', is_active: true, is_admin: true, groups: [], permissions: [], created_at: '2024-01-01T00:00:00Z' });
        }),
        http.post('*/api/v1/printers/camera/stream-token', () => HttpResponse.json({ token: 'camera-test-token' })),
      );
      renderCameraPage(1);
      await waitFor(() => expect(identityRequested).toBe(true));
      expect(document.querySelector('img[src*="/camera/"], video[src*="/camera/"]')).toBeNull();
      resolveIdentity();
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
        expect(document.querySelector('img')?.getAttribute('src')).toContain('token=camera-test-token');
      });
      expect(document.querySelector('video')).toBeNull();
    });

    it('remembers a camera-page mode change for the next opening', async () => {
      const first = renderCameraPage(1);
      await screen.findByText('X1 Carbon');
      fireEvent.load(document.querySelector('img')!);
      fireEvent.click(screen.getByRole('button', { name: 'Snapshot' }));
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
      });
      first.unmount();
      renderCameraPage(1);
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
      });
      expect(JSON.parse(localStorage.getItem(preferenceKey)!)).toEqual({ version: 1, mode: 'snapshot' });
    });

    it('keeps camera-token links independent of stored appliance preferences', async () => {
      localStorage.setItem(preferenceKey, JSON.stringify({ version: 1, mode: 'snapshot' }));
      renderCameraPage(1, '?camera_token=anonymous-link');
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/stream');
      });
      fireEvent.load(document.querySelector('img')!);
      fireEvent.click(screen.getByRole('button', { name: 'Snapshot' }));
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
      });
      fireEvent.load(document.querySelector('img')!);
      fireEvent.click(screen.getByRole('button', { name: 'Live' }));
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/stream');
      });
      expect(JSON.parse(localStorage.getItem(preferenceKey)!)).toEqual({ version: 1, mode: 'snapshot' });
    });

    it('honors an explicit launch view without rewriting the saved default', async () => {
      localStorage.setItem(preferenceKey, '{"version":1,"mode":"snapshot"}');
      renderCameraPage(1, '?view=stream');
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/stream');
      });
      expect(JSON.parse(localStorage.getItem(preferenceKey)!)).toEqual({ version: 1, mode: 'snapshot' });
    });

    it.each(['stream', null] as const)('releases the snapshot launch hint when this printer default changes to %s in another tab', async (value) => {
      renderCameraPage(1, '?view=snapshot');
      await waitFor(() => expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot'));
      if (value === null) localStorage.removeItem(preferenceKey);
      else localStorage.setItem(preferenceKey, JSON.stringify({ version: 1, mode: value }));
      act(() => window.dispatchEvent(new StorageEvent('storage', { key: preferenceKey })));
      await waitFor(() => expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/stream'));
      expect(screen.getByRole('button', { name: 'Live' })).toHaveAttribute('aria-pressed', 'true');
    });

    it('ignores unknown launch views and uses the saved default', async () => {
      localStorage.setItem(preferenceKey, '{"version":1,"mode":"snapshot"}');
      renderCameraPage(1, '?view=invalid');
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
      });
    });

    it('cancels a live retry when another tab changes this printer to snapshot', async () => {
      renderCameraPage(1);
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/stream');
      });
      vi.useFakeTimers();
      try {
        fireEvent.error(document.querySelector('img')!);
        expect(screen.getByText(/Reconnecting in/)).toBeInTheDocument();
        localStorage.setItem(preferenceKey, '{"version":1,"mode":"snapshot"}');
        act(() => window.dispatchEvent(new StorageEvent('storage', { key: preferenceKey })));
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
        expect(screen.queryByText(/Reconnecting in/)).not.toBeInTheDocument();
        fireEvent.load(document.querySelector('img')!);
        const snapshotUrl = document.querySelector('img')?.getAttribute('src');
        act(() => vi.advanceTimersByTime(2500));
        expect(document.querySelector('img')?.getAttribute('src')).toBe(snapshotUrl);
        expect(screen.getByRole('button', { name: 'Live' })).toBeEnabled();
      } finally {
        vi.useRealTimers();
      }
    });

    it('uses a snapshot launch hint and remains switchable when camera storage is blocked', async () => {
      vi.mocked(localStorage.getItem).mockImplementation(key => {
        if (key.includes('camera')) throw new Error('camera storage blocked');
        return null;
      });
      vi.mocked(localStorage.setItem).mockImplementation(key => {
        if (key.includes('camera')) throw new Error('camera storage blocked');
      });
      renderCameraPage(1, '?view=snapshot');
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
      });
      fireEvent.load(document.querySelector('img')!);
      fireEvent.click(screen.getByRole('button', { name: 'Live' }));
      await waitFor(() => {
        expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/stream');
      });
      fireEvent.load(document.querySelector('img')!);
      expect(screen.getByRole('button', { name: 'Snapshot' })).toBeEnabled();
    });
  });

  describe('rendering', () => {
    it('renders camera page for printer', async () => {
      renderCameraPage(1);

      // Camera page should load - look for the header with camera icon
      await waitFor(() => {
        expect(screen.getByRole('heading')).toBeInTheDocument();
      });
    });

    it('shows live and snapshot mode buttons', async () => {
      renderCameraPage(1);

      await waitFor(() => {
        // Check for translation key or translated text
        expect(screen.getByText(/Live|camera\.live/)).toBeInTheDocument();
        expect(screen.getByText(/Snapshot|camera\.snapshot/)).toBeInTheDocument();
      });
    });

    it('shows printer name in header', async () => {
      renderCameraPage(1);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });
    });
  });

  describe('camera controls', () => {
    it('renders without crashing', async () => {
      renderCameraPage(1);

      // Just verify no crash during render
      await waitFor(() => {
        expect(document.body).toBeInTheDocument();
      });
    });

    it('shows the camera diagnostic (stethoscope) button in the control bar (#1395)', async () => {
      // The diagnostic shipped wired into the embedded viewer only; window mode
      // (this page) was missing it. The control-bar button must be present here.
      renderCameraPage(1);

      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });
      expect(screen.getByTitle('Diagnose')).toBeInTheDocument();
    });
  });

  describe('temperature overlay (#101)', () => {
    beforeEach(() => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json({
            connected: true,
            state: 'RUNNING',
            progress: 42,
            temperatures: {
              nozzle: 219.6,
              nozzle_target: 220,
              bed: 59.8,
              bed_target: 60,
              chamber: 34.1,
            },
          });
        }),
      );
    });

    it('shows live temperature readings over the video by default', async () => {
      renderCameraPage(1);

      await waitFor(() => {
        expect(screen.getByText('220°C')).toBeInTheDocument();
      });
      expect(screen.getByText('60°C')).toBeInTheDocument();
      expect(screen.getByText('34°C')).toBeInTheDocument();
    });

    it('hides the overlay when the toggle button is clicked', async () => {
      const { default: userEvent } = await import('@testing-library/user-event');
      const user = userEvent.setup();
      renderCameraPage(1);

      await waitFor(() => {
        expect(screen.getByText('220°C')).toBeInTheDocument();
      });

      await user.click(screen.getByTitle('Toggle temperature overlay'));

      expect(screen.queryByText('220°C')).not.toBeInTheDocument();
    });
  });

  describe('stream token handling (#979)', () => {
    it('does not render image src until stream token arrives when auth is enabled', async () => {
      setAuthToken('camera-user-session');
      let resolveToken!: (value: unknown) => void;
      const tokenPromise = new Promise((resolve) => {
        resolveToken = resolve;
      });

      server.use(
        http.get('*/api/v1/auth/status', () =>
          HttpResponse.json({ auth_enabled: true, requires_setup: false })
        ),
        http.post('*/api/v1/printers/camera/stream-token', async () => {
          await tokenPromise;
          return HttpResponse.json({ token: 'tok-abc' });
        })
      );

      renderCameraPage(1);

      // Before the token resolves the <img> should not have a src pointing at
      // the stream endpoint — otherwise the backend would 401 with the
      // "Valid camera stream token required" error from #979.
      await waitFor(() => {
        expect(screen.getByText('X1 Carbon')).toBeInTheDocument();
      });
      const img = document.querySelector('img') as HTMLImageElement | null;
      expect(img).not.toBeNull();
      expect(img?.getAttribute('src') || '').not.toContain('/camera/stream');

      resolveToken(undefined);

      // After the token resolves the image src picks it up as ?token=...
      await waitFor(() => {
        const src = (document.querySelector('img') as HTMLImageElement | null)?.getAttribute('src') || '';
        expect(src).toContain('/camera/stream');
        expect(src).toContain('token=tok-abc');
      });
    });

    it('renders image src immediately when auth is disabled (no token required)', async () => {
      renderCameraPage(1);

      await waitFor(() => {
        const src = (document.querySelector('img') as HTMLImageElement | null)?.getAttribute('src') || '';
        expect(src).toContain(`/api/v1/printers/1/camera/stream`);
        expect(src).not.toContain('token=');
      });
    });
  });

  describe('fps URL parameter (#1131)', () => {
    it('defaults to fps=15 when no query parameter is provided', async () => {
      renderCameraPage(1);

      await waitFor(() => {
        const src = (document.querySelector('img') as HTMLImageElement | null)?.getAttribute('src') || '';
        expect(src).toContain('fps=15');
      });
    });

    it('honors fps query parameter from URL', async () => {
      renderCameraPage(1, '?fps=5');

      await waitFor(() => {
        const src = (document.querySelector('img') as HTMLImageElement | null)?.getAttribute('src') || '';
        expect(src).toContain('fps=5');
      });
    });

    it('clamps fps above 30 to 30', async () => {
      renderCameraPage(1, '?fps=60');

      await waitFor(() => {
        const src = (document.querySelector('img') as HTMLImageElement | null)?.getAttribute('src') || '';
        expect(src).toContain('fps=30');
      });
    });

    it('clamps fps below 1 to 1', async () => {
      renderCameraPage(1, '?fps=0');

      await waitFor(() => {
        const src = (document.querySelector('img') as HTMLImageElement | null)?.getAttribute('src') || '';
        expect(src).toContain('fps=1');
      });
    });

    it('falls back to 15 for non-numeric fps', async () => {
      renderCameraPage(1, '?fps=invalid');

      await waitFor(() => {
        const src = (document.querySelector('img') as HTMLImageElement | null)?.getAttribute('src') || '';
        expect(src).toContain('fps=15');
      });
    });
  });

  describe('invalid printer', () => {
    it('shows invalid printer message for ID 0', async () => {
      renderCameraPage(0);

      await waitFor(() => {
        // Check for translation key or translated text
        expect(screen.getByText(/Invalid printer ID|camera\.invalidPrinterId/)).toBeInTheDocument();
      });
    });
  });
});
