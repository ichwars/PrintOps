import { resolveSupportedLanguage } from '../../../i18n';
import { useTranslation } from 'react-i18next';
import { Plus, Trash2 } from 'lucide-react';
import type { CalculationOperation } from '../../../api/calculations';
import { NumberField , LegacySelect, TextField} from '../../ui';

const inputClass = 'h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white outline-none focus:border-bambu-green';

export function LaborEditor({ operation, locale, onChange }: { operation: CalculationOperation; locale: string; onChange: (operation: CalculationOperation) => void }) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language });
  const update = (index: number, key: string, value: string) => onChange({ ...operation, labor: operation.labor.map((entry, i) => i === index ? { ...entry, [key]: value } : entry) });
  return <div className="mt-3 border-t border-bambu-dark-tertiary pt-3 lg:col-span-7">
    <div className="flex items-center justify-between"><span className="text-xs font-medium text-bambu-gray">{t('orders.runtimeCalculation.laborLaborEditor', { lng: language })}</span><button onClick={() => onChange({ ...operation, labor: [...operation.labor, { kind: 'post_processing', hours: '0', hourly_rate: '20', allocation_basis: 'unit', sort_order: operation.labor.length }] })} className="inline-flex items-center gap-1 text-xs text-bambu-green"><Plus className="h-3 w-3" />{t('orders.runtimeCalculation.laborLaborEditor2', { lng: language })}</button></div>
    {operation.labor.map((entry, index) => <div key={index} className="mt-2 grid gap-2 sm:grid-cols-[1fr_110px_130px_150px_40px]">
      <TextField aria-label={t('orders.runtimeCalculation.activity', { lng: language })} value={entry.kind} onChange={e => update(index, 'kind', e.target.value)} className={inputClass} />
      <NumberField aria-label={t('orders.runtimeCalculation.hours', { lng: language })}  min="0" step="0.05" value={entry.hours} onChange={e => update(index, 'hours', e.target.value)} className={inputClass} />
      <NumberField aria-label={t('orders.runtimeCalculation.hourlyRateLaborEditor', { lng: language })}  min="0" step="0.01" value={entry.hourly_rate} onChange={e => update(index, 'hourly_rate', e.target.value)} className={inputClass} />
      <LegacySelect aria-label={t('orders.runtimeCalculation.allocation', { lng: language })} value={entry.allocation_basis} onChange={e => update(index, 'allocation_basis', e.target.value)} className={inputClass}><option value="request">{t('orders.runtimeCalculation.perRequest', { lng: language })}</option><option value="run">{t('orders.runtimeCalculation.perRun', { lng: language })}</option><option value="unit">{t('orders.runtimeCalculation.perUnit', { lng: language })}</option></LegacySelect>
      <button aria-label={t('orders.runtimeCalculation.deleteLabor', { lng: language })} onClick={() => onChange({ ...operation, labor: operation.labor.filter((_, i) => i !== index).map((item, i) => ({ ...item, sort_order: i })) })} className="text-red-300"><Trash2 className="h-4 w-4" /></button>
    </div>)}
  </div>;
}
