import { useLayoutEffect } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router';
import { http, HttpResponse } from 'msw';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { ExternalLinkPage } from '../../pages/ExternalLinkPage';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';
import { ThemeProvider, useTheme } from '../../contexts/ThemeContext';
import { setAuthToken, type ExternalLink, type UserResponse } from '../../api/client';
import { server } from '../mocks/server';

const registered: ExternalLink = {
  id: 1, name: 'Local app', url: 'https://app.example.test:8443/tool', icon: 'Link',
  open_in_new_tab: false, custom_icon: null, sort_order: 0,
  created_at: '2026-10-14T00:00:00Z', updated_at: '2026-10-14T00:00:00Z',
};
const account: UserResponse = {
  id: 7, sub: 'account-a', username: 'alice', role: 'user', is_active: true,
  is_admin: false, auth_source: 'local', groups: [], permissions: ['external_links:read'],
  created_at: '2026-10-14T00:00:00Z',
};
let auth: ReturnType<typeof useAuth>;
let theme: ReturnType<typeof useTheme>;
let navigate: ReturnType<typeof useNavigate>;
function Probe() {
  const currentAuth = useAuth();
  const currentTheme = useTheme();
  const currentNavigate = useNavigate();
  useLayoutEffect(() => { auth = currentAuth; theme = currentTheme; navigate = currentNavigate; });
  const location = useLocation();
  return <output data-testid="location">{location.pathname + location.search + location.hash}</output>;
}
function setup(path = '/external/1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const result = render(<QueryClientProvider client={client}>
    <MemoryRouter initialEntries={[path]}><AuthProvider><ThemeProvider>
      <Probe /><Routes>
        <Route path="/external/:id" element={<ExternalLinkPage />} />
        <Route path="*" element={<p>Destination</p>} />
      </Routes>
    </ThemeProvider></AuthProvider></MemoryRouter>
  </QueryClientProvider>);
  return { ...result, client };
}
async function frame() { return await screen.findByTitle('Local app') as HTMLIFrameElement; }
function message(source: MessageEventSource | null, origin: string, data: unknown) {
  act(() => { window.dispatchEvent(new MessageEvent('message', { source, origin, data })); });
}
const origin = 'https://app.example.test:8443';
const darkTheme = { type: 'printops:theme', mode: 'dark', style: 'vibrant', background: 'cool', accent: 'green', canNavigate: true };

