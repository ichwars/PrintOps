import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { useLocation, useNavigate } from 'react-router';
import { http, HttpResponse } from 'msw';
import type { Printer } from '../../api/client';
import { CameraOverlayButton, CameraOverlayProvider } from '../../components/CameraOverlayLauncher';
import { useEmbeddedCameraSelection } from '../../hooks/useEmbeddedCameraSelection';
import * as cameraHandoff from '../../utils/cameraHandoff';
import { server } from '../mocks/server';
import { render } from '../utils';

vi.mock('../../components/EmbeddedCameraViewer', () => ({
  EmbeddedCameraViewer: ({ printerName, onClose }: { printerName: string; onClose: () => void }) => (
    <button type="button" onClick={onClose}>Close global camera {printerName}</button>
  ),
}));

const printer = { id: 1, name: 'Workshop', serial_number: 'serial-1', is_active: true } as Printer;

beforeEach(() => {
  window.history.replaceState({}, '', '/printers');
  sessionStorage.clear();
  const storage = new Map<string, string>();
  vi.mocked(localStorage.getItem).mockImplementation((key) => storage.get(key) ?? null);
  vi.mocked(localStorage.setItem).mockImplementation((key, value) => { storage.set(key, value); });
  vi.mocked(localStorage.removeItem).mockImplementation((key) => { storage.delete(key); });
  server.use(http.get('/api/v1/printers/', () => HttpResponse.json([printer])));
});

function Page() {
  const location = useLocation();
  const navigate = useNavigate();
  const camera = useEmbeddedCameraSelection([printer]);
  return (
    <>
      <CameraOverlayButton />
      <button type="button" onClick={() => navigate('/archives')}>Go to archives</button>
      <button type="button" onClick={() => navigate('/printers')}>Go to printers</button>
      {location.pathname === '/printers' && (
        <>
          <button type="button" disabled={!camera.ready} onClick={() => camera.openCamera(1)}>Open from card</button>
          <output>{camera.cameras.length} card cameras</output>
        </>
      )}
    </>
  );
}

it('keeps card cameras on their page and promotes an existing camera to the app overlay', async () => {
  render(<CameraOverlayProvider><Page /></CameraOverlayProvider>);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Open from card' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Open from card' }));
  expect(screen.getByText('1 card cameras')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Go to archives' }));
  expect(screen.queryByText('1 card cameras')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Go to printers' }));
  expect(screen.getByText('1 card cameras')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Open camera overlay' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Workshop' }));
  const viewer = await screen.findByRole('button', { name: 'Close global camera Workshop' });
  expect(screen.getByText('0 card cameras')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Open from card' }));
  expect(screen.getByText('0 card cameras')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Go to archives' }));
  expect(viewer).toBeInTheDocument();
  fireEvent.click(viewer);
  expect(viewer).not.toBeInTheDocument();
});

it('rechecks an incoming camera against the signed-in tab’s visible printers', async () => {
  const source = { postMessage: vi.fn() } as unknown as Window;
  const listen = vi.spyOn(cameraHandoff, 'listenForCameraOverlay');
  try {
    render(<CameraOverlayProvider><Page /></CameraOverlayProvider>);
    // The button can appear before React attaches the passive message listener.
    await waitFor(() => expect(listen).toHaveBeenCalledWith('appliance', expect.any(Function)));
  } finally {
    listen.mockRestore();
  }
  const send = (printerId: number, nonce: string, account = 'appliance') => window.dispatchEvent(new MessageEvent('message', {
    origin: window.location.origin,
    source,
    data: { type: 'printops:camera-overlay-open', account, printerId, nonce, deadline: Date.now() + 1500 },
  }));
  send(1, 'other', 'other-account');
  send(99, 'missing');
  await waitFor(() => expect(source.postMessage).toHaveBeenCalledTimes(1));
  expect(source.postMessage).toHaveBeenCalledWith(expect.objectContaining({ nonce: 'missing', accepted: false }), window.location.origin);
  send(1, 'valid');
  expect(await screen.findByRole('button', { name: 'Close global camera Workshop' })).toBeInTheDocument();
  expect(source.postMessage).toHaveBeenCalledWith(expect.objectContaining({ nonce: 'valid', accepted: true }), window.location.origin);
});
