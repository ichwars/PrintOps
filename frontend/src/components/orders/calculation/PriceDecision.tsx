import { resolveSupportedLanguage } from '../../../i18n';
import { useTranslation } from 'react-i18next';
import type { CalculationPreview } from '../../../api/calculations';

export function PriceDecision({ preview, locale, currency }: { preview: CalculationPreview | null; locale: string; currency: string }) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language }); const money = (value?: string) => value === undefined ? '–' : new Intl.NumberFormat(locale, { style: 'currency', currency }).format(Number(value));
  const cards = [[t('orders.runtimeCalculation.productionCost', { lng: language }), money(preview?.production_cost)], [t('orders.runtimeCalculation.profit', { lng: language }), money(preview?.contribution)], [t('orders.runtimeCalculation.effectiveMarginPriceDecision', { lng: language }), preview ? `${(Number(preview.effective_margin) * 100).toFixed(1)} %` : '–'], [t('orders.runtimeCalculation.unitPrice', { lng: language }), money(preview?.unit_price)], [t('orders.runtimeCalculation.netLabel', { lng: language }), money(preview?.net_price)], [t('orders.runtimeCalculation.grossLabel', { lng: language }), money(preview?.gross_price)]];
  return <section className="rounded-xl border border-bambu-green/30 bg-bambu-green/5 p-4"><div className="flex items-center justify-between"><h3 className="font-semibold text-white">{t('orders.runtimeCalculation.priceDecision', { lng: language })}</h3><span className="rounded-full bg-bambu-green/15 px-2 py-1 text-xs text-bambu-green">Live</span></div><div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{cards.map(([label, value]) => <div key={label} className="rounded-lg bg-bambu-dark p-3"><span className="text-xs text-bambu-gray">{label}</span><strong className="mt-1 block text-lg text-white">{value}</strong></div>)}</div></section>;
}
