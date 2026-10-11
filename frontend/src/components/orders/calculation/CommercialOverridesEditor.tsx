import { resolveSupportedLanguage } from '../../../i18n';
import { useTranslation } from 'react-i18next';
import { RotateCcw } from 'lucide-react';

import type { EffectiveCalculationDefaults } from '../../../api/calculations';
import { IconButton, NumberField } from '../../ui';

const fields = [
  ['setup_hours', 'setup_hours', 'orders.runtimeCalculation.overrideSetupHours', false, '0.05'],
  ['post_processing_hours_per_unit', 'post_processing_hours_per_unit', 'orders.runtimeCalculation.overridePostProcessingHoursPerUnit', false, '0.01'],
  ['cad_hours', 'cad_hours', 'orders.runtimeCalculation.overrideCadHours', false, '0.05'],
  ['qa_hours', 'qa_hours', 'orders.runtimeCalculation.overrideQaHours', false, '0.01'],
  ['material_price_per_kg', 'filament_price_per_kg', 'orders.runtimeCalculation.overrideMaterialPricePerKg', false, '0.01'],
  ['material_markup_rate', 'material_markup_percent', 'orders.runtimeCalculation.overrideMaterialMarkupRate', true, '0.1'],
  ['scrap_rate', 'scrap_percent', 'orders.runtimeCalculation.overrideScrapRate', true, '0.1'],
  ['labor_rate', 'hourly_rate', 'orders.runtimeCalculation.overrideLaborRate', false, '0.01'],
  ['consumables', 'consumables', 'orders.runtimeCalculation.overrideConsumables', false, '0.01'],
  ['packaging', 'packaging', 'orders.runtimeCalculation.overridePackaging', false, '0.01'],
  ['shipping', 'shipping', 'orders.runtimeCalculation.overrideShipping', false, '0.01'],
  ['discount_rate', 'discount_percent', 'orders.runtimeCalculation.overrideDiscountRate', true, '0.1'],
] as const;

interface Props {
  values: Record<string, string>;
  defaults?: EffectiveCalculationDefaults;
  locale: string;
  onChange: (values: Record<string, string>) => void;
}

export function CommercialOverridesEditor({ values, defaults = {}, locale, onChange }: Props) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language });
  const resetField = (key: string) => {
    const next = { ...values };
    delete next[key];
    onChange(next);
  };
  return <section><div className="mb-3"><h3 className="font-semibold text-white">5. {t('orders.runtimeCalculation.laborPostProcessing', { lng: language })}</h3><p className="text-xs text-bambu-gray">{t('orders.runtimeCalculation.centralSettingsAreShownAndCanBeOverriddenForThisCalculation', { lng: language })}</p></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{fields.map(([key, defaultKey, labelKey, percentage, step]) => {
    const label = t(labelKey, { lng: language });
    const overridden = values[key] !== undefined;
    const displayed = overridden ? String(Number(values[key]) * (percentage ? 100 : 1)) : '';
    const fallback = defaults[defaultKey]?.value ?? '0';
    return <label key={key} className="rounded-lg bg-bambu-dark p-3 text-sm text-bambu-gray"><span className="flex min-h-[34px] items-center justify-between gap-2"><span>{label}</span>{overridden ? <IconButton label={t('orders.runtimeCalculation.resetLabel', { lng: language, label })} title={t('orders.runtimeCalculation.resetLabel', { lng: language, label })} icon={RotateCcw} size="sm" onClick={(event) => { event.preventDefault(); resetField(key); }} className="!h-7 !w-7 text-amber-200 hover:bg-amber-500/10" /> : null}</span><NumberField aria-label={label} min="0" step={step} value={displayed} placeholder={fallback} onChange={(event) => { const next = { ...values }; if (!event.target.value) delete next[key]; else next[key] = String(Number(event.target.value) / (percentage ? 100 : 1)); onChange(next); }} containerClassName="mt-2" className="h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white" /><span className="mt-1 block text-xs">{overridden ? (t('orders.runtimeCalculation.overridden', { lng: language })) : `${t('orders.default', { lng: language })}: ${fallback}`}</span></label>;
  })}</div></section>;
}
