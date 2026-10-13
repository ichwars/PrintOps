import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import App from '../App';
import { setAuthToken } from '../api/client';
import { server } from './mocks/server';

const callback = 'https://workshop.example/callback?existing=yes';
const query = new URLSearchParams({ client_id: 'poa_test', redirect_uri: callback,
  code_challenge: 'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM', code_challenge_method: 'S256', state: 'opaque & state' });
const destination = `/connect/authorize?${query}`;
let permissions: string[];
let approvals: unknown[];
let authEnabled: boolean;

beforeEach(() => {
  permissions = ['settings:read', 'settings:update'];
  approvals = [];
  authEnabled = true;
  vi.mocked(localStorage.getItem).mockReturnValue(null);
  setAuthToken('connect-fixture-token');
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: authEnabled, requires_setup: false })),
    http.get('/api/v1/auth/me', () => HttpResponse.json({ id: 102, username: 'person', role: 'user', is_admin: false,
      is_active: true, groups: [], permissions, created_at: '2026-01-01T00:00:00Z' })),
    http.get('/api/v1/connect/authorize/info', ({ request }) => {
      const params = new URL(request.url).searchParams;
      if (params.get('redirect_uri') !== callback) return HttpResponse.json({ detail: 'Callback mismatch' }, { status: 400 });
      return HttpResponse.json({ app_name: 'Workshop', username: 'person', redirect_uri: callback, already_granted: true });
    }),
    http.post('/api/v1/connect/authorize', async ({ request }) => {
      approvals.push(await request.json());
      return HttpResponse.json({ code: 'single-use-code', redirect_uri: callback });
    }),
    http.get('/api/v1/connect/apps', () => HttpResponse.json([])),
  );
});
afterEach(() => setAuthToken(null));

it('shows identity disclosure and requires explicit consent even for a prior grant', async () => {
  window.history.replaceState({}, '', destination);
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Sign in to Workshop' })).toBeInTheDocument();
  expect(screen.getByText(/email address, groups and current permissions/i)).toBeInTheDocument();
  expect(screen.getByText(/does not grant access to the PrintOps API/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Allow sign-in' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Deny' })).toBeEnabled();
  expect(approvals).toEqual([]);
});

it('never offers approval or a denial redirect for an unregistered callback', async () => {
  const invalid = new URLSearchParams(query);
  invalid.set('redirect_uri', 'https://attacker.example/');
  window.history.replaceState({}, '', `/connect/authorize?${invalid}`);
  render(<App />);
  expect(await screen.findByRole('alert')).toHaveTextContent(/Callback mismatch|invalid|unable/i);
  expect(screen.queryByRole('button', { name: 'Deny' })).not.toBeInTheDocument();
  expect(approvals).toEqual([]);
});

it('preserves the full consent query and state through the existing login route', async () => {
  setAuthToken(null);
  window.history.replaceState({}, '', destination);
  render(<App />);
  expect(await screen.findByRole('heading', { name: /PrintOps Login/i })).toBeInTheDocument();
  await waitFor(() => expect(window.location.pathname).toBe('/login'));
  expect(window.history.state.usr.from.pathname + window.history.state.usr.from.search).toBe(destination);
  server.use(http.post('/api/v1/auth/login', () => HttpResponse.json({ access_token: 'new-fixture-token', token_type: 'bearer', user: { id: 102, username: 'person', role: 'user', is_admin: false, is_active: true, groups: [], permissions, created_at: '2026-01-01T00:00:00Z' } })));
  fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: 'person' } });
  fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: 'fixture-password' } });
  fireEvent.click(screen.getByRole('button', { name: /Sign in/i }));
  expect(await screen.findByRole('heading', { name: 'Sign in to Workshop' })).toBeInTheDocument();
  expect(window.location.pathname + window.location.search).toBe(destination);

});

it('shows the disabled-auth explanation instead of approval', async () => {
  authEnabled = false;
  setAuthToken(null);
  window.history.replaceState({}, '', destination);
  render(<App />);
  expect(await screen.findByText('Enable authentication to use connected applications.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Allow sign-in' })).not.toBeInTheDocument();
});

it('integrates app management at the existing API and metrics settings path', async () => {
  window.history.replaceState({}, '', '/settings?tab=integrations&sub=api-metrics');
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Connected applications' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Register application' })).toBeInTheDocument();
  expect(document.getElementById('card-connected-apps')).toBeInTheDocument();
});


it('lets an update-only manager navigate to connected apps without reading other settings', async () => {
  permissions = ['settings:update'];
  let settingsRequests = 0;
  server.use(http.get('/api/v1/settings/', () => {
    settingsRequests += 1;
    return HttpResponse.json({ detail: 'Forbidden' }, { status: 403 });
  }));
  window.history.replaceState({}, '', '/settings');
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Connected applications' })).toBeInTheDocument();
  const navigation = document.querySelector('aside a[href="/settings?tab=integrations"]');
  expect(navigation).toBeInTheDocument();
  fireEvent.click(navigation!);
  expect(await screen.findByRole('button', { name: 'Register application' })).toBeInTheDocument();
  expect(window.location.pathname + window.location.search).toBe('/settings?tab=integrations');
  expect(document.querySelector('aside a[href="/settings?tab=general"]')).not.toBeInTheDocument();
  expect(document.querySelector('aside a[href="/settings?tab=users-security"]')).not.toBeInTheDocument();
  expect(settingsRequests).toBe(0);
});

it('does not expose connected app management without settings:update', async () => {
  permissions = [];
  window.history.replaceState({}, '', '/settings?tab=integrations&sub=api-metrics');
  render(<App />);
  await waitFor(() => expect(window.location.pathname).toBe('/'));
  expect(screen.queryByRole('heading', { name: 'Connected applications' })).not.toBeInTheDocument();
  expect(document.querySelector('aside a[href="/settings?tab=integrations"]')).not.toBeInTheDocument();
});
