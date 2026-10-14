import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { screen, waitFor, fireEvent, within } from '@testing-library/react';
import { useQueryClient } from '@tanstack/react-query';
import { render, selectComboboxOption } from '../utils';
import { PrintersPage } from '../../pages/PrintersPage';
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';

const mockPrinter = {
  id: 1,
  name: 'X1 Carbon',
  ip_address: '192.168.1.100',
  serial_number: '00M09A350100001',
  access_code: '12345678',
  model: 'X1C',
  enabled: true,
  nozzle_diameter: 0.4,
  nozzle_type: 'hardened_steel',
  location: 'Workshop',
  auto_archive: true,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

const baseTray = {
  tray_color: 'FF0000FF',
  tray_type: 'PLA',
  tray_sub_brands: 'PLA Basic',
  tray_id_name: 'A00-R0',
  tray_info_idx: 'GFA00',
  remain: 80,
  k: 0.02,
  cali_idx: null,
  tag_uid: null,
  tray_uuid: null,
  nozzle_temp_min: 190,
  nozzle_temp_max: 230,
  drying_temp: null,
  drying_time: null,
  state: 11,
};

const mockIdleStatusWithAms = {
  connected: true,
  state: 'IDLE',
  progress: 0,
  layer_num: 0,
  total_layers: 0,
  temperatures: { nozzle: 25, bed: 25, chamber: 25 },
  remaining_time: 0,
  filename: null,
  wifi_signal: -50,
  speed_level: 2,
  vt_tray: [],
  ams: [
    {
      id: 0,
      humidity: 30,
      temp: 25,
      is_ams_ht: false,
      serial_number: 'AMS00',
      sw_ver: '1.0.0',
      dry_time: 0,
      dry_status: 0,
      dry_sub_status: 0,
      dry_sf_reason: [],
      module_type: 'ams',
      tray: [
        { id: 0, ...baseTray },
        { id: 1, ...baseTray, tray_color: '00FF00FF', tray_type: 'PETG' },
        { id: 2, ...baseTray, tray_color: '0000FFFF', tray_type: 'ABS' },
        { id: 3, ...baseTray, tray_color: 'FFFF00FF', tray_type: 'TPU' },
      ],
    },
  ],
};


const prefix = 'printops:external-spool-hidden:v1:http%3A%2F%2Flocalhost%3A3000:appliance:printer:';
function Fixture() {
  const client = useQueryClient();
  return <><button onClick={() => client.invalidateQueries({ queryKey: ['printerStatus'] })}>Refresh fixture</button><PrintersPage /></>;
}

describe('external spool display on rendered printer cards', () => {
  let storage: Map<string, string>;
  let status: typeof mockIdleStatusWithAms;
  beforeEach(() => {
    storage = new Map();
    vi.mocked(localStorage.getItem).mockImplementation(key => storage.get(key) ?? null);
    vi.mocked(localStorage.setItem).mockImplementation((key, value) => { storage.set(key, value); });
    vi.mocked(localStorage.removeItem).mockImplementation(key => { storage.delete(key); });
    status = { ...mockIdleStatusWithAms, vt_tray: [{ id: 254, ...baseTray, tray_type: 'ASA' }] } as typeof status;
    server.use(
      http.get('/api/v1/printers/', () => HttpResponse.json([mockPrinter])),
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json(status)),
      http.get('/api/v1/queue/', () => HttpResponse.json([])),
    );
  });
  afterEach(() => {
    vi.mocked(localStorage.getItem).mockReset();
    vi.mocked(localStorage.setItem).mockReset();
    vi.mocked(localStorage.removeItem).mockReset();
  });

  it('defaults visible, hides only external slots, persists and restores original authorized actions', async () => {
    let loaded: string | null = null;
    let unloaded = 0;
    server.use(
      http.post('/api/v1/printers/:id/ams/load', ({ request }) => {
        loaded = new URL(request.url).searchParams.get('tray_id');
        return HttpResponse.json({ success: true });
      }),
      http.post('/api/v1/printers/:id/ams/unload', () => { unloaded++; return HttpResponse.json({ success: true }); }),
    );
    const view = render(<PrintersPage />);
    const hide = await screen.findByRole('button', { name: 'Hide external spool' });
    expect(screen.getAllByTestId('filament-slot')).toHaveLength(5);
    expect(screen.getByText('ASA')).toBeVisible();
    const scale = screen.getByRole('combobox', { name: 'Card text and icons' });
    selectComboboxOption(scale, '120%');
    fireEvent.click(hide);
    expect(screen.queryByText('ASA')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('filament-slot')).toHaveLength(4);
    expect(document.querySelector('[data-card-text-scale]')).toHaveAttribute('data-card-text-scale', '120');
    expect(storage.get(prefix + mockPrinter.serial_number)).toBe('true');
    expect(loaded).toBeNull();
    expect(unloaded).toBe(0);
    view.unmount();
    render(<PrintersPage />);
    const show = await screen.findByRole('button', { name: 'Show external spool' });
    expect(screen.queryByText('ASA')).not.toBeInTheDocument();
    fireEvent.click(show);
    expect(storage.has(prefix + mockPrinter.serial_number)).toBe(false);
    const external = screen.getAllByTestId('filament-slot')[4];
    fireEvent.mouseEnter(external);
    const load = await screen.findByText('Load');
    expect(load.closest('button')).toBeEnabled();
    expect(screen.getByText('Unload').closest('button')).toBeEnabled();
    expect(screen.getByText('Configure').closest('button')).toBeEnabled();
    expect(screen.getByText('Assign Spool').closest('button')).toBeEnabled();
    fireEvent.click(load);
    await waitFor(() => expect(loaded).toBe('254'));
    fireEvent.click(screen.getByText('Unload'));
    await waitFor(() => expect(unloaded).toBe(1));
  });

  it('shows external fallback immediately after AMS disconnect despite cached AMS and restores hidden choice on reconnect', async () => {
    render(<Fixture />);
    fireEvent.click(await screen.findByRole('button', { name: 'Hide external spool' }));
    status = { ...status, ams: [] };
    fireEvent.click(screen.getByText('Refresh fixture'));
    await waitFor(() => expect(screen.getByText('ASA')).toBeVisible());
    expect(screen.queryByRole('button', { name: /external spool/ })).not.toBeInTheDocument();
    expect(storage.get(prefix + mockPrinter.serial_number)).toBe('true');
    status = { ...status, ams: mockIdleStatusWithAms.ams };
    fireEvent.click(screen.getByText('Refresh fixture'));
    await screen.findByRole('button', { name: 'Show external spool' });
    expect(screen.queryByText('ASA')).not.toBeInTheDocument();
  });

  it('ignores a stored hide on an external-only printer and offers no useless toggle without external trays', async () => {
    storage.set(prefix + mockPrinter.serial_number, 'true');
    status = { ...status, ams: [] };
    const view = render(<PrintersPage />);
    expect(await screen.findByText('ASA')).toBeVisible();
    expect(screen.queryByRole('button', { name: /external spool/ })).not.toBeInTheDocument();
    view.unmount();
    status = mockIdleStatusWithAms;
    render(<PrintersPage />);
    await waitFor(() => expect(screen.getAllByTestId('filament-slot')).toHaveLength(4));
    expect(screen.queryByRole('button', { name: /external spool/ })).not.toBeInTheDocument();
  });

  it('keeps another printer visible when only the first printer is hidden', async () => {
    server.use(http.get('/api/v1/printers/', () => HttpResponse.json([mockPrinter, { ...mockPrinter, id: 2, serial_number: 'different-hardware', name: 'Second printer' }])));
    render(<PrintersPage />);
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Hide external spool' })).toHaveLength(2));
    fireEvent.click(within(document.getElementById('printer-card-1')!).getByRole('button', { name: 'Hide external spool' }));
    expect(within(document.getElementById('printer-card-1')!).queryByText('ASA')).not.toBeInTheDocument();
    expect(within(document.getElementById('printer-card-2')!).getByText('ASA')).toBeVisible();
  });

  it('restores the original inventory unassign action after showing the card', async () => {
    let removed = false;
    server.use(
      http.get('/api/v1/inventory/assignments', () => HttpResponse.json([{
        printer_id: 1, ams_id: 255, tray_id: 0, spool_id: 42,
        spool: { id: 42, material: 'ASA', brand: 'Fixture brand', color_name: 'Red', label_weight: 1000, weight_used: 100 },
      }])),
      http.delete('/api/v1/inventory/assignments/1/255/0', () => { removed = true; return HttpResponse.json({ status: 'ok' }); }),
    );
    render(<PrintersPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'Hide external spool' }));
    fireEvent.click(screen.getByRole('button', { name: 'Show external spool' }));
    fireEvent.mouseEnter(screen.getAllByTestId('filament-slot')[4]);
    fireEvent.click(await screen.findByText('Unassign'));
    await waitFor(() => expect(removed).toBe(true));
  });

});
