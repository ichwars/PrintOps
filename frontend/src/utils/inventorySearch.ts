import type { InventorySpool } from '../api/client';

export function exactSpoolIdQuery(query: string): number | null {
  const match = /^#(\d+)$/.exec(query.trim());
  if (!match) return null;
  const id = Number(match[1]);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

/**
 * Return true when spool matches the search query across all searchable text fields.
 * Case-insensitive. Empty query always returns true.
 */
export function spoolMatchesQuery(spool: InventorySpool, query: string): boolean {
  if (!query) return true;
  const id = exactSpoolIdQuery(query);
  if (id !== null) return spool.id === id;
  const q = query.toLowerCase();
  return (
    String(spool.id).includes(q) ||
    (spool.material_number?.toLowerCase().includes(q) ?? false) ||
    spool.material.toLowerCase().includes(q) ||
    (spool.brand?.toLowerCase().includes(q) ?? false) ||
    (spool.color_name?.toLowerCase().includes(q) ?? false) ||
    (spool.subtype?.toLowerCase().includes(q) ?? false) ||
    (spool.note?.toLowerCase().includes(q) ?? false) ||
    (spool.slicer_filament_name?.toLowerCase().includes(q) ?? false) ||
    (spool.storage_location?.toLowerCase().includes(q) ?? false)
  );
}

/** Filter a spool list by a free-text search query. */
export function filterSpoolsByQuery(spools: InventorySpool[], query: string): InventorySpool[] {
  if (!query) return spools;
  return spools.filter((spool) => spoolMatchesQuery(spool, query));
}
