import { describe, expect, it } from 'vitest';
import type { SlotMaterial } from '../../api/client';
import { computeFilamentWarnings } from '../../components/PrintModal/filamentWarnings';

const slot = (
  globalTrayId: number,
  materialKey: string,
  remaining: number,
  extruder = 0,
): SlotMaterial => ({
  ams_id: Math.floor(globalTrayId / 4),
  tray_id: globalTrayId % 4,
  global_tray_id: globalTrayId,
  material_key: materialKey,
  remaining_g: remaining,
  extruder,
});

const requirements = [
  { slot_id: 1, type: 'PLA', color: '#000000', used_grams: 80 },
];

describe('computeFilamentWarnings', () => {
  it('accepts a short mapped spool when an eligible backup covers the need', () => {
    const warnings = computeFilamentWarnings(
      requirements,
      [0],
      [slot(0, 'preset:GFA00|color:000000', 60), slot(1, 'preset:GFA00|color:000000', 40)],
      true,
    );

    expect(warnings).toEqual([]);
  });

  it('does not pool a different colour or extruder side', () => {
    const warnings = computeFilamentWarnings(
      requirements,
      [0],
      [
        slot(0, 'preset:GFA00|color:000000', 60),
        slot(1, 'preset:GFA00|color:FFFFFF', 1000),
        slot(4, 'preset:GFA00|color:000000', 1000, 1),
      ],
      true,
    );

    expect(warnings).toEqual([
      { globalTrayId: 0, requiredGrams: 80, remainingGrams: 60, pooled: false },
    ]);
  });

  it('reports one pooled warning when two mapped slots share one insufficient pool', () => {
    const warnings = computeFilamentWarnings(
      [
        { slot_id: 1, type: 'PLA', color: '#000000', used_grams: 50 },
        { slot_id: 2, type: 'PLA', color: '#000000', used_grams: 50 },
      ],
      [0, 1],
      [slot(0, 'preset:GFA00|color:000000', 30), slot(1, 'preset:GFA00|color:000000', 40)],
      true,
    );

    expect(warnings).toEqual([
      { globalTrayId: 0, requiredGrams: 100, remainingGrams: 70, pooled: true },
    ]);
  });

  it('weighs only the mapped slot when backup is disabled', () => {
    const warnings = computeFilamentWarnings(
      requirements,
      [0],
      [slot(0, 'preset:GFA00|color:000000', 60), slot(1, 'preset:GFA00|color:000000', 1000)],
      false,
    );

    expect(warnings).toEqual([
      { globalTrayId: 0, requiredGrams: 80, remainingGrams: 60, pooled: false },
    ]);
  });
});
