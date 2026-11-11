import type { PrintQueueItem, PrinterStatus } from '../../api/client';
import { buildLoadedFilaments } from '../../hooks/useFilamentMapping';
import { getColorName } from '../../utils/colors';
import type { FilamentOverrideChoice, FilamentReqsData } from './types';
import { extractMaterialHint } from './useFilamentLabels';

export function buildQueuedFilamentOverrides(
  requirements: FilamentReqsData['filaments'] | undefined,
  overrides: Record<number, FilamentOverrideChoice>,
  forceColor: Record<number, boolean>,
  presetNames: Record<string, string>,
) {
  const entries = [];
  const slots = requirements ?? Object.entries(overrides).map(([slot, choice]) => ({ ...choice, slot_id: Number(slot) }));
  for (const req of slots) {
    const override = overrides[req.slot_id];
    const forced = forceColor[req.slot_id] ?? false;
    if (!override && !forced) continue;
    const choice: FilamentOverrideChoice = override ?? req;
    const presetName = presetNames[choice.tray_info_idx ?? ''];
    const material = choice.tray_sub_brands || (presetName ? extractMaterialHint(presetName) : choice.type);
    entries.push({
      slot_id: req.slot_id,
      type: choice.type,
      color: choice.color,
      color_name: getColorName(choice.color, material, choice.tray_info_idx),
      tray_info_idx: override?.tray_info_idx,
      force_color_match: forced,
    });
  }
  return entries.length ? entries : undefined;
}


type QueueOverride = NonNullable<PrintQueueItem['filament_overrides']>[number];

export function fixedPrinterFilamentOverrides({
  entries,
  changes,
  forceVisible,
  chosenTrays,
  status,
  saved,
}: {
  entries: QueueOverride[] | undefined;
  changes: Record<number, FilamentOverrideChoice>;
  forceVisible: boolean;
  chosenTrays: Record<number, number> | undefined;
  status: PrinterStatus | undefined;
  saved?: Pick<PrintQueueItem, 'ams_mapping' | 'filament_overrides'>;
}): QueueOverride[] | undefined {
  const loaded = status?.connected ? buildLoadedFilaments(status) : [];
  const result = entries?.flatMap((entry) => {
    const explicitlyChanged = Boolean(changes[entry.slot_id]);
    const forced = Boolean(entry.force_color_match) && forceVisible;
    if (!forced) return explicitlyChanged ? [{ ...entry, force_color_match: false }] : [];

    const trayId = chosenTrays?.[entry.slot_id];
    const savedEntry = saved?.filament_overrides?.find((old) => old.slot_id === entry.slot_id && old.force_color_match);
    if (savedEntry && (trayId == null || trayId === saved?.ams_mapping?.[entry.slot_id - 1])) return [savedEntry];
    if (trayId == null || trayId < 0) return [entry];

    const filament = loaded.find((spool) => spool.globalTrayId === trayId);
    const liveTray = filament?.isExternal
      ? status?.vt_tray?.find((tray) => (tray.id ?? 254) === trayId)
      : status?.ams?.find((unit) => unit.id === filament?.amsId)?.tray.find((tray) => tray.id === filament?.trayId);
    if (!filament || !liveTray || ('exists' in liveTray && liveTray.exists === false)
      || !/^#?[\da-f]{6}(?:[\da-f]{2})?$/i.test(liveTray.tray_color ?? '')) {
      return explicitlyChanged ? [{ ...entry, force_color_match: false }] : [];
    }
    return [{
      slot_id: entry.slot_id,
      type: filament.type,
      color: filament.color,
      color_name: filament.colorName,
      tray_info_idx: filament.trayInfoIdx || undefined,
      force_color_match: true,
    }];
  });
  return result?.length ? result : undefined;
}
