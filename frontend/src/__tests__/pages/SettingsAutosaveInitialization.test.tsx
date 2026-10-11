import { it, expect, vi } from 'vitest';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '../utils';
import { server } from '../mocks/server';
import { SettingsPage } from '../../pages/SettingsPage';

it('saves an early device edit while the initial-load delay is still pending', async () => {
  const settings = { ftp_retry_enabled: true, ftp_retry_count: 3, ftp_retry_delay: 2, ftp_timeout: 30, external_url: '', currency: 'EUR' };
  const updates: Array<Record<string, unknown>> = [];
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: false, requires_setup: false })),
    http.get('/api/v1/settings/', () => HttpResponse.json(settings)),
    http.put('/api/v1/settings/', async ({ request }) => {
      const body = await request.json() as Record<string, unknown>;
      updates.push(body);
      return HttpResponse.json({ ...settings, ...body });
    }),
    ...['equipment', 'printers', 'smart-plugs', 'notifications', 'external-links', 'virtual-printers'].map(path =>
      http.get(`/api/v1/${path}/`, () => HttpResponse.json([]))),
  );
  // Hold the old bootstrap delay so the first user edit deterministically
  // reaches the autosave flow before the delay has completed.
  const realTimeout = globalThis.setTimeout;
  const held: ReturnType<typeof setTimeout>[] = [];
  const timeoutSpy = vi.spyOn(globalThis, 'setTimeout').mockImplementation((callback, delay, ...args) => {
    const timer = realTimeout(callback, delay === 100 ? 10_000 : delay, ...args);
    if (delay === 100) held.push(timer);
    return timer;
  });
  try {
    window.history.replaceState({}, '', '/settings?tab=printers-production');
    render(<SettingsPage />);
    const grid = await screen.findByTestId('ftp-retry-fields-grid');
    await new Promise(resolve => realTimeout(resolve, 600));
    expect(updates).toEqual([]);
    const user = userEvent.setup();
    await user.click(within(grid).getAllByRole('combobox')[0]);
    await user.click(screen.getByRole('option', { name: '5 times' }));
    await waitFor(() => expect(updates).toContainEqual(expect.objectContaining({ ftp_retry_count: 5 })));
  } finally {
    held.forEach(timer => clearTimeout(timer));
    timeoutSpy.mockRestore();
  }
});
