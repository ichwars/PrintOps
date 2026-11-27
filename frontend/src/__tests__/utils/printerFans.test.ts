import { describe, it, expect } from 'vitest';
import { usesExhaustFanLabel } from '../../pages/printers/printer-fans';

describe('usesExhaustFanLabel', () => {
  // BambuStudio machine profiles label fan 3 "Chamber" only on the
  // X1/X1C/X1E and P1S; every other model uses the default "Exhaust" label.
  it.each(['X1', 'X1C', 'X1E', 'P1S', 'BL-P003'])('labels %s as chamber fan', (model) => {
    expect(usesExhaustFanLabel(model)).toBe(false);
  });

  it.each(['P1P', 'P2S', 'X2D', 'H2D', 'H2D Pro', 'H2C', 'H2S', 'H3C', 'P3C'])(
    'labels %s as exhaust fan',
    (model) => {
      expect(usesExhaustFanLabel(model)).toBe(true);
    }
  );
});
