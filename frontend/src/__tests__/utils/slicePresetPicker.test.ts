import { describe, expect, it } from 'vitest';

import type { UnifiedPreset, UnifiedPresetsBySlot, UnifiedPresetsResponse } from '../../api/client';
import {
  pickFilamentForSlot,
  pickProcessDefault,
  statesDifferentMaterial,
} from '../../utils/slicePresetPicker';
import { buildCompatibilityIndex } from '../../utils/slicerPrinterMatch';

const X1C = 'Bambu Lab X1 Carbon 0.4 nozzle';
const P1S = 'Bambu Lab P1S 0.4 nozzle';
const A1 = 'Bambu Lab A1 0.4 nozzle';
const index = buildCompatibilityIndex({
  'Bambu Lab X1 Carbon': 'X1C',
  'Bambu Lab P1S': 'P1S',
  'Bambu Lab A1': 'A1',
});

function empty(): UnifiedPresetsBySlot {
  return { printer: [], process: [], filament: [] };
}

function unified(overrides: Partial<UnifiedPresetsResponse> = {}): UnifiedPresetsResponse {
  return {
    orca_cloud: empty(),
    cloud: empty(),
    local: empty(),
    standard: empty(),
    cloud_status: 'ok',
    orca_cloud_status: 'ok',
    ...overrides,
  };
}

function standard(
  slot: 'process' | 'filament',
  entries: Partial<UnifiedPreset>[],
): UnifiedPresetsResponse {
  const list = entries.map((entry) => ({
    id: entry.name as string,
    source: 'standard' as const,
    ...entry,
  })) as UnifiedPreset[];
  return unified({ standard: { ...empty(), [slot]: list } });
}

describe('statesDifferentMaterial', () => {
  it('only rejects a stated, different material', () => {
    expect(statesDifferentMaterial({ filament_type: 'PETG' }, 'PLA')).toBe(true);
    expect(statesDifferentMaterial({ filament_type: ' pla ' }, 'PLA')).toBe(false);
    expect(statesDifferentMaterial({ filament_type: 'PA12-CF' }, 'PA-CF')).toBe(false);
    expect(statesDifferentMaterial({ filament_type: null }, 'PLA')).toBe(false);
    expect(statesDifferentMaterial({ filament_type: 'PETG' }, '')).toBe(false);
  });
});

describe('pickFilamentForSlot', () => {
  it('does not choose PETG for a PLA plate just because its colour is closer', () => {
    const presets = standard('filament', [
      { name: 'PETG red', filament_type: 'PETG', filament_colour: '#FF0000' },
      { name: 'PLA white', filament_type: 'PLA', filament_colour: '#FFFFFF' },
    ]);

    expect(pickFilamentForSlot(presets, { type: 'PLA', color: '#FF0000' }, A1, index)).toEqual({
      source: 'standard',
      id: 'PLA white',
    });
  });

  it('keeps an unknown material eligible and fills the slot', () => {
    const presets = standard('filament', [
      { name: 'Unknown', filament_type: null },
      { name: 'PETG white', filament_type: 'PETG', filament_colour: '#FFFFFF' },
    ]);

    expect(pickFilamentForSlot(presets, { type: 'PLA', color: '#FFFFFF' }, A1, index)?.id).toBe('Unknown');
  });

  it('prefers a canonically equivalent engineering material over an unknown preset', () => {
    const presets = standard('filament', [
      { name: 'Unknown', filament_type: null, filament_colour: '#FFFFFF' },
      { name: 'PA12-CF black', filament_type: 'PA12-CF', filament_colour: '#000000' },
    ]);

    expect(pickFilamentForSlot(presets, { type: 'PA-CF', color: '#FFFFFF' }, A1, index)?.id).toBe(
      'PA12-CF black',
    );
  });
});

describe('pickProcessDefault', () => {
  it('uses compatible_printers even when the preset name names another model', () => {
    const presets = standard('process', [
      { name: '0.06mm Fine @BBL A1', compatible_printers: [A1] },
      { name: '0.20mm Standard @BBL X1C', compatible_printers: [X1C, P1S] },
    ]);

    expect(pickProcessDefault(presets, P1S, index)?.id).toBe('0.20mm Standard @BBL X1C');
  });

  it('prefers the normal 0.20mm process within an equally compatible tier', () => {
    const presets = standard('process', [
      { name: '0.08mm Extra Fine @BBL X1C', compatible_printers: [X1C] },
      { name: '0.20mm Standard @BBL X1C', compatible_printers: [X1C] },
      { name: '0.28mm Draft @BBL X1C', compatible_printers: [X1C] },
    ]);

    expect(pickProcessDefault(presets, X1C, index)?.id).toBe('0.20mm Standard @BBL X1C');
  });

  it('never overrides the process explicitly named by the source file', () => {
    const presets = standard('process', [
      { name: '0.08mm Extra Fine @BBL X1C', compatible_printers: [X1C] },
      { name: '0.20mm Standard @BBL X1C', compatible_printers: [X1C] },
    ]);

    expect(pickProcessDefault(presets, X1C, index, '0.08mm Extra Fine @BBL X1C')?.id).toBe(
      '0.08mm Extra Fine @BBL X1C',
    );
  });
});
