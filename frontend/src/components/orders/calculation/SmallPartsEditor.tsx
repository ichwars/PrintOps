import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import { smallPartsApi, type SmallPartOption } from '../../../api/smallParts';
import type { CalculationVariantSmallPart } from '../../../api/calculations';
import { formatCount, formatMoney } from '../../../utils/calculationFormatting';
import { SmallPartCombobox } from '../../warehouse/SmallPartCombobox';
import { NumberField } from '../../ui';

interface SmallPartsEditorProps {
  parts: CalculationVariantSmallPart[];
  locale: string;
  currency: string;
  onChange: (parts: CalculationVariantSmallPart[]) => void;
}

export function SmallPartsEditor({ parts, locale, currency, onChange }: SmallPartsEditorProps) {
  const de = locale.startsWith('de');
  const [options, setOptions] = useState<Record<number, SmallPartOption>>({});
  const [adding, setAdding] = useState(false);
  useEffect(() => {
    void Promise.all(parts.filter((part) => !options[part.small_part_id]).map(async (part) => {
      const item = await smallPartsApi.get(part.small_part_id);
      return item as SmallPartOption;
    })).then((loaded) => setOptions((current) => ({ ...current, ...Object.fromEntries(loaded.map((item) => [item.id, item])) }))).catch(() => undefined);
  }, [parts]); // eslint-disable-line react-hooks/exhaustive-deps
  const add = (option: SmallPartOption | null) => {
    if (!option || parts.some((part) => part.small_part_id === option.id)) return;
    setOptions((current) => ({ ...current, [option.id]: option }));
    onChange([...parts, { small_part_id: option.id, quantity: '1', description_snapshot: option.name, unit_code_snapshot: option.unit_code, unit_cost_snapshot: option.unit_cost, sort_order: parts.length }]);
    setAdding(false);
  };
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div><h3 className="font-semibold text-white">4. {de ? 'Material' : 'Materials'}</h3><p className="text-xs text-bambu-gray">{de ? 'Verfügbarkeit wird geprüft; reserviert wird erst nach Angebotsannahme.' : 'Availability is checked; stock is reserved only after offer acceptance.'}</p></div>
        <button type="button" onClick={() => setAdding(true)} className="inline-flex items-center gap-2 rounded bg-bambu-dark px-3 py-2 text-sm text-white"><Plus className="h-4 w-4" />{de ? 'Material' : 'Material'}</button>
      </div>
      {adding && <div className="rounded-lg border border-bambu-green/30 bg-bambu-dark p-3"><SmallPartCombobox value={null} onChange={add} locale={locale} label={de ? 'Material hinzufügen' : 'Add material'} /></div>}
      {parts.length === 0 ? <p className="rounded-lg bg-bambu-dark p-3 text-sm text-bambu-gray">{de ? 'Kein Material hinterlegt.' : 'No materials selected.'}</p> : <div className="space-y-2">{parts.map((part, index) => {
        const option = options[part.small_part_id];
        const available = Number(option?.available ?? 0);
        const enough = available >= Number(part.quantity);
        return <div key={part.small_part_id} className="grid items-center gap-3 rounded-lg bg-bambu-dark p-3 md:grid-cols-[1fr_130px_170px_130px_40px]">
          <div><strong className="text-sm text-white">{option?.sku ? `${option.sku} · ` : ''}{part.description_snapshot}</strong><span className="mt-1 block text-xs text-bambu-gray">{formatMoney(part.unit_cost_snapshot, locale, currency)} / {part.unit_code_snapshot}</span></div>
          <label className="text-xs text-bambu-gray">{de ? 'Anzahl' : 'Quantity'}<NumberField min="0.001" step="1" value={part.quantity} onChange={(event) => onChange(parts.map((item, itemIndex) => itemIndex === index ? { ...item, quantity: event.target.value } : item))} containerClassName="mt-1" className="h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white" /></label>
          <div className={`rounded-lg border px-3 py-2 text-sm ${enough ? 'border-bambu-green/30 text-bambu-green' : 'border-red-500/40 text-red-300'}`}><span className="block text-xs opacity-75">{de ? 'Verfügbar' : 'Available'}</span>{formatCount(available, locale)} {part.unit_code_snapshot}</div>
          <div className="text-sm text-bambu-gray"><span className="block text-xs">{de ? 'Bedarfskosten' : 'Requirement cost'}</span>{formatMoney(Number(part.quantity) * Number(part.unit_cost_snapshot), locale, currency)}</div>
          <button type="button" aria-label={de ? `${part.description_snapshot} entfernen` : `Remove ${part.description_snapshot}`} onClick={() => onChange(parts.filter((_, itemIndex) => itemIndex !== index).map((item, itemIndex) => ({ ...item, sort_order: itemIndex })))} className="text-red-300"><Trash2 className="h-4 w-4" /></button>
        </div>;
      })}</div>}
    </section>
  );
}
