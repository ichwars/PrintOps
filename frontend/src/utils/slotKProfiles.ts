import type { AMSTray, KProfile, PrinterStatus } from '../api/client';
import { calibrationFlow } from '../components/spool-form/calibrationSelection';

type Context = AMSTray['calibration_context'];

export function slotCalibrationContext(status: PrinterStatus | undefined, amsId: number, trayId: number): Context {
  const tray = amsId === 255
    ? status?.vt_tray?.find(t => t.id === 254 + trayId)
    : status?.ams?.find(a => a.id === amsId)?.tray.find(t => t.id === trayId);
  return tray?.calibration_context;
}

export function kProfileOptionValue(profile: KProfile): string {
  return JSON.stringify([profile.slot_id, profile.extruder_id ?? 0, profile.nozzle_diameter,
    calibrationFlow(profile.nozzle_id), profile.name, profile.k_value, profile.filament_id]);
}

export function kProfileOptionLabel(profile: KProfile, hotendLabel?: string): string {
  const flow = calibrationFlow(profile.nozzle_id);
  return `${flow ? `[${flow === 'HH' ? 'HF' : 'S'}] ` : ''}${profile.name} (K=${profile.k_value})${hotendLabel ? ` · ${hotendLabel}` : ''}`;
}

export function compatibleSlotKProfile(profile: KProfile, context: Context, extruderId?: number): boolean {
  if (context) return (profile.extruder_id ?? 0) === context.extruder
    && Number(profile.nozzle_diameter) === Number(context.diameter)
    && (calibrationFlow(profile.nozzle_id) || null) === context.flow;
  return extruderId === undefined || (profile.extruder_id ?? 0) === extruderId;
}

export function automaticSlotKProfile(profiles: KProfile[], activeIndex?: number | null): KProfile | null {
  const active = activeIndex != null && activeIndex > 0 ? profiles.filter(p => p.slot_id === activeIndex) : [];
  if (active.length === 1) return active[0];
  // A bare index or equal name/K cannot choose between different hotends/flows.
  const contexts = new Set(profiles.map(p => `${p.extruder_id ?? 0}|${p.nozzle_diameter}|${calibrationFlow(p.nozzle_id)}`));
  return contexts.size === 1 ? profiles[0] ?? null : null;
}
