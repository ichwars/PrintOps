import type {
  LoadedSpoolPreset,
  LoadedSpoolPrinter,
  LoadedSpoolTray,
  PresetRef,
  PresetSource,
  UnifiedPreset,
  UnifiedPresetsResponse,
} from '../api/client';
import { slotPresetDescribesTray } from './amsHelpers';
import { findPreset, printerPresetParents, SLICE_MODAL_TIER_ORDER, statesDifferentMaterial } from './slicePresetPicker';
import {
  matchesPrinterModelSuffix,
  presetCompatibility,
  type PrinterCompatibilityIndex,
} from './slicerPrinterMatch';

export function printerPresetModel(
  names: string[],
  printerModels: Record<string, string>,
): string | null {
  for (const name of names) {
    const model = name.replace(/^#\s+/, '').trim().replace(/\s+[\d.]+\s*nozzle$/i, '');
    const registered = Object.entries(printerModels).find(([label]) => label.toLowerCase() === model.toLowerCase());
    if (registered) return registered[1];
  }
  return null;
}

export function sameModel(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  return matchesPrinterModelSuffix(a.trim(), b.trim());
}

/** Connected printers of ``model``; every connected printer when it's unknown. */
export function printersOfModel(
  printers: LoadedSpoolPrinter[],
  model: string | null,
): LoadedSpoolPrinter[] {
  if (!model) return printers;
  return printers.filter((p) => sameModel(p.model, model));
}

/** Whether a printer profile belongs to a connected model, or can't be told. */
export function isConnectedModelPreset(
  data: UnifiedPresetsResponse,
  preset: UnifiedPreset,
  connectedModels: (string | null)[],
  printerModels: Record<string, string>,
): boolean {
  const model = printerPresetModel([...printerPresetParents(data, preset).reverse(), preset.name], printerModels);
  if (model === null) return true;
  return connectedModels.some((c) => sameModel(c, model));
}

/**
 * A printer profile for one of the connected models, for the auto-pick while
 * "only online printers" is on. Prefers the 0.4 nozzle, Bambu's default, as
 * nothing here says which nozzle is fitted.
 */
export function pickConnectedPrinterPreset(
  data: UnifiedPresetsResponse,
  connectedModels: (string | null)[],
  printerModels: Record<string, string>,
): PresetRef | null {
  let fallback: PresetRef | null = null;
  for (const source of SLICE_MODAL_TIER_ORDER) {
    for (const preset of data[source].printer) {
      const names = [...printerPresetParents(data, preset).reverse(), preset.name];
      const model = printerPresetModel(names, printerModels);
      if (model === null || !connectedModels.some((c) => sameModel(c, model))) continue;
      const ref = { source, id: preset.id };
      if (/\b0\.4\s*nozzle$/i.test(names[0])) return ref;
      fallback ??= ref;
    }
  }
  return fallback;
}

/** A profile name without its "# " clone prefix and "@printer" suffix, case-folded. */
export function presetBaseName(name: string): string {
  let s = name.replace(/^#\s*/, '');
  const at = s.lastIndexOf('@');
  if (at > 0) s = s.slice(0, at);
  return s.replace(/\s+/g, ' ').trim().toLowerCase();
}

/** The same, keeping the case, for display. */
export function presetDisplayName(name: string): string {
  let s = name.replace(/^#\s*/, '');
  const at = s.lastIndexOf('@');
  if (at > 0) s = s.slice(0, at);
  return s.replace(/\s+/g, ' ').trim();
}

export function isLoaded(tray: LoadedSpoolTray): boolean {
  return tray.exists ?? Boolean(tray.tray_type);
}

/** The saved profile, unless the slot has been reconfigured since (#3216). */
export function savedPresetFor(tray: LoadedSpoolTray): LoadedSpoolPreset | null {
  const saved = tray.saved_preset;
  if (!saved) return null;
  return slotPresetDescribesTray(saved.preset_id, tray.tray_info_idx, saved.tray_info_idx) ? saved : null;
}

function savedRef(saved: LoadedSpoolPreset): PresetRef | null {
  if (saved.preset_source === 'local') {
    const m = saved.preset_id.match(/^local_(\d+)$/);
    return m ? { source: 'local', id: m[1] } : null;
  }
  if (saved.preset_source === 'cloud' || saved.preset_source === 'orca_cloud') {
    return saved.preset_id ? { source: saved.preset_source, id: saved.preset_id } : null;
  }
  // "builtin_<filament id>" names a bundled filament by its id, which the
  // bundled listing doesn't carry; its saved name is matched below instead.
  return null;
}

function nameCandidates(tray: LoadedSpoolTray, saved: LoadedSpoolPreset | null): string[] {
  const out: string[] = [];
  if (saved?.preset_name) out.push(saved.preset_name);
  const sub = (tray.tray_sub_brands ?? '').trim();
  if (sub) {
    // Bambu's own spools report "PLA Basic"; the profile is "Bambu PLA Basic".
    // Only for Bambu filament ids, so a third-party "PLA Basic" isn't renamed.
    if (/^GF/i.test(tray.tray_info_idx ?? '') && !/^bambu\b/i.test(sub)) out.push(`Bambu ${sub}`);
    out.push(sub);
  } else if (tray.tray_type) {
    out.push(`Generic ${tray.tray_type}`);
  }
  const seen = new Set<string>();
  return out.filter((n) => {
    const key = presetBaseName(n);
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

interface IndexedPreset {
  source: PresetSource;
  preset: UnifiedPreset;
}

/** Filament profiles by base name, each list in the dialog's tier order. */
export type FilamentNameIndex = Map<string, IndexedPreset[]>;

export function buildFilamentNameIndex(data: UnifiedPresetsResponse): FilamentNameIndex {
  const index: FilamentNameIndex = new Map();
  for (const source of SLICE_MODAL_TIER_ORDER) {
    for (const preset of data[source].filament) {
      const key = presetBaseName(preset.name);
      const list = index.get(key);
      if (list) list.push({ source, preset });
      else index.set(key, [{ source, preset }]);
    }
  }
  return index;
}

export interface SlotMatch {
  ref: PresetRef;
  preset: UnifiedPreset;
}

/**
 * The filament profile for ``tray`` on the selected printer, or null when
 * nothing fits. See the header for the order evidence is tried in.
 */
export function matchSlotPreset(
  tray: LoadedSpoolTray,
  data: UnifiedPresetsResponse,
  index: FilamentNameIndex,
  selectedPrinterName: string | null,
  compatIndex: PrinterCompatibilityIndex,
): SlotMatch | null {
  if (!isLoaded(tray) || !tray.tray_type) return null;
  const saved = savedPresetFor(tray);
  const fits = (p: UnifiedPreset) => presetCompatibility(p, 'filament', selectedPrinterName, compatIndex);

  if (saved) {
    const ref = savedRef(saved);
    const preset = ref && findPreset(data, ref, 'filament');
    // The user picked this profile for the slot, so its material isn't
    // second-guessed — only whether it is for the selected printer.
    if (ref && preset && fits(preset) !== 'mismatch') return { ref: { source: preset.source, id: preset.id }, preset };
  }

  const savedSource = saved ? savedRef(saved)?.source : undefined;
  for (const name of nameCandidates(tray, saved)) {
    const entries = index.get(presetBaseName(name)) ?? [];
    // The tier the saved profile came from goes first, then the usual order.
    const ordered = savedSource
      ? [...entries.filter((e) => e.source === savedSource), ...entries.filter((e) => e.source !== savedSource)]
      : entries;
    let unknown: SlotMatch | null = null;
    for (const { source, preset } of ordered) {
      if (statesDifferentMaterial(preset, tray.tray_type ?? '')) continue;
      const fit = fits(preset);
      if (fit === 'match') return { ref: { source, id: preset.id }, preset };
      if (fit === 'unknown' && !unknown) unknown = { ref: { source, id: preset.id }, preset };
    }
    if (unknown) return unknown;
  }
  return null;
}

/** "#RRGGBB" from the printer's RRGGBBAA, or null when it isn't one. */
export function trayColourHex(tray: Pick<LoadedSpoolTray, 'tray_color'>): string | null {
  const raw = (tray.tray_color ?? '').replace(/^#/, '');
  return /^[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$/.test(raw) ? `#${raw.slice(0, 6).toUpperCase()}` : null;
}
