import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { render } from '../utils';
import { server } from '../mocks/server';
import InventoryPageRouter from '../../pages/InventoryPage';
import type { InventorySpool } from '../../api/client';

function spool(id: number, rgba: string | null, color_name: string, extra_colors: string | null = null): InventorySpool {
  return { id, rgba, color_name, extra_colors, material: 'PLA', subtype: null,
    effect_type: null, brand: 'Test', label_weight: 1000, core_weight: 250,
    core_weight_catalog_id: null, weight_used: 0, slicer_filament: null,
    slicer_filament_name: null, nozzle_temp_min: null, nozzle_temp_max: null,
    note: null, added_full: null, last_used: null, encode_time: null, tag_uid: null,
    tray_uuid: null, data_origin: null, tag_type: null, archived_at: null,
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    cost_per_kg: null, last_scale_weight: null, last_weighed_at: null,
    category: null, low_stock_threshold_pct: null, k_profiles: [], storage_location: null };
}

const spools = [spool(7, null, 'Missing'), spool(3, 'FF0000FF', 'Z misleading blue'),
  spool(5, '00000000', 'Clear'), spool(1, '000000FF', 'Neutral'),
  spool(6, 'FF0000FF', 'Multi', 'FF0000,0000FF'), spool(4, '0000FFFF', 'A misleading red'),
  spool(2, '8B4513FF', 'Brown')];

beforeEach(() => {
  vi.mocked(localStorage.getItem).mockReset();
  server.use(
    http.get('/api/v1/settings/spoolman', () => HttpResponse.json({ spoolman_enabled: 'false' })),
    http.get('/api/v1/inventory/spools', () => HttpResponse.json(spools)),
    http.get('/api/v1/inventory/assignments', () => HttpResponse.json([])),
    http.get('/api/v1/inventory/catalog', () => HttpResponse.json([])),
    http.get('/api/v1/inventory/spool-catalog', () => HttpResponse.json([])),
  );
});

afterEach(() => vi.mocked(localStorage.getItem).mockReset());

function tableIds() {
  const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1);
  return rows.map(row => Number(within(row).getAllByRole('cell')[1].textContent));
}

describe('inventory color sort controls', () => {
  it('sorts the actual swatch values with keyboard controls and announces the direction', async () => {
    const user = userEvent.setup();
    render(<InventoryPageRouter />);
    await screen.findByRole('table');
    const colorButton = within(screen.getByRole('table')).getByRole('button', { name: 'Color' });
    colorButton.focus();
    await user.keyboard('{Enter}');
    await waitFor(() => expect(tableIds()).toEqual([1, 2, 3, 4, 5, 6, 7]));
    expect(screen.getByRole('columnheader', { name: 'Color' })).toHaveAttribute('aria-sort', 'ascending');
    await user.keyboard(' ');
    await waitFor(() => expect(tableIds()).toEqual([7, 6, 5, 4, 3, 2, 1]));
    expect(screen.getByRole('columnheader', { name: 'Color' })).toHaveAttribute('aria-sort', 'descending');
    expect(localStorage.setItem).toHaveBeenCalledWith('printops-inventory-sort', JSON.stringify({ column: 'rgba', direction: 'desc' }));
  });

  it('uses the same color order in cards through the compact mobile control', async () => {
    render(<InventoryPageRouter />);
    await screen.findByRole('table');
    fireEvent.click(screen.getByRole('button', { name: /^Cards$/ }));
    fireEvent.click(screen.getByRole('button', { name: /^Sort by actual color/ }));
    await waitFor(() => expect(screen.getAllByText(/^(Neutral|Brown|Z misleading blue|A misleading red|Clear|Multi|Missing)$/)
      .map(label => label.textContent)).toEqual(['Neutral', 'Brown', 'Z misleading blue', 'A misleading red', 'Clear', 'Multi', 'Missing']));
    expect(screen.getByRole('button', { name: 'Sort by actual color: Ascending' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('restores actual-color sorting from the existing preference', async () => {
    vi.mocked(localStorage.getItem).mockImplementation(key => key === 'printops-inventory-sort'
      ? JSON.stringify({ column: 'rgba', direction: 'asc' }) : null);
    render(<InventoryPageRouter />);
    await screen.findByRole('table');
    await waitFor(() => expect(tableIds()).toEqual([1, 2, 3, 4, 5, 6, 7]));
    expect(screen.getByRole('columnheader', { name: 'Color' })).toHaveAttribute('aria-sort', 'ascending');
  });
});
