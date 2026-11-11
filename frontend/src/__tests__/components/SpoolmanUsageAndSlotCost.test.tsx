import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import { FilamentMapping } from '../../components/PrintModal/FilamentMapping';
import { SpoolUsageHistory } from '../../components/SpoolUsageHistory';

describe('Spoolman usage and slot pricing', () => {
  it('reads the Spoolman history in the Spoolman spool form', async () => {
    server.use(http.get('/api/v1/inventory/spools/7/usage', ({ request }) => {
      const source = new URL(request.url).searchParams.get('source');
      return HttpResponse.json([{
        id: 1, spool_id: null, spoolman_spool_id: 7, weight_used: 21, percent_used: 2,
        status: 'cancelled', print_name: source === 'spoolman' ? 'Spoolman run' : 'Local run',
        created_at: '2026-11-05T00:00:00Z',
      }]);
    }));
    render(<SpoolUsageHistory spoolId={7} spoolmanMode />);
    expect(await screen.findByText('Spoolman run')).toBeInTheDocument();
    expect(screen.getByText('21.0g')).toBeInTheDocument();
  });

  it('prices the loaded slot from the inventory remain response', async () => {
    server.use(
      http.get('/api/v1/printers/1/status', () => HttpResponse.json({
        id: 1, connected: true, state: 'IDLE',
        ams: [{ id: 0, tray: [{ id: 0, tray_type: 'PLA', tray_color: 'FF0000' }] }], vt_tray: [],
      })),
      http.get('/api/v1/printers/1/inventory-remain', () => HttpResponse.json({
        inventory_remain_g: { 0: 312 },
        slot_materials: [{ ams_id: 0, tray_id: 0, global_tray_id: 0, remaining_g: 312, cost_per_kg: 40 }],
      })),
    );
    render(<FilamentMapping
      printerId={1}
      filamentReqs={{ filaments: [{ slot_id: 1, type: 'PLA', color: '#FF0000', used_grams: 100, used_meters: 0 }] }}
      manualMappings={{}}
      onManualMappingChange={() => {}}
      currencySymbol="$"
      defaultCostPerKg={25}
      defaultExpanded
    />);
    expect(await screen.findByText('$4.00')).toBeInTheDocument();
  });
});
