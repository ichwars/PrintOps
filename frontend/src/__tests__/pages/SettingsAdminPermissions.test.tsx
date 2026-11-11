import { afterEach, expect, it } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setAuthToken } from '../../api/client';
import { SettingsPage } from '../../pages/SettingsPage';
import { server } from '../mocks/server';
import { render } from '../utils';

afterEach(() => setAuthToken(null));

it('saves an ordinary edit without resubmitting administrator settings', async () => {
  window.history.replaceState({}, '', '/');
  setAuthToken('test-token', 'session');
  const writes: Record<string, unknown>[] = [];
  const settings = {
    currency: 'USD',
    external_url: '',
    show_sponsor_prompts: true,
    local_login_enabled: true,
    session_max_hours: 24,
    prometheus_enabled: false,
    prometheus_token: '',
  };
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/auth/me', () =>
      HttpResponse.json({ id: 1, username: 'editor', is_admin: false, permissions: ['settings:read', 'settings:update'] }),
    ),
    http.get('/api/v1/settings/', () => HttpResponse.json(settings)),
    http.put('/api/v1/settings/', async ({ request }) => {
      const body = await request.json() as Record<string, unknown>;
      writes.push(body);
      return HttpResponse.json({ ...settings, ...body });
    }),
  );
  render(<SettingsPage />);
  const label = await screen.findByText('Show supporter notices');
  const row = label.parentElement?.parentElement;
  if (!row) throw new Error('Expected supporter notices row');

  await new Promise(resolve => setTimeout(resolve, 1000));
  expect(writes).toHaveLength(0);
  await userEvent.click(within(row).getByRole('switch'));

  await waitFor(() => expect(writes).toHaveLength(1), { timeout: 3000 });
  expect(writes[0].show_sponsor_prompts).toBe(false);
  for (const key of ['external_url', 'local_login_enabled', 'session_max_hours', 'prometheus_enabled', 'prometheus_token']) {
    expect(writes[0]).not.toHaveProperty(key);
  }
});
