import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import { getCurrencySymbol } from '../utils/currency';

export function useDisplayCurrency(fallbackCurrency?: string | null) {
  const canLoadDisplayCurrency = typeof api.getDisplayCurrency === 'function';
  const { data } = useQuery({
    queryKey: ['display-currency'],
    queryFn: () => api.getDisplayCurrency(),
    enabled: canLoadDisplayCurrency,
    retry: false,
  });

  const currencyCode = data?.currency || fallbackCurrency || 'EUR';
  return {
    currencyCode,
    currencySymbol: getCurrencySymbol(currencyCode),
  };
}
