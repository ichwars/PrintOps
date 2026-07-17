import { Plus, Trash2 } from 'lucide-react';
import type { CalculationOperation } from '../../../api/calculations';
import { NumberField , LegacySelect, TextField} from '../../ui';

const inputClass = 'h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white outline-none focus:border-bambu-green';

export function LaborEditor({ operation, locale, onChange }: { operation: CalculationOperation; locale: string; onChange: (operation: CalculationOperation) => void }) {
  const de = locale.startsWith('de');
  const update = (index: number, key: string, value: string) => onChange({ ...operation, labor: operation.labor.map((entry, i) => i === index ? { ...entry, [key]: value } : entry) });
  return <div className="mt-3 border-t border-bambu-dark-tertiary pt-3 lg:col-span-7">
    <div className="flex items-center justify-between"><span className="text-xs font-medium text-bambu-gray">{de ? 'Arbeitszeiten' : 'Labor'}</span><button onClick={() => onChange({ ...operation, labor: [...operation.labor, { kind: 'post_processing', hours: '0', hourly_rate: '20', allocation_basis: 'unit', sort_order: operation.labor.length }] })} className="inline-flex items-center gap-1 text-xs text-bambu-green"><Plus className="h-3 w-3" />{de ? 'Arbeitszeit' : 'Labor'}</button></div>
    {operation.labor.map((entry, index) => <div key={index} className="mt-2 grid gap-2 sm:grid-cols-[1fr_110px_130px_150px_40px]">
      <TextField aria-label={de ? 'Tätigkeit' : 'Activity'} value={entry.kind} onChange={e => update(index, 'kind', e.target.value)} className={inputClass} />
      <NumberField aria-label={de ? 'Stunden' : 'Hours'}  min="0" step="0.05" value={entry.hours} onChange={e => update(index, 'hours', e.target.value)} className={inputClass} />
      <NumberField aria-label={de ? 'Stundensatz' : 'Hourly rate'}  min="0" step="0.01" value={entry.hourly_rate} onChange={e => update(index, 'hourly_rate', e.target.value)} className={inputClass} />
      <LegacySelect aria-label={de ? 'Zuordnung' : 'Allocation'} value={entry.allocation_basis} onChange={e => update(index, 'allocation_basis', e.target.value)} className={inputClass}><option value="request">{de ? 'je Anfrage' : 'per request'}</option><option value="run">{de ? 'je Lauf' : 'per run'}</option><option value="unit">{de ? 'je Stück' : 'per unit'}</option></LegacySelect>
      <button aria-label={de ? 'Arbeitszeit löschen' : 'Delete labor'} onClick={() => onChange({ ...operation, labor: operation.labor.filter((_, i) => i !== index).map((item, i) => ({ ...item, sort_order: i })) })} className="text-red-300"><Trash2 className="h-4 w-4" /></button>
    </div>)}
  </div>;
}
