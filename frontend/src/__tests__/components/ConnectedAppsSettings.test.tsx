import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, screen } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { setAuthToken } from '../../api/client';
import { ConnectedAppsSettings } from '../../components/ConnectedAppsSettings';
import { connectCallbackUrl } from '../../utils/connectCallbackUrl';
import type { ConnectedApp } from '../../api/client/connected-apps';

let apps: ConnectedApp[];
beforeEach(() => {
  apps = [];
  vi.mocked(localStorage.getItem).mockReturnValue(null);
  setAuthToken('fixture-token');
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/auth/me', () => HttpResponse.json({ id: 102, username: 'manager', role: 'user', is_admin: false,
      is_active: true, groups: [], permissions: ['settings:read', 'settings:update'], created_at: '2026-01-01T00:00:00Z' })),
    http.get('/api/v1/connect/apps', () => HttpResponse.json(apps)),
    http.post('/api/v1/connect/apps', async ({ request }) => {
      const data = await request.json() as { name: string; redirect_uri: string };
      apps = [{ ...data, id: 1, client_id: 'poa_fixture', enabled: true, created_at: '2026-10-13T00:00:00Z', last_used_at: null }];
      return HttpResponse.json({ ...apps[0], client_secret: 'pos_created_fixture' });
    }),
    http.patch('/api/v1/connect/apps/1', async ({ request }) => {
      apps = [{ ...apps[0], ...await request.json() as object }];
      return HttpResponse.json(apps[0]);
    }),
    http.post('/api/v1/connect/apps/1/rotate-secret', () => HttpResponse.json({ ...apps[0], client_secret: 'pos_rotated_fixture' })),
    http.delete('/api/v1/connect/apps/1', () => { apps = []; return HttpResponse.json({ message: 'deleted' }); }),
  );
});
afterEach(() => setAuthToken(null));

it('creates, dismisses the only secret disclosure, edits, disables, rotates and deletes an app', async () => {
  render(<ConnectedAppsSettings />);
  await screen.findByText('No applications registered.');
  fireEvent.change(screen.getByLabelText('Application name'), { target: { value: 'Workshop' } });
  fireEvent.change(screen.getByLabelText('Callback URL'), { target: { value: 'https://workshop.example/cb' } });
  fireEvent.click(screen.getByRole('button', { name: 'Register application' }));
  expect(await screen.findByLabelText('Client secret')).toHaveValue('pos_created_fixture');
  expect(screen.getByLabelText('Client ID')).toHaveValue('poa_fixture');
  fireEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(screen.queryByLabelText('Client secret')).not.toBeInTheDocument();
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
  fireEvent.change(screen.getByLabelText('Application name'), { target: { value: 'Renamed workshop' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Renamed workshop')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Disable' }));
  expect(await screen.findByText('Disabled')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Rotate secret' }));
  expect(screen.getByText(/old secret and pending codes will stop working/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  expect(await screen.findByLabelText('Client secret')).toHaveValue('pos_rotated_fixture');
  expect(screen.queryByDisplayValue('pos_created_fixture')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  expect(await screen.findByText('No applications registered.')).toBeInTheDocument();
  expect(screen.queryByLabelText('Client secret')).not.toBeInTheDocument();
});

it('preserves opaque state and existing query parameters in allow and deny redirects', () => {
  const callback = 'https://workshop.example/cb?existing=yes&code=old&error=old&state=old';
  const allowed = new URL(connectCallbackUrl(callback, 'opaque & value', { code: 'new-code' }));
  expect([...allowed.searchParams]).toEqual([['existing', 'yes'], ['code', 'new-code'], ['state', 'opaque & value']]);
  const denied = new URL(connectCallbackUrl(callback, '', { error: 'access_denied' }));
  expect([...denied.searchParams]).toEqual([['existing', 'yes'], ['error', 'access_denied'], ['state', '']]);
});


it('discards edited name and callback on Cancel without saving', async () => {
  apps = [{ id: 1, name: 'Workshop', redirect_uri: 'https://workshop.example/cb',
    client_id: 'poa_fixture', enabled: true, created_at: '2026-10-13T00:00:00Z', last_used_at: null }];
  const original = { ...apps[0] };
  render(<ConnectedAppsSettings />);
  fireEvent.click(await screen.findByRole('button', { name: 'Edit' }));
  fireEvent.change(screen.getByLabelText('Application name'), { target: { value: 'Discard me' } });
  fireEvent.change(screen.getByLabelText('Callback URL'), { target: { value: 'https://discard.example/cb' } });
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Cancel' })); });
  expect(screen.getByRole('button', { name: 'Register application' })).toBeInTheDocument();
  expect(screen.getByLabelText('Application name')).toHaveValue('');
  expect(screen.getByLabelText('Callback URL')).toHaveValue('');
  expect(apps).toEqual([original]);
  expect(screen.getByText('Workshop')).toBeInTheDocument();
});
