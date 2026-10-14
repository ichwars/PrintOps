import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../utils';
import { PrintersPage } from '../../pages/PrintersPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

const printer = { id: 1, name: 'Camera fixture', serial_number: 'serial-camera', model: 'X1C', enabled: true, nozzle_diameter: .4 };
let storage: Map<string, string>;
const contentKey = 'printops:camera-view:v2:http%3A%2F%2Flocalhost%3A3000:appliance:printer:serial-camera';
const placementKey = contentKey.replace('camera-view:v2', 'camera-placement:v1');
beforeEach(() => {
  storage = new Map();
  vi.mocked(localStorage.getItem).mockImplementation(k => storage.get(k) ?? null);
  vi.mocked(localStorage.setItem).mockImplementation((k, v) => { storage.set(k, v); });
  vi.mocked(localStorage.removeItem).mockImplementation(k => { storage.delete(k); });
  server.use(http.get('/api/v1/settings/ui-preferences', () => HttpResponse.json({ camera_view_mode: 'window' })),
    http.get('/api/v1/printers/', () => HttpResponse.json([printer])),
    http.get('/api/v1/printers/1', () => HttpResponse.json(printer)),
    http.get('/api/v1/printers/1/status', () => HttpResponse.json({ connected: true, state: 'IDLE', ams: [], vt_tray: [], temperatures: {} })),
    http.get('/api/v1/queue/', () => HttpResponse.json([])));
});
afterEach(() => { vi.restoreAllMocks(); vi.mocked(localStorage.getItem).mockReset(); vi.mocked(localStorage.setItem).mockReset(); vi.mocked(localStorage.removeItem).mockReset(); });
it.each(['stream', 'snapshot'])('launches both placements immediately retaining %s independently', async mode => {
  storage.set(contentKey, JSON.stringify({ version: 1, mode }));
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  render(<PrintersPage />);
  const menu = await screen.findByRole('button', { name: 'Choose camera placement' });
  await waitFor(() => expect(menu).toBeEnabled());
  fireEvent.click(menu);
  fireEvent.click(screen.getByRole('menuitemradio', { name: 'Open camera in new window' }));
  expect(open).toHaveBeenCalledWith(`/camera/1?view=${mode}`, 'camera-1', expect.not.stringContaining('noopener'));
  expect(storage.get(contentKey)).toBe(JSON.stringify({ version: 1, mode }));
  expect(storage.get(placementKey)).toBe('{"version":1,"mode":"window"}');
  fireEvent.click(menu);
  expect(screen.getByRole('menuitemradio', { name: 'Open camera in new window' })).toHaveAttribute('aria-checked', 'true');
  fireEvent.click(screen.getByRole('menuitemradio', { name: 'Open camera overlay' }));
  await waitFor(() => expect(screen.getByRole('combobox', { name: 'Default camera view' })).toHaveAttribute('data-value', mode));
  expect(storage.get(placementKey)).toBe('{"version":1,"mode":"embedded"}');
  expect(storage.get(contentKey)).toBe(JSON.stringify({ version: 1, mode }));
});
it('supports keyboard navigation, Escape, Tab and outside dismissal', async () => {
  const user = userEvent.setup();
  render(<PrintersPage />);
  const menu = await screen.findByRole('button', { name: 'Choose camera placement' });
  await waitFor(() => expect(menu).toBeEnabled());
  menu.focus();
  await user.keyboard('{ArrowDown}');
  expect(screen.getAllByRole('menuitemradio')[0]).toHaveFocus();
  await user.keyboard('{End}');
  expect(screen.getAllByRole('menuitemradio')[1]).toHaveFocus();
  await user.keyboard('{Escape}');
  await user.keyboard('{ArrowUp}');
  expect(screen.getAllByRole('menuitemradio')[1]).toHaveFocus();
  await user.keyboard('{Escape}');
  expect(menu).toHaveFocus();
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(menu); await user.keyboard('{Tab}');
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(menu); await user.click(document.body);
  expect(screen.queryByRole('menu')).toBeNull();
});
it('disables both launch controls when disconnected', async () => {
  server.use(http.get('/api/v1/printers/1/status', () => HttpResponse.json({ connected: false, ams: [], vt_tray: [], temperatures: {} })));
  render(<PrintersPage />);
  expect(await screen.findByRole('button', { name: 'Choose camera placement' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Open camera in new window' })).toBeDisabled();
});

// Use the actual placement hook and popup helper even when the host has no overlay callback.
it('uses the global fallback until a local selection, then retains the local choice without settings writes', async () => {
  const { CameraLaunchButton } = await import('../../components/CameraLaunchButton');
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  const props = { printerId: 1, printerName: 'Fixture', serialNumber: 'serial-camera', contentMode: 'snapshot' as const, ready: true, connected: true, permitted: true };
  const view = render(<CameraLaunchButton {...props} fallback="embedded" />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Open camera overlay' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Open camera overlay' }));
  expect(open).toHaveBeenCalledWith('/camera/1?view=snapshot', 'camera-1', expect.any(String));
  expect(storage.has(placementKey)).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Choose camera placement' }));
  fireEvent.click(screen.getByRole('menuitemradio', { name: 'Open camera in new window' }));
  view.rerender(<CameraLaunchButton {...props} fallback="embedded" />);
  expect(screen.getByRole('button', { name: 'Open camera in new window' })).toBeEnabled();
  expect(storage.get(placementKey)).toBe('{"version":1,"mode":"window"}');
  fireEvent.click(screen.getByRole('button', { name: 'Open camera in new window' }));
  expect(open).toHaveBeenCalledTimes(3);
});
it.each(['ready', 'connected', 'permitted'] as const)('gates main and menu actions when %s is false', async flag => {
  const { CameraLaunchButton } = await import('../../components/CameraLaunchButton');
  const open = vi.spyOn(window, 'open').mockReturnValue(null);
  const props = { printerId: 1, printerName: 'Fixture', serialNumber: 'serial-camera', contentMode: 'snapshot' as const, ready: true, connected: true, permitted: true, [flag]: false };
  render(<CameraLaunchButton {...props} />);
  for (const button of screen.getAllByRole('button')) { expect(button).toBeDisabled(); fireEvent.click(button); }
  expect(open).not.toHaveBeenCalled();
  expect(screen.queryByRole('menu')).toBeNull();
  expect(storage.has(placementKey)).toBe(false);
});
it('closes a menu when permission is revoked and keeps it closed when permission returns', async () => {
  const { CameraLaunchButton } = await import('../../components/CameraLaunchButton');
  const props = { printerId: 1, printerName: 'Fixture', serialNumber: 'serial-camera', contentMode: 'stream' as const, ready: true, connected: true, permitted: true };
  const view = render(<CameraLaunchButton {...props} />);
  const toggle = screen.getByRole('button', { name: 'Choose camera placement' });
  await waitFor(() => expect(toggle).toBeEnabled());
  fireEvent.click(toggle);
  expect(screen.getByRole('menu')).toBeVisible();
  view.rerender(<CameraLaunchButton {...props} permitted={false} />);
  expect(screen.queryByRole('menu')).toBeNull();
  view.rerender(<CameraLaunchButton {...props} />);
  expect(screen.queryByRole('menu')).toBeNull();
});
it('does not restore unscoped legacy overlay IDs into another account or replacement printer', async () => {
  storage.set('openEmbeddedCameras', JSON.stringify([{ id: 1, name: 'Previous owner camera' }]));
  render(<PrintersPage />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Choose camera placement' })).toBeEnabled());
  expect(screen.queryByRole('combobox', { name: 'Default camera view' })).toBeNull();
});
it('restores explicitly opened overlays on navigation by hardware serial and does not follow a reused printer ID', async () => {
  const first = render(<PrintersPage />);
  const menu = await screen.findByRole('button', { name: 'Choose camera placement' });
  await waitFor(() => expect(menu).toBeEnabled());
  fireEvent.click(menu); fireEvent.click(screen.getByRole('menuitemradio', { name: 'Open camera overlay' }));
  await screen.findByRole('combobox', { name: 'Default camera view' });
  first.unmount();
  const second = render(<PrintersPage />);
  await screen.findByRole('combobox', { name: 'Default camera view' });
  second.unmount();
  server.use(http.get('/api/v1/printers/', () => HttpResponse.json([{ ...printer, serial_number: 'replacement-hardware' }])));
  render(<PrintersPage />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Choose camera placement' })).toBeEnabled());
  expect(screen.queryByRole('combobox', { name: 'Default camera view' })).toBeNull();
});
