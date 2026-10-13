/**
 * Tests for the StreamOverlayPage component.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, screen, waitFor, fireEvent, render as rtlRender } from '@testing-library/react';
import { StreamOverlayPage } from '../../pages/StreamOverlayPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { MemoryRouter, Route, Routes } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '../../contexts/ThemeContext';
import { ToastProvider } from '../../contexts/ToastContext';
import { AuthProvider } from '../../contexts/AuthContext';

const mockPrinter = {
  id: 1,
  name: 'X1 Carbon',
  ip_address: '192.168.1.100',
  serial_number: '00M09A350100001',
  access_code: '12345678',
  model: 'X1C',
  enabled: true,
};

const mockStatusIdle = {
  id: 1,
  name: 'X1 Carbon',
  connected: true,
  state: 'IDLE',
  progress: 0,
  current_print: null,
  remaining_time: null,
  layer_num: null,
  total_layers: null,
  stg_cur_name: null,
};

const mockStatusPrinting = {
  id: 1,
  name: 'X1 Carbon',
  connected: true,
  state: 'RUNNING',
  progress: 45,
  current_print: 'Benchy.gcode.3mf',
  remaining_time: 82,
  layer_num: 150,
  total_layers: 300,
  stg_cur_name: null,
};

// Custom render for StreamOverlayPage
function renderOverlayPage(printerId: number, queryParams = '') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return rtlRender(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/overlay/${printerId}${queryParams}`]}>
        <AuthProvider>
          <ThemeProvider>
            <ToastProvider>
              <Routes>
                <Route path="/overlay/:printerId" element={<StreamOverlayPage />} />
              </Routes>
            </ToastProvider>
          </ThemeProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('StreamOverlayPage', () => {
  const originalTitle = document.title;

  beforeEach(() => {
    // Mock WebSocket. vitest 4 dropped support for arrow-function constructor
    // mocks (`new (() => ...)` throws "is not a constructor"); use a plain
    // function so `new WebSocket(...)` resolves correctly.
    vi.stubGlobal(
      'WebSocket',
      vi.fn().mockImplementation(function (this: { close: () => void; onmessage: null; onerror: null }) {
        this.close = vi.fn();
        this.onmessage = null;
        this.onerror = null;
      }),
    );

    server.use(
      http.get('/api/v1/printers/:id', () => {
        return HttpResponse.json(mockPrinter);
      }),
      http.get('/api/v1/printers/:id/status', () => {
        return HttpResponse.json(mockStatusIdle);
      })
    );
  });

  afterEach(() => {
    document.title = originalTitle;
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  describe('optional scoped details', () => {
    const narrow = {
      ...mockStatusPrinting, model: 'H2D', camera_rotation: 0, time_format: '24h',
      supports_chamber_sensor: true,
      temperatures: { nozzle: 180, nozzle_target: 220, nozzle_2: 215, bed: 60, chamber: 35 },
    };
    beforeEach(() => {
      server.use(http.get('/api/v1/printers/:id/overlay-status', () => HttpResponse.json(narrow)));
    });
    it('renders opt-in model and both nozzle readings using only the scoped endpoint', async () => {
      const forbidden: string[] = [];
      server.use(...['/api/v1/printers/:id', '/api/v1/printers/:id/status'].map(path =>
        http.get(path, ({ request }) => { forbidden.push(request.url); return new HttpResponse(null, { status: 403 }); })),
        http.post('/api/v1/auth/ws-token', ({ request }) => { forbidden.push(request.url); return new HttpResponse(null, { status: 403 }); }));
      renderOverlayPage(1, '?token=bblt_fixture&show=model,temperatures');
      expect(await screen.findByText('H2D')).toBeInTheDocument();
      expect(screen.getByText('180°C → 220°C')).toBeInTheDocument();
      expect(screen.getByText('215°C')).toBeInTheDocument();
      expect(screen.getByText('35°C')).toBeInTheDocument();
      expect(forbidden).toEqual([]);
      expect(WebSocket).not.toHaveBeenCalled();
    });
    it('keeps new details and artwork off for existing URLs', async () => {
      renderOverlayPage(1, '?token=bblt_fixture');
      await screen.findByText('Benchy');
      expect(screen.queryByText('H2D')).not.toBeInTheDocument();
      expect(screen.queryByText(/°C/)).not.toBeInTheDocument();
      expect(screen.queryByTestId('overlay-artwork')).not.toBeInTheDocument();
    });
    it('omits absent chamber capability and supports independent model/temperature toggles', async () => {
      server.use(http.get('/api/v1/printers/:id/overlay-status', () => HttpResponse.json({ ...narrow, supports_chamber_sensor: false })));
      renderOverlayPage(1, '?token=bblt_fixture&show=temperatures&artwork=portrait');
      expect(await screen.findByText('215°C')).toBeInTheDocument();
      expect(screen.queryByText('35°C')).not.toBeInTheDocument();
      expect(screen.queryByText('H2D')).not.toBeInTheDocument();
      expect(screen.getByTestId('overlay-artwork')).toHaveAttribute('data-layout', 'portrait');
    });
    it('recovers errors silently and stops after three unsuccessful reloads', async () => {
      renderOverlayPage(1, '?token=bblt_fixture');
      await screen.findByText('Benchy');
      vi.useFakeTimers();
      const firstSrc = screen.getByAltText('Camera stream').getAttribute('src');
      for (const delay of [3000, 6000, 12000]) {
        fireEvent.error(screen.getByAltText('Camera stream'));
        await act(() => vi.advanceTimersByTimeAsync(delay));
      }
      const lastSrc = screen.getByAltText('Camera stream').getAttribute('src');
      expect(lastSrc).not.toBe(firstSrc);
      expect(lastSrc).toContain('token=bblt_fixture');
      fireEvent.error(screen.getByAltText('Camera stream'));
      await act(() => vi.advanceTimersByTimeAsync(120000));
      expect(screen.getByAltText('Camera stream').getAttribute('src')).toBe(lastSrc);
      vi.useRealTimers();
    });
  });

  describe('rendering', () => {
    it('renders overlay page for printer', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        expect(screen.getByText('Printer is idle')).toBeInTheDocument();
      });
    });

    it('shows PrintOps logo', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        expect(screen.getByAltText('PrintOps')).toBeInTheDocument();
      });
    });

    it('logo links to GitHub', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        const logo = screen.getByAltText('PrintOps');
        const link = logo.closest('a');
        expect(link).toHaveAttribute('href', 'https://github.com/ichwars/PrintOps');
      });
    });
  });

  describe('printing state', () => {
    beforeEach(() => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json(mockStatusPrinting);
        })
      );
    });

    it('shows filename when printing', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        expect(screen.getByText('Benchy')).toBeInTheDocument();
      });
    });

    it('shows progress percentage', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        expect(screen.getByText('45%')).toBeInTheDocument();
      });
    });

    it('shows layer count', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        expect(screen.getByText('150')).toBeInTheDocument();
        expect(screen.getByText('300')).toBeInTheDocument();
      });
    });

    it('shows status text', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        expect(screen.getByText('Printing')).toBeInTheDocument();
      });
    });
  });

  describe('invalid printer', () => {
    it('shows invalid printer message for ID 0', async () => {
      renderOverlayPage(0);

      await waitFor(() => {
        expect(screen.getByText('Invalid printer ID')).toBeInTheDocument();
      });
    });
  });

  describe('query parameters', () => {
    it('respects size parameter', async () => {
      renderOverlayPage(1, '?size=large');

      await waitFor(() => {
        // Just verify it renders without error
        expect(screen.getByAltText('PrintOps')).toBeInTheDocument();
      });
    });

    it('respects show parameter to hide elements', async () => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json(mockStatusPrinting);
        })
      );

      renderOverlayPage(1, '?show=progress');

      await waitFor(() => {
        // Progress should be visible
        expect(screen.getByText('45%')).toBeInTheDocument();
        // Status text should be hidden when not in show list
        expect(screen.queryByText('Printing')).not.toBeInTheDocument();
      });
    });
  });

  describe('FPS configuration', () => {
    it('uses default FPS of 15 when not specified', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        const img = screen.getByAltText('Camera stream') as HTMLImageElement;
        expect(img.src).toContain('fps=15');
      });
    });

    it('uses custom FPS when specified in query params', async () => {
      renderOverlayPage(1, '?fps=30');

      await waitFor(() => {
        const img = screen.getByAltText('Camera stream') as HTMLImageElement;
        expect(img.src).toContain('fps=30');
      });
    });

    it('clamps FPS to maximum of 30', async () => {
      renderOverlayPage(1, '?fps=60');

      await waitFor(() => {
        const img = screen.getByAltText('Camera stream') as HTMLImageElement;
        expect(img.src).toContain('fps=30');
      });
    });

    it('clamps FPS to minimum of 1', async () => {
      renderOverlayPage(1, '?fps=0');

      await waitFor(() => {
        const img = screen.getByAltText('Camera stream') as HTMLImageElement;
        expect(img.src).toContain('fps=1');
      });
    });

    it('handles invalid FPS value gracefully', async () => {
      renderOverlayPage(1, '?fps=invalid');

      await waitFor(() => {
        const img = screen.getByAltText('Camera stream') as HTMLImageElement;
        // Should fall back to default of 15
        expect(img.src).toContain('fps=15');
      });
    });
  });

  describe('camera toggle (status-only mode)', () => {
    it('shows camera by default', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        expect(screen.getByAltText('Camera stream')).toBeInTheDocument();
      });
    });

    it('hides camera when camera=false', async () => {
      renderOverlayPage(1, '?camera=false');

      await waitFor(() => {
        // Status should still be visible
        expect(screen.getByText('Printer is idle')).toBeInTheDocument();
      });

      // Camera should not be rendered
      expect(screen.queryByAltText('Camera stream')).not.toBeInTheDocument();
    });

    it('hides camera when camera=0', async () => {
      renderOverlayPage(1, '?camera=0');

      await waitFor(() => {
        expect(screen.getByText('Printer is idle')).toBeInTheDocument();
      });

      expect(screen.queryByAltText('Camera stream')).not.toBeInTheDocument();
    });

    it('shows camera when camera=true', async () => {
      renderOverlayPage(1, '?camera=true');

      await waitFor(() => {
        expect(screen.getByAltText('Camera stream')).toBeInTheDocument();
      });
    });

    it('shows camera when camera=1', async () => {
      renderOverlayPage(1, '?camera=1');

      await waitFor(() => {
        expect(screen.getByAltText('Camera stream')).toBeInTheDocument();
      });
    });
  });

  describe('combined parameters', () => {
    it('supports fps and camera together', async () => {
      renderOverlayPage(1, '?fps=25&camera=true');

      await waitFor(() => {
        const img = screen.getByAltText('Camera stream') as HTMLImageElement;
        expect(img.src).toContain('fps=25');
      });
    });

    it('supports status-only with custom size', async () => {
      renderOverlayPage(1, '?camera=false&size=large');

      await waitFor(() => {
        expect(screen.getByText('Printer is idle')).toBeInTheDocument();
      });

      expect(screen.queryByAltText('Camera stream')).not.toBeInTheDocument();
    });

    it('supports show parameter with fps', async () => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json(mockStatusPrinting);
        })
      );

      renderOverlayPage(1, '?fps=20&show=progress');

      await waitFor(() => {
        const img = screen.getByAltText('Camera stream') as HTMLImageElement;
        expect(img.src).toContain('fps=20');
        expect(screen.getByText('45%')).toBeInTheDocument();
      });
    });
  });

  describe('offline state', () => {
    beforeEach(() => {
      server.use(
        http.get('/api/v1/printers/:id/status', () => {
          return HttpResponse.json({
            ...mockStatusIdle,
            connected: false,
          });
        })
      );
    });

    it('shows offline message when printer disconnected', async () => {
      renderOverlayPage(1);

      await waitFor(() => {
        expect(screen.getByText('Printer offline')).toBeInTheDocument();
      });
    });
  });
});
