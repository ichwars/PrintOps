import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import App from '../App';
import { setAuthToken } from '../api/client';
import { server } from './mocks/server';

let permissions: string[];
let settingsRequests: number;
let profileOptionsRequests: number;
let connectionRequests: number;

beforeEach(() => {
  permissions = ['accounting_integrations:manage'];
  settingsRequests = profileOptionsRequests = connectionRequests = 0;
  vi.mocked(localStorage.getItem).mockReturnValue(null);
  setAuthToken('integration-route-test-token');
  server.use(
    http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/auth/me', () => HttpResponse.json({
      id: 41, username: 'integration-manager', role: 'user', is_admin: false,
      is_active: true, groups: [], permissions, created_at: '2026-01-01T00:00:00Z',
    })),
    http.get('/api/v1/settings/', () => {
      settingsRequests += 1;
      return HttpResponse.json({ detail: 'Forbidden' }, { status: 403 });
    }),
    http.get('/api/v1/business-profiles/options', () => {
      profileOptionsRequests += 1;
      return HttpResponse.json([{ id: 7, name: 'Delegated profile', is_active: true }]);
    }),
    http.get('/api/v1/lexware/connections', () => {
      connectionRequests += 1;
      return HttpResponse.json([]);
    }),
  );
});

afterEach(() => setAuthToken(null));

describe('delegated Lexware settings routing', () => {
  it('admits integration managers only to the isolated Lexware panel', async () => {
      window.history.replaceState({}, '', '/settings?tab=orders-calculation&sub=lexware');
      render(<App />);
      expect(await screen.findByRole('heading', { name: 'Lexware Office', level: 1 })).toBeInTheDocument();
      expect(await screen.findByRole('button', { name: 'Set up connection' })).toBeInTheDocument();
      expect(connectionRequests).toBe(1);
      expect(profileOptionsRequests).toBe(1);
      expect(settingsRequests).toBe(0);
      expect(document.querySelector('aside a[href="/settings"]')).toBeInTheDocument();
      expect(document.querySelector('aside a[href="/settings?tab=orders-calculation"]')).toBeInTheDocument();
      expect(document.querySelector('aside a[href="/settings?tab=users-security"]')).not.toBeInTheDocument();
      act(() => {
        window.history.pushState({}, '', '/settings?tab=users-security');
        window.dispatchEvent(new PopStateEvent('popstate'));
      });
      expect(screen.getByRole('heading', { name: 'Lexware Office', level: 1 })).toBeInTheDocument();
      expect(settingsRequests).toBe(0);
  });

  it('does not admit a user without either settings or integration permissions', async () => {
    permissions = ['stats:read'];
    window.history.replaceState({}, '', '/settings?tab=orders-calculation&sub=lexware');
    render(<App />);
    await waitFor(() => expect(window.location.pathname).not.toBe('/settings'));
    expect(screen.queryByRole('heading', { name: 'Lexware Office' })).not.toBeInTheDocument();
    expect(connectionRequests).toBe(0);
    expect(profileOptionsRequests).toBe(0);
  });
});
