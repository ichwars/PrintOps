import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { PrintersPage } from '../../pages/PrintersPage';
import { useAuth } from '../../contexts/AuthContext';
import { setAuthToken } from '../../api/client';

const printer = { id: 1, name: 'Wall camera', serial_number: 'wall-serial', model: 'X1C', enabled: true, nozzle_diameter: .4 };
let storage: Map<string, string>;
let settingsRead: boolean;
function AuthProbe() {
  const { loading, authStatusVerified } = useAuth();
  return <output data-testid="auth">{`${loading}:${authStatusVerified}`}</output>;
}
function page() { return render(<><AuthProbe /><PrintersPage /></>); }
function placement(mode: string) {
  server.use(http.get('/api/v1/settings/ui-preferences', () => {
    settingsRead = true;
    return HttpResponse.json({ camera_view_mode: mode });
  }));
}
const overlay = () => screen.queryByRole('combobox', { name: 'Default camera view' });
const cameraKeys = () => [...storage.keys()].filter(k => /printops:(camera-|open-cameras)/.test(k));
async function ready() {
  await waitFor(() => { expect(screen.getByTestId('auth')).toHaveTextContent('false:true'); expect(settingsRead).toBe(true); });
}
beforeEach(() => {
  settingsRead = false;
  storage = new Map([['printerPageView', 'camwall']]);
  vi.mocked(localStorage.getItem).mockImplementation(k => storage.get(k) ?? null);
  vi.mocked(localStorage.setItem).mockImplementation((k, v) => { storage.set(k, v); });
  vi.mocked(localStorage.removeItem).mockImplementation(k => { storage.delete(k); });
  placement('embedded');
  server.use(http.get('/api/v1/printers/', () => HttpResponse.json([printer])),
    http.get('/api/v1/printers/1', () => HttpResponse.json(printer)),
    http.get('/api/v1/printers/1/status', () => HttpResponse.json({ connected: true, state: 'IDLE', ams: [], vt_tray: [], temperatures: {} })),
    http.post('/api/v1/printers/1/camera/stop', () => HttpResponse.json({})),
    http.get('/api/v1/queue/', () => HttpResponse.json([])));
});
afterEach(() => {
  setAuthToken(null);
  vi.restoreAllMocks();
  vi.mocked(localStorage.getItem).mockReset(); vi.mocked(localStorage.setItem).mockReset(); vi.mocked(localStorage.removeItem).mockReset();
});
it('opens the verified serial overlay and explicit close survives remount', async () => {
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  const first = page();
  const tile = await screen.findByTitle('Wall camera'); await ready();
  expect(tile).toBeEnabled(); fireEvent.click(tile);
  await screen.findByRole('combobox', { name: 'Default camera view' });
  expect(cameraKeys()).toHaveLength(1); expect(open).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTitle('Close'));
  expect(overlay()).toBeNull(); expect(cameraKeys()).toEqual([]);
  first.unmount(); page(); await ready(); await screen.findByTitle('Wall camera');
  expect(overlay()).toBeNull();
});
it.each(['embedded', 'window'])('disables %s launches after failed real auth discovery without fallback or persistence', async mode => {
  placement(mode);
  server.use(http.get('/api/v1/auth/status', () => HttpResponse.error()));
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  page(); const tile = await screen.findByTitle('Wall camera');
  await waitFor(() => expect(screen.getByTestId('auth')).toHaveTextContent('false:false'));
  expect(tile).toBeDisabled(); fireEvent.click(tile);
  expect(overlay()).toBeNull(); expect(open).not.toHaveBeenCalled(); expect(cameraKeys()).toEqual([]);
});
it.each(['embedded', 'window'])('disables %s launches while proof is pending, then enables on verification', async mode => {
  placement(mode);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  server.use(http.get('/api/v1/auth/status', async () => { await pending; return HttpResponse.json({ auth_enabled: false, requires_setup: false }); }));
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  page(); const tile = await screen.findByTitle('Wall camera');
  try {
    expect(screen.getByTestId('auth')).toHaveTextContent('true:false');
    expect(tile).toBeDisabled(); fireEvent.click(tile);
    expect(overlay()).toBeNull(); expect(open).not.toHaveBeenCalled(); expect(cameraKeys()).toEqual([]);
  } finally { await act(async () => { release(); }); }
  await waitFor(() => expect(tile).toBeEnabled());
});
it('does not convert a missing camera permission into a window fallback', async () => {
  setAuthToken('wall-session');
  server.use(http.get('/api/v1/auth/status', () => HttpResponse.json({ auth_enabled: true, requires_setup: false })),
    http.get('/api/v1/auth/me', () => HttpResponse.json({ id: 7, sub: 'wall-user', username: 'viewer', is_admin: false, is_active: true, groups: [], permissions: ['printers:read'] })));
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  page(); const tile = await screen.findByTitle('Wall camera'); await ready();
  expect(tile).toBeDisabled(); fireEvent.click(tile);
  expect(open).not.toHaveBeenCalled(); expect(overlay()).toBeNull(); expect(cameraKeys()).toEqual([]);
});
it.each(['embedded', 'window'])('uses the synchronous existing window contract for verified missing serial under global %s', async mode => {
  placement(mode);
  server.use(http.get('/api/v1/printers/', () => HttpResponse.json([{ ...printer, serial_number: '' }])));
  storage.set('cameraWindowState', JSON.stringify({ width: 720, height: 450, left: 10, top: 20 }));
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  page(); const tile = await screen.findByTitle('Wall camera'); await ready();
  expect(tile).toBeEnabled(); fireEvent.click(tile);
  expect(open).toHaveBeenCalledExactlyOnceWith('/camera/1', 'camera-1', 'width=720,height=450,left=10,top=20,menubar=no,toolbar=no,location=no,status=no');
  expect(overlay()).toBeNull(); expect(cameraKeys()).toEqual([]);
});
it('retains global Window launch for a verified serial without saving local placement', async () => {
  placement('window');
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  page(); const tile = await screen.findByTitle('Wall camera'); await ready();
  fireEvent.click(tile);
  expect(open).toHaveBeenCalledExactlyOnceWith('/camera/1', 'camera-1', 'width=640,height=400,menubar=no,toolbar=no,location=no,status=no');
  expect(overlay()).toBeNull(); expect(cameraKeys()).toEqual([]);
});
