import { useCallback, useEffect, useLayoutEffect, useRef } from 'react';
import { useNavigate } from 'react-router';
import { getAuthSessionId, type ExternalLink } from '../api/client';
import { useTheme } from '../contexts/ThemeContext';

// Control characters are deliberately rejected at the postMessage boundary.
// eslint-disable-next-line no-control-regex
const CONTROL_CHARACTERS = /[\u0000-\u001f\u007f]/;

/** Only explicitly registered, unambiguous HTTP(S) URLs grant bridge authority. */
function registeredOrigin(url: string): string | null {
  if (!/^https?:\/\/[^/]/i.test(url) || /[\s\\]/.test(url) || CONTROL_CHARACTERS.test(url)) return null;
  try {
    const parsed = new URL(url);
    if (parsed.username || parsed.password || !parsed.hostname || parsed.origin === 'null') return null;
    return parsed.origin;
  } catch {
    return null;
  }
}

/** Return the same-origin path plus query/hash; the normal router owns access. */
function inAppPath(path: unknown): string | null {
  if (typeof path !== 'string' || path.length > 512 || !path.startsWith('/') || path.startsWith('//')
    || path.includes('\\') || CONTROL_CHARACTERS.test(path)) return null;
  try {
    const url = new URL(path, window.location.origin);
    if (url.origin !== window.location.origin || url.pathname.startsWith('//')) return null;
    return url.pathname + url.search + url.hash;
  } catch {
    return null;
  }
}

/** A separate keyed lifetime prevents old documents sharing a new link's authority. */
export function SidebarAppFrame({ link, session }: { link: ExternalLink; session: number }) {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const navigate = useNavigate();
  const { resolvedMode, darkStyle, darkBackground, darkAccent, lightStyle, lightBackground, lightAccent } = useTheme();
  const dark = resolvedMode === 'dark';
  const style = dark ? darkStyle : lightStyle;
  const background = dark ? darkBackground : lightBackground;
  const accent = dark ? darkAccent : lightAccent;
  const origin = registeredOrigin(link.url);

  const sendTheme = useCallback(() => {
    const frame = frameRef.current;
    if (!origin || !frame?.contentWindow || getAuthSessionId() !== session) return;
    frame.contentWindow.postMessage(
      { type: 'printops:theme', mode: resolvedMode, style, background, accent, canNavigate: true },
      origin,
    );
  }, [origin, session, resolvedMode, style, background, accent]);

  useEffect(() => sendTheme(), [sendTheme]);
  useLayoutEffect(() => {
    const frame = frameRef.current;
    if (!origin || !frame?.contentWindow) return;
    const onMessage = (event: MessageEvent) => {
      if (getAuthSessionId() !== session || frame !== frameRef.current
        || event.source !== frame.contentWindow || event.origin !== origin) return;
      const data: unknown = event.data;
      if (!data || typeof data !== 'object' || !('type' in data)) return;
      if (data.type === 'printops:theme-request') sendTheme();
      if (data.type === 'printops:navigate' && 'path' in data) {
        const path = inAppPath(data.path);
        if (path !== null) void navigate(path);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [origin, session, navigate, sendTheme]);

  return <iframe
    ref={frameRef}
    src={link.url}
    onLoad={sendTheme}
    className="h-full w-full border-0"
    style={{ colorScheme: resolvedMode }}
    title={link.name}
    sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
  />;
}
