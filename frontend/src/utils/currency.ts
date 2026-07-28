const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$',
  EUR: '€',
  GBP: '£',
  CHF: 'Fr.',
  JPY: '¥',
  CNY: '¥',
  CAD: '$',
  AUD: '$',
  INR: '₹',
  HKD: 'HK$',
  KRW: '₩',
  SEK: 'kr',
  NOK: 'kr',
  DKK: 'kr',
  PLN: 'zł',
  BRL: 'R$',
  TWD: 'NT$',
  SGD: 'S$',
  NZD: 'NZ$',
  MXN: 'MX$',
  BZD: 'BZ$',
  MYR: 'RM',
  CZK: 'Kč',
  THB: '฿',
  ZAR: 'R',
  TRY: '₺',
  RUB: '₽',
  HUF: 'Ft',
  ILS: '₪',
  UAH: '₴',
  IDR: 'Rp',
};

export function getCurrencySymbol(currencyCode: string): string {
  return CURRENCY_SYMBOLS[currencyCode.toUpperCase()] || currencyCode;
}

type CurrencyProfile = {
  default_currency?: string | null;
  is_default?: boolean;
  is_active?: boolean;
};

export function resolveDisplayCurrencyCode(
  profiles: CurrencyProfile[] | undefined,
  fallbackCurrency?: string | null,
): string {
  const defaultActiveProfile = profiles?.find((profile) => profile.is_default && profile.is_active);
  const defaultProfile = defaultActiveProfile ?? profiles?.find((profile) => profile.is_default);
  const activeProfile = defaultProfile ?? profiles?.find((profile) => profile.is_active);
  const profileCurrency = activeProfile?.default_currency?.trim();
  if (profileCurrency) return profileCurrency.toUpperCase();

  const fallback = fallbackCurrency?.trim();
  return (fallback || 'EUR').toUpperCase();
}

export const SUPPORTED_CURRENCIES = Object.entries(CURRENCY_SYMBOLS).map(([code, symbol]) => ({
  code,
  label: `${code} (${symbol})`,
}));
