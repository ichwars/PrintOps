import { useEffect, useMemo, useState } from 'react';
import { BadgeEuro, Calculator, Clock3, Coins, Loader2, Package, TriangleAlert, type LucideIcon } from 'lucide-react';
import { calculationsApi, type CalculationPreview, type CalculationPreviewInput, type PriceMethod } from '../../../api/calculations';

type SettingKey = 'currency' | 'default_filament_cost' | 'energy_cost_per_kwh' | 'calculation_defaults';
type Settings = { currency: string; default_filament_cost: number; energy_cost_per_kwh: number; calculation_defaults: string };
type Defaults = Record<string, number | string>;

const FALLBACK: Defaults = {
  acquisitionValue: 749, residualValue: 0, serviceYears: 4, annualHours: 1200, maintenancePercent: 25,
  printerPowerWatts: 200, dryerPowerWatts: 250, dryingHours: 0, laborRate: 20,
  requestHours: 0.15, cadHours: 0, slicingHours: 0.1, setupHours: 0.3,
  postProcessingHours: 0.25, qaHours: 0.05, packingHours: 0.1, scrapRuns: 0,
  riskPercent: 8, priceMethod: 'target_margin', priceRate: 35, explicitPrice: 0,
  discountPercent: 0, taxPercent: 19, minimumPrice: 12, minimumProfit: 4,
  consumables: 0.75, packaging: 2.5, additionalCosts: 0, shipping: 5.49,
  exampleParts: 1, examplePartsPerRun: 1, exampleMaterialGrams: 200, examplePrintHours: 5,
};

const inputClass = 'mt-1 h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white outline-none focus:border-bambu-green';

function parseDefaults(value: string): Defaults {
  try { return { ...FALLBACK, ...JSON.parse(value || '{}') }; } catch { return { ...FALLBACK }; }
}

