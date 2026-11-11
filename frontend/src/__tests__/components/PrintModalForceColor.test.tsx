import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { PrintQueueItem } from '../../api/client';
import { PrintModal } from '../../components/PrintModal';
import { server } from '../mocks/server';
import { render } from '../utils';

describe('PrintModal fixed-printer colour requirements', () => {
  const requirements = [{ slot_id: 1, type: 'PLA', color: '#8B4513', used_grams: 12 }];
  const status = {
    connected: true, state: 'IDLE', vt_tray: [],
    ams: [{ id: 0, tray: [
      { id: 0, tray_type: 'PLA', tray_color: '8B4513FF', tray_info_idx: 'GFA00' },
      { id: 1, tray_type: 'PLA', tray_color: 'FFFFFFFF', tray_info_idx: 'GFA01' },
    ] }],
  };
  let saved: Record<string, unknown>[];

  beforeEach(() => {
    saved = [];
    const capture = async ({ request }: { request: Request }) => {
      saved.push(await request.json() as Record<string, unknown>);
      return HttpResponse.json({ id: 1, status: 'pending' });
    };
    server.use(
      http.get('/api/v1/printers/', () => HttpResponse.json([
        { id: 1, name: 'Workshop', model: 'X1C', is_active: true },
      ])),
      http.get('/api/v1/archives/:id/plates', () => HttpResponse.json({ is_multi_plate: false, plates: [] })),
      http.get('/api/v1/archives/:id/filament-requirements', () => HttpResponse.json({ filaments: requirements })),
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json(status)),
      http.get('/api/v1/printers/:id/assignments', () => HttpResponse.json([])),
      http.post('/api/v1/queue/', capture),
      http.patch('/api/v1/queue/:id', capture),
    );
  });

  async function expandMapping() {
    const header = await screen.findByText(/filament mapping/i);
    const panel = header.closest('.mb-4') as HTMLElement;
    if (!within(panel).queryByRole('combobox')) await userEvent.click(header);
    return panel;
  }

  it('queues a manually selected live tray with its own material, colour and profile', async () => {
    render(<PrintModal mode="create" archiveId={1} archiveName="Job" initialSelectedPrinterIds={[1]} onClose={vi.fn()} />);
    const panel = await expandMapping();
    await userEvent.click(await within(panel).findByRole('combobox'));
    const options = within(await screen.findByRole('listbox')).getAllByRole('option');
    await userEvent.click(options[2]);
    await userEvent.click(within(panel).getByRole('checkbox', { name: 'Force color match' }));
    await userEvent.click(document.querySelector('button[type="submit"]') as HTMLElement);
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0].filament_overrides).toEqual([expect.objectContaining({
      slot_id: 1, type: 'PLA', color: '#FFFFFF', tray_info_idx: 'GFA01', force_color_match: true,
    })]);
  });

  it('keeps the saved required colour on edit when the same tray has been refilled', async () => {
    const required = { slot_id: 1, type: 'PLA', color: '#32A852', tray_info_idx: 'GFA99', force_color_match: true };
    const job = {
      id: 1, printer_id: 1, status: 'pending', ams_mapping: [1], filament_overrides: [required], plate_id: null,
    } as PrintQueueItem;
    render(<PrintModal mode="edit-queue-item" archiveId={1} archiveName="Job" queueItem={job} onClose={vi.fn()} />);
    const panel = await expandMapping();
    expect(within(panel).getByRole('checkbox', { name: 'Force color match' })).toBeChecked();
    await userEvent.click(document.querySelector('button[type="submit"]') as HTMLElement);
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0].filament_overrides).toEqual([required]);
  });
});
