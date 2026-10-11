import { resolveSupportedLanguage } from '../../../i18n';
import { useTranslation } from 'react-i18next';
import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BadgeEuro, Calculator, Clock3, Coins, Loader2, Package, TriangleAlert, type LucideIcon } from 'lucide-react';
import { calculationsApi, type CalculationPreview, type CalculationPreviewInput, type PriceMethod } from '../../../api/calculations';
import { api } from '../../../api/client';
import { SUPPORTED_CURRENCIES } from '../../../utils/currency';
import { NumberField, Select } from '../../ui';

type SettingKey = 'currency' | 'default_filament_cost' | 'energy_cost_per_kwh' | 'energy_tracking_mode' | 'calculation_defaults';
type Settings = { currency: string; default_filament_cost: number; energy_cost_per_kwh: number; energy_tracking_mode: string; calculation_defaults: string };
type Defaults = Record<string, number | string>;

const FALLBACK: Defaults = {
  defaultPrinterId: 0, defaultDryerId: 0, dryingHours: 0, laborRate: 20,
  requestHours: 0.15, cadHours: 0, slicingHours: 0.1, setupHours: 0.3,
  postProcessingHours: 0.25, qaHours: 0.05, packingHours: 0.1, scrapRuns: 0,
  riskPercent: 8, priceMethod: 'target_margin', priceRate: 35, explicitPrice: 0,
  scrapPercent: 8, materialMarkupPercent: 15,
  discountPercent: 0, taxPercent: 19, minimumPrice: 12, minimumProfit: 4,
  roundingMode: 'none',
  consumables: 0.75, packaging: 2.5, additionalCosts: 0, shipping: 5.49,
  exampleParts: 1, examplePartsPerRun: 1, exampleMaterialGrams: 200, examplePrintHours: 5,
};

function parseDefaults(value: string): Defaults {
  try { return { ...FALLBACK, ...JSON.parse(value || '{}') }; } catch { return { ...FALLBACK }; }
}

