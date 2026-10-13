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
let departedTo: string | null;
const originalLocation = window.location;

beforeEach(() => {
  permissions = ['settings:read', 'settings:update'];
  approvals = [];
  authEnabled = true;
  departedTo = null;
  // The global test setup suppresses location.href writes. Record the browser
  // boundary here while exercising the real login/router/storage implementation.
  Object.defineProperty(window, 'location', { configurable: true, value: new Proxy(originalLocation, {
    set(target, property, value) {
      if (property === 'href') { departedTo = String(value); return true; }
      return Reflect.set(target, property, value);
    },
  }) });
  sessionStorage.removeItem('auth_post_login_redirect');
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
afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
  setAuthToken(null);
  sessionStorage.removeItem('auth_post_login_redirect');
});

it.each([false, true])('restores the full consent URL after automatic OIDC with MFA=%s', async (requiresMfa) => {
  setAuthToken(null);
  const loginResponse = { access_token: 'oidc-fixture-token', token_type: 'bearer', user: {
    id: 102, username: 'person', role: 'user', is_admin: false, is_active: true,
    groups: [], permissions, created_at: '2026-01-01T00:00:00Z',
  } };
  server.use(
    http.get('/api/v1/auth/advanced-auth/status', () => HttpResponse.json({
      advanced_auth_enabled: true, local_login_enabled: true, autologin_provider_id: 7,
    })),
    http.get('/api/v1/auth/oidc/authorize/7', () => HttpResponse.json({
      auth_url: 'https://provider.example/authorize',
    })),
    http.post('/api/v1/auth/oidc/exchange', () => HttpResponse.json(requiresMfa
      ? { requires_2fa: true, pre_auth_token: 'oidc-fixture-preauth', two_fa_methods: ['totp'] }
      : loginResponse)),
    http.post('/api/v1/auth/2fa/verify', () => HttpResponse.json(loginResponse)),
  );
  window.history.replaceState({}, '', destination);
  const firstVisit = render(<App />);
  await waitFor(() => expect(departedTo).toBe('https://provider.example/authorize'));
  firstVisit.unmount();
  // A real provider callback loses the old router state and remounts the application.
  window.history.replaceState(null, '', '/login#oidc_token=fixture-exchange-token');
  render(<App />);
  if (requiresMfa) {
    const input = await screen.findByRole('textbox', { name: /Verification Code/i });
    fireEvent.change(input, { target: { value: '123456' } });
    fireEvent.click(screen.getByRole('button', { name: /Verify/i }));
  }
  expect(await screen.findByRole('heading', { name: 'Sign in to Workshop' })).toBeInTheDocument();
  expect(window.location.pathname + window.location.search).toBe(destination);
  expect(sessionStorage.getItem('auth_post_login_redirect')).toBeNull();
  expect(approvals).toEqual([]);
});
