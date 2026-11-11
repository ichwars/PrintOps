import type { InventorySpool } from '../api/client';
import { parseUTCDate } from './date';

export interface SkuGroup {
  key: string;
  material: string;
  subtype: string | null;
  brand: string | null;
  colorName: string | null;
  spools: InventorySpool[];
  recentlyArchived: InventorySpool[];
  usedBefore: boolean;
}

export const ARCHIVED_RATE_WINDOW_MS = 90 * 86400000;

export function skuKey(material: string, subtype: string | null, brand: string | null, colorName: string | null) {
  return [material, subtype, brand, colorName].map((value) => value?.trim() ?? '').join('||');
}

export function skuLabel(brand: string | null, material: string, subtype: string | null, colorName: string | null) {
  const repeatsSubtype = colorName?.trim().toLowerCase() === subtype?.trim().toLowerCase();
  return [brand, material, subtype, repeatsSubtype ? null : colorName].filter(Boolean).join(' ');
}

export function groupStockSpools(spools: InventorySpool[], now = Date.now()): SkuGroup[] {
  const groups = new Map<string, SkuGroup>();
  for (const spool of spools) {
    if (spool.archived_at) continue;
    const { material, subtype, brand, color_name: colorName } = spool;
    const key = skuKey(material, subtype, brand, colorName);
    const group = groups.get(key) ?? { key, material, subtype, brand, colorName, spools: [], recentlyArchived: [], usedBefore: false };
    group.spools.push(spool);
    groups.set(key, group);
  }
  for (const spool of spools) {
    if (!spool.archived_at) continue;
    const timestamp = parseUTCDate(spool.archived_at)?.getTime();
    if (timestamp === undefined) continue;
    const age = now - timestamp;
    const group = groups.get(skuKey(spool.material, spool.subtype, spool.brand, spool.color_name));
    if (!group) continue;
    if (age >= 0 && age <= ARCHIVED_RATE_WINDOW_MS) group.recentlyArchived.push(spool);
    else if (age > ARCHIVED_RATE_WINDOW_MS && spool.weight_used > 0) group.usedBefore = true;
  }
  return [...groups.values()];
}
