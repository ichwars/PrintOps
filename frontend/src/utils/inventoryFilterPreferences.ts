export interface InventoryFilters {
  archiveFilter: 'active' | 'archived';
  usageFilter: 'all' | 'used' | 'new' | 'lowstock';
  materialFilter: string;
  brandFilter: string;
  categoryFilter: string;
  spoolFilter: string;
  stockFilter: 'all' | 'stock' | 'configured';
  search: string;
}

export const defaultInventoryFilters: InventoryFilters = {
  archiveFilter: 'active', usageFilter: 'all', materialFilter: '', brandFilter: '',
  categoryFilter: '', spoolFilter: '', stockFilter: 'all', search: '',
};

export function inventoryFilterScope(
  authEnabled: boolean, userId: number | undefined, loading: boolean, spoolmanMode: boolean,
): string | null {
  if (loading || (authEnabled && (!Number.isSafeInteger(userId) || (userId ?? 0) <= 0))) return null;
  const owner = authEnabled ? `user:${userId}` : 'appliance';
  return `printops-inventory-filters:v1:${spoolmanMode ? 'spoolman' : 'local'}:${owner}`;
}

function choice<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === 'string' && allowed.includes(value as T) ? value as T : fallback;
}

function text(value: unknown, maxLength = 256): string {
  return typeof value === 'string' && value.length <= maxLength ? value : '';
}

export function loadInventoryFilters(scope: string | null): InventoryFilters {
  if (!scope) return { ...defaultInventoryFilters };
  try {
    const raw = localStorage.getItem(scope);
    if (!raw || raw.length > 8192) return { ...defaultInventoryFilters };
    const record = JSON.parse(raw);
    if (record?.version !== 1 || !record.filters || typeof record.filters !== 'object') {
      return { ...defaultInventoryFilters };
    }
    const filters = record.filters;
    const spool = text(filters.spoolFilter);
    return {
      archiveFilter: choice(filters.archiveFilter, ['active', 'archived'], 'active'),
      usageFilter: choice(filters.usageFilter, ['all', 'used', 'new', 'lowstock'], 'all'),
      stockFilter: choice(filters.stockFilter, ['all', 'stock', 'configured'], 'all'),
      materialFilter: text(filters.materialFilter), brandFilter: text(filters.brandFilter),
      categoryFilter: text(filters.categoryFilter),
      spoolFilter: /^[1-9]\d*$/.test(spool) && Number.isSafeInteger(Number(spool)) ? spool : '',
      search: text(filters.search, 1024),
    };
  } catch {
    return { ...defaultInventoryFilters };
  }
}

export function saveInventoryFilters(scope: string | null, filters: InventoryFilters): void {
  if (!scope) return;
  try {
    const isDefault = Object.entries(defaultInventoryFilters)
      .every(([key, value]) => filters[key as keyof InventoryFilters] === value);
    if (isDefault) localStorage.removeItem(scope);
    else localStorage.setItem(scope, JSON.stringify({ version: 1, filters }));
  } catch {
    // Storage may be unavailable or full. The current view remains usable.
  }
}
