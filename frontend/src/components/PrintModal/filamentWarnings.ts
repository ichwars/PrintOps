import type { SlotMaterial } from '../../api/client';

interface FilamentRequirement {
  slot_id: number;
  used_grams: number;
}

export interface FilamentWarning {
  globalTrayId: number;
  requiredGrams: number;
  remainingGrams: number;
  pooled: boolean;
}

/** Apply the backend's material identity to the modal's mapped filament need. */
export function computeFilamentWarnings(
  requirements: readonly FilamentRequirement[],
  mapping: readonly number[],
  materials: readonly SlotMaterial[],
  backupEnabled: boolean,
): FilamentWarning[] {
  const slotsByTray = new Map<number, SlotMaterial>();
  materials.forEach((slot) => slotsByTray.set(slot.global_tray_id, slot));

  const demandByTray = new Map<number, number>();
  requirements.forEach((requirement) => {
    if (!Number.isInteger(requirement.slot_id) || requirement.slot_id <= 0 || requirement.used_grams <= 0) return;
    const globalTrayId = mapping[requirement.slot_id - 1];
    if (!Number.isFinite(globalTrayId) || globalTrayId < 0) return;
    demandByTray.set(globalTrayId, (demandByTray.get(globalTrayId) ?? 0) + requirement.used_grams);
  });

  if (!backupEnabled) {
    return [...demandByTray].flatMap(([globalTrayId, requiredGrams]) => {
      const material = slotsByTray.get(globalTrayId);
      if (!material || material.remaining_g >= requiredGrams) return [];
      return [{ globalTrayId, requiredGrams, remainingGrams: material.remaining_g, pooled: false }];
    });
  }

  const poolKey = (slot: SlotMaterial) => `${slot.material_key}\u0000${slot.extruder}`;
  const availableByPool = new Map<string, number>();
  const slotCountByPool = new Map<string, number>();
  slotsByTray.forEach((slot) => {
    const key = poolKey(slot);
    availableByPool.set(key, (availableByPool.get(key) ?? 0) + slot.remaining_g);
    slotCountByPool.set(key, (slotCountByPool.get(key) ?? 0) + 1);
  });

  const demandByPool = new Map<string, { globalTrayId: number; requiredGrams: number }>();
  demandByTray.forEach((requiredGrams, globalTrayId) => {
    const slot = slotsByTray.get(globalTrayId);
    if (!slot) return;
    const key = poolKey(slot);
    const demand = demandByPool.get(key);
    demandByPool.set(key, {
      globalTrayId: demand?.globalTrayId ?? globalTrayId,
      requiredGrams: (demand?.requiredGrams ?? 0) + requiredGrams,
    });
  });

  return [...demandByPool].flatMap(([key, demand]) => {
    const remainingGrams = availableByPool.get(key) ?? 0;
    if (remainingGrams >= demand.requiredGrams) return [];
    return [{
      ...demand,
      remainingGrams,
      pooled: (slotCountByPool.get(key) ?? 0) > 1,
    }];
  });
}
