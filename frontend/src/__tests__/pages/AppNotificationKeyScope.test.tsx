import { it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { SettingsPage } from '../../pages/SettingsPage';

it('creates a key with the explicit app notification grant, defaulting off', async () => {
  let posted: Record<string, unknown> | undefined;
  server.use(
    http.get('*/api/v1/api-keys/', () => HttpResponse.json([])),
    http.post('*/api/v1/api-keys/', async ({ request }) => {
      posted = await request.json() as Record<string, unknown>;
      return HttpResponse.json({ ...posted, id: 1, key: 'bb_fake' });
    }),
  );
  window.history.replaceState({}, '', '/settings?tab=integrations&sub=api-metrics');
  const user = userEvent.setup();
  render(<SettingsPage />);
  await user.click(await screen.findByRole('button', { name: /Create Your First Key/i }));
  const scope = await screen.findByRole('checkbox', { name: /App messages/ });
  expect(scope).not.toBeChecked();
  await user.click(scope);
  const buttons = screen.getAllByRole('button', { name: /^Create Key$/i });
  await user.click(buttons[buttons.length - 1]);
  await waitFor(() => expect(posted).toMatchObject({ can_send_notifications: true, can_access_cloud: false }));
});

it('updates the app notification grant on an existing owned key', async () => {
  let patched: unknown;
  server.use(
    http.get('*/api/v1/api-keys/', () => HttpResponse.json([{id: 7, name: 'Owned app key', user_id: 1, key_prefix: 'bb_test', enabled: true, can_send_notifications: false}])),
    http.patch('*/api/v1/api-keys/7', async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({id: 7, can_send_notifications: true});
    }),
  );
  window.history.replaceState({}, '', '/settings?tab=integrations&sub=api-metrics');
  const user = userEvent.setup();
  render(<SettingsPage />);
  const scope = await screen.findByRole('switch', { name: 'App messages' });
  expect(scope).toHaveAttribute('aria-checked', 'false');
  await user.click(scope);
  await waitFor(() => expect(patched).toEqual({ can_send_notifications: true }));
});
