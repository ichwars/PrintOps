import type { PaymentMethod } from '../api/documentManagement';
import i18n, { resolveSupportedLanguage } from '../i18n';

// Read the current catalog when labels are constructed. The dashboard uses
// useTranslation to refresh these labels after the language changes.
export function dashboardText(key: string, values?: Record<string, string | number>) {
  return i18n.t(`orders.runtimeDashboard.${key}`, {
    ...values, lng: resolveSupportedLanguage(i18n.language || 'en'),
  });
}

export const dashboardPaymentMethod = (method: PaymentMethod) => dashboardText(`paymentMethods.${method}`);

export function dashboardEnergySource(source: string | null | undefined, fallback: string) {
  if (!source) return fallback;
  return ['smart_plug_live', 'smart_plug_snapshots', 'print_logs'].includes(source)
    ? dashboardText(`energySources.${source}`)
    : source;
}

export type DateRangeValue = '7' | '30' | '90' | '365';

export const dateRangeOptions: Array<{ value: DateRangeValue; days: number; label: string }> = [
  { value: '7', days: 7, get label() { return dashboardText('last7Days'); } },
  { value: '30', days: 30, get label() { return dashboardText('last30Days'); } },
  { value: '90', days: 90, get label() { return dashboardText('last90Days'); } },
  { value: '365', days: 365, get label() { return dashboardText('last12Months'); } },
];

export const isDateRangeValue = (value: string | null): value is DateRangeValue =>
  dateRangeOptions.some((option) => option.value === value);
