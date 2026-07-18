import { RotateCcw } from 'lucide-react';

import type { EffectiveCalculationDefaults } from '../../../api/calculations';
import { NumberField } from '../../ui';

const fields = [
  ['setup_hours', 'setup_hours', 'Rüstzeit h', 'Setup h', false],
  ['post_processing_hours_per_unit', 'post_processing_hours_per_unit', 'Nachbereitung h/Stück', 'Post-processing h/unit', false],
  ['cad_hours', 'cad_hours', 'CAD/Konstruktion h', 'CAD/design h', false],
  ['qa_hours', 'qa_hours', 'Qualitätskontrolle h', 'Quality control h', false],
  ['material_price_per_kg', 'filament_price_per_kg', 'Filamentpreis €/kg', 'Filament price €/kg', false],
  ['material_markup_rate', 'material_markup_percent', 'Materialaufschlag %', 'Material markup %', true],
  ['scrap_rate', 'scrap_percent', 'Ausschuss %', 'Scrap %', true],
  ['labor_rate', 'hourly_rate', 'Stundensatz €/h', 'Hourly rate €/h', false],
  ['consumables', 'consumables', 'Verbrauchsmaterial €', 'Consumables €', false],
  ['packaging', 'packaging', 'Verpackung €', 'Packaging €', false],
  ['shipping', 'shipping', 'Versand €', 'Shipping €', false],
  ['discount_rate', 'discount_percent', 'Rabatt %', 'Discount %', true],
] as const;

interface Props {
  values: Record<string, string>;
  defaults?: EffectiveCalculationDefaults;
  locale: string;
  onChange: (values: Record<string, string>) => void;
  onReset: () => void;
}

export function CommercialOverridesEditor({ values, defaults = {}, locale, onChange, onReset }: Props) {
  const de = locale.startsWith('de');
  return <section><div className="mb-3 flex items-center justify-between"><div><h3 className="font-semibold text-white">5. {de ? 'Arbeitszeit & Nachbereitung' : 'Labor & post-processing'}</h3><p className="text-xs text-bambu-gray">{de ? 'Zentrale Einstellungswerte werden sichtbar übernommen und können je Kalkulation überschrieben werden.' : 'Central settings are shown and can be overridden for this calculation.'}</p></div><button type="button" onClick={onReset} className="inline-flex items-center gap-2 rounded bg-bambu-dark px-3 py-2 text-sm text-white"><RotateCcw className="h-4 w-4" />{de ? 'Zurücksetzen' : 'Reset'}</button></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{fields.map(([key, defaultKey, labelDe, labelEn, percentage]) => {
    const overridden = values[key] !== undefined;
    const displayed = overridden ? String(Number(values[key]) * (percentage ? 100 : 1)) : '';
    const fallback = defaults[defaultKey]?.value ?? '0';
    return <label key={key} className="rounded-lg bg-bambu-dark p-3 text-sm text-bambu-gray"><span className="flex items-center justify-between gap-2"><span>{de ? labelDe : labelEn}</span><span className={`rounded-full px-2 py-0.5 text-[10px] ${overridden ? 'bg-amber-500/15 text-amber-200' : 'bg-bambu-green/10 text-bambu-green'}`}>{overridden ? (de ? 'überschrieben' : 'override') : (de ? 'Einstellung' : 'setting')}</span></span><NumberField min="0" step="0.01" value={displayed} placeholder={fallback} onChange={(event) => { const next = { ...values }; if (!event.target.value) delete next[key]; else next[key] = String(Number(event.target.value) / (percentage ? 100 : 1)); onChange(next); }} containerClassName="mt-2" className="h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white" /><span className="mt-1 block text-xs">{!overridden && `${de ? 'Standard' : 'Default'}: ${fallback}`}</span></label>;
  })}</div></section>;
}
