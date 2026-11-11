import { describe, it, expect, beforeEach } from 'vitest';
import {
  hexToColorName,
  getColorName,
  resolveSpoolColorName,
  setColorCatalog,
  __resetColorCatalogForTests,
} from '../../utils/colors';

describe('hexToColorName', () => {
  it('returns "Unknown" for null/empty input', () => {
    expect(hexToColorName(null)).toBe('Unknown');
    expect(hexToColorName('')).toBe('Unknown');
    expect(hexToColorName(undefined)).toBe('Unknown');
  });

  it('classifies dark low-saturation colors as Dark Gray', () => {
    // Titan Gray hex (5F6367) — low saturation, lightness < 0.4
    expect(hexToColorName('5F6367')).toBe('Dark Gray');
  });

  it('classifies black hex as Black', () => {
    expect(hexToColorName('000000')).toBe('Black');
  });

  it('classifies white hex as White', () => {
    expect(hexToColorName('FFFFFF')).toBe('White');
  });

  // #1545: transparent filament is reported as `00000000` (alpha=00).
  // Without the alpha-aware short-circuit it would fall through to the HSL
  // bucketing and resolve to "Black" because the RGB happens to be 000000.
  it('classifies any alpha=00 rgba as Clear', () => {
    expect(hexToColorName('00000000')).toBe('Clear');
    expect(hexToColorName('FF000000')).toBe('Clear');
    expect(hexToColorName('#abcdef00')).toBe('Clear');
  });

  it('still classifies fully opaque colors via HSL even when alpha is FF', () => {
    expect(hexToColorName('000000FF')).toBe('Black');
    expect(hexToColorName('FFFFFFFF')).toBe('White');
  });
});

describe('getColorName', () => {
  beforeEach(() => {
    __resetColorCatalogForTests();
  });

  it('looks up the runtime color catalog before HSL fallback', () => {
    setColorCatalog({ '5f6367': 'Titan Gray' });
    expect(getColorName('5f6367')).toBe('Titan Gray');
    expect(getColorName('5F6367')).toBe('Titan Gray');
  });

  it('falls back to HSL when hex is not in the runtime catalog', () => {
    // No catalog entry for 123456; HSL bucketing puts it in Blue.
    expect(getColorName('123456')).toBe('Blue');
  });

  it('returns "Unknown" for empty string', () => {
    expect(getColorName('')).toBe('Unknown');
  });

  it('handles hex with # prefix', () => {
    setColorCatalog({ '5f6367': 'Titan Gray' });
    expect(getColorName('#5f6367')).toBe('Titan Gray');
  });

  it('normalizes catalog keys (strips # and lowercases)', () => {
    // Provider can pass keys in any case / with or without '#'; the utility
    // must normalize so lookups succeed regardless of input shape.
    setColorCatalog({ '#F5B6CD': 'Cherry Pink' });
    expect(getColorName('F5B6CD')).toBe('Cherry Pink');
    expect(getColorName('f5b6cd')).toBe('Cherry Pink');
  });

  it('resolves #857 regression — A17-R1 / F5B6CD is Cherry Pink, not Scarlet Red', () => {
    setColorCatalog({ 'f5b6cd': 'Cherry Pink' });
    expect(getColorName('F5B6CDFF')).toBe('Cherry Pink');
  });

  // #1545: alpha=00 must short-circuit catalog lookup too — otherwise a
  // catalog entry on the underlying RGB would mislabel transparent filament.
  it('returns Clear for transparent rgba regardless of catalog entry', () => {
    setColorCatalog({ '000000': 'Inky Night' });
    expect(getColorName('00000000')).toBe('Clear');
    expect(getColorName('000000FF')).toBe('Inky Night');
  });
});

describe('resolveSpoolColorName', () => {
  beforeEach(() => {
    __resetColorCatalogForTests();
    setColorCatalog({ '5f6367': 'Titan Gray' });
  });

  it('returns readable color name directly', () => {
    expect(resolveSpoolColorName('Titan Gray', '5F6367FF')).toBe('Titan Gray');
  });

  it('looks up hex when color_name is a Bambu code', () => {
    expect(resolveSpoolColorName('A06-D0', '5F6367FF')).toBe('Titan Gray');
  });

  it('returns null when color_name is a code and hex is unknown', () => {
    // Opaque, not in catalog — must not be misread as transparent (#1545).
    expect(resolveSpoolColorName('A99-Z9', '123456FF')).toBeNull();
  });

  // #1545
  it('returns Clear for transparent rgba even when color_name is a code', () => {
    expect(resolveSpoolColorName('A99-Z9', '00000000')).toBe('Clear');
  });
});

