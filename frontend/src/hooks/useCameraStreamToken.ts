import { useEffect, useRef, useSyncExternalStore } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, getAuthSessionId, subscribeAuthSession, setStreamToken, getStreamToken, withStreamToken, setMediaToken, getMediaToken } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

type TokenKind = 'media' | 'camera';

const mediaPaths = [
  /^\/api\/v1\/library\/files\/\d+\/(?:thumbnail|plate-thumbnail\/\d+|photos\/[^/]+)$/,
  /^\/api\/v1\/archives\/\d+\/(?:thumbnail|plate-thumbnail\/\d+|plate-preview|timelapse|photos\/.+|qrcode|project-image\/.+)$/,
  /^\/api\/v1\/print-log\/\d+\/thumbnail$/,
  /^\/api\/v1\/projects\/\d+\/cover-image$/,
  /^\/api\/v1\/calculations\/project-files\/\d+\/plates\/\d+\/thumbnail$/,
  /^\/api\/v1\/external-links\/\d+\/icon$/,
  /^\/api\/v1\/printers\/\d+\/(?:cover|files\/plate-thumbnail\/\d+)$/,
];

function tokenKindForUrl(src: string): TokenKind | null {
  let url: URL;
  try { url = new URL(src, window.location.origin); } catch { return null; }
  // Never put credentials on another origin or unrelated API routes.
  if (url.origin !== window.location.origin) return null;
  if (/^\/api\/v1\/printers\/\d+\/camera\//.test(url.pathname)) return 'camera';
  if (mediaPaths.some((pattern) => pattern.test(url.pathname))) return 'media';
  return null;
}

/** Retrofit only local media URLs belonging to this credential type. */
export function rewriteMediaSrcWithToken(root: ParentNode, token: string, kind: TokenKind = 'media'): number {
  const explicitStreamToken = /^\/(?:overlay\/\d+|camera\/\d+|camwall)\/?$/.test(window.location.pathname)
    ? new URLSearchParams(window.location.search).get('token') : null;
  const tokenParam = `token=${encodeURIComponent(token)}`;
  let updated = 0;
  root.querySelectorAll<HTMLImageElement | HTMLVideoElement>('img[src*="/api/v1/"], video[src*="/api/v1/"]').forEach((el) => {
    const src = el.getAttribute('src') || '';
    if (tokenKindForUrl(src) !== kind) return;
    const url = new URL(src, window.location.origin);
    if (kind === 'camera' && explicitStreamToken && url.searchParams.get('token') === explicitStreamToken) return;
    if (url.searchParams.get('token') === token) return;
    const withoutToken = src.replace(/([?&])token=[^&#]*(&|(?=#)|$)/, (_m, pre, post) => post === '&' ? pre : '');
    const hashIndex = withoutToken.indexOf('#');
    const base = hashIndex < 0 ? withoutToken : withoutToken.slice(0, hashIndex);
    const hash = hashIndex < 0 ? '' : withoutToken.slice(hashIndex);
    el.src = `${base}${base.includes('?') ? '&' : '?'}${tokenParam}${hash}`;
    updated += 1;
  });
  return updated;
}

/** Share one identified media token and, when permitted, one camera token. */
export function useStreamTokenSync() {
  const { authEnabled, user, loading: authLoading, hasPermission } = useAuth();
  const sessionId = useSyncExternalStore(subscribeAuthSession, getAuthSessionId);
  const queryClient = useQueryClient();
  const refreshingRef = useRef(new Set<TokenKind>());
  const enabled = !authLoading && (!authEnabled || user !== null);
  const canViewCamera = !authEnabled || hasPermission('camera:view');
  const mediaKey = ['media-token', user?.id ?? null, sessionId];
  const cameraKey = ['camera-stream-token', user?.id ?? null, sessionId];
  const common = { staleTime: 50 * 60 * 1000, refetchInterval: 50 * 60 * 1000 };
  const media = useQuery({ queryKey: mediaKey, queryFn: () => api.getMediaToken(), enabled, ...common });
  const camera = useQuery({ queryKey: cameraKey, queryFn: () => api.getCameraStreamToken(), enabled: enabled && canViewCamera, ...common });

  useEffect(() => {
    const token = enabled && getAuthSessionId() === sessionId ? media.data?.token ?? null : null;
    setMediaToken(token);
    if (token) rewriteMediaSrcWithToken(document, token, 'media');
    return () => setMediaToken(null);
  }, [media.data?.token, enabled, sessionId]);

  useEffect(() => {
    const token = enabled && canViewCamera && getAuthSessionId() === sessionId ? camera.data?.token ?? null : null;
    setStreamToken(token);
    if (token) rewriteMediaSrcWithToken(document, token, 'camera');
    return () => setStreamToken(null);
  }, [camera.data?.token, enabled, canViewCamera, sessionId]);

  // Remove previous sessions, including pending results that could otherwise
  // be cached until the same account signs in again.
  useEffect(() => {
    queryClient.removeQueries({ predicate: (query) =>
      ['media-token', 'camera-stream-token'].includes(String(query.queryKey[0])) && query.queryKey[2] !== sessionId,
    });
  }, [queryClient, sessionId]);

  useEffect(() => {
    if (!authEnabled || !enabled) return;
    const timers = new Set<ReturnType<typeof setTimeout>>();
    const refreshing = refreshingRef.current;
    const handleError = (event: Event) => {
      const el = event.target;
      if (!(el instanceof HTMLImageElement || el instanceof HTMLVideoElement)) return;
      const kind = tokenKindForUrl(el.src);
      if (!kind) return;
      const token = kind === 'camera' ? getStreamToken() : getMediaToken();
      if (!token || new URL(el.src).searchParams.get('token') !== token || refreshing.has(kind)) return;
      refreshing.add(kind);
      queryClient.invalidateQueries({ queryKey: [kind === 'camera' ? 'camera-stream-token' : 'media-token', user?.id ?? null, sessionId], exact: true });
      const timer = setTimeout(() => { refreshing.delete(kind); timers.delete(timer); }, 5000);
      timers.add(timer);
    };
    document.addEventListener('error', handleError, true);
    return () => {
      document.removeEventListener('error', handleError, true);
      timers.forEach(clearTimeout);
      refreshing.clear();
    };
  }, [authEnabled, enabled, queryClient, user?.id, sessionId]);
}

export function useCameraStreamToken() {
  return { withToken: withStreamToken };
}
