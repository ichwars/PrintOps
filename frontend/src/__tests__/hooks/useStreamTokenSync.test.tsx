/**
 * Tests for the two-token split in useStreamTokenSync (#3025).
 *
 * Thumbnails, plate previews, timelapses, cover images and link icons used to
 * ride on the camera stream token, so a user without camera:view saw broken
 * images everywhere and got a 403 from the camera mint on every page load.
 * The hook now fetches a media token for everyone and asks for a camera token
 * only when the user can actually have one.
 */

import type { ReactNode } from 'react';
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { renderHook, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { useStreamTokenSync } from '../../hooks/useCameraStreamToken';
import { api, getMediaToken, getStreamToken, setAuthToken, setStreamToken } from '../../api/client';

const auth = {
  authEnabled: true,
  user: { id: 7 } as { id: number } | null,
  loading: false,
  granted: ['library:read_own'] as string[],
};

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    authEnabled: auth.authEnabled,
    user: auth.user,
    loading: auth.loading,
    hasPermission: (p: string) => auth.granted.includes(p),
  }),
}));

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

let mediaMints = 0;
let cameraMints = 0;

beforeEach(() => {
  mediaMints = 0;
  cameraMints = 0;
  setAuthToken('session-1');
  auth.authEnabled = true;
  auth.user = { id: 7 };
  auth.loading = false;
  auth.granted = ['library:read_own'];
  server.use(
    http.post('*/api/v1/auth/media-token', () => {
      mediaMints += 1;
      return HttpResponse.json({ token: 'media-tok' });
    }),
    http.post('*/api/v1/printers/camera/stream-token', () => {
      cameraMints += 1;
      return HttpResponse.json({ token: 'camera-tok' });
    })
  );
});

afterEach(() => {
  cleanup();
  setAuthToken(null);
  setStreamToken(null);
});

describe('useStreamTokenSync token split (#3025)', () => {
  it('gives a user without camera:view a media token', async () => {
    renderHook(() => useStreamTokenSync(), { wrapper: wrapper() });
    await waitFor(() => expect(api.getLibraryFileThumbnailUrl(1)).toBe('/api/v1/library/files/1/thumbnail?token=media-tok'));
  });

  it('does not ask the camera mint for a user without camera:view', async () => {
    renderHook(() => useStreamTokenSync(), { wrapper: wrapper() });
    await waitFor(() => expect(mediaMints).toBe(1));
    // The 403 this used to produce on every page load was the reporter's only
    // clue that thumbnails were gated on the camera at all.
    expect(cameraMints).toBe(0);
    expect(getStreamToken()).toBeNull();
  });

  it('fetches both tokens for a user who does have camera:view', async () => {
    auth.granted = ['library:read_own', 'camera:view'];
    renderHook(() => useStreamTokenSync(), { wrapper: wrapper() });
    await waitFor(() => expect(api.getLibraryFileThumbnailUrl(1)).toBe('/api/v1/library/files/1/thumbnail?token=media-tok'));
    await waitFor(() => expect(getStreamToken()).toBe('camera-tok'));
  });

  it('fetches nothing while auth is still bootstrapping', async () => {
    auth.loading = true;
    renderHook(() => useStreamTokenSync(), { wrapper: wrapper() });
    await new Promise((r) => setTimeout(r, 20));
    expect(mediaMints).toBe(0);
    expect(cameraMints).toBe(0);
  });

  it('fetches nothing when auth is enabled and nobody is signed in', async () => {
    auth.user = null;
    renderHook(() => useStreamTokenSync(), { wrapper: wrapper() });
    await new Promise((r) => setTimeout(r, 20));
    expect(mediaMints).toBe(0);
    expect(cameraMints).toBe(0);
  });

  it('fetches both when auth is disabled, where neither mint is gated', async () => {
    auth.authEnabled = false;
    auth.user = null;
    auth.granted = [];
    renderHook(() => useStreamTokenSync(), { wrapper: wrapper() });
    await waitFor(() => expect(api.getLibraryFileThumbnailUrl(1)).toBe('/api/v1/library/files/1/thumbnail?token=media-tok'));
    await waitFor(() => expect(getStreamToken()).toBe('camera-tok'));
  });
});


describe('session isolation', () => {
  it('does not restore cached tokens when the same user logs in again', async () => {
    auth.granted = ['camera:view'];
    const { rerender } = renderHook(() => useStreamTokenSync(), { wrapper: wrapper() });
    await waitFor(() => expect(getStreamToken()).toBe('camera-tok'));
    setAuthToken(null);
    auth.user = null;
    rerender();
    await waitFor(() => expect(getStreamToken()).toBeNull());
    server.use(http.post('*/api/v1/printers/camera/stream-token', () => HttpResponse.json({ token: 'new-camera' })));
    setAuthToken('session-2');
    auth.user = { id: 7 };
    rerender();
    await waitFor(() => expect(getStreamToken()).toBe('new-camera'));
  });

  it('clears URL credentials synchronously when another user signs in', async () => {
    auth.granted = ['camera:view'];
    renderHook(() => useStreamTokenSync(), { wrapper: wrapper() });
    await waitFor(() => expect(getStreamToken()).toBe('camera-tok'));
    setAuthToken('other-user-session');
    expect(getStreamToken()).toBeNull();
    expect(api.getLibraryFileThumbnailUrl(1)).toBe('/api/v1/library/files/1/thumbnail');
  });
});


describe('pending media requests', () => {
  it('does not publish a previous users late token response', async () => {
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    server.use(http.post('*/api/v1/auth/media-token', async ({ request }) => {
      if (request.headers.get('Authorization') === 'Bearer session-1') {
        await pending;
        return HttpResponse.json({ token: 'previous-user-media' });
      }
      return HttpResponse.json({ token: 'current-user-media' });
    }));
    const { rerender } = renderHook(() => useStreamTokenSync(), { wrapper: wrapper() });
    await new Promise((resolve) => setTimeout(resolve, 20));
    setAuthToken('session-2');
    auth.user = { id: 8 };
    rerender();
    await waitFor(() => expect(getMediaToken()).toBe('current-user-media'));
    release();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(getMediaToken()).toBe('current-user-media');
  });
});
