import { useEffect } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';
import { setAuthToken } from '../../api/client';
import { useExternalSpoolDisplay } from '../../hooks/useExternalSpoolDisplay';

const prefix = 'printops:external-spool-hidden:v1:http%3A%2F%2Flocalhost%3A3000:user:';
const account = { id: 7, sub: 'account-a', username: 'viewer', role: 'user', is_active: true,
  is_admin: false, auth_source: 'local', groups: [], permissions: [], created_at: '2026-01-01T00:00:00Z' };
let finishLogin: ReturnType<typeof useAuth>['loginWithToken'];
function Probe() {
  const auth = useAuth();
  useEffect(() => { finishLogin = auth.loginWithToken; }, [auth.loginWithToken]);
  const { hidden, setHidden, ready } = useExternalSpoolDisplay('serial-a');
  return <><output data-testid="hidden">{String(hidden)}</output><output data-testid="ready">{String(ready)}</output>
    <output data-testid="loading">{String(auth.loading)}</output><button onClick={() => setHidden(true)}>Hide</button></>;
}

describe('external display with the real session-bound auth provider', () => {
  afterEach(() => {
    setAuthToken(null);
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
  });
  it('does not inherit A preference when delayed /me A arrives after same-ID login B', async () => {
    const storage = new Map([[prefix + 'account-a:printer:serial-a', 'true']]);
    vi.mocked(localStorage.getItem).mockImplementation(key => storage.get(key) ?? null);
    vi.mocked(localStorage.setItem).mockImplementation((key, value) => { storage.set(key, value); });
    vi.mocked(localStorage.removeItem).mockImplementation(key => { storage.delete(key); });
    setAuthToken('session-a');
    let release!: () => void;
    const pending = new Promise<void>(resolve => { release = resolve; });
    let calls = 0;
    server.use(
      http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
      http.get('/api/v1/auth/me', async () => { calls++; await pending; return HttpResponse.json(account); }),
    );
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(calls).toBe(1));
    act(() => finishLogin('session-b', { ...account, sub: 'account-b' }));
    await act(async () => { release(); });
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expect(screen.getByTestId('ready')).toHaveTextContent('true');
    expect(screen.getByTestId('hidden')).toHaveTextContent('false');
    fireEvent.click(screen.getByText('Hide'));
    expect(storage.get(prefix + 'account-b:printer:serial-a')).toBe('true');
    act(() => setAuthToken('unverified-session'));
    expect(screen.getByTestId('hidden')).toHaveTextContent('false');
    expect(screen.getByTestId('ready')).toHaveTextContent('false');
  });
});
