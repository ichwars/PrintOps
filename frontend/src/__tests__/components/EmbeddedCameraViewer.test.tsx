import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { EmbeddedCameraViewer } from '../../components/EmbeddedCameraViewer';
import { render, selectComboboxOption } from '../utils';
import { server } from '../mocks/server';

describe('EmbeddedCameraViewer camera defaults', () => {
  beforeEach(() => {
    const storage = new Map<string, string>([
      ['printops:camera-view:v1:http%3A%2F%2Flocalhost%3A3000:appliance:1', JSON.stringify({ version: 1, mode: 'snapshot' })],
    ]);
    vi.mocked(localStorage.getItem).mockImplementation(key => storage.get(key) ?? null);
    vi.mocked(localStorage.setItem).mockImplementation((key, value) => { storage.set(key, value); });
    vi.mocked(localStorage.removeItem).mockImplementation(key => { storage.delete(key); });
    server.use(
      http.get('*/api/v1/printers/1', () => HttpResponse.json({ id: 1, name: 'Workshop', model: 'X1C' })),
      http.get('*/api/v1/printers/1/status', () => HttpResponse.json({ connected: true, state: 'IDLE' })),
      http.post('*/api/v1/printers/1/camera/stop', () => HttpResponse.json({ success: true })),
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
  });

  it('honors the saved snapshot in the existing embedded viewer', async () => {
    render(<EmbeddedCameraViewer printerId={1} printerName="Workshop" onClose={() => {}} />);
    await waitFor(() => {
      expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
    });
    expect(document.querySelector('video')).toBeNull();
    expect(screen.getByRole('combobox', { name: 'Default camera view' })).toHaveAttribute('data-value', 'snapshot');
  });

  it('changes and resets the default through the owned camera combobox', async () => {
    render(<EmbeddedCameraViewer printerId={1} printerName="Workshop" onClose={() => {}} />);
    await waitFor(() => expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot'));
    const control = screen.getByRole('combobox', { name: 'Default camera view' });
    selectComboboxOption(control, 'Stream');
    expect(control).toHaveAttribute('data-value', 'stream');
    await waitFor(() => expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/stream'));
    selectComboboxOption(control, 'Default (Stream)');
    expect(control).toHaveAttribute('data-value', 'default');
    expect(localStorage.getItem('printops:camera-view:v1:http%3A%2F%2Flocalhost%3A3000:appliance:1')).toBeNull();
  });

  it('keeps new and restored viewers inside a mobile viewport after resizing', async () => {
    vi.stubGlobal('innerWidth', 390);
    vi.stubGlobal('innerHeight', 844);
    const first = render(<EmbeddedCameraViewer printerId={1} printerName="Workshop" onClose={() => {}} />);
    const viewer = screen.getByRole('combobox', { name: 'Default camera view' }).closest('div.fixed') as HTMLElement;
    expect(Number.parseFloat(viewer.style.left) + Number.parseFloat(viewer.style.width)).toBeLessThanOrEqual(390);
    expect(viewer.style.width).toBe('370px');
    first.unmount();

    vi.mocked(localStorage.getItem).mockImplementation((key) => key === 'embeddedCameraState_1'
      ? JSON.stringify({ x: 700, y: 500, width: 400, height: 300 }) : null);
    vi.stubGlobal('innerWidth', 1200);
    render(<EmbeddedCameraViewer printerId={1} printerName="Workshop" onClose={() => {}} />);
    const restoredViewer = screen.getByRole('combobox', { name: 'Default camera view' }).closest('div.fixed') as HTMLElement;
    vi.stubGlobal('innerWidth', 390);
    fireEvent(window, new Event('resize'));
    expect(Number.parseFloat(restoredViewer.style.left) + Number.parseFloat(restoredViewer.style.width)).toBeLessThanOrEqual(390);
    expect(Number.parseFloat(restoredViewer.style.top) + Number.parseFloat(restoredViewer.style.height)).toBeLessThanOrEqual(844);
    await waitFor(() => expect(document.querySelector('img')).toBeInTheDocument());
  });

  it('keeps failed snapshots out of the automatic live-stream retry loop', async () => {
    render(<EmbeddedCameraViewer printerId={1} printerName="Workshop" onClose={() => {}} />);
    await waitFor(() => {
      expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
    });
    fireEvent.error(document.querySelector('img')!);
    expect(await screen.findByText('Camera unavailable')).toBeInTheDocument();
    expect(screen.queryByText(/Reconnecting in/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => {
      expect(document.querySelector('img')?.getAttribute('src')).toContain('/camera/snapshot');
    });
  });
});
