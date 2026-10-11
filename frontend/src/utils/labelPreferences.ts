import type { LabelField } from "../api/client";

export const DEFAULT_FIELDS: LabelField[] = ['brand', 'material', 'hex', 'name', 'location', 'qr', 'spool_id'];
export const FIELDS: [LabelField, string][] = [
  ['brand', 'brand'], ['material', 'material'], ['hex', 'hex'], ['name', 'name'],
  ['location', 'location'], ['material_number', 'materialNumber'], ['temps', 'temps'],
  ['weight', 'weight'], ['note', 'note'], ['added', 'added'], ['qr', 'qr'], ['spool_id', 'spoolId'],
];
export interface LabelPreferences {
  fields: LabelField[];
  format: 'pdf' | 'png';
  dpi: 203 | 300 | 600;
  monochrome: boolean;
}
export function defaultLabelPreferences(): LabelPreferences {
  return { fields: [...DEFAULT_FIELDS], format: 'pdf', dpi: 300, monochrome: false };
}
export function readLabelPreferences(key: string): LabelPreferences {
  const defaults = defaultLabelPreferences();
  try {
    const saved = JSON.parse(localStorage.getItem(key) || 'null');
    if (!saved || !Array.isArray(saved.fields) || !saved.fields.every((field: unknown) => FIELDS.some(([value]) => value === field))) return defaults;
    return { fields: [...new Set(saved.fields as LabelField[])], format: saved.format === 'png' ? 'png' : 'pdf',
      dpi: [203, 300, 600].includes(saved.dpi) ? saved.dpi : 300, monochrome: saved.monochrome === true };
  } catch { return defaults; }
}

