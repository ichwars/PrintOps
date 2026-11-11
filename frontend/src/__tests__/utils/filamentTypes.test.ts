import { describe, expect, it } from 'vitest';
import { splitFilamentTypes } from '../../utils/filamentTypes';

describe('splitFilamentTypes', () => {
  it('recognizes comma-separated names from spool and slicer metadata', () => {
    expect(splitFilamentTypes('PLA Basic,PLA, PETG HF')).toEqual(['PLA Basic', 'PLA', 'PETG HF']);
  });

  it('drops blank entries and counts each distinct material once', () => {
    expect(splitFilamentTypes(' PLA ,, PETG, PLA,')).toEqual(['PLA', 'PETG']);
    expect(splitFilamentTypes(null)).toEqual([]);
  });
});
