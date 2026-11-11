/**
 * Tests for the AuthContext permission helpers.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';
import { ThemeProvider } from '../../contexts/ThemeContext';
import { ToastProvider } from '../../contexts/ToastContext';
import { api, getAuthToken, setAuthToken, type LoginResponse, type Permission } from '../../api/client';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          {/* ThemeProvider sits inside AuthProvider (matches App.tsx
              after the GHSA-r2qv login-page-quiet fix) so its
              useAuth() call resolves. */}
          <AuthProvider>
            <ThemeProvider>
              <ToastProvider>{children}</ToastProvider>
            </ThemeProvider>
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    );
  };
}

describe('AuthContext', () => {
  it.each(['/overlay/1', '/camera/1', '/camwall'])('preserves the streaming token on %s across bootstrap without importing login auth', async (path) => {
    setAuthToken(null);
    window.history.replaceState({}, '', `${path}?token=bblt_fixture&fps=20`);
    server.use(http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })));
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    try {
      expect(window.location.search).toBe('?token=bblt_fixture&fps=20');
      expect(getAuthToken()).toBeNull();
    } finally {
      window.history.replaceState({}, '', '/');
      setAuthToken(null);
    }
  });

  it('retains the existing API-key bootstrap on ordinary app routes', async () => {
    setAuthToken(null);
    window.history.replaceState({}, '', '/dashboard?token=bb_fixture&tab=printers');
    server.use(http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })));
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.loading).toBe(false));
    try {
      expect(window.location.search).toBe('?tab=printers');
      expect(getAuthToken()).toBe('bb_fixture');
    } finally {
      window.history.replaceState({}, '', '/');
      setAuthToken(null);
    }
  });

  describe('when auth is disabled', () => {
    beforeEach(() => {
      server.use(
        http.get('/api/v1/auth/status', () => {
          return HttpResponse.json({
            auth_enabled: false,
            requires_setup: false,
          });
        })
      );
    });

    it('authEnabled is false', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.authEnabled).toBe(false);
      });
    });

    it('hasPermission returns true for any permission when auth disabled', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.authEnabled).toBe(false);
      });

      // When auth is disabled, all permissions should be granted
      expect(result.current.hasPermission('printers:read' as Permission)).toBe(true);
      expect(result.current.hasPermission('settings:update' as Permission)).toBe(true);
      expect(result.current.hasPermission('users:delete' as Permission)).toBe(true);
    });

    it('hasAnyPermission returns true for any permissions when auth disabled', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.authEnabled).toBe(false);
      });

      expect(
        result.current.hasAnyPermission('printers:read' as Permission, 'settings:update' as Permission)
      ).toBe(true);
    });

    it('hasAllPermissions returns true for any permissions when auth disabled', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.authEnabled).toBe(false);
      });

      expect(
        result.current.hasAllPermissions('printers:read' as Permission, 'settings:update' as Permission)
      ).toBe(true);
    });
  });

  describe('when auth requires setup', () => {
    beforeEach(() => {
      server.use(
        http.get('/api/v1/auth/status', () => {
          return HttpResponse.json({
            auth_enabled: false,
            requires_setup: true,
          });
        })
      );
    });

    it('requiresSetup is true', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.requiresSetup).toBe(true);
      });
    });
  });

  describe('when auth is enabled but not logged in', () => {
    beforeEach(() => {
      // Clear any stored token
      localStorage.removeItem('auth_token');

      server.use(
        http.get('/api/v1/auth/status', () => {
          return HttpResponse.json({
            auth_enabled: true,
            requires_setup: false,
          });
        })
      );
    });

    it('user is null when not logged in', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.authEnabled).toBe(true);
      });

      // User should be null when not logged in
      expect(result.current.user).toBeNull();
    });

    it('hasPermission returns false when not logged in', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.authEnabled).toBe(true);
      });

      // Without a user, permissions should be denied
      expect(result.current.hasPermission('printers:read' as Permission)).toBe(false);
    });
  });

  describe('CVE-2026-25505 fix: auth disabled grants all access', () => {
    beforeEach(() => {
      server.use(
        http.get('/api/v1/auth/status', () => {
          return HttpResponse.json({
            auth_enabled: false,
            requires_setup: false,
          });
        })
      );
    });

    it('isAdmin is true when auth is disabled', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // When auth disabled, user is treated as admin
      expect(result.current.isAdmin).toBe(true);
    });

    it('canModify allows all modifications when auth disabled', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // All canModify checks should pass when auth is disabled
      expect(result.current.canModify('queue', 'update', 1)).toBe(true);
      expect(result.current.canModify('queue', 'update', 999)).toBe(true);
      expect(result.current.canModify('queue', 'update', null)).toBe(true);
      expect(result.current.canModify('archives', 'delete', 1)).toBe(true);
      expect(result.current.canModify('library', 'update', null)).toBe(true);
    });

    it('all permissions are granted when auth is disabled', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      // All permission checks should pass
      expect(result.current.hasPermission('archives:read' as Permission)).toBe(true);
      expect(result.current.hasPermission('archives:delete_all' as Permission)).toBe(true);
      expect(result.current.hasPermission('settings:update' as Permission)).toBe(true);
      expect(result.current.hasPermission('api_keys:create' as Permission)).toBe(true);
      expect(result.current.hasPermission('groups:delete' as Permission)).toBe(true);
    });

    it('hasAnyPermission returns true for protected permissions', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(
        result.current.hasAnyPermission(
          'api_keys:create' as Permission,
          'groups:delete' as Permission
        )
      ).toBe(true);
    });

    it('hasAllPermissions returns true for any combination', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.loading).toBe(false);
      });

      expect(
        result.current.hasAllPermissions(
          'settings:update' as Permission,
          'api_keys:create' as Permission,
          'groups:delete' as Permission
        )
      ).toBe(true);
    });
  });

  describe('auth:expired event (#1698)', () => {
    beforeEach(() => {
      // authToken is a module-level variable initialised once at import time;
      // writing to sessionStorage after import doesn't propagate. Use the
      // canonical setter so checkAuthStatus() finds the token and loads /me.
      setAuthToken('valid-token');
      server.use(
        http.get('/api/v1/auth/status', () => {
          return HttpResponse.json({
            auth_enabled: true,
            requires_setup: false,
          });
        })
      );
    });

    afterEach(() => {
      setAuthToken(null);
    });

    it('clears user when an auth:expired event is dispatched', async () => {
      const { result } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      // Wait for the initial user load from /auth/me.
      await waitFor(() => {
        expect(result.current.user).not.toBeNull();
      });

      // Simulate client.ts dispatching the event after a 401 + token clear.
      act(() => {
        window.dispatchEvent(new CustomEvent('auth:expired'));
      });

      // User is cleared synchronously — ProtectedRoute (App.tsx:101) sees
      // user === null and redirects to /login on the next render.
      await waitFor(() => {
        expect(result.current.user).toBeNull();
      });
    });

    it('does not crash when the event fires after unmount', async () => {
      const { result, unmount } = renderHook(() => useAuth(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.user).not.toBeNull();
      });

      unmount();

      // mountedRef guards setUser; dispatching after unmount must be a no-op,
      // not a React state-update-after-unmount warning.
      expect(() => {
        window.dispatchEvent(new CustomEvent('auth:expired'));
      }).not.toThrow();
    });
  });

  describe('token validation on mount (#1889)', () => {
    beforeEach(() => {
      // Persisted "Remember Me" token — lives in localStorage.
      setAuthToken('valid-token', 'persistent');
      server.use(
        http.get('/api/v1/auth/status', () =>
          HttpResponse.json({ auth_enabled: true, requires_setup: false })
        )
      );
    });

    afterEach(() => {
      setAuthToken(null);
      localStorage.removeItem('auth_token');
    });

    it('keeps the persisted token when /auth/me fails transiently (does not force re-login)', async () => {
      // Backend not ready yet / brief blip → 500 on every attempt.
      server.use(http.get('/api/v1/auth/me', () => new HttpResponse(null, { status: 500 })));
      vi.mocked(window.localStorage.removeItem).mockClear();

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 4000 });

      // No user this load, but the token MUST survive so a reload can recover —
      // the pre-#1889 blanket catch deleted it, making the session unrecoverable.
      expect(result.current.user).toBeNull();
      expect(getAuthToken()).toBe('valid-token');
      // Persisted copy must not be wiped (setAuthToken(null) removes it).
      expect(window.localStorage.removeItem).not.toHaveBeenCalledWith('auth_token');
    });

    it('clears the token on a definitive 401 invalid-token response', async () => {
      server.use(
        http.get('/api/v1/auth/me', () =>
          HttpResponse.json({ detail: 'Could not validate credentials' }, { status: 401 })
        )
      );
      vi.mocked(window.localStorage.removeItem).mockClear();

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.loading).toBe(false), { timeout: 4000 });

      expect(result.current.user).toBeNull();
      expect(getAuthToken()).toBeNull();
      // Definitive invalid-token → persisted copy is removed.
      expect(window.localStorage.removeItem).toHaveBeenCalledWith('auth_token');
    });

    it('loads the user when the persisted token is valid', async () => {
      server.use(
        http.get('/api/v1/auth/me', () =>
          HttpResponse.json({
            id: 1,
            username: 'alice',
            is_active: true,
            permissions: [],
            groups: [],
          })
        )
      );

      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });

      await waitFor(() => expect(result.current.user).not.toBeNull());
      expect(result.current.user?.username).toBe('alice');
      expect(getAuthToken()).toBe('valid-token');
    });
  });

  it('confirms and persists a new kiosk key after the auth status endpoint recovers', async () => {
    setAuthToken(null);
    vi.mocked(localStorage.setItem).mockClear();
    window.history.replaceState({}, '', '/spoolbuddy?token=bb_new_kiosk');
    let statusAvailable = false;
    server.use(
      http.get('/api/v1/auth/status', () => statusAvailable
        ? HttpResponse.json({ auth_enabled: true, requires_setup: false })
        : HttpResponse.json({ detail: 'Temporary outage' }, { status: 503 })),
      http.get('/api/v1/auth/me', () => HttpResponse.json({
        id: 0, username: 'api-key', is_active: true, permissions: [], groups: [],
      })),
    );
    try {
      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.authRetrying).toBe(true));
      expect(result.current.authStatusVerified).toBe(false);
      expect(getAuthToken()).toBe('bb_new_kiosk');
      expect(localStorage.setItem).not.toHaveBeenCalledWith('auth_token', 'bb_new_kiosk');
      expect(window.location.search).toBe('');

      statusAvailable = true;
      await waitFor(() => expect(result.current.user?.username).toBe('api-key'), { timeout: 4000 });
      expect(result.current.authRetrying).toBe(false);
      expect(result.current.authStatusVerified).toBe(true);
      expect(localStorage.setItem).toHaveBeenCalledWith('auth_token', 'bb_new_kiosk');
    } finally {
      window.history.replaceState({}, '', '/');
      setAuthToken(null);
    }
  });

  it('waits without opening an anonymous dashboard when authentication discovery fails', async () => {
    setAuthToken(null);
    let statusAvailable = false;
    server.use(http.get('/api/v1/auth/status', () => statusAvailable
      ? HttpResponse.json({ auth_enabled: true, requires_setup: false })
      : HttpResponse.json({}, { status: 503 })));
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.authRetrying).toBe(true));
    expect(result.current.authStatusVerified).toBe(false);

    statusAvailable = true;
    await waitFor(() => expect(result.current.authRetrying).toBe(false), { timeout: 4000 });
    expect(result.current.authEnabled).toBe(true);
    expect(result.current.user).toBeNull();
  });

  it('uses the renewed JWT when a live socket closes during silent renewal', async () => {
    const initialJwt = `fixture.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 60 }))}.signature`;
    const replacementJwt = 'renewed-session';
    setAuthToken(initialJwt);
    const status = vi.fn(() => HttpResponse.json({ auth_enabled: true, requires_setup: false }));
    const currentUser = vi.fn(({ request }: { request: Request }) => {
      const authorization = request.headers.get('Authorization');
      return HttpResponse.json({ id: 1, username: authorization === `Bearer ${initialJwt}` ? 'original' : 'renewed', is_active: true });
    });
    let finishRenewal!: (value: LoginResponse) => void;
    const pending = new Promise<LoginResponse>(resolve => { finishRenewal = resolve; });
    const refresh = vi.spyOn(api, 'refreshToken').mockReturnValue(pending);
    const timers = vi.spyOn(globalThis, 'setTimeout');
    server.use(http.get('/api/v1/auth/status', status), http.get('/api/v1/auth/me', currentUser));
    try {
      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.user?.username).toBe('original'));
      const scheduled = timers.mock.calls.find(([callback, delay]) => typeof callback === 'function' && delay === 5000);
      expect(scheduled).toBeDefined();
      act(() => { (scheduled![0] as () => void)(); });
      expect(refresh).toHaveBeenCalledTimes(1);

      await act(async () => { window.dispatchEvent(new Event('auth:recheck')); });
      expect(status).toHaveBeenCalledTimes(1);
      finishRenewal({ access_token: replacementJwt });
      await waitFor(() => expect(result.current.user?.username).toBe('renewed'));
      expect(getAuthToken()).toBe(replacementJwt);
      expect(status).toHaveBeenCalledTimes(2);
    } finally {
      timers.mockRestore();
      refresh.mockRestore();
      setAuthToken(null);
    }
  });

  it('sends the issuing JWT for revocation before clearing the browser session', async () => {
    setAuthToken('session-to-revoke');
    const revoke = vi.fn(({ request }: { request: Request }) => {
      expect(request.headers.get('Authorization')).toBe('Bearer session-to-revoke');
      expect(request.keepalive).toBe(true);
      return HttpResponse.json({ message: 'Logged out' });
    });
    server.use(
      http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
      http.get('/api/v1/auth/me', () => HttpResponse.json({
        id: 1, username: 'alice', is_active: true, permissions: [], groups: [],
      })),
      http.post('/api/v1/auth/logout', revoke),
    );
    const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.user?.username).toBe('alice'));
    act(() => result.current.logout());
    expect(getAuthToken()).toBeNull();
    expect(result.current.user).toBeNull();
    await waitFor(() => expect(revoke).toHaveBeenCalledTimes(1));
  });

  describe('live connection auth recheck', () => {
    const user = { id: 1, username: 'alice', sub: 'alice-sub', is_active: true, permissions: [], groups: [] };

    afterEach(() => setAuthToken(null));

    it('updates an open anonymous tab when the server enables login', async () => {
      let enabled = false;
      setAuthToken(null);
      server.use(http.get('/api/v1/auth/status', () =>
        HttpResponse.json({ auth_enabled: enabled, requires_setup: false })));
      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.authStatusVerified).toBe(true));
      expect(result.current.authEnabled).toBe(false);

      enabled = true;
      act(() => { window.dispatchEvent(new Event('auth:recheck')); });
      await waitFor(() => expect(result.current.authEnabled).toBe(true));
      expect(result.current.user).toBeNull();
      expect(result.current.authStatusVerified).toBe(true);
    });

    it.each([401, 403])('clears the active user after a definitive %s from the server', async (status) => {
      let denied = false;
      const token = status === 403 ? 'bb_kiosk' : 'valid-token';
      setAuthToken(token, 'persistent');
      server.use(
        http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
        http.get('/api/v1/auth/me', () => denied
          ? HttpResponse.json({ detail: 'Token has been revoked' }, { status })
          : HttpResponse.json(user)),
      );
      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.user?.username).toBe('alice'));

      denied = true;
      act(() => { window.dispatchEvent(new Event('auth:recheck')); });
      await waitFor(() => expect(result.current.user).toBeNull());
      expect(result.current.authEnabled).toBe(true);
      expect(result.current.preferenceSubject).toBeNull();
      expect(getAuthToken()).toBe(status === 403 ? token : null);
    });

    it('keeps the active session during a failed status probe and retries when the server returns', async () => {
      setAuthToken('valid-token', 'persistent');
      const statusReply = vi.fn(() => HttpResponse.json({ auth_enabled: true, requires_setup: false }));
      server.use(
        http.get('/api/v1/auth/status', statusReply),
        http.get('/api/v1/auth/me', () => HttpResponse.json(user)),
      );
      const { result } = renderHook(() => useAuth(), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.user?.username).toBe('alice'));

      statusReply.mockClear();
      statusReply.mockImplementationOnce(() => HttpResponse.json({}, { status: 503 }));
      statusReply.mockImplementationOnce(() => HttpResponse.json({ auth_enabled: false, requires_setup: false }));
      act(() => { window.dispatchEvent(new Event('auth:recheck')); });
      await waitFor(() => expect(statusReply).toHaveBeenCalledTimes(1));
      expect(result.current.authEnabled).toBe(true);
      expect(result.current.user?.username).toBe('alice');
      expect(getAuthToken()).toBe('valid-token');

      await waitFor(() => expect(result.current.authEnabled).toBe(false), { timeout: 4000 });
      expect(statusReply).toHaveBeenCalledTimes(2);
      expect(result.current.authStatusVerified).toBe(true);
    });
  });
});
