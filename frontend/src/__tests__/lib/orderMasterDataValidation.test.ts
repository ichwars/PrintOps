import { describe, expect, it } from 'vitest';
import {
  isIsoCountryCode,
  isIsoCurrencyCode,
  normalizeNfkcCasefold,
  orderMasterDataValidationMetadata,
} from '../../lib/orderMasterDataValidation';

describe('order master data validation', () => {
  it('uses the backend pycountry country set instead of browser region data', () => {
    expect(isIsoCountryCode('DE')).toBe(true);
    expect(isIsoCountryCode('AC')).toBe(false);
  });

  it('uses the backend pycountry currency set instead of browser ICU data', () => {
    expect(isIsoCurrencyCode('ANG')).toBe(false);
    expect(isIsoCurrencyCode('BGN')).toBe(false);
    expect(isIsoCurrencyCode('BOV')).toBe(true);
  });

  it('matches Python NFKC casefold for full casefold expansions', () => {
    expect(normalizeNfkcCasefold('Straße')).toBe('strasse');
    expect(normalizeNfkcCasefold('ΐ')).toBe('ι\u0308\u0301');
  });

  it('publishes the exact generated source versions and set sizes', () => {
    expect(orderMasterDataValidationMetadata).toEqual({
      pycountryVersion: '26.2.16',
      pythonVersion: '3.13.x',
      unicodeVersion: '15.1.0',
      countryCodeCount: 249,
      currencyCodeCount: 178,
      assignedCodePointCount: 289394,
      assignedRangeCount: 707,
      fullCasefoldOverrideCount: 297,
    });
  });

  it('preserves code points that were unassigned in backend Unicode 15.1', () => {
    expect(normalizeNfkcCasefold('\u{10D50}')).toBe('\u{10D50}');
  });

  it('normalizes and composes each complete Unicode-15.1-assigned run', () => {
    expect(normalizeNfkcCasefold('A\u030A\u212B\u1100\u1161')).toBe('\u00E5\u00E5\uAC00');
  });

  it('treats Unicode-15.1-unassigned code points as normalization boundaries', () => {
    expect(normalizeNfkcCasefold('A\u030A\u{10D50}E\u0301')).toBe('\u00E5\u{10D50}\u00E9');
  });
});
