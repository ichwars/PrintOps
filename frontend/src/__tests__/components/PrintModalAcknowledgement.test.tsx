import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { PrintModal } from '../../components/PrintModal';

describe('PrintModal filament-warning acknowledgement', () => {
  it('acknowledges only the printer whose short spool was shown', async () => {
    const queued: { printer_id: number; skip_filament_check?: boolean }[] = [];
    server.use(
      http.get('/api/v1/printers/', () => HttpResponse.json([
        { id: 1, name: 'Printer A', model: 'X1C', is_active: true },
        { id: 2, name: 'Printer B', model: 'X1C', is_active: true },
      ])),
      http.get('/api/v1/archives/:id/plates', () => HttpResponse.json({ is_multi_plate: false, plates: [] })),
      http.get('/api/v1/archives/:id/filament-requirements', () => HttpResponse.json({
        filaments: [{ slot_id: 1, type: 'PLA', color: '#FF0000', tray_info_idx: 'GFA00', used_grams: 50 }],
      })),
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json({
        connected: true, state: 'IDLE',
        ams: [{ id: 0, tray: [{ id: 0, tray_type: 'PLA', tray_color: 'FF0000FF', tray_info_idx: 'GFA00' }] }],
        vt_tray: [],
      })),
      http.get('/api/v1/printers/:id/inventory-remain', ({ params }) => {
        const grams = params.id === '1' ? 10 : 1000;
        return HttpResponse.json({ inventory_remain_g: { '0': grams }, slot_materials: [
          { ams_id: 0, tray_id: 0, global_tray_id: 0, material_key: 'preset:GFA00|color:FF0000', remaining_g: grams, extruder: 0 },
        ] });
      }),
      http.post('/api/v1/queue/', async ({ request }) => {
        queued.push(await request.json() as { printer_id: number; skip_filament_check?: boolean });
        return HttpResponse.json({ id: queued.length, status: 'pending' });
      }),
    );
    const user = userEvent.setup();
    render(<PrintModal mode="create" archiveId={1} archiveName="Part.3mf" onClose={vi.fn()} />);
    await user.click(await screen.findByText('Printer A'));
    await user.click(screen.getByText('Printer B'));
    await user.click(document.querySelector('button[type="submit"]') as HTMLElement);
    await user.click(await screen.findByRole('button', { name: /print anyway/i }));
    await waitFor(() => expect(queued).toHaveLength(2));
    expect(Object.fromEntries(queued.map(item => [item.printer_id, item.skip_filament_check]))).toEqual({ 1: true, 2: undefined });
  });
});