describe('getColorName with a material (#2875)', () => {
  beforeEach(() => {
    __resetColorCatalogForTests();
    // What the backend ships for a real Bambu catalog: the flat map can only
    // keep one name for #FFFFFF, and the qualified map carries the rest.
    setColorCatalog(
      { ffffff: 'Jade White', '000000': 'Black' },
      { 'pla matte|ffffff': 'Ivory White', 'pla matte|000000': 'Charcoal' },
    );
  });

  it('returns the material-specific name when the caller knows the material', () => {
    expect(getColorName('FFFFFFFF', 'PLA Matte')).toBe('Ivory White');
    expect(getColorName('000000FF', 'PLA Matte')).toBe('Charcoal');
  });

  it('still returns the flat name for a material with no entry of its own', () => {
    expect(getColorName('FFFFFFFF', 'PLA Basic')).toBe('Jade White');
    expect(getColorName('FFFFFFFF', 'Some Third Party Filament')).toBe('Jade White');
  });

  it('ignores case and padding in the material, as tray_sub_brands is not normalized', () => {
    expect(getColorName('FFFFFFFF', '  pla MATTE ')).toBe('Ivory White');
  });

  it('falls back to the flat name when no material is passed', () => {
    expect(getColorName('FFFFFFFF')).toBe('Jade White');
    expect(getColorName('FFFFFFFF', null)).toBe('Jade White');
    expect(getColorName('FFFFFFFF', '')).toBe('Jade White');
  });

  it('keeps Clear ahead of any catalog lookup for a transparent spool', () => {
    expect(getColorName('FFFFFF00', 'PLA Matte')).toBe('Clear');
  });

  it('falls back to HSL when neither map knows the hex', () => {
    expect(getColorName('5F6367', 'PLA Matte')).toBe('Dark Gray');
  });

  it('survives a catalog with no qualified map at all', () => {
    __resetColorCatalogForTests();
    setColorCatalog({ ffffff: 'Jade White' });
    expect(getColorName('FFFFFFFF', 'PLA Matte')).toBe('Jade White');
  });

  it('reads the hex from the last separator, so a material may contain one', () => {
    // Material is free text -- users edit the colour catalog.
    __resetColorCatalogForTests();
    setColorCatalog({ ffffff: 'Jade White' }, { 'pla|matte|ffffff': 'Ivory White' });
    expect(getColorName('FFFFFFFF', 'PLA|Matte')).toBe('Ivory White');
  });

  it('ignores malformed qualified keys instead of poisoning the map', () => {
    __resetColorCatalogForTests();
    setColorCatalog(
      { ffffff: 'Jade White' },
      { 'pla matte|nothex': 'Nope', '|ffffff': 'Nope', 'pla matte': 'Nope', 'pla matte|ffffff': 'Ivory White' },
    );
    expect(getColorName('FFFFFFFF', 'PLA Matte')).toBe('Ivory White');
    expect(getColorName('FFFFFFFF')).toBe('Jade White');
  });
});

