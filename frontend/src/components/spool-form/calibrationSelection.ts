import type { SpoolKProfile, SpoolKProfileInput } from '../../api/client';
import type { CalibrationProfile, PrinterWithCalibrations } from './types';

const diameter = (value: string | undefined) => {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 && number <= 2 ? String(number) : '';
};

export const calibrationFlow = (value: string | null | undefined) => {
  const prefix = value?.trim().toUpperCase().slice(0, 2);
  return prefix === 'HS' || prefix === 'HH' ? prefix : '';
};

export function calibrationKey(printerId: number | string, profile: CalibrationProfile): string {
  return `${printerId}:${profile.cali_idx}:${profile.extruder_id ?? 0}:${diameter(profile.nozzle_diameter)}:${calibrationFlow(profile.nozzle_id)}`;
}

export function storedCalibrationKey(profile: SpoolKProfile): string {
  return calibrationKey(profile.printer_id, {
    cali_idx: profile.cali_idx!, extruder_id: profile.extruder,
    nozzle_diameter: profile.nozzle_diameter, nozzle_id: profile.nozzle_type,
    filament_id: '', setting_id: '', name: '', k_value: profile.k_value, n_coef: 0,
  });
}

export function calibrationInput(key: string, printers: PrinterWithCalibrations[]): SpoolKProfileInput | null {
  const parts = key.split(':');
  const printer = printers.find(p => p.printer.id === Number(parts[0]));
  if (!printer) return null;
  const legacy = parts.length === 3;
  const candidates = printer.calibrations.filter(cal => legacy
    ? cal.cali_idx === Number(parts[1]) && (cal.extruder_id ?? 0) === (parts[2] === 'null' ? 0 : Number(parts[2]))
    : calibrationKey(printer.printer.id, cal) === key);
  // Legacy keys and duplicated firmware IDs must have exactly one compatible row.
  if (candidates.length !== 1 || !diameter(candidates[0].nozzle_diameter)) return null;
  const cal = candidates[0];
  return {
    printer_id: printer.printer.id, extruder: cal.extruder_id ?? 0,
    nozzle_diameter: diameter(cal.nozzle_diameter), nozzle_type: calibrationFlow(cal.nozzle_id) || null,
    k_value: cal.k_value, name: cal.name || null, cali_idx: cal.cali_idx, setting_id: cal.setting_id || null,
  };
}
