import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { PrintModal } from '../../components/PrintModal';
import { render } from '../utils';
import { server } from '../mocks/server';

const printerStatus = {
  connected: true,
  state: 'IDLE',
  ams_filament_backup: true,
  ams: [{
    id: 0,
    tray: [
      { id: 0, tray_type: 'PLA', tray_color: '000000', tray_sub_brands: 'PLA Basic', tray_info_idx: 'GFA00' },
      { id: 1, tray_type: 'PLA', tray_color: '000000', tray_sub_brands: 'PLA Basic', tray_info_idx: 'GFA00' },
    ],
  }],
  vt_tray: null,
};

describe('PrintModal filament deficit parity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    server.use(
      http.get('/api/v1/archives/:id/plates', () =>
        HttpResponse.json({ is_multi_plate: false, plates: [] }),
      ),
      http.get('/api/v1/archives/:id/filament-requirements', () =>
        HttpResponse.json({
          filaments: [{ slot_id: 1, type: 'PLA', color: '#000000', tray_info_idx: 'GFA00', used_grams: 80 }],
        }),
      ),
      http.get('/api/v1/printers/:id/status', () => HttpResponse.json(printerStatus)),
    );
  });

  it('shows one pooled warning using the server-computed backup inventory', async () => {
    let queueCalls = 0;
    server.use(
      http.get('/api/v1/printers/:id/inventory-remain', () =>
        HttpResponse.json({
          inventory_remain_g: { '0': 60, '1': 10 },
          slot_materials: [
            { ams_id: 0, tray_id: 0, global_tray_id: 0, material_key: 'preset:GFA00|color:000000', remaining_g: 60, extruder: 0 },
            { ams_id: 0, tray_id: 1, global_tray_id: 1, material_key: 'preset:GFA00|color:000000', remaining_g: 10, extruder: 0 },
          ],
        }),
      ),
      http.post('/api/v1/queue/', () => {
        queueCalls += 1;
        return HttpResponse.json({ id: 1, status: 'pending' });
      }),
    );
    const user = userEvent.setup();
    render(
      <PrintModal
        mode="create"
        archiveId={1}
        archiveName="Short.gcode.3mf"
        initialSelectedPrinterIds={[1]}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText(/Filament Mapping/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^print$/i }));

    expect(await screen.findByText(/needs 80g, 70g available across matching spools/i)).toBeInTheDocument();
    expect(queueCalls).toBe(0);
  });

  it('queues when the matching backup pool covers the mapped spool', async () => {
    let queueCalls = 0;
    server.use(
      http.get('/api/v1/printers/:id/inventory-remain', () =>
        HttpResponse.json({
          inventory_remain_g: { '0': 60, '1': 40 },
          slot_materials: [
            { ams_id: 0, tray_id: 0, global_tray_id: 0, material_key: 'preset:GFA00|color:000000', remaining_g: 60, extruder: 0 },
            { ams_id: 0, tray_id: 1, global_tray_id: 1, material_key: 'preset:GFA00|color:000000', remaining_g: 40, extruder: 0 },
          ],
        }),
      ),
      http.post('/api/v1/queue/', () => {
        queueCalls += 1;
        return HttpResponse.json({ id: 1, status: 'pending' });
      }),
    );
    const user = userEvent.setup();
    render(
      <PrintModal
        mode="create"
        archiveId={1}
        archiveName="Covered.gcode.3mf"
        initialSelectedPrinterIds={[1]}
        onClose={vi.fn()}
      />,
    );

    await waitFor(() => expect(screen.getByText(/Filament Mapping/i)).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: /^print$/i }));

    await waitFor(() => expect(queueCalls).toBe(1));
    expect(screen.queryByText(/Not enough filament/i)).not.toBeInTheDocument();
  });
});
