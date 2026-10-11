import { describe, it, expect } from 'vitest';
import { mapModelCode } from '../../pages/printers/printer-status';

describe('discovery model codes', () => {
  it.each([['C11', 'P1P'], ['C12', 'P1S'], ['C13', 'X1E'], ['N7', 'P2S'], ['BL-P001', 'X1C'], ['BL-P002', 'X1'], ['A04', 'A1 Mini']])('maps %s to %s', (code, expected) => { expect(mapModelCode(code)).toBe(expected); });
});
