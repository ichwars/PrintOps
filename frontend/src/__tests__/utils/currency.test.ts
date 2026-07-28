import { describe, it, expect } from 'vitest';
import { getCurrencySymbol, resolveDisplayCurrencyCode, SUPPORTED_CURRENCIES } from '../../utils/currency';

describe('getCurrencySymbol', () => {
  it('returns $ for USD', () => {
    expect(getCurrencySymbol('USD')).toBe('$');
  });

  it('returns € for EUR', () => {
    expect(getCurrencySymbol('EUR')).toBe('€');
  });

  it('returns £ for GBP', () => {
    expect(getCurrencySymbol('GBP')).toBe('£');
  });

  it('returns ₹ for INR', () => {
    expect(getCurrencySymbol('INR')).toBe('₹');
  });

  it('returns HK$ for HKD', () => {
    expect(getCurrencySymbol('HKD')).toBe('HK$');
  });

  it('returns RM for MYR', () => {
    expect(getCurrencySymbol('MYR')).toBe('RM');
  });

  it('returns ₴ for UAH', () => {
    expect(getCurrencySymbol('UAH')).toBe('₴');
  });

  it('returns BZ$ for BZD', () => {
    expect(getCurrencySymbol('BZD')).toBe('BZ$');
  });

  it('returns the code itself for unknown currencies', () => {
    expect(getCurrencySymbol('XYZ')).toBe('XYZ');
  });

  it('is case-insensitive', () => {
    expect(getCurrencySymbol('usd')).toBe('$');
    expect(getCurrencySymbol('eur')).toBe('€');
  });
});

describe('SUPPORTED_CURRENCIES', () => {
  it('contains INR', () => {
    expect(SUPPORTED_CURRENCIES.find((c) => c.code === 'INR')).toBeDefined();
  });

  it('contains MYR', () => {
    expect(SUPPORTED_CURRENCIES.find((c) => c.code === 'MYR')).toBeDefined();
  });

  it('contains BZD', () => {
    expect(SUPPORTED_CURRENCIES.find((c) => c.code === 'BZD')).toBeDefined();
  });

  it('contains IDR', () => {
    expect(SUPPORTED_CURRENCIES.find((c) => c.code === 'IDR')).toBeDefined();
  });

  it('has 31 entries', () => {
    expect(SUPPORTED_CURRENCIES).toHaveLength(31);
  });
});

describe('resolveDisplayCurrencyCode', () => {
  it('prefers the active default business profile currency', () => {
    expect(resolveDisplayCurrencyCode([
      { default_currency: 'USD', is_default: false, is_active: true },
      { default_currency: 'eur', is_default: true, is_active: true },
    ], 'CHF')).toBe('EUR');
  });

  it('falls back to the configured app currency when no business profile is available', () => {
    expect(resolveDisplayCurrencyCode([], 'CHF')).toBe('CHF');
    expect(resolveDisplayCurrencyCode(undefined, 'USD')).toBe('USD');
  });

  it('uses EUR as the final display fallback', () => {
    expect(resolveDisplayCurrencyCode([], null)).toBe('EUR');
  });
});
