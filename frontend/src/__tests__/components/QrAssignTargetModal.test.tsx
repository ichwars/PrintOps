import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { api, type InventorySpool } from '../../api/client';
import { QrAssignTargetModal } from '../../components/QrAssignTargetModal';
import { render, selectComboboxOption } from '../utils';

vi.mock('../../api/client', () => ({
  getAuthSessionId: () => 0,
  subscribeAuthSession: () => () => {},
  api: {
    getAuthStatus: vi.fn().mockResolvedValue({ auth_enabled: false }),
    getUiFlags: vi.fn().mockResolvedValue({}),
    getLocations: vi.fn(),
    getPrinters: vi.fn(),
    getPrinterStatus: vi.fn(),
    resolveSpoolLabel: vi.fn(),
    getSpool: vi.fn(),
    getSpoolmanInventorySpool: vi.fn(),
    updateSpool: vi.fn(),
    updateSpoolmanInventorySpool: vi.fn(),
    assignSpool: vi.fn(),
    assignSpoolmanSlot: vi.fn(),
  },
}));

const SPOOL = { id: 7, material: 'PLA', color_name: 'Ultramarine' } as InventorySpool;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getLocations).mockResolvedValue([{ id: 4, name: 'Shelf 4' }] as never);
  vi.mocked(api.getPrinters).mockResolvedValue([{ id: 2, name: 'Workshop printer' }] as never);
  vi.mocked(api.getPrinterStatus).mockResolvedValue({
    connected: true, ams: [{ id: 0, tray: [{ id: 0, tray_type: 'PETG' }] }], vt_tray: [],
  } as never);
  vi.mocked(api.getSpool).mockResolvedValue(SPOOL);
  vi.mocked(api.getSpoolmanInventorySpool).mockResolvedValue(SPOOL);
  vi.mocked(api.updateSpool).mockResolvedValue(SPOOL);
  vi.mocked(api.updateSpoolmanInventorySpool).mockResolvedValue(SPOOL);
});

async function pickOption(select: string, option: string) {
  const combo = await screen.findByRole('combobox', { name: select, exact: true });
  await waitFor(() => expect(combo).toBeEnabled());
  fireEvent.click(combo);
  fireEvent.click(await screen.findByRole('option', { name: option, exact: true }));
}

async function readLabel(text: string) {
  const field = await screen.findByRole('textbox', { name: 'Spool label link' });
  fireEvent.change(field, { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: 'Read label' }));
}

describe('QrAssignTargetModal', () => {
  it.each([false, true])('assigns the resolved spool to a structured location in mode %s', async spoolmanMode => {
    const source = spoolmanMode ? 'spoolman' : 'inventory';
    vi.mocked(api.resolveSpoolLabel).mockResolvedValue({ spool_id: 7, source });
    render(<QrAssignTargetModal spoolmanMode={spoolmanMode} onClose={vi.fn()} />);
    await pickOption('Storage Location', 'Shelf 4');
    const payload = `http://printops.test/inventory?spool=7&source=${source}`;
    await readLabel(payload);
    expect(api.resolveSpoolLabel).toHaveBeenCalledWith(payload);
    expect(api.updateSpool).not.toHaveBeenCalled();
    expect(api.updateSpoolmanInventorySpool).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole('button', { name: 'Assign to Shelf 4' }));
    const update = spoolmanMode ? api.updateSpoolmanInventorySpool : api.updateSpool;
    await waitFor(() => expect(update).toHaveBeenCalledWith(7, { location_id: 4 }));
  });

  it('requires confirmation before moving a spool to a slot with a different material', async () => {
    vi.mocked(api.resolveSpoolLabel).mockResolvedValue({ spool_id: 7, source: 'inventory' });
    vi.mocked(api.assignSpool).mockResolvedValue({ pending_config: true } as never);
    render(<QrAssignTargetModal spoolmanMode={false} onClose={vi.fn()} />);
    selectComboboxOption(screen.getByRole('combobox', { name: 'Assignment target' }), 'AMS slot');
    await pickOption('Printer', 'Workshop printer');
    await pickOption('AMS slot', 'A1');
    await readLabel('/inventory?spool=7&source=inventory');
    await screen.findByText('The slot reports PETG. The scanned spool contains PLA.');
    expect(api.assignSpool).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Assign to Workshop printer · A1' }));
    await waitFor(() => expect(api.assignSpool).toHaveBeenCalledWith({
      spool_id: 7, printer_id: 2, ams_id: 0, tray_id: 0, move: true,
    }));
  });

  it('refuses an inventory mismatch without fetching or changing a spool', async () => {
    vi.mocked(api.resolveSpoolLabel).mockResolvedValue({ spool_id: 7, source: 'spoolman' });
    render(<QrAssignTargetModal spoolmanMode={false} onClose={vi.fn()} />);
    await pickOption('Storage Location', 'Shelf 4');
    await readLabel('web+spoolman:s-7');
    await screen.findByText('This label belongs to a different inventory.');
    expect(api.getSpool).not.toHaveBeenCalled();
    expect(api.getSpoolmanInventorySpool).not.toHaveBeenCalled();
  });
});
