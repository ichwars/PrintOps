import type { InventorySpool } from '../api/client';

export function shownCostPerKg(spool: Pick<InventorySpool, 'cost_per_kg' | 'effective_cost_per_kg'>) {
  return spool.effective_cost_per_kg ?? spool.cost_per_kg;
}
