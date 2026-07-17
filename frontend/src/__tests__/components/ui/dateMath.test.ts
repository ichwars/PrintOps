import { describe, expect, it } from 'vitest';

import {
  addDays,
  addMonthsClamped,
  buildMonthGrid,
  compareDateKeys,
  formatDateKey,
  parseDateKey,
  weekStartsOn,
} from '../../../components/ui/dateMath';

describe('dateMath', () => {
  it('keeps date keys stable across leap days and month clamping', () => {
    expect(addDays('2028-02-28', 1)).toBe('2028-02-29');
    expect(addMonthsClamped('2026-01-31', 1)).toBe('2026-02-28');
    expect(formatDateKey(parseDateKey('2026-07-17')!)).toBe('2026-07-17');
  });

  it('rejects malformed and normalized dates', () => {
    expect(parseDateKey('2026-2-03')).toBeUndefined();
    expect(parseDateKey('2026-02-31')).toBeUndefined();
    expect(parseDateKey('not-a-date')).toBeUndefined();
  });

  it('builds a fixed six-week grid from the locale week start', () => {
    const grid = buildMonthGrid('2026-07-01', weekStartsOn('de-DE'));
    expect(grid).toHaveLength(42);
    expect(grid[0]).toBe('2026-06-29');
    expect(grid.at(-1)).toBe('2026-08-09');
  });

  it('compares stable keys chronologically', () => {
    expect(compareDateKeys('2026-07-16', '2026-07-17')).toBeLessThan(0);
    expect(compareDateKeys('2026-07-17', '2026-07-17')).toBe(0);
    expect(compareDateKeys('2026-07-18', '2026-07-17')).toBeGreaterThan(0);
  });
});
