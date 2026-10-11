type InventoryFocusFilter = 'low-stock' | 'missing-cost' | 'missing-location' | 'used';

function isInventoryFocusFilter(value: string | null): value is InventoryFocusFilter {
  return value === 'low-stock' || value === 'missing-cost' || value === 'missing-location' || value === 'used';
}

// Keep the same digit-only, positive ID semantics as the location and edit links.
function positiveId(value: string | null): number | null {
  return value && /^\d+$/.test(value) && Number(value) > 0 ? Number(value) : null;
}

export function parseInventoryURLFilters(params: URLSearchParams) {
  const rawFocus = params.get('focus');
  const rawLocation = params.get('location_id');
  const focusFilter = isInventoryFocusFilter(rawFocus) ? rawFocus : null;
  const storageLocationFilter = rawLocation === '__none__' ? '__none__'
    : positiveId(rawLocation) !== null ? rawLocation! : '';
  const deepLinkSpoolId = positiveId(params.get('spool'));
  return {
    focusFilter, storageLocationFilter, deepLinkSpoolId,
    hasURLOverride: focusFilter !== null || storageLocationFilter !== '' || deepLinkSpoolId !== null,
  };
}
