import { afterEach, describe, expect, it } from 'vitest';
import { buildQueuedFilamentOverrides, fixedPrinterFilamentOverrides } from '../../components/PrintModal/filamentOverrides';
import { __resetColorCatalogForTests, setColorCatalog } from '../../utils/colors';

describe('queued filament override labels', () => {
  afterEach(() => __resetColorCatalogForTests());

  it('uses the selected product line and stores the selected preset', () => {
    setColorCatalog({ '000000': 'Black' }, { 'pla matte|000000': 'Charcoal' });
    const filaments = [{ slot_id: 1, type: 'PLA', color: '#000000', tray_info_idx: 'GFA00', used_grams: 12 }];
    const overrides = { 1: { type: 'PLA', color: '#000000', tray_info_idx: 'GFA01', tray_sub_brands: 'PLA Matte' } };
    const presets = { GFA00: 'Bambu PLA Basic', GFA01: 'Bambu PLA Matte' };
    expect(buildQueuedFilamentOverrides(filaments, overrides, {}, presets)).toEqual([
      { slot_id: 1, type: 'PLA', color: '#000000', color_name: 'Charcoal', tray_info_idx: 'GFA01', force_color_match: false },
    ]);
  });
});

describe('fixed printer force colour', () => {
  const forced = { slot_id: 1, type: 'PLA', color: '#112233', force_color_match: true };
  const options = {
    entries: [forced],
    changes: {},
    forceVisible: true,
    status: undefined,
    chosenTrays: undefined,
  };

  it('uses the sliced requirement when the tray was auto-picked', () => {
    expect(fixedPrinterFilamentOverrides(options)).toEqual([forced]);
  });

  it('does not save an old tick when more printers were selected', () => {
    expect(fixedPrinterFilamentOverrides({ ...options, forceVisible: false })).toBeUndefined();
  });

  it('does not force a stale or unreadable manual tray', () => {
    expect(fixedPrinterFilamentOverrides({ ...options, chosenTrays: { 1: 0 } })).toBeUndefined();
    expect(fixedPrinterFilamentOverrides({
      ...options, chosenTrays: { 1: 0 }, changes: { 1: { type: 'PLA', color: '#112233' } },
    })).toEqual([{ ...forced, force_color_match: false }]);
  });
});
