import { RotateCcw } from 'lucide-react';

import type { EffectiveCalculationDefaults } from '../../../api/calculations';
import { IconButton, NumberField } from '../../ui';

const fields = [
  ['setup_hours', 'setup_hours', 'Rüstzeit h', 'Setup h', false, '0.05'],
  ['post_processing_hours_per_unit', 'post_processing_hours_per_unit', 'Nachbereitung h/Stück', 'Post-processing h/unit', false, '0.01'],
  ['cad_hours', 'cad_hours', 'CAD/Konstruktion h', 'CAD/design h', false, '0.05'],
  ['qa_hours', 'qa_hours', 'Qualitätskontrolle h', 'Quality control h', false, '0.01'],
  ['material_price_per_kg', 'filament_price_per_kg', 'Filamentpreis €/kg', 'Filament price €/kg', false, '0.01'],
  ['material_markup_rate', 'material_markup_percent', 'Materialaufschlag %', 'Material markup %', true, '0.1'],
  ['scrap_rate', 'scrap_percent', 'Ausschuss %', 'Scrap %', true, '0.1'],
  ['labor_rate', 'hourly_rate', 'Stundensatz €/h', 'Hourly rate €/h', false, '0.01'],
  ['consumables', 'consumables', 'Verbrauchsmaterial €', 'Consumables €', false, '0.01'],
  ['packaging', 'packaging', 'Verpackung €', 'Packaging €', false, '0.01'],
  ['shipping', 'shipping', 'Versand €', 'Shipping €', false, '0.01'],
  ['discount_rate', 'discount_percent', 'Rabatt %', 'Discount %', true, '0.1'],
] as const;

interface Props {
  values: Record<string, string>;
  defaults?: EffectiveCalculationDefaults;
  locale: string;
  onChange: (values: Record<string, string>) => void;
}

export function CommercialOverridesEditor({ values, defaults = {}, locale, onChange }: Props) {
  const de = locale.startsWith('de');
  const resetField = (key: string) => {
    const next = { ...values };
    delete next[key];
    onChange(next);
  };
  return <section><div className="mb-3"><h3 className="font-semibold text-white">5. {de ? 'Arbeitszeit & Nachbereitung' : 'Labor & post-processing'}</h3><p className="text-xs text-bambu-gray">{de ? 'Zentrale Einstellungswerte werden sichtbar übernommen und können je Kalkulation überschrieben werden.' : 'Central settings are shown and can be overridden for this calculation.'}</p></div><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{fields.map(([key, defaultKey, labelDe, labelEn, percentage, step]) => {
    const overridden = values[key] !== undefined;
    const displayed = overridden ? String(Number(values[key]) * (percentage ? 100 : 1)) : '';
    const fallback = defaults[defaultKey]?.value ?? '0';
    return <label key={key} className="rounded-lg bg-bambu-dark p-3 text-sm text-bambu-gray"><span className="flex min-h-[34px] items-center justify-between gap-2"><span>{de ? labelDe : labelEn}</span>{overridden ? <IconButton label={de ? `${labelDe} zurücksetzen` : `Reset ${labelEn}`} title={de ? `${labelDe} zurücksetzen` : `Reset ${labelEn}`} icon={RotateCcw} size="sm" onClick={(event) => { event.preventDefault(); resetField(key); }} className="!h-7 !w-7 text-amber-200 hover:bg-amber-500/10" /> : null}</span><NumberField aria-label={de ? labelDe : labelEn} min="0" step={step} value={displayed} placeholder={fallback} onChange={(event) => { const next = { ...values }; if (!event.target.value) delete next[key]; else next[key] = String(Number(event.target.value) / (percentage ? 100 : 1)); onChange(next); }} containerClassName="mt-2" className="h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white" /><span className="mt-1 block text-xs">{overridden ? (de ? 'Überschrieben' : 'Overridden') : `${de ? 'Standard' : 'Default'}: ${fallback}`}</span></label>;
  })}</div></section>;
}
