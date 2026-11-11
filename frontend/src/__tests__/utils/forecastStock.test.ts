import { describe, expect, it } from 'vitest';
import type { InventorySpool } from '../../api/client';
import { groupStockSpools, skuLabel } from '../../utils/forecastStock';
import { shownCostPerKg } from '../../utils/spoolCost';

describe('forecast stock', () => {
  it('groups recent usage separately from active stock and drops archived-only SKUs', () => {
    const active = { id: 1, material: 'PLA', subtype: 'Basic', brand: null, color_name: 'Black', archived_at: null } as InventorySpool;
    const now = Date.UTC(2026, 10, 11);
    const recent = { ...active, id: 2, archived_at: '2026-10-31T00:00:00Z' };
    const stale = { ...active, id: 3, archived_at: '2026-07-01T00:00:00Z' };
    const retired = { ...recent, id: 4, color_name: 'Blue' };
    expect(groupStockSpools([active, recent, stale, retired], now)).toEqual([
      expect.objectContaining({ spools: [active], recentlyArchived: [recent] }),
    ]);
  });

  it('names a repeated subtype and colour once', () => {
    expect(skuLabel('Bambu Lab', 'PLA Basic', 'Black', ' black ')).toBe('Bambu Lab PLA Basic Black');
    expect(skuLabel('Polymaker', 'PLA', 'Matte', 'Red')).toBe('Polymaker PLA Matte Red');
  });

  it('shows the charged rate and preserves a zero price for local inventory', () => {
    expect(shownCostPerKg({ cost_per_kg: 0, effective_cost_per_kg: 24 })).toBe(24);
    expect(shownCostPerKg({ cost_per_kg: 0 })).toBe(0);
  });
});