export function CalculationSettings({ settings, onChange, locale }: { settings: Settings; onChange: (key: SettingKey, value: string | number) => void; locale: string }) {
  const de = locale.startsWith('de');
  const defaults = useMemo(() => parseDefaults(settings.calculation_defaults), [settings.calculation_defaults]);
  const [preview, setPreview] = useState<CalculationPreview | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const [loading, setLoading] = useState(false);
  const update = (key: string, value: number | string) => onChange('calculation_defaults', JSON.stringify({ ...defaults, [key]: value }));
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true); setPreviewError(false);
      const n = (key: string) => Number(defaults[key] ?? 0);
      const labor = [
        ['request', 'requestHours', 'request'], ['cad', 'cadHours', 'request'], ['slicing', 'slicingHours', 'request'],
        ['setup', 'setupHours', 'run'], ['post_processing', 'postProcessingHours', 'unit'],
        ['qa', 'qaHours', 'request'], ['packing', 'packingHours', 'request'],
      ].map(([kind, key, allocation_basis], sort_order) => ({ kind, hours: String(n(key)), hourly_rate: String(n('laborRate')), allocation_basis: allocation_basis as 'request' | 'run' | 'unit', sort_order }));
      const input: CalculationPreviewInput = {
        good_parts: n('exampleParts'), parts_per_run: n('examplePartsPerRun'), scrap_runs: n('scrapRuns'),
        material_grams_per_run: String(n('exampleMaterialGrams')), material_price_per_kg: String(settings.default_filament_cost),
        print_hours_per_run: String(n('examplePrintHours')), machine_cost_per_hour: '0',
        acquisition_value: String(n('acquisitionValue')), residual_value: String(n('residualValue')),
        service_years: String(n('serviceYears')), annual_hours: String(n('annualHours')), maintenance_rate: String(n('maintenancePercent') / 100),
        printer_power_kw: String(n('printerPowerWatts') / 1000), electricity_price_per_kwh: String(settings.energy_cost_per_kwh),
        drying_hours: String(n('dryingHours')), dryer_power_kw: String(n('dryerPowerWatts') / 1000), labor,
        consumables: String(n('consumables')), packaging: String(n('packaging')), additional_costs: String(n('additionalCosts')),
        risk_rate: String(n('riskPercent') / 100), shipping: String(n('shipping')), price_method: String(defaults.priceMethod) as PriceMethod,
        price_rate: String(n('priceRate') / 100), explicit_price: String(n('explicitPrice')), discount_rate: String(n('discountPercent') / 100),
        tax_rate: String(n('taxPercent') / 100), minimum_price: String(n('minimumPrice')), minimum_profit: String(n('minimumProfit')),
      };
      calculationsApi.preview(input).then(setPreview).catch(() => setPreviewError(true)).finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [defaults, settings.default_filament_cost, settings.energy_cost_per_kwh]);

  const groups: Array<{ title: string; description: string; icon: LucideIcon; column: 'cost' | 'commercial'; fields: Array<[string, string, number]> }> = [
    { title: de ? 'Kostenbasis' : 'Cost basis', icon: Coins, column: 'cost', description: de ? 'Maschine, Material und Energie als Ersatzwerte.' : 'Machine, material, and energy fallbacks.', fields: [
      ['acquisitionValue', de ? 'Anschaffungswert' : 'Acquisition value', .01], ['residualValue', de ? 'Restwert' : 'Residual value', .01],
      ['serviceYears', de ? 'Nutzungsdauer (Jahre)' : 'Service life (years)', .1], ['annualHours', de ? 'Nutzbare Stunden/Jahr' : 'Usable hours/year', 1],
      ['maintenancePercent', de ? 'Wartung & Verschleiß %' : 'Maintenance & wear %', .1], ['printerPowerWatts', de ? 'Druckerleistung W' : 'Printer power W', 1],
      ['dryerPowerWatts', de ? 'Trocknerleistung W' : 'Dryer power W', 1], ['dryingHours', de ? 'Trocknungszeit h' : 'Drying time h', .05],
    ]},
    { title: de ? 'Arbeitszeiten' : 'Labor times', icon: Clock3, column: 'cost', description: de ? 'Stundensatz und Standardzeiten je Tätigkeit.' : 'Hourly rate and defaults per activity.', fields: [
      ['laborRate', de ? 'Arbeitsstundensatz' : 'Hourly rate', .01], ['requestHours', de ? 'Anfragevorbereitung h' : 'Request preparation h', .05],
      ['cadHours', 'CAD/Reparatur h', .05], ['slicingHours', 'Slicing h', .05], ['setupHours', de ? 'Rüstzeit h/Lauf' : 'Setup h/run', .05],
      ['postProcessingHours', de ? 'Nachbearbeitung h/Stück' : 'Post-processing h/unit', .05], ['qaHours', de ? 'Qualitätssicherung h' : 'Quality assurance h', .05], ['packingHours', de ? 'Verpackungszeit h' : 'Packing time h', .05],
    ]},
    { title: de ? 'Risiko und Ausschuss' : 'Risk and scrap', icon: TriangleAlert, column: 'commercial', description: de ? 'Explizite Zusatzläufe und Risikoreserve.' : 'Explicit extra runs and risk reserve.', fields: [
      ['scrapRuns', de ? 'Ausschussläufe' : 'Scrap runs', 1], ['riskPercent', de ? 'Risikoreserve %' : 'Risk reserve %', .1],
    ]},
    { title: de ? 'Preisbildung' : 'Price derivation', icon: BadgeEuro, column: 'commercial', description: de ? 'Marge, Aufschlag oder fester Zielpreis.' : 'Margin, markup, or explicit target.', fields: [
      ['priceRate', de ? 'Marge/Aufschlag %' : 'Margin/markup %', .1], ['explicitPrice', de ? 'Fester Zielpreis' : 'Explicit price', .01],
      ['discountPercent', de ? 'Standardrabatt %' : 'Default discount %', .1], ['taxPercent', de ? 'Steuer %' : 'Tax %', .1],
      ['minimumPrice', de ? 'Mindestpreis' : 'Minimum price', .01], ['minimumProfit', de ? 'Mindestgewinn' : 'Minimum profit', .01],
    ]},
    { title: de ? 'Nebenkosten' : 'Ancillary costs', icon: Package, column: 'cost', description: de ? 'Offen ausgewiesene Zusatzkosten.' : 'Explicit ancillary amounts.', fields: [
      ['consumables', de ? 'Verbrauchsmaterial' : 'Consumables', .01], ['packaging', de ? 'Verpackung' : 'Packaging', .01],
      ['additionalCosts', de ? 'Weitere Kosten' : 'Additional costs', .01], ['shipping', de ? 'Versand' : 'Shipping', .01],
    ]},
    { title: de ? 'Beispielrechnung' : 'Example calculation', icon: Calculator, column: 'commercial', description: de ? 'Eingaben für die Live-Prüfung der Standards.' : 'Inputs for the live defaults check.', fields: [
      ['exampleParts', de ? 'Gutteile' : 'Good parts', 1], ['examplePartsPerRun', de ? 'Teile/Lauf' : 'Parts/run', 1],
      ['exampleMaterialGrams', de ? 'Material g/Lauf' : 'Material g/run', 1], ['examplePrintHours', de ? 'Druckzeit h/Lauf' : 'Print time h/run', .05],
    ]},
  ];

  const money = (value: string) => new Intl.NumberFormat(locale, { style: 'currency', currency: settings.currency }).format(Number(value));
  const renderGroup = (group: typeof groups[number]) => {
    const Icon = group.icon;
    return <section key={group.title} className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-5">
      <div className="flex items-start gap-3"><div className="rounded-lg bg-bambu-orange/10 p-2 text-bambu-orange"><Icon className="h-5 w-5" /></div><div><h3 className="font-semibold text-white">{group.title}</h3><p className="mt-1 text-xs text-bambu-gray">{group.description}</p></div></div>
      {group.title === (de ? 'Preisbildung' : 'Price derivation') && <label className="mt-4 block text-sm text-bambu-gray">{de ? 'Verfahren' : 'Method'}<select value={String(defaults.priceMethod)} onChange={e => update('priceMethod', e.target.value)} className={inputClass}><option value="target_margin">{de ? 'Zielmarge' : 'Target margin'}</option><option value="markup">{de ? 'Aufschlag' : 'Markup'}</option><option value="explicit_price">{de ? 'Fester Zielpreis' : 'Explicit price'}</option></select></label>}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">{group.fields.map(([key, label, step]) => <label key={key} className="text-sm text-bambu-gray">{label}<input type="number" min="0" step={step} value={Number(defaults[key] ?? 0)} onChange={e => update(key, Number(e.target.value))} className={inputClass} /></label>)}</div>
      {group.title === (de ? 'Beispielrechnung' : 'Example calculation') && <div className="mt-4">
        {loading && <div className="flex items-center gap-2 text-sm text-bambu-gray"><Loader2 className="h-4 w-4 animate-spin" />{de ? 'Berechnung läuft…' : 'Calculating…'}</div>}
        {previewError && <div role="alert" className="text-sm text-red-300">{de ? 'Beispiel konnte nicht berechnet werden.' : 'Example could not be calculated.'}</div>}
        {preview && <div className="grid grid-cols-2 gap-2 xl:grid-cols-3">{[
          [de ? 'Material' : 'Material', preview.material_cost], [de ? 'Maschine' : 'Machine', preview.machine_cost], [de ? 'Energie' : 'Energy', preview.energy_cost],
          [de ? 'Arbeit' : 'Labor', preview.labor_cost], [de ? 'Risiko' : 'Risk', preview.risk_cost], [de ? 'Herstellkosten' : 'Production cost', preview.production_cost],
          [de ? 'Deckungsbeitrag' : 'Contribution', preview.contribution], [de ? 'Netto' : 'Net', preview.net_price], [de ? 'Steuer' : 'Tax', preview.tax],
          [de ? 'Brutto' : 'Gross', preview.gross_price], [de ? 'Stückpreis' : 'Unit price', preview.unit_price], [de ? 'Läufe' : 'Runs', String(preview.total_runs)],
        ].map(([label, value]) => <div key={label} className="rounded-lg bg-bambu-dark p-3"><span className="block text-xs text-bambu-gray">{label}</span><strong className="text-white">{label === (de ? 'Läufe' : 'Runs') ? value : money(value)}</strong></div>)}</div>}
      </div>}
    </section>;
  };
  return <div id="card-cost" className="space-y-5">
    <div className="grid gap-3 md:grid-cols-3">
      <label className="text-sm text-bambu-gray">{de ? 'Währung' : 'Currency'}<input value={settings.currency} onChange={e => onChange('currency', e.target.value.toUpperCase())} className={inputClass} /></label>
      <label className="text-sm text-bambu-gray">{de ? 'Filamentpreis/kg' : 'Filament price/kg'}<input type="number" min="0" step="0.01" value={settings.default_filament_cost} onChange={e => onChange('default_filament_cost', Number(e.target.value))} className={inputClass} /></label>
      <label className="text-sm text-bambu-gray">{de ? 'Strompreis/kWh' : 'Electricity/kWh'}<input type="number" min="0" step="0.001" value={settings.energy_cost_per_kwh} onChange={e => onChange('energy_cost_per_kwh', Number(e.target.value))} className={inputClass} /></label>
    </div>
    <div className="grid items-start gap-5 lg:grid-cols-2"><div className="space-y-5">{groups.filter(group => group.column === 'cost').map(renderGroup)}</div><div className="space-y-5">{groups.filter(group => group.column === 'commercial').map(renderGroup)}</div></div>
    <div className="flex items-center gap-2 rounded-lg border border-bambu-green/30 bg-bambu-green/5 p-3 text-xs text-bambu-gray"><Calculator className="h-4 w-4 text-bambu-green" />{de ? 'Vorschau und spätere Freigabe verwenden denselben Decimal-Kostenkern.' : 'Preview and approval use the same Decimal cost engine.'}</div>
  </div>;
}
