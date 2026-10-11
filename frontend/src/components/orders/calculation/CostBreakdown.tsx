import { resolveSupportedLanguage } from '../../../i18n';
import { useTranslation } from 'react-i18next';
import type { CalculationPreview } from '../../../api/calculations';

export function CostBreakdown({ preview, locale, currency }: { preview: CalculationPreview | null; locale: string; currency: string }) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language }); const money = (value: string) => new Intl.NumberFormat(locale, { style: 'currency', currency }).format(Number(value));
  const basisLabel = (basis: string) => {
    if (!locale.startsWith('nl')) return basis;
    const keys: Record<string, string> = {
      'allocated time': 'basisAllocatedTime', 'printer and dryer': 'basisDevices',
      'line items': 'basisLines', 'flat amount': 'basisFlatAmount', 'all operations': 'basisAllOperations',
    };
    if (keys[basis]) return t(`orders.runtimeCalculation.${keys[basis]}`, { lng: language });
    const runs = /^(\d+) runs$/.exec(basis);
    return runs ? t('orders.runtimeCalculation.basisRuns', { lng: language, count: Number(runs[1]) }) : basis;
  };
  return <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark p-4"><h3 className="font-semibold text-white">{t('orders.runtimeCalculation.costBreakdown', { lng: language })}</h3>{!preview ? <p className="mt-3 text-sm text-bambu-gray">{t('orders.runtimeCalculation.enterCompleteProductionValues', { lng: language })}</p> : <div className="mt-3 divide-y divide-bambu-dark-tertiary">{preview.breakdown.map(item => <div key={item.code} className="grid grid-cols-[1fr_auto] gap-3 py-2 text-sm"><div><strong className="text-white">{({ machine: t('orders.runtimeCalculation.machine', { lng: language }), labor: t('orders.runtimeCalculation.labor', { lng: language }), material: t('printops.nav.parts', { lng: language }), energy: t('orders.runtimeCalculation.energyDrying', { lng: language }), additive_materials: t('orders.runtimeCalculation.additionalMaterials', { lng: language }), consumables: t('orders.runtimeCalculation.consumablesCostBreakdown', { lng: language }), scrap: t('orders.runtimeCalculation.scrapCostBreakdown', { lng: language }), risk: t('orders.runtimeCalculation.risk', { lng: language }), packaging: t('orders.runtimeCalculation.packaging', { lng: language }), shipping: t('orders.runtimeCalculation.shippingCost', { lng: language }) } as Record<string, string>)[item.code] ?? item.label}</strong><span className="ml-2 text-xs text-bambu-gray">{basisLabel(item.basis)}</span></div><strong className="text-white">{money(item.amount)}</strong></div>)}</div>}</section>;
}
