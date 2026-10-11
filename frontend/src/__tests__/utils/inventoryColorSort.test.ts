import { describe, expect, it } from 'vitest';
import { classifyInventoryColor, compareInventoryColors } from '../../utils/inventoryColorSort';

function color(id: number, rgba: string | null, extra_colors: string | null = null) {
  return { id, rgba, extra_colors };
}

describe('inventory actual-color sorting', () => {
  it.each([
    ['000000FF', 'neutral'], ['808080', 'neutral'], ['FFFFFFFF', 'neutral'],
    ['8B4513FF', 'brown'], ['FFD700FF', 'chromatic'], ['FF0000FF', 'chromatic'],
    ['00000000', 'transparent'], ['FF000080', 'transparent'],
    [null, 'missing'], ['', 'missing'], ['#oops', 'missing'], ['FFFFFFzzz', 'missing'],
  ])('classifies %s by actual RGB/alpha values as %s', (rgba, expected) => {
    expect(classifyInventoryColor(color(1, rgba))).toBe(expected);
  });

  it('orders black, gray, white, brown, spectrum, transparent, multicolor, and missing', () => {
    const spools = [color(12, null), color(9, '0000FFFF'), color(5, 'FF0000FF'),
      color(3, 'FFFFFFFF'), color(2, '808080FF'), color(1, '000000FF'),
      color(11, 'FF0000FF', 'FF0000,0000FF'), color(10, '00000000'),
      color(8, '00FF00FF'), color(7, 'FFFF00FF'), color(6, 'FF8000FF'), color(4, '8B4513FF')];
    expect([...spools].sort(compareInventoryColors).map(s => s.id)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
    expect([...spools].reverse().sort(compareInventoryColors).map(s => s.id)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
  });

  it('sorts the displayed gradient stops instead of an unused base color', () => {
    expect(classifyInventoryColor(color(1, 'FF0000FF', '0000FF'))).toBe('chromatic');
    expect(compareInventoryColors(color(1, 'FF0000FF', '0000FF'), color(2, '00FF00FF'))).toBeGreaterThan(0);
    expect(classifyInventoryColor(color(1, 'FF0000FF', '00000000,FFFFFF00'))).toBe('transparent');
    expect(classifyInventoryColor(color(1, 'FF0000FF', '00FF00,0000FF'))).toBe('multicolor');
  });

  it('normalizes hex notation and repeated stops, with ID as the final tie-breaker', () => {
    expect(compareInventoryColors(color(4, '#ff0000'), color(2, 'FF0000FF'))).toBeGreaterThan(0);
    expect(classifyInventoryColor(color(1, null, '#FF0000,ff0000ff'))).toBe('chromatic');
    expect(compareInventoryColors(color(4, null), color(2, 'invalid'))).toBeGreaterThan(0);
  });
});
