import { RotateCcw } from 'lucide-react';
import { NumberField } from '../../ui';

const fields = [
  ['material_price_per_kg', 'Filamentpreis €/kg', 'Filament price/kg'], ['material_markup_rate', 'Materialaufschlag %', 'Material markup %'],
  ['scrap_rate', 'Ausschuss %', 'Scrap %'], ['labor_rate', 'Stundensatz €/h', 'Hourly rate'], ['consumables', 'Verbrauchsmaterial €', 'Consumables'],
  ['packaging', 'Verpackung €', 'Packaging'], ['shipping', 'Versand €', 'Shipping'], ['discount_rate', 'Rabatt %', 'Discount %'],
] as const;

export function CommercialOverridesEditor({ values, locale, onChange, onReset }: { values: Record<string, string>; locale: string; onChange: (values: Record<string, string>) => void; onReset: () => void }) {
  const de = locale.startsWith('de');
  return <section><div className="mb-3 flex items-center justify-between"><div><h3 className="font-semibold text-white">{de ? 'Kalkulationswerte' : 'Calculation values'}</h3><p className="text-xs text-bambu-gray">{de ? 'Leer lassen, um die zentralen Vorgaben zu verwenden.' : 'Leave empty to use central defaults.'}</p></div><button type="button" onClick={onReset} className="inline-flex items-center gap-2 rounded bg-bambu-dark px-3 py-2 text-sm text-white"><RotateCcw className="h-4 w-4" />{de ? 'Zurücksetzen' : 'Reset'}</button></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{fields.map(([key, labelDe, labelEn]) => { const percentage = key.endsWith('_rate'); return <label key={key} className="text-sm text-bambu-gray">{de ? labelDe : labelEn}<NumberField min="0" step="0.01" value={values[key] ? String(Number(values[key]) * (percentage ? 100 : 1)) : ''} placeholder={de ? 'Standard' : 'Default'} onChange={e => { const next = { ...values }; if (!e.target.value) delete next[key]; else next[key] = String(Number(e.target.value) / (percentage ? 100 : 1)); onChange(next); }} containerClassName="mt-1" className="h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white" /></label>; })}</div></section>;
}