beforeEach(() => {
  setAuthToken(null);
  server.use(
    http.get('*/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: false, requires_setup: false })),
    http.get('*/api/v1/auth/me', () => HttpResponse.json(account)),
    http.get('*/api/v1/settings/', () => HttpResponse.json({})),
    http.get('*/api/v1/external-links/:id', ({ params }) => HttpResponse.json({ ...registered, id: Number(params.id) })),
  );
});
afterEach(() => { act(() => setAuthToken(null)); vi.restoreAllMocks(); });

describe('registered sidebar app bridge', () => {
  it('sends only visual metadata on load, theme change, and an authenticated request', async () => {
    setup();
    const iframe = await frame();
    const post = vi.spyOn(iframe.contentWindow!, 'postMessage');
    fireEvent.load(iframe);
    expect(post).toHaveBeenLastCalledWith(darkTheme, origin);
    post.mockClear();
    message(iframe.contentWindow, origin, { type: 'printops:theme-request' });
    expect(post).toHaveBeenCalledExactlyOnceWith(darkTheme, origin);
    act(() => theme.setMode('system'));
    expect(post).toHaveBeenLastCalledWith({ type: 'printops:theme', mode: 'light', style: 'classic', background: 'neutral', accent: 'green', canNavigate: true }, origin);
    expect(iframe.style.colorScheme).toBe('light');
    expect(iframe.getAttribute('sandbox')).toBe('allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox');
  });

  it.each([
    'https://app.example.test', 'http://app.example.test:8443',
    'https://app.example.test.evil.test:8443', 'null', '',
  ])('rejects requests and navigation from wrong origin %s', async (wrongOrigin) => {
    setup(); const iframe = await frame();
    const post = vi.spyOn(iframe.contentWindow!, 'postMessage');
    message(iframe.contentWindow, wrongOrigin, { type: 'printops:theme-request' });
    message(iframe.contentWindow, wrongOrigin, { type: 'printops:navigate', path: '/queue' });
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByTestId('location')).toHaveTextContent('/external/1');
    message(iframe.contentWindow, origin, { type: 'printops:theme-request' });
    expect(post).toHaveBeenCalledExactlyOnceWith(darkTheme, origin);
  });

  it('rejects a sibling window, the host window, null source and malformed messages', async () => {
    setup(); const iframe = await frame();
    const sibling = document.createElement('iframe'); document.body.append(sibling);
    const post = vi.spyOn(iframe.contentWindow!, 'postMessage');
    for (const source of [sibling.contentWindow, window, null]) {
      message(source, origin, { type: 'printops:theme-request' });
      message(source, origin, { type: 'printops:navigate', path: '/queue' });
    }
    for (const data of [null, 1, 'printops:navigate', [], {}, { type: 'bambuddy:navigate', path: '/queue' }]) {
      message(iframe.contentWindow, origin, data);
    }
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByTestId('location')).toHaveTextContent('/external/1');
    sibling.remove();
  });

  it.each(['/queue?batch=12#pending', '/', '/' + 'a'.repeat(511)])('navigates internally preserving valid path %s', async (path) => {
    setup(); const iframe = await frame();
    message(iframe.contentWindow, origin, { type: 'printops:navigate', path });
    expect(screen.getByTestId('location').textContent).toBe(path);
  });

  it.each([undefined, null, 42, {}, '', 'queue', '//evil.test', '/\\evil.test', '/a\\b',
    'https://evil.test', '/a/..//evil.test', '/%2e//evil.test', '/\n/evil.test', '/a\tb', '/a\rb', '/a\u0000b', '/a\u007fb', '/' + 'a'.repeat(512),
  ])('ignores invalid navigation path %j', async (path) => {
    setup(); const iframe = await frame();
    message(iframe.contentWindow, origin, { type: 'printops:navigate', path });
    expect(screen.getByTestId('location').textContent).toBe('/external/1');
  });

  it.each(['https://', 'https:///app.example.test', 'https://user:password@app.example.test',
    'https://app.example.test\\@evil.test', 'https://app.example.test\n.evil.test', 'http://[invalid',
    'javascript:alert(1)', '//app.example.test',
  ])('never grants bridge authority to malformed/ambiguous registration %s', async (url) => {
    server.use(http.get('*/api/v1/external-links/:id', () => HttpResponse.json({ ...registered, url })));
    setup(); const iframe = await frame();
    const post = vi.spyOn(iframe.contentWindow!, 'postMessage');
    fireEvent.load(iframe);
    message(iframe.contentWindow, 'https://app.example.test', { type: 'printops:theme-request' });
    message(iframe.contentWindow, 'https://app.example.test', { type: 'printops:navigate', path: '/queue' });
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByTestId('location').textContent).toBe('/external/1');
  });

  it('destroys the old frame when the registered ID or URL changes', async () => {
    const { client } = setup(); const oldFrame = await frame(); const oldWindow = oldFrame.contentWindow;
    act(() => navigate('/external/2'));
    await waitFor(() => expect(screen.queryByTitle('Local app')).not.toBe(oldFrame));
    const nextFrame = await frame();
    const post = vi.spyOn(nextFrame.contentWindow!, 'postMessage');
    message(oldWindow, origin, { type: 'printops:theme-request' });
    message(oldWindow, origin, { type: 'printops:navigate', path: '/queue' });
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByTestId('location').textContent).toBe('/external/2');
    server.use(http.get('*/api/v1/external-links/:id', () => HttpResponse.json({ ...registered, id: 2, url: 'http://localhost:3000/tool' })));
    await act(async () => { await client.invalidateQueries({ queryKey: ['external-link'] }); });
    await waitFor(() => expect(screen.getByTitle('Local app')).not.toBe(nextFrame));
    const current = await frame();
    message(nextFrame.contentWindow, origin, { type: 'printops:navigate', path: '/queue' });
    expect(screen.getByTestId('location').textContent).toBe('/external/2');
    message(current.contentWindow, 'http://localhost:3000', { type: 'printops:navigate', path: '/queue?x=1#hash' });
    expect(screen.getByTestId('location').textContent).toBe('/queue?x=1#hash');
  });

  it.each([403, 404, 500])('removes cached authority on registered-link revalidation failure %s', async (status) => {
    const { client } = setup(); const iframe = await frame(); const source = iframe.contentWindow;
    server.use(http.get('*/api/v1/external-links/:id', () => HttpResponse.json({ detail: 'Unavailable' }, { status })));
    await act(async () => { await client.invalidateQueries({ queryKey: ['external-link'] }); });
    await waitFor(() => expect(screen.queryByTitle('Local app')).toBeNull());
    message(source, origin, { type: 'printops:navigate', path: '/queue' });
    expect(screen.getByTestId('location').textContent).toBe('/external/1');
  });

  it('does not reuse cached registration after same numeric user ID changes account/session', async () => {
    setup(); await frame();
    act(() => auth.loginWithToken('test-account-a', account));
    const first = await frame();
    let resolve!: (value: Response) => void;
    server.use(http.get('*/api/v1/external-links/:id', () => new Promise<Response>(done => { resolve = done; })));
    act(() => auth.loginWithToken('test-account-b', { ...account, sub: 'account-b', username: 'bob' }));
    expect(screen.queryByTitle('Local app')).toBeNull();
    message(first.contentWindow, origin, { type: 'printops:navigate', path: '/queue' });
    expect(screen.getByTestId('location').textContent).toBe('/external/1');
    await waitFor(() => expect(resolve).toBeDefined());
    await act(async () => { resolve(HttpResponse.json(registered)); });
    const second = await frame(); expect(second).not.toBe(first);
    message(second.contentWindow, origin, { type: 'printops:navigate', path: '/queue' });
    expect(screen.getByTestId('location').textContent).toBe('/queue');
  });

  it('removes authority after permission is revoked without a session change', async () => {
    setup(); await frame();
    act(() => auth.loginWithToken('test-account-a', account));
    const iframe = await frame();
    server.use(http.get('*/api/v1/auth/me', () => HttpResponse.json({ ...account, permissions: [] })));
    await act(async () => { await auth.refreshUser(); });
    expect(screen.queryByTitle('Local app')).toBeNull();
    message(iframe.contentWindow, origin, { type: 'printops:navigate', path: '/queue' });
    expect(screen.getByTestId('location').textContent).toBe('/external/1');
  });

  it('immediately rejects the old frame after credentials change, before auth refresh', async () => {
    setup(); const iframe = await frame(); const source = iframe.contentWindow;
    const post = vi.spyOn(source!, 'postMessage');
    act(() => {
      setAuthToken('new-unverified-session');
      window.dispatchEvent(new MessageEvent('message', { source, origin, data: { type: 'printops:theme-request' } }));
      window.dispatchEvent(new MessageEvent('message', { source, origin, data: { type: 'printops:navigate', path: '/queue' } }));
    });
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByTestId('location').textContent).toBe('/external/1');
  });

  it.each([null, { ...registered, id: 2 }])('rejects missing or mismatched registered link data %j', async (data) => {
    server.use(http.get('*/api/v1/external-links/:id', () => HttpResponse.json(data)));
    setup();
    await screen.findByText('Link not found');
    expect(screen.queryByTitle('Local app')).toBeNull();
  });

  it('does not grant authority while auth mode is unverified', async () => {
    server.use(http.get('*/api/v1/auth/status', () => HttpResponse.json({ detail: 'Unavailable' }, { status: 500 })));
    setup(); await waitFor(() => expect(auth.loading).toBe(false));
    expect(screen.queryByTitle('Local app')).toBeNull();
  });
});
