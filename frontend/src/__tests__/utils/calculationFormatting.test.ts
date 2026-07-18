import { describe, expect, it } from 'vitest';
import { formatCount, formatGrams, formatHours, formatMoney } from '../../utils/calculationFormatting';

describe('calculation formatting', () => {
  it('uses domain-specific precision instead of database precision', () => {
    expect(formatCount('10.000000', 'de-DE')).toBe('10');
    expect(formatGrams('274.220000', 'de-DE')).toBe('274,2 g');
    expect(formatHours('18.940000', 'de-DE')).toBe('18,94 h');
    expect(formatMoney('4.500000', 'de-DE', 'EUR')).toBe('4,50 €');
  });
});