export function CalculationSettings({ settings, onChange, locale }: { settings: Settings; onChange: (key: SettingKey, value: string | number) => void; locale: string }) {
  const language = resolveSupportedLanguage(locale);
  const { t } = useTranslation(undefined, { lng: language });
  const defaults = useMemo(() => parseDefaults(settings.calculation_defaults), [settings.calculation_defaults]);
  const [preview, setPreview] = useState<CalculationPreview | null>(null);
  const [previewError, setPreviewError] = useState(false);
  const [loading, setLoading] = useState(false);
  const { data: printers = [] } = useQuery({ queryKey: ['printers'], queryFn: api.getPrinters });
  const { data: dryers = [] } = useQuery({ queryKey: ['equipment', 'active'], queryFn: () => api.getEquipment(true) });
  const selectedPrinter = printers.find(item => item.id === Number(defaults.defaultPrinterId));
  const selectedDryer = dryers.find(item => item.id === Number(defaults.defaultDryerId));
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
        material_markup_rate: String(n('materialMarkupPercent') / 100),
        print_hours_per_run: String(n('examplePrintHours')), machine_cost_per_hour: '0',
        acquisition_value: selectedPrinter?.acquisition_value ?? '0', residual_value: '0',
        service_years: selectedPrinter?.service_years ?? '1', annual_hours: selectedPrinter?.annual_hours ?? '1', maintenance_rate: selectedPrinter?.maintenance_rate ?? '0',
        printer_power_kw: String(Number(selectedPrinter?.nominal_power_watts ?? 0) / 1000), electricity_price_per_kwh: String(settings.energy_cost_per_kwh),
        drying_hours: String(n('dryingHours')), dryer_power_kw: String(Number(selectedDryer?.nominal_power_watts ?? 0) / 1000), labor,
        consumables: String(n('consumables')), packaging: String(n('packaging')), additional_costs: String(n('additionalCosts')),
        additive_materials: '0', scrap_rate: String(n('scrapPercent') / 100),
        risk_rate: String(n('riskPercent') / 100), shipping: String(n('shipping')), price_method: String(defaults.priceMethod) as PriceMethod,
        price_rate: String(n('priceRate') / 100), explicit_price: String(n('explicitPrice')), discount_rate: String(n('discountPercent') / 100),
        tax_rate: String(n('taxPercent') / 100), minimum_price: String(n('minimumPrice')), minimum_profit: String(n('minimumProfit')),
        rounding_mode: String(defaults.roundingMode) as CalculationPreviewInput['rounding_mode'],
      };
      calculationsApi.preview(input).then(setPreview).catch(() => setPreviewError(true)).finally(() => setLoading(false));
    }, 250);
    return () => window.clearTimeout(timer);
  }, [defaults, selectedDryer, selectedPrinter, settings.default_filament_cost, settings.energy_cost_per_kwh]);

  const groups: Array<{ title: string; description: string; icon: LucideIcon; column: 'cost' | 'commercial'; fields: Array<[string, string, number]> }> = [
    { title: t('orders.runtimeCalculation.costBasis', { lng: language }), icon: Coins, column: 'cost', description: t('orders.runtimeCalculation.defaultDevicesFromCentralDeviceManagement', { lng: language }), fields: [['dryingHours', t('orders.runtimeCalculation.defaultDryingTimeH', { lng: language }), .05]]},
    { title: t('orders.runtimeCalculation.laborTimes', { lng: language }), icon: Clock3, column: 'cost', description: t('orders.runtimeCalculation.hourlyRateAndDefaultsPerActivity', { lng: language }), fields: [
      ['laborRate', t('orders.runtimeCalculation.hourlyRate', { lng: language }), .01], ['requestHours', t('orders.runtimeCalculation.requestPreparationH', { lng: language }), .05],
      ['cadHours', t('orders.runtimeCalculation.cadRepairHours', { lng: language }), .05], ['slicingHours', t('orders.runtimeCalculation.slicingHours', { lng: language }), .05], ['setupHours', t('orders.runtimeCalculation.setupHRun', { lng: language }), .05],
      ['postProcessingHours', t('orders.runtimeCalculation.postProcessingHUnit', { lng: language }), .05], ['qaHours', t('orders.runtimeCalculation.qualityAssuranceH', { lng: language }), .05], ['packingHours', t('orders.runtimeCalculation.packingTimeH', { lng: language }), .05],
    ]},
    { title: t('orders.runtimeCalculation.riskAndScrap', { lng: language }), icon: TriangleAlert, column: 'commercial', description: t('orders.runtimeCalculation.explicitExtraRunsAndRiskReserve', { lng: language }), fields: [
      ['scrapRuns', t('orders.runtimeCalculation.scrapRuns', { lng: language }), 1], ['scrapPercent', t('orders.runtimeCalculation.scrap', { lng: language }), .1],
      ['riskPercent', t('orders.runtimeCalculation.riskReserve', { lng: language }), .1], ['materialMarkupPercent', t('orders.runtimeCalculation.materialMarkup', { lng: language }), .1],
    ]},
    { title: t('orders.runtimeCalculation.priceDerivation', { lng: language }), icon: BadgeEuro, column: 'commercial', description: t('orders.runtimeCalculation.marginMarkupOrExplicitTarget', { lng: language }), fields: [
      ['priceRate', t('orders.runtimeCalculation.marginMarkup', { lng: language }), .1], ['explicitPrice', t('orders.runtimeCalculation.explicitPrice', { lng: language }), .01],
      ['discountPercent', t('orders.runtimeCalculation.defaultDiscount', { lng: language }), .1], ['taxPercent', t('orders.runtimeCalculation.taxCalculationSettings', { lng: language }), .1],
      ['minimumPrice', t('orders.runtimeCalculation.minimumPrice', { lng: language }), .01], ['minimumProfit', t('orders.runtimeCalculation.minimumProfit', { lng: language }), .01],
    ]},
    { title: t('orders.runtimeCalculation.ancillaryCosts', { lng: language }), icon: Package, column: 'cost', description: t('orders.runtimeCalculation.explicitAncillaryAmounts', { lng: language }), fields: [
      ['consumables', t('orders.runtimeCalculation.consumables', { lng: language }), .01], ['packaging', t('orders.runtimeCalculation.packaging', { lng: language }), .01],
      ['additionalCosts', t('orders.runtimeCalculation.additionalCosts', { lng: language }), .01], ['shipping', t('orders.runtimeCalculation.shippingCost', { lng: language }), .01],
    ]},
    { title: t('orders.runtimeCalculation.exampleCalculation', { lng: language }), icon: Calculator, column: 'commercial', description: t('orders.runtimeCalculation.inputsForTheLiveDefaultsCheck', { lng: language }), fields: [
      ['exampleParts', t('orders.runtimeCalculation.goodParts', { lng: language }), 1], ['examplePartsPerRun', t('orders.runtimeCalculation.partsRun', { lng: language }), 1],
      ['exampleMaterialGrams', t('orders.runtimeCalculation.materialGRun', { lng: language }), 1], ['examplePrintHours', t('orders.runtimeCalculation.printTimeHRun', { lng: language }), .05],
    ]},
  ];

  const money = (value: string) => new Intl.NumberFormat(locale, { style: 'currency', currency: settings.currency }).format(Number(value));
  const renderGroup = (group: typeof groups[number]) => {
    const Icon = group.icon;
    return <section key={group.title} className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-5">
      <div className="flex items-start gap-3"><div className="rounded-lg bg-bambu-orange/10 p-2 text-bambu-orange"><Icon className="h-5 w-5" /></div><div><h3 className="font-semibold text-white">{group.title}</h3><p className="mt-1 text-xs text-bambu-gray">{group.description}</p></div></div>
      {group.title === (t('orders.runtimeCalculation.costBasis', { lng: language })) && <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Select<number> label={t('orders.runtimeCalculation.defaultPrinter', { lng: language })} value={Number(defaults.defaultPrinterId)} onValueChange={(value) => update('defaultPrinterId', value)} options={[{ value: 0, label: t('orders.runtimeCalculation.noDefaultPrinter', { lng: language }) }, ...printers.filter(item => item.is_active).map(item => ({ value: item.id, label: item.name }))]} />
        <Select<number> label={t('orders.runtimeCalculation.defaultDryer', { lng: language })} value={Number(defaults.defaultDryerId)} onValueChange={(value) => update('defaultDryerId', value)} options={[{ value: 0, label: t('orders.runtimeCalculation.noDefaultDryer', { lng: language }) }, ...dryers.map(item => ({ value: item.id, label: item.name }))]} />
        {selectedPrinter && <div className="rounded-lg bg-bambu-dark p-3 text-sm"><span className="block text-xs text-bambu-gray">{t('orders.runtimeCalculation.printerResidualHourly', { lng: language })}</span><strong className="text-white">{money(selectedPrinter.residual_value ?? '0')} / {money(selectedPrinter.hourly_rate ?? '0')}/h</strong></div>}
        {selectedDryer && <div className="rounded-lg bg-bambu-dark p-3 text-sm"><span className="block text-xs text-bambu-gray">{t('orders.runtimeCalculation.dryerResidualHourly', { lng: language })}</span><strong className="text-white">{money(selectedDryer.residual_value)} / {money(selectedDryer.hourly_rate)}/h</strong></div>}
      </div>}
      {group.title === (t('orders.runtimeCalculation.priceDerivation', { lng: language })) && <Select label={t('orders.runtimeCalculation.method', { lng: language })} value={String(defaults.priceMethod)} onValueChange={(value) => update('priceMethod', value)} className="mt-4" options={[
        { value: 'target_margin', label: t('orders.runtimeCalculation.targetMargin', { lng: language }) },
        { value: 'markup', label: t('orders.runtimeCalculation.markup', { lng: language }) },
        { value: 'explicit_price', label: t('orders.runtimeCalculation.explicitPrice', { lng: language }) },
      ]} />}
      {group.title === (t('orders.runtimeCalculation.priceDerivation', { lng: language })) && <Select label={t('orders.runtimeCalculation.priceRounding', { lng: language })} value={String(defaults.roundingMode)} onValueChange={(value) => update('roundingMode', value)} className="mt-3" options={[
        { value: 'none', label: t('common.none', { lng: language }) }, { value: '0.05', label: '0,05' }, { value: '0.10', label: '0,10' }, { value: '0.50', label: '0,50' }, { value: '1.00', label: '1,00' }, { value: 'x.90', label: 'x,90' }, { value: 'x.99', label: 'x,99' },
      ]} />}
      <div className="mt-4 grid gap-3 sm:grid-cols-2">{group.fields.map(([key, label, step]) => <NumberField key={key} label={label} min="0" step={step} value={Number(defaults[key] ?? 0)} onValueChange={(value) => update(key, Number(value))} />)}</div>
      {group.title === (t('orders.runtimeCalculation.exampleCalculation', { lng: language })) && <div className="mt-4">
        {loading && <div className="flex items-center gap-2 text-sm text-bambu-gray"><Loader2 className="h-4 w-4 animate-spin" />{t('orders.runtimeCalculation.calculating', { lng: language })}</div>}
        {previewError && <div role="alert" className="text-sm text-red-300">{t('orders.runtimeCalculation.exampleCouldNotBeCalculated', { lng: language })}</div>}
        {preview && <div className="grid grid-cols-2 gap-2 xl:grid-cols-3">{[
          [t('printops.nav.parts', { lng: language }), preview.material_cost], [t('orders.runtimeCalculation.machine', { lng: language }), preview.machine_cost], [t('settings.energyCostBadge', { lng: language }), preview.energy_cost],
          [t('orders.runtimeCalculation.labor', { lng: language }), preview.labor_cost], [t('orders.runtimeCalculation.risk', { lng: language }), preview.risk_cost], [t('orders.runtimeCalculation.productionCost', { lng: language }), preview.production_cost],
          [t('orders.runtimeCalculation.contribution', { lng: language }), preview.contribution], [t('inventory.net', { lng: language }), preview.net_price], [t('orders.runtimeCalculation.tax', { lng: language }), preview.tax],
          [t('orders.runtimeCalculation.gross', { lng: language }), preview.gross_price], [t('orders.runtimeCalculation.unitPrice', { lng: language }), preview.unit_price], [t('orders.runtimeCalculation.runs', { lng: language }), String(preview.total_runs)],
        ].map(([label, value]) => <div key={label} className="rounded-lg bg-bambu-dark p-3"><span className="block text-xs text-bambu-gray">{label}</span><strong className="text-white">{label === (t('orders.runtimeCalculation.runs', { lng: language })) ? value : money(value)}</strong></div>)}</div>}
      </div>}
    </section>;
  };
  return <div id="card-cost" className="space-y-5">
    <h2 className="sr-only">{t('settings.costTracking', { lng: language })}</h2>
    <div className="grid gap-3 md:grid-cols-4">
      <Select label={t('orders.businessProfile.currency', { lng: language })} value={settings.currency} onValueChange={(value) => onChange('currency', value)} options={SUPPORTED_CURRENCIES.map(currency => ({ value: currency.code, label: currency.label }))} />
      <NumberField label={t('orders.runtimeCalculation.filamentPriceKg', { lng: language })} min="0" step="0.01" value={settings.default_filament_cost} onValueChange={(value) => onChange('default_filament_cost', Number(value))} />
      <NumberField label={t('orders.runtimeCalculation.electricityKWh', { lng: language })} min="0" step="0.001" value={settings.energy_cost_per_kwh} onValueChange={(value) => onChange('energy_cost_per_kwh', Number(value))} />
      <Select label={t('orders.runtimeCalculation.energyDisplay', { lng: language })} value={settings.energy_tracking_mode} onValueChange={(value) => onChange('energy_tracking_mode', value)} options={[{ value: 'total', label: t('orders.runtimeCalculation.totalConsumption', { lng: language }) }, { value: 'print', label: t('orders.runtimeCalculation.printEnergyOnly', { lng: language }) }]} />
    </div>
    <div className="grid items-start gap-5 lg:grid-cols-2"><div className="space-y-5">{groups.filter(group => group.column === 'cost').map(renderGroup)}</div><div className="space-y-5">{groups.filter(group => group.column === 'commercial').map(renderGroup)}</div></div>
    <div className="flex items-center gap-2 rounded-lg border border-bambu-green/30 bg-bambu-green/5 p-3 text-xs text-bambu-gray"><Calculator className="h-4 w-4 text-bambu-green" />{t('orders.runtimeCalculation.previewAndApprovalUseTheSameDecimalCostEngine', { lng: language })}</div>
  </div>;
}
