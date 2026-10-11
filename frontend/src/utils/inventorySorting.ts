import type { InventorySpool } from '../api/client';
import { formatSlotLabel } from './amsHelpers';
import { compareInventoryColors } from './inventoryColorSort';

export type SortState = { column: string; direction: 'asc' | 'desc' } | null;

// Fields shared by local and Spoolman slot assignments for location sorting.
export type LocationDisplay = {
  printer_id: number;
  printer_name: string | null;
  ams_id: number;
  tray_id: number;
  ams_label: string | null;
};

// Sort value extractors — return a comparable value for each sortable column
const columnSortValues: Record<string, (spool: InventorySpool, assignmentMap: Record<number, LocationDisplay>) => string | number> = {
  id: (s) => s.id,
  added_time: (s) => s.created_at || '',
  encode_time: (s) => s.encode_time || '',
  last_used_time: (s) => s.last_used || '',
  material: (s) => (s.material || '').toLowerCase(),
  subtype: (s) => (s.subtype || '').toLowerCase(),
  color_name: (s) => (s.color_name || '').toLowerCase(),
  brand: (s) => (s.brand || '').toLowerCase(),
  slicer_filament: (s) => (s.slicer_filament_name || s.slicer_filament || '').toLowerCase(),
  location: (s, am) => {
    const a = am[s.id];
    if (!a) return '';
    const isExt = a.ams_id === 254 || a.ams_id === 255;
    const isHt = !isExt && a.ams_id >= 128;
    const label = a.ams_label ? ` (${a.ams_label})` : '';
    return `${a.printer_name || ''} ${formatSlotLabel(a.ams_id, a.tray_id, isHt, isExt)}${label}`;
  },
  storage_location: (s) => (s.storage_location || '').toLowerCase(),
  label_weight: (s) => s.label_weight,
  net: (s) => Math.max(0, s.label_weight - s.weight_used),
  gross: (s) => Math.max(0, s.label_weight - s.weight_used) + s.core_weight,
  used: (s) => s.weight_used,
  remaining: (s) => s.label_weight > 0 ? Math.max(0, s.label_weight - s.weight_used) / s.label_weight : 0,
  note: (s) => (s.note || '').toLowerCase(),
  data_origin: (s) => (s.data_origin || '').toLowerCase(),
  tag_type: (s) => (s.tag_type || '').toLowerCase(),
  stock: (s) => s.slicer_filament ? 1 : 0,
  spool_name: (s) => s.core_weight_catalog_id ?? 0,
  cost_per_kg: (s) => s.cost_per_kg ?? 0,
  weight_check: (s) => {
    if (s.last_scale_weight == null) return -1;
    const expectedGross = Math.max(0, s.label_weight - s.weight_used) + s.core_weight;
    return Math.abs(s.last_scale_weight - expectedGross);
  },
};

export function isSortableInventoryColumn(column: string): boolean {
  return column === 'rgba' || Object.hasOwn(columnSortValues, column);
}

export function sortInventorySpools(spools: InventorySpool[], state: SortState, assignments: Record<number, LocationDisplay>): InventorySpool[] {
  if (!state || !isSortableInventoryColumn(state.column)) return spools;
  return [...spools].sort((left, right) => {
    let result: number;
    if (state.column === 'rgba') result = compareInventoryColors(left, right);
    else {
      const a = columnSortValues[state.column](left, assignments), b = columnSortValues[state.column](right, assignments);
      result = a < b ? -1 : a > b ? 1 : 0;
    }
    return state.direction === 'asc' ? result : -result;
  });
}
