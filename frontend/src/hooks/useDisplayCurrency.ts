import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { getCurrencySymbol, resolveDisplayCurrencyCode } from '../utils/currency';

export function useDisplayCurrency(fallbackCurrency?: string | null) {
  const canLoadProfiles = typeof api.getBusinessProfileOptions === 'function';
  const { data: profiles } = useQuery({
    queryKey: ['businessProfileOptions'],
    queryFn: () => api.getBusinessProfileOptions(),
    enabled: canLoadProfiles,
    retry: false,
  });

  const currencyCode = resolveDisplayCurrencyCode(profiles, fallbackCurrency);
  return {
    currencyCode,
    currencySymbol: getCurrencySymbol(currencyCode),
  };
}
