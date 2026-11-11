import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { ApiError, api, getAuthSessionId, subscribeAuthSession, getAuthToken, getTokenExpiry, getTokenPersistence, setAuthToken } from '../api/client';
import type { LoginResponse, Permission, TokenPersistence, UserResponse } from '../api/client';

// Renew the token this long before it actually expires, so a request made
// right at the boundary doesn't race an expiring token.
const REFRESH_BUFFER_MS = 5 * 60 * 1000;
// setTimeout delays overflow past ~24.8 days (2^31-1 ms); the admin-configurable
// session ceiling is 30 days, so long-lived tokens must reschedule in chunks.
const MAX_TIMEOUT_MS = 20 * 24 * 60 * 60 * 1000;

interface AuthContextType {
  user: UserResponse | null;
  authEnabled: boolean;
  /** Server-confirmed auth mode; false while discovery is pending or failed. */
  authStatusVerified: boolean;
  /** Stable public subject verified in the active session, independent of late user responses. */
  preferenceSubject: string | null;
  /** Login/status-check epoch of the verified subject; preserved only by silent renewal. */
  authenticationEpoch: number | null;
  requiresSetup: boolean;
  loading: boolean;
  authRetrying: boolean;
  isAdmin: boolean;
  /** Login with username/password. Returns LoginResponse (may include requires_2fa). */
  login: (username: string, password: string, persistence?: TokenPersistence) => Promise<LoginResponse>;
  /** Finalise login after 2FA or OIDC — store token and set user directly. */
  loginWithToken: (token: string, user: UserResponse, persistence?: TokenPersistence) => void;
  logout: () => void;
  refreshUser: () => Promise<void>;
  refreshAuth: () => Promise<void>;
  hasPermission: (permission: Permission) => boolean;
  hasAnyPermission: (...permissions: Permission[]) => boolean;
  hasAllPermissions: (...permissions: Permission[]) => boolean;
  canModify: (resource: 'queue' | 'archives' | 'library', action: 'update' | 'delete' | 'reprint', createdById: number | null | undefined) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null);
  const [authEnabled, setAuthEnabled] = useState(false);
  const [verifiedAuthMode, setVerifiedAuthMode] = useState<boolean | null>(null);
  const [preferenceIdentity, setPreferenceIdentity] = useState<{ session: number; sub: string; epoch: number } | null>(null);
  const session = useSyncExternalStore(subscribeAuthSession, getAuthSessionId);
  const [requiresSetup, setRequiresSetup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [authRetrying, setAuthRetrying] = useState(false);
  const pendingKioskTokenRef = useRef<string | null>(null);
  const authStatusCheckRef = useRef(0);
  const hasRedirectedRef = useRef(false);
  const mountedRef = useRef(true);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const renewalRef = useRef<Promise<LoginResponse> | null>(null);

  const clearRefreshTimer = () => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  };

  // Silently renew the JWT shortly before it expires so a long-open tab (or,
  // for SSO users, one where a full IdP round-trip would otherwise be needed)
  // doesn't get logged out just because the session lifetime elapsed while
  // the user was actively using the app.
  const scheduleTokenRefresh = useCallback(() => {
    clearRefreshTimer();
    const token = getAuthToken();
    if (!token) return;
    const exp = getTokenExpiry(token); // null for non-JWT tokens (e.g. API keys) — nothing to refresh
    if (exp === null) return;

    const msUntilRefresh = exp * 1000 - Date.now() - REFRESH_BUFFER_MS;
    const delay = Math.max(5000, Math.min(msUntilRefresh, MAX_TIMEOUT_MS));

    refreshTimerRef.current = setTimeout(async () => {
      if (!mountedRef.current) return;
      const currentToken = getAuthToken();
      if (!currentToken) return;
      const currentExp = getTokenExpiry(currentToken);
      if (currentExp !== null && currentExp * 1000 - Date.now() > REFRESH_BUFFER_MS) {
        // Delay was clamped to MAX_TIMEOUT_MS and the token isn't actually due yet.
        scheduleTokenRefresh();
        return;
      }
      const requestSession = getAuthSessionId();
      const check = authStatusCheckRef.current;
      const renewal = api.refreshToken();
      renewalRef.current = renewal;
      try {
        const resp = await renewal;
        if (!mountedRef.current || !resp.access_token || requestSession !== getAuthSessionId()) return;
        const sameCheck = check === authStatusCheckRef.current;
        setAuthToken(resp.access_token, getTokenPersistence());
        const renewedSession = getAuthSessionId();
        // Carry preference proof through renewal only for the session that requested it.
        setPreferenceIdentity(previous => sameCheck && previous?.session === requestSession
          ? { ...previous, session: renewedSession } : null);
        scheduleTokenRefresh();
      } catch {
        // Refresh failed (token already expired/revoked, offline, etc.) — the
        // existing 401 handling (`auth:expired`) takes over on the next
        // authenticated request rather than forcing anything here.
      } finally {
        if (renewalRef.current === renewal) renewalRef.current = null;
      }
    }, delay);
  }, []);

  const persistConfirmedKioskToken = useCallback(() => {
    const token = pendingKioskTokenRef.current;
    if (token && token === getAuthToken()) {
      setAuthToken(token, 'persistent');
      pendingKioskTokenRef.current = null;
    }
  }, []);

  const waitForAuthServer = useCallback(() => {
    setAuthRetrying(true);
    window.dispatchEvent(new Event('auth:recheck'));
  }, []);

  const checkAuthStatus = useCallback(async () => {
    const check = ++authStatusCheckRef.current;
    setVerifiedAuthMode(null);
    setPreferenceIdentity(null);
    try {
      // Bootstrap: if URL has ?token= param, store it session-only first and
      // strip it from the URL. Allows SpoolBuddy kiosk to pass an API key via
      // URL on first load. Persistence to localStorage is deferred until the
      // token has been verified by the server (L-4: prevents session fixation
      // where an attacker-crafted URL immediately persists a forged/stolen token).
      const urlParams = new URLSearchParams(window.location.search);
      const streamingRoute = /^\/(?:overlay\/\d+|camera\/\d+|camwall)\/?$/.test(window.location.pathname);
      const urlToken = streamingRoute ? null : urlParams.get('token');
      if (urlToken) {
        pendingKioskTokenRef.current = urlToken;
        setAuthToken(urlToken, 'session'); // session-only until server confirms it's valid
        urlParams.delete('token');
        const cleanSearch = urlParams.toString();
        const cleanUrl = window.location.pathname
          + (cleanSearch ? `?${cleanSearch}` : '')
          + window.location.hash;
        window.history.replaceState({}, '', cleanUrl);
      }

      const status = await api.getAuthStatus();
      if (!mountedRef.current || check !== authStatusCheckRef.current) return;
      if (typeof status.auth_enabled !== 'boolean') throw new Error('Invalid authentication status');
      setAuthEnabled(status.auth_enabled);
      setRequiresSetup(status.requires_setup);

      setVerifiedAuthMode(status.auth_enabled);
      if (status.auth_enabled) {
        const token = getAuthToken();
        const requestSession = getAuthSessionId();
        if (token) {
          // Validate the stored token. A transient failure here (backend not
          // yet ready after a container/proxy restart, a brief network blip)
          // must NOT discard a valid persisted token — doing so logs the user
          // out and, because the token is deleted, a reload can't recover it
          // (#1889). Only a definitive 401 invalid-token response clears the
          // token, and `request()` already does that clearing + dispatches
          // `auth:expired`; here we just retry the transient cases and keep the
          // token so the session survives a slow load.
          let currentUser: UserResponse | null = null;
          let authFailureStatus: number | undefined;
          const maxAttempts = 3;
          for (let attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
              currentUser = await api.getCurrentUser();
              break;
            } catch (err) {
              if (!mountedRef.current || check !== authStatusCheckRef.current) return;
              // An explicit rejection ends the check. Keep a kiosk key on
              // 403 so the owner can regain access without configuring it again.
              if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
                authFailureStatus = err.status;
                break;
              }
              // Brief startup retries precede the longer background backoff.
              if (attempt < maxAttempts) {
                await new Promise((r) => setTimeout(r, 400 * attempt));
              }
            }
          }
          if (!mountedRef.current || check !== authStatusCheckRef.current || requestSession !== getAuthSessionId()) return;
          if (currentUser) {
            setUser(currentUser);
            setPreferenceIdentity(currentUser.id > 0 && currentUser.sub
              ? { session: requestSession, sub: currentUser.sub, epoch: check } : null);
            // Persist kiosk token only after the server confirms it is valid.
            persistConfirmedKioskToken();
          } else {
            setUser(null);
            if (authFailureStatus === undefined) {
              waitForAuthServer();
              return;
            }
            if (authFailureStatus === 401) setAuthToken(null);
            pendingKioskTokenRef.current = null;
          }
        } else {
          setUser(null);
        }
      } else {
        // Auth not enabled, allow access
        setUser(null);
      }
      setAuthRetrying(false);
    } catch {
      if (!mountedRef.current || check !== authStatusCheckRef.current) return;
      waitForAuthServer();
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [persistConfirmedKioskToken, waitForAuthServer]);

  useEffect(() => {
    mountedRef.current = true;

    // Listen for token-expiry events from the API client. setAuthToken(null)
    // in client.ts only clears storage; without this listener, `user` stays
    // populated and ProtectedRoute keeps rendering the protected tree until a
    // manual refresh — every request silently fails in the meantime (#1698).
    const handleAuthExpired = () => {
      if (!mountedRef.current) return;
      authStatusCheckRef.current += 1;
      pendingKioskTokenRef.current = null;
      setAuthRetrying(false);
      setPreferenceIdentity(null);
      setUser(null);
    };
    window.addEventListener('auth:expired', handleAuthExpired);

    let cancelled = false;
    let rechecking = false;
    let retryTimer: number | undefined;
    let retryDelay = 2000;

    // A refused live connection can mean that the authentication mode or
    // current permissions changed while this tab was open.
    const recheckAuth = async () => {
      if (cancelled || rechecking) return;
      window.clearTimeout(retryTimer);
      rechecking = true;
      const check = authStatusCheckRef.current;
      let requestSession = getAuthSessionId();
      const isCurrent = () => !cancelled && check === authStatusCheckRef.current
        && requestSession === getAuthSessionId();
      try {
        // The server revokes the old JWT while renewing it. A socket can
        // close in that interval, before this tab stores the replacement.
        const renewal = renewalRef.current;
        if (renewal) {
          await renewal.catch(() => undefined);
          requestSession = getAuthSessionId();
          if (!isCurrent()) return;
        }
        const status = await api.getAuthStatus();
        if (!isCurrent()) return;
        if (typeof status.auth_enabled !== 'boolean') throw new Error('Invalid authentication status');

        setAuthEnabled(status.auth_enabled);
        setVerifiedAuthMode(status.auth_enabled);
        setRequiresSetup(status.requires_setup);
        if (!status.auth_enabled || !getAuthToken()) {
          setUser(null);
          setPreferenceIdentity(null);
        } else {
          try {
            const currentUser = await api.getCurrentUser();
            if (!isCurrent()) return;
            setUser(currentUser);
            persistConfirmedKioskToken();
            setPreferenceIdentity(previous => currentUser.id > 0 && currentUser.sub
              ? { session: requestSession, sub: currentUser.sub,
                  epoch: previous?.session === requestSession && previous.sub === currentUser.sub ? previous.epoch : check }
              : null);
          } catch (error) {
            if (!isCurrent()) return;
            if (!(error instanceof ApiError) || (error.status !== 401 && error.status !== 403)) throw error;
            // Keep a kiosk key when its owner has temporarily lost access.
            if (error.status === 401) setAuthToken(null);
            pendingKioskTokenRef.current = null;
            setUser(null);
            setPreferenceIdentity(null);
          }
        }
        retryDelay = 2000;
        setAuthRetrying(false);
      } catch {
        if (!isCurrent()) return;
        retryTimer = window.setTimeout(recheckAuth, retryDelay);
        retryDelay = Math.min(retryDelay * 2, 60000);
      } finally {
        rechecking = false;
      }
    };
    window.addEventListener('auth:recheck', recheckAuth);
    void checkAuthStatus();

    return () => {
      mountedRef.current = false;
      authStatusCheckRef.current += 1;
      window.removeEventListener('auth:expired', handleAuthExpired);
      cancelled = true;
      window.removeEventListener('auth:recheck', recheckAuth);
      window.clearTimeout(retryTimer);
      clearRefreshTimer();
    };
  }, [checkAuthStatus, persistConfirmedKioskToken]);

  // (Re)schedule silent renewal whenever a user session becomes active (initial
  // load, login, 2FA/OIDC completion) and stop it once logged out.
  useEffect(() => {
    if (user) {
      scheduleTokenRefresh();
    } else {
      clearRefreshTimer();
    }
  }, [user, scheduleTokenRefresh]);

  // Separate effect to handle redirect only when setup is required
  useEffect(() => {
    // Only redirect if setup is truly required (first time setup)
    // Don't redirect if user manually navigated to /setup or is on camera page
    if (!loading && !authRetrying && requiresSetup && !authEnabled) {
      const currentPath = window.location.pathname;
      // Only redirect if not already on setup page or camera page, and haven't redirected yet
      if (currentPath !== '/setup' && !currentPath.startsWith('/camera/') && !hasRedirectedRef.current) {
        hasRedirectedRef.current = true;
        window.location.href = '/setup';
      }
    } else if (!requiresSetup) {
      // Reset redirect flag when setup is no longer required
      hasRedirectedRef.current = false;
    }
  }, [loading, authRetrying, requiresSetup, authEnabled]);

  const login = async (username: string, password: string, persistence: TokenPersistence = 'session'): Promise<LoginResponse> => {
    const response = await api.login({ username, password });
    if (!response.requires_2fa && response.access_token) {
      setAuthToken(response.access_token, persistence);
      await checkAuthStatus();
    }
    return response;
  };

  const loginWithToken = (token: string, userObj: UserResponse, persistence: TokenPersistence = 'session') => {
    authStatusCheckRef.current += 1;
    setAuthToken(token, persistence);
    setUser(userObj);
    setAuthRetrying(false);
    setAuthEnabled(true);
    setVerifiedAuthMode(true);
    setPreferenceIdentity(userObj.id > 0 && userObj.sub
      ? { session: getAuthSessionId(), sub: userObj.sub, epoch: authStatusCheckRef.current } : null);
  };

  const logout = () => {
    authStatusCheckRef.current += 1;
    setPreferenceIdentity(null);
    setVerifiedAuthMode(null);
    clearRefreshTimer();
    const revoke = api.logout();
    setAuthToken(null);
    setUser(null);
    void revoke.catch(() => {
      // Ignore logout errors
    });
    window.location.href = '/login';
  };

  const refreshUser = async () => {
    if (authEnabled && getAuthToken()) {
      const check = authStatusCheckRef.current;
      const requestSession = getAuthSessionId();
      try {
        const currentUser = await api.getCurrentUser();
        if (mountedRef.current) {
          setUser(currentUser);
          if (check === authStatusCheckRef.current && requestSession === getAuthSessionId()) {
            setPreferenceIdentity(currentUser.id > 0 && currentUser.sub
              ? { session: requestSession, sub: currentUser.sub, epoch: check } : null);
          }
        }
      } catch {
        setAuthToken(null);
        if (mountedRef.current) {
          setPreferenceIdentity(null);
          setUser(null);
        }
      }
    }
  };

  const refreshAuth = async () => {
    await checkAuthStatus();
  };

  // Memoize permission set for efficient lookups
  const permissionSet = useMemo(() => {
    return new Set(user?.permissions ?? []);
  }, [user?.permissions]);

  // Computed admin status
  const isAdmin = useMemo(() => {
    if (!authEnabled) return true; // Auth disabled = admin access
    return user?.is_admin ?? false;
  }, [authEnabled, user?.is_admin]);

  // Permission check functions
  const hasPermission = useCallback((permission: Permission): boolean => {
    if (!authEnabled) return true; // Auth disabled = allow all
    if (isAdmin) return true; // Admins have all permissions
    return permissionSet.has(permission);
  }, [authEnabled, isAdmin, permissionSet]);

  const hasAnyPermission = useCallback((...permissions: Permission[]): boolean => {
    if (!authEnabled) return true;
    if (isAdmin) return true;
    return permissions.some(p => permissionSet.has(p));
  }, [authEnabled, isAdmin, permissionSet]);

  const hasAllPermissions = useCallback((...permissions: Permission[]): boolean => {
    if (!authEnabled) return true;
    if (isAdmin) return true;
    return permissions.every(p => permissionSet.has(p));
  }, [authEnabled, isAdmin, permissionSet]);

  // Ownership-based permission check
  const canModify = useCallback((
    resource: 'queue' | 'archives' | 'library',
    action: 'update' | 'delete' | 'reprint',
    createdById: number | null | undefined,
  ): boolean => {
    if (!authEnabled) return true;  // Auth disabled, allow all
    if (isAdmin) return true;  // Admins can modify anything

    const allPerm = `${resource}:${action}_all` as Permission;
    const ownPerm = `${resource}:${action}_own` as Permission;

    // User has *_all permission - can modify any item
    if (permissionSet.has(allPerm)) return true;

    // User has *_own permission - can only modify their own items
    if (permissionSet.has(ownPerm)) {
      // Ownerless items (null created_by_id) require *_all permission
      if (createdById == null) return false;
      return createdById === user?.id;
    }

    return false;
  }, [authEnabled, isAdmin, permissionSet, user?.id]);

  return (
    <AuthContext.Provider
      value={{
        user,
        authEnabled,
        authStatusVerified: verifiedAuthMode !== null && verifiedAuthMode === authEnabled,
        preferenceSubject: preferenceIdentity?.session === session ? preferenceIdentity.sub : null,
        authenticationEpoch: preferenceIdentity?.session === session ? preferenceIdentity.epoch : null,
        requiresSetup,
        loading,
        authRetrying,
        isAdmin,
        login,
        loginWithToken,
        logout,
        refreshUser,
        refreshAuth,
        hasPermission,
        hasAnyPermission,
        hasAllPermissions,
        canModify,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
