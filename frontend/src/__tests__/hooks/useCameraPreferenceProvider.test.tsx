import { useEffect } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { AuthProvider, useAuth } from '../../contexts/AuthContext';
import { useEmbeddedCameraSelection } from '../../hooks/useEmbeddedCameraSelection';
import type { Printer } from '../../api/client';
import { setAuthToken } from '../../api/client';
import { useCameraPlacementPreference, useCameraViewPreference } from '../../hooks/useCameraViewPreference';

const origin = 'http%3A%2F%2Flocalhost%3A3000';
const account = { id: 7, sub: 'account-a', username: 'viewer', role: 'user', is_active: true,
  is_admin: false, auth_source: 'local', groups: [], permissions: ['camera:view' as const], created_at: '2026-01-01T00:00:00Z' };
let finishLogin: ReturnType<typeof useAuth>['loginWithToken'];
function Probe({ serial = 'serial-a' }: { serial?: string }) {
  const auth = useAuth();
  useEffect(() => { finishLogin = auth.loginWithToken; }, [auth.loginWithToken]);
  const content = useCameraViewPreference(serial);
  const placement = useCameraPlacementPreference(serial, 'window');
  const overlays = useEmbeddedCameraSelection([{ id: 1, name: 'Fixture', serial_number: serial } as Printer]);
  return <><output data-testid="content">{content.mode}</output><output data-testid="placement">{placement.mode}</output>
    <output data-testid="overlays">{overlays.cameras.length}</output><output data-testid="loading">{String(auth.loading)}</output>
    <button onClick={() => { content.setPreference('snapshot'); placement.setPreference('embedded'); overlays.openCamera(1); }}>Choose</button></>;
}
let storage: Map<string, string>;
const key = (kind: 'content' | 'placement', subject: string, serial = 'serial-a') =>
  `printops:${kind === 'content' ? 'camera-view:v2' : 'camera-placement:v1'}:${origin}:${subject}:printer:${serial}`;
describe('camera preferences with the real session-bound auth provider', () => {
  beforeEach(() => {
    storage = new Map();
    vi.mocked(localStorage.getItem).mockImplementation(k => storage.get(k) ?? null);
    vi.mocked(localStorage.setItem).mockImplementation((k, v) => { storage.set(k, v); });
    vi.mocked(localStorage.removeItem).mockImplementation(k => { storage.delete(k); });
  });
  afterEach(() => {
    setAuthToken(null);
    vi.mocked(localStorage.getItem).mockReset(); vi.mocked(localStorage.setItem).mockReset(); vi.mocked(localStorage.removeItem).mockReset();
  });
  it('ignores late /me A after same-ID login B, and drops B defaults when the session token changes', async () => {
    storage.set(key('content', 'user:account-a'), '{"version":1,"mode":"snapshot"}');
    storage.set(key('placement', 'user:account-a'), '{"version":1,"mode":"embedded"}');
    storage.set(`printops:open-cameras:v1:${origin}:user:account-a`, '["serial-a"]');
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
    expect(screen.getByTestId('content')).toHaveTextContent('stream');
    expect(screen.getByTestId('placement')).toHaveTextContent('window');
    expect(screen.getByTestId('overlays')).toHaveTextContent('0');
    fireEvent.click(screen.getByText('Choose'));
    expect(storage.get(key('content', 'user:account-b'))).toBe('{"version":1,"mode":"snapshot"}');
    expect(storage.get(key('placement', 'user:account-b'))).toBe('{"version":1,"mode":"embedded"}');
    act(() => setAuthToken('unverified-session'));
    expect(screen.getByTestId('content')).toHaveTextContent('stream');
    expect(screen.getByTestId('placement')).toHaveTextContent('window');
    expect(screen.getByTestId('overlays')).toHaveTextContent('0');
    const before = new Map(storage);
    fireEvent.click(screen.getByText('Choose'));
    expect(storage).toEqual(before);
  });
  it('never interprets a failed auth-status request as verified appliance mode', async () => {
    storage.set(key('content', 'appliance'), '{"version":1,"mode":"snapshot"}');
    storage.set(key('placement', 'appliance'), '{"version":1,"mode":"embedded"}');
    storage.set(`printops:open-cameras:v1:${origin}:appliance`, '["serial-a"]');
    server.use(http.get('/api/v1/auth/status', () => HttpResponse.error()));
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    expect(screen.getByTestId('content')).toHaveTextContent('stream');
    expect(screen.getByTestId('placement')).toHaveTextContent('window');
    expect(screen.getByTestId('overlays')).toHaveTextContent('0');
    const before = new Map(storage);
    fireEvent.click(screen.getByText('Choose'));
    expect(storage).toEqual(before);
  });
  it('keeps verified auth-off hardware defaults separate when a printer ID is reused and does not persist missing serials', async () => {
    const view = render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    fireEvent.click(screen.getByText('Choose'));
    expect(storage.get(key('placement', 'appliance'))).toBe('{"version":1,"mode":"embedded"}');
    view.rerender(<AuthProvider><Probe serial="replacement-hardware" /></AuthProvider>);
    expect(screen.getByTestId('content')).toHaveTextContent('stream');
    expect(screen.getByTestId('placement')).toHaveTextContent('window');
    expect(screen.getByTestId('overlays')).toHaveTextContent('0');
    view.rerender(<AuthProvider><Probe serial="" /></AuthProvider>);
    expect(screen.getByTestId('overlays')).toHaveTextContent('0');
    const before = new Map(storage); fireEvent.click(screen.getByText('Choose')); expect(storage).toEqual(before);
  });
  it('restores overlays for the same verified subject/hardware and gates them immediately when permission is lost', async () => {
    setAuthToken('verified-session');
    server.use(
      http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
      http.get('/api/v1/auth/me', () => HttpResponse.json(account)),
    );
    const first = render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('loading')).toHaveTextContent('false'));
    fireEvent.click(screen.getByText('Choose'));
    expect(screen.getByTestId('overlays')).toHaveTextContent('1');
    first.unmount();
    render(<AuthProvider><Probe /></AuthProvider>);
    await waitFor(() => expect(screen.getByTestId('overlays')).toHaveTextContent('1'));
    act(() => finishLogin('no-camera-session', { ...account, permissions: [] }));
    expect(screen.getByTestId('overlays')).toHaveTextContent('0');
  });

});
