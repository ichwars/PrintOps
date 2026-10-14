import { useEffect } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';
import { setAuthToken } from '../../api/client';
import { usePrinterCardTextScale } from '../../hooks/usePrinterCardTextScale';
import { PrinterCardTextScaleControl } from '../../pages/printers/PrinterCardTextScale';

const prefix = 'printops:card-text-scale:v1:http%3A%2F%2Flocalhost%3A3000:';
const account = { id: 7, sub: 'provider-account', username: 'viewer', role: 'user', is_active: true,
  is_admin: false, auth_source: 'local', groups: [], permissions: [], created_at: '2026-01-01T00:00:00Z' };
let refresh: () => Promise<void>;
let finishLogin: ReturnType<typeof useAuth>['loginWithToken'];
function Probe() {
  const auth = useAuth();
  const preference = usePrinterCardTextScale();
  useEffect(() => {
    refresh = auth.refreshAuth;
    finishLogin = auth.loginWithToken;
  }, [auth]);
  return <>
    <output data-testid="verified">{String(auth.authStatusVerified)}</output>
    <output data-testid="loading">{String(auth.loading)}</output>
    <output data-testid="scale">{preference.scale}</output>
    <output data-testid="ready">{String(preference.ready)}</output>
    <button onClick={() => preference.setScale(90)}>Attempt preference write</button>
    <PrinterCardTextScaleControl />
  </>;
}
const expectUnavailable = () => {
  expect(screen.getByTestId('scale')).toHaveTextContent('100');
  expect(screen.getByTestId('ready')).toHaveTextContent('false');
  expect(screen.getByRole('combobox', { name: 'Card text and icons' })).toBeDisabled();
};

describe('card scale with real auth-status provenance', () => {
  let storage: Map<string, string>;
  beforeEach(() => {
    storage = new Map([[prefix + 'appliance', '120'], [prefix + 'user:provider-account', '110']]);
    vi.mocked(localStorage.getItem).mockImplementation(key => storage.get(key) ?? null);
    vi.mocked(localStorage.setItem).mockImplementation((key, value) => { storage.set(key, value); });
    vi.mocked(localStorage.removeItem).mockImplementation(key => { storage.delete(key); });
    setAuthToken(null);
    window.history.replaceState({}, '', '/');
  });
  afterEach(() => {
    setAuthToken(null);
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
  });

  it('rejects the appliance preference after an actual status network failure, then recovers to the verified scope', async () => {
    let mode: 'error' | 'on' | 'off' = 'error';
    server.use(
      http.get('/api/v1/auth/status', () => mode === 'error' ? HttpResponse.error()
        : HttpResponse.json({ auth_enabled: mode === 'on', requires_setup: false })),
      http.get('/api/v1/auth/me', () => HttpResponse.json(account)),
    );
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expectUnavailable();
    fireEvent.click(screen.getByText('Attempt preference write'));
    expect(storage.get(prefix + 'appliance')).toBe('120');
    expect(storage.get(prefix + 'user:provider-account')).toBe('110');

    mode = 'on';
    setAuthToken('provider-test-session');
    await act(async () => { await refresh(); });
    expect(screen.getByTestId('scale')).toHaveTextContent('110');
    expect(screen.getByRole('combobox', { name: 'Card text and icons' })).toBeEnabled();
    fireEvent.click(screen.getByText('Attempt preference write'));
    expect(storage.get(prefix + 'user:provider-account')).toBe('90');
    expect(storage.get(prefix + 'appliance')).toBe('120');

    mode = 'off';
    await act(async () => { await refresh(); });
    expect(screen.getByTestId('scale')).toHaveTextContent('120');
    fireEvent.click(screen.getByText('Attempt preference write'));
    expect(storage.get(prefix + 'appliance')).toBe('90');
  });

  it('clears previously verified auth-off provenance while refreshing and after a failed refresh', async () => {
    server.use(http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: false, requires_setup: false })));
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('scale')).toHaveTextContent('120'));
    let resolveStatus!: () => void;
    const pending = new Promise<void>(resolve => { resolveStatus = resolve; });
    server.use(http.get('/api/v1/auth/status', async () => { await pending; return HttpResponse.error(); }));
    let request!: Promise<void>;
    await act(async () => { request = refresh(); });
    expectUnavailable();
    fireEvent.click(screen.getByText('Attempt preference write'));
    expect(storage.get(prefix + 'appliance')).toBe('120');
    await act(async () => { resolveStatus(); await request; });
    expectUnavailable();
    fireEvent.click(screen.getByText('Attempt preference write'));
    expect(storage.get(prefix + 'appliance')).toBe('120');

    server.use(http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: false, requires_setup: false })));
    await act(async () => { await refresh(); });
    expect(screen.getByTestId('scale')).toHaveTextContent('120');
    expect(screen.getByRole('combobox', { name: 'Card text and icons' })).toBeEnabled();
  });
  it('keeps successful auth-on discovery verified without a user and accepts verified token-login identity', async () => {
    setAuthToken('expired-provider-session');
    server.use(
      http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
      http.get('/api/v1/auth/me', () => HttpResponse.json({ detail: 'Invalid token' }, { status: 401 })),
    );
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expect(screen.getByTestId('verified')).toHaveTextContent('true');
    expectUnavailable();
    act(() => finishLogin('verified-token-session', account));
    expect(screen.getByTestId('scale')).toHaveTextContent('110');
    expect(screen.getByRole('combobox', { name: 'Card text and icons' })).toBeEnabled();
    act(() => window.dispatchEvent(new Event('auth:expired')));
    expectUnavailable();
    expect(storage.get(prefix + 'appliance')).toBe('120');
  });

  it.each(['error', 'off'] as const)('keeps the latest %s provenance when an older successful auth-off lookup arrives', async mode => {
    server.use(http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: false, requires_setup: false })));
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('scale')).toHaveTextContent('120'));
    let releaseOlder!: () => void;
    const pending = new Promise<void>(resolve => { releaseOlder = resolve; });
    let calls = 0;
    server.use(http.get('/api/v1/auth/status', async () => {
      calls += 1;
      if (calls === 1) {
        await pending;
        return HttpResponse.json({ auth_enabled: false, requires_setup: false });
      }
      return mode === 'error' ? HttpResponse.error() : HttpResponse.json({ auth_enabled: false, requires_setup: false });
    }));
    let older!: Promise<void>;
    await act(async () => { older = refresh(); });
    await waitFor(() => expect(calls).toBe(1));
    await act(async () => { await refresh(); });
    if (mode === 'error') expectUnavailable();
    else expect(screen.getByTestId('scale')).toHaveTextContent('120');
    await act(async () => { releaseOlder(); await older; });
    if (mode === 'error') {
      expectUnavailable();
      fireEvent.click(screen.getByText('Attempt preference write'));
      expect(storage.get(prefix + 'appliance')).toBe('120');
    } else {
      expect(screen.getByTestId('scale')).toHaveTextContent('120');
      expect(screen.getByRole('combobox', { name: 'Card text and icons' })).toBeEnabled();
    }
  });

});