describe('getColorName: nearest Bambu colour (#3279)', () => {
  // A colour picked on the printer's touchscreen arrives as a hex a step or
  // two off Bambu Studio's: Blue Grey is 5B6579 in the catalogue, the printer
  // reports 5A657B. The exact lookup missed it and the hue bucket said "Blue".
  const BAMBU = [
    { hex: '5b6579', name: 'Blue Grey', material: 'PLA Basic' },
    { hex: 'ff9016', name: 'Pumpkin Orange', material: 'PLA Basic' },
    { hex: 'ff911a', name: 'Translucent Orange', material: 'PETG Translucent' },
    { hex: 'a6a9aa', name: 'Silver', material: 'PLA Basic' },
  ];

  beforeEach(() => {
    __resetColorCatalogForTests();
    setColorCatalog({}, {}, BAMBU);
  });

  it('names a printer-palette hex by the Bambu colour it is a step away from', () => {
    expect(getColorName('5A657BFF')).toBe('Blue Grey');
    expect(getColorName('5A657B', 'PLA Basic')).toBe('Blue Grey');
  });

  it('keeps the hue bucket for a colour no Bambu entry is close to', () => {
    expect(getColorName('123456')).toBe('Blue');
  });

  it('prefers the colour of the material the caller names', () => {
    // FF9017 is nearer Pumpkin Orange (PLA Basic) than Translucent Orange (PETG).
    expect(getColorName('FF9017')).toBe('Pumpkin Orange');
    expect(getColorName('FF9017', 'PETG Translucent')).toBe('Translucent Orange');
    expect(getColorName('FF9017', ' petg TRANSLUCENT ')).toBe('Translucent Orange');
  });

  it('looks in every Bambu range when the material is not one of them', () => {
    expect(getColorName('5A657B', 'Generic PETG')).toBe('Blue Grey');
  });

  it('does not borrow another range\'s name when the material is a Bambu range', () => {
    expect(getColorName('5A657B', 'PETG Translucent')).toBe('Blue');
  });

  it('never moves a different Bambu colour onto the file colour', () => {
    // #3279's own pair: the file's A4AAAC is Silver, the tray's 5A657B Blue Grey.
    expect(getColorName('A4AAAC')).toBe('Silver');
  });

  it('lets an exact catalogue name win over a nearer-sounding guess', () => {
    __resetColorCatalogForTests();
    setColorCatalog({ '5a657b': 'Slate' }, {}, BAMBU);
    expect(getColorName('5A657B')).toBe('Slate');
  });

  it('forgets the old answers when the catalogue is replaced', () => {
    expect(getColorName('5A657B')).toBe('Blue Grey');
    setColorCatalog({}, {}, [{ hex: '5b6579', name: 'Renamed Grey', material: 'PLA Basic' }]);
    expect(getColorName('5A657B')).toBe('Renamed Grey');
  });

  it('takes the first listed of two equally near colours', () => {
    __resetColorCatalogForTests();
    setColorCatalog({}, {}, [
      { hex: '5b6579', name: 'Blue Grey', material: 'PLA Basic' },
      { hex: '5b6579', name: 'Slate Grey', material: 'PLA Matte' },
    ]);
    expect(getColorName('5A657B')).toBe('Blue Grey');
  });

  it('stays within the material when it has Bambu colours of its own', () => {
    // A PLA Basic slot at 8F8F8F is not Translucent Gray (PETG Translucent,
    // 0.3 away) just because PLA Basic's Gray is further than the threshold.
    __resetColorCatalogForTests();
    setColorCatalog({}, {}, [
      { hex: '8e8e8e', name: 'Translucent Gray', material: 'PETG Translucent' },
      { hex: '8e9089', name: 'Gray', material: 'PLA Basic' },
    ]);
    expect(getColorName('8F8F8F', 'PLA Basic')).toBe('Gray');
    expect(getColorName('8F8F8F', 'PLA Basic')).not.toBe('Translucent Gray');
    expect(getColorName('8F8F8F', 'Some Third Party PLA')).toBe('Translucent Gray');
  });

  it("finds the material's own colour before another range's exact hex", () => {
    // Pumpkin Orange (PLA Basic) owns FF9016 in the flat map; a PETG
    // Translucent slot one step away from it is still Translucent Orange.
    __resetColorCatalogForTests();
    setColorCatalog({ ff9016: 'Pumpkin Orange' }, {}, BAMBU);
    expect(getColorName('FF9016', 'PETG Translucent')).toBe('Translucent Orange');
    expect(getColorName('FF9016')).toBe('Pumpkin Orange');
  });

  it("takes the material from the slot's preset when the printer sends none", () => {
    // Without RFID the printer leaves tray_sub_brands empty but still reports
    // the preset picked on its screen (GFA00 = Bambu PLA Basic).
    __resetColorCatalogForTests();
    setColorCatalog({}, {}, BAMBU, { GFA00: 'PLA Basic', GFG01: 'PETG Translucent' });
    expect(getColorName('FF9017', '', 'GFG01')).toBe('Translucent Orange');
    expect(getColorName('FF9017', null, 'gfa00')).toBe('Pumpkin Orange');
    // tray_sub_brands, when there is one, is the more direct answer.
    expect(getColorName('FF9017', 'PLA Basic', 'GFG01')).toBe('Pumpkin Orange');
  });

  it('keeps Clear for a transparent spool', () => {
    expect(getColorName('5A657B00')).toBe('Clear');
  });

  it('ignores malformed entries', () => {
    __resetColorCatalogForTests();
    setColorCatalog({}, {}, [
      { hex: 'zzzzzz', name: 'Nope', material: 'PLA Basic' },
      { hex: '5b6579', name: '', material: 'PLA Basic' },
    ]);
    expect(getColorName('5A657B')).toBe('Blue');
  });
});
