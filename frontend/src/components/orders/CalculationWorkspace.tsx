import { useEffect, useId, useMemo, useState } from 'react';
import { Archive, Check, GitBranch, Save, Trash2, X } from 'lucide-react';
import { api, ApiError, type AppSettings, type BusinessProfileOption, type CustomerListItem, type Equipment, type InventorySpool, type Printer, type ProjectListItem } from '../../api/client';
import { calculationsApi, type CalculationCreate, type CalculationDetail, type CalculationPreview, type CalculationRevision, type CalculationVariant, type EffectiveCalculationDefaults } from '../../api/calculations';
import { NumberField, LegacySelect, ScrollArea, TextField } from '../ui';
import { RequestEditor } from './calculation/RequestEditor';
import { CommercialOverridesEditor } from './calculation/CommercialOverridesEditor';
import { CostBreakdown } from './calculation/CostBreakdown';
import { PriceDecision } from './calculation/PriceDecision';
import { FollowUpActions } from './calculation/FollowUpActions';
import { ProjectFileSection } from './calculation/ProjectFileSection';
import { SmallPartsEditor } from './calculation/SmallPartsEditor';
import { VariantStrip } from './calculation/VariantStrip';
import { AvailabilityPanel } from './calculation/AvailabilityPanel';

interface Props { calculation: CalculationDetail | null; onClose: () => void; onSaved: () => void; locale: string }
const inputClass = 'mt-1 h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white outline-none focus:border-bambu-green';
const numberInputClass = 'h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white outline-none focus:border-bambu-green';

const emptyVariant = (): CalculationVariant => ({
  name: 'Standard', is_preferred: true, sort_order: 0, price_method: 'target_margin', price_rate: '0.35',
  lines: [], operations: [], plates: [], small_parts: [],
});

function parseCalculationDefaults(value?: string): Record<string, number | string> {
  try { return JSON.parse(value || '{}'); } catch { return {}; }
}

export function CalculationWorkspace({ calculation, onClose, onSaved, locale }: Props) {
  const de = locale.startsWith('de');
  const titleId = useId().replace(/:/g, '');
  const [profiles, setProfiles] = useState<BusinessProfileOption[]>([]);
  const [customers, setCustomers] = useState<CustomerListItem[]>([]);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [effectiveDefaults, setEffectiveDefaults] = useState<EffectiveCalculationDefaults>({});
  const [preview, setPreview] = useState<CalculationPreview | null>(null);
  const [conflict, setConflict] = useState(false);
  const [revisions, setRevisions] = useState<CalculationRevision[]>([]);
  const [templateName, setTemplateName] = useState('');
  const [printers, setPrinters] = useState<Printer[]>([]);
  const [dryers, setDryers] = useState<Equipment[]>([]);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [spools, setSpools] = useState<InventorySpool[]>([]);
  const [approvalWarnings, setApprovalWarnings] = useState<string[]>([]);
  const [warningReasons, setWarningReasons] = useState<Record<string, string>>({});
  const [activeVariantIndex, setActiveVariantIndex] = useState(0);
  const [draft, setDraft] = useState<CalculationCreate>(() => calculation ? {
    business_profile_id: calculation.business_profile_id, customer_id: calculation.customer_id, project_id: calculation.project_id,
    request_kind: calculation.request_kind, quantity: calculation.quantity, title: calculation.title,
    position_description: calculation.position_description, special_terms: calculation.special_terms,
    commercial_overrides: { ...calculation.commercial_overrides }, currency: calculation.currency, notes: calculation.notes, variants: structuredClone(calculation.variants),
  } : { business_profile_id: 0, customer_id: null, project_id: null, request_kind: 'single', quantity: 1, title: '', position_description: null, special_terms: null, commercial_overrides: {}, currency: 'EUR', notes: null, variants: [emptyVariant()] });
  const [saving, setSaving] = useState(false); const [message, setMessage] = useState<string | null>(null);
  useEffect(() => { void api.getBusinessProfileOptions().then(items => { setProfiles(items.filter(item => item.is_active)); if (!calculation && draft.business_profile_id === 0 && items.length) setDraft(current => ({ ...current, business_profile_id: (items.find(item => item.is_default) ?? items[0]).id })); }); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { void api.getSettings().then(value => setSettings({ ...value, calculation_defaults: JSON.stringify(parseCalculationDefaults(value.calculation_defaults)) })); void calculationsApi.effectiveDefaults().then(setEffectiveDefaults); void api.getPrinters().then(setPrinters); void api.getEquipment(true).then(setDryers); void api.getProjects('active').then(setProjects); void api.getSpools(false).then(setSpools); }, []);
  useEffect(() => { if (calculation) void calculationsApi.revisions(calculation.id).then(setRevisions); }, [calculation]);
  useEffect(() => {
    if (!draft.business_profile_id) { setCustomers([]); return; }
    void api.getCustomers({ businessProfileId: draft.business_profile_id, status: 'active', limit: 200, offset: 0 }).then(result => setCustomers(result.items));
  }, [draft.business_profile_id]);
  const selected = draft.variants[activeVariantIndex] ?? draft.variants[0];
  const totals = useMemo(() => {
    const sell = selected.lines.reduce((sum, line) => sum + Number(line.quantity) * Number(line.unit_price ?? 0), 0);
    const production = selected.plates.length ? selected.plates.map((plate) => ({ good_parts: plate.good_parts, parts_per_run: plate.parts_per_print, scrap_runs: plate.scrap_prints, material_grams_per_run: plate.grams_per_print ?? '0', print_hours_per_run: plate.hours_per_print ?? '0' })) : selected.operations;
    const runs = production.reduce((sum, op) => sum + Math.ceil(op.good_parts / Math.max(1, op.parts_per_run)) + op.scrap_runs, 0);
    const grams = production.reduce((sum, op) => sum + (Math.ceil(op.good_parts / Math.max(1, op.parts_per_run)) + op.scrap_runs) * Number(op.material_grams_per_run), 0);
    const hours = production.reduce((sum, op) => sum + (Math.ceil(op.good_parts / Math.max(1, op.parts_per_run)) + op.scrap_runs) * Number(op.print_hours_per_run), 0);
    return { sell, runs, grams, hours };
  }, [selected]);
  const changeVariant = (index: number, update: (variant: CalculationVariant) => CalculationVariant) => setDraft(current => ({ ...current, variants: current.variants.map((variant, itemIndex) => itemIndex === index ? update(variant) : variant) }));
  const selectedIndex = Math.min(activeVariantIndex, Math.max(0, draft.variants.length - 1));
  const preferred = draft.variants.find(variant => variant.is_preferred) ?? draft.variants[0];
  const blockers = [
    !draft.business_profile_id && (de ? 'Unternehmensprofil auswählen' : 'Select a business profile'),
    !draft.title.trim() && (de ? 'Bezeichnung eintragen' : 'Enter a title'),
    !draft.variants.length && (de ? 'Mindestens eine Variante anlegen' : 'Add at least one variant'),
    preferred && !preferred.lines.length && !preferred.plates.length && (de ? 'Mindestens eine Projektplatte auswählen' : 'Select at least one project plate'),
  ].filter(Boolean) as string[];
  useEffect(() => {
    if (!settings || !selected) return;
    if (!selected.operations.length && !selected.plates.length) { setPreview(null); return; }
    const defaults = parseCalculationDefaults(settings.calculation_defaults);
    const n = (key: string, fallback = 0) => Number(defaults[key] ?? fallback);
    const roundingMode = String(defaults.roundingMode ?? 'none') as 'none' | '0.05' | '0.10' | '0.50' | '1.00' | 'x.90' | 'x.99';
    const productionOperations = selected.plates.length ? selected.plates.map((plate, index) => ({
      good_parts: plate.good_parts,
      parts_per_run: plate.parts_per_print,
      scrap_runs: plate.scrap_prints,
      material_grams_per_run: plate.grams_per_print ?? '0',
      print_hours_per_run: plate.hours_per_print ?? '0',
      provenance: plate.provenance,
      labor: [],
      sort_order: index,
    })) : selected.operations;
    const operationInputs = productionOperations.map(operation => {
      const printer = printers.find(item => item.id === Number(Object.hasOwn(operation.provenance, 'printer_id') ? operation.provenance.printer_id ?? 0 : defaults.defaultPrinterId ?? 0));
      const dryer = dryers.find(item => item.id === Number(Object.hasOwn(operation.provenance, 'dryer_id') ? operation.provenance.dryer_id ?? 0 : defaults.defaultDryerId ?? 0));
      return { good_parts: operation.good_parts, parts_per_run: operation.parts_per_run, scrap_runs: operation.scrap_runs, material_grams_per_run: operation.material_grams_per_run, material_price_per_kg: String(draft.commercial_overrides.material_price_per_kg ?? settings.default_filament_cost), material_markup_rate: String(draft.commercial_overrides.material_markup_rate ?? n('materialMarkupPercent') / 100), print_hours_per_run: operation.print_hours_per_run, machine_cost_per_hour: printer?.hourly_rate ?? '0', printer_power_kw: String(Number(printer?.nominal_power_watts ?? 0) / 1000), electricity_price_per_kwh: String(settings.energy_cost_per_kwh), drying_hours: String(operation.provenance.drying_hours ?? n('dryingHours')), dryer_power_kw: String(Number(dryer?.nominal_power_watts ?? 0) / 1000), labor: operation.labor, consumables: '0', packaging: '0', additional_costs: '0', additive_materials: '0', scrap_rate: '0', risk_rate: '0', shipping: '0', price_method: 'markup' as const, price_rate: '0', explicit_price: '0', discount_rate: '0', tax_rate: '0', minimum_price: '0', minimum_profit: '0', rounding_mode: 'none' as const };
    });
    const totalUnits = Math.max(1, selected.plates.length ? selected.plates.reduce((sum, plate) => sum + plate.good_parts, 0) : selected.lines.reduce((sum, line) => sum + Number(line.quantity), 0));
    const additive = selected.lines.filter(line => line.kind === 'material').reduce((sum, line) => sum + Number(line.quantity) * Number(line.unit_price ?? 0), 0) + selected.small_parts.reduce((sum, part) => sum + Number(part.quantity) * Number(part.unit_cost_snapshot), 0);
    const ov = draft.commercial_overrides;
    const commercial = { ...operationInputs[0], good_parts: Math.max(totalUnits, draft.quantity), parts_per_run: 1, scrap_runs: 0, material_grams_per_run: '0', material_price_per_kg: '0', material_markup_rate: '0', print_hours_per_run: '0', machine_cost_per_hour: '0', printer_power_kw: '0', drying_hours: '0', dryer_power_kw: '0', labor: [], consumables: String(ov.consumables ?? n('consumables', .75)), packaging: String(ov.packaging ?? n('packaging', 2.5)), additional_costs: String(ov.additional_costs ?? n('additionalCosts')), additive_materials: String(additive), scrap_rate: String(ov.scrap_rate ?? n('scrapPercent', 8) / 100), risk_rate: String(ov.risk_rate ?? n('riskPercent', 8) / 100), shipping: String(ov.shipping ?? n('shipping', 5.49)), price_method: selected.price_method, price_rate: selected.price_method === 'explicit_price' ? '0' : selected.price_rate, explicit_price: selected.price_method === 'explicit_price' ? selected.price_rate : String(n('explicitPrice')), discount_rate: String(ov.discount_rate ?? n('discountPercent') / 100), tax_rate: String(ov.tax_rate ?? n('taxPercent', 19) / 100), minimum_price: String(ov.minimum_price ?? n('minimumPrice', 12)), minimum_profit: String(ov.minimum_profit ?? n('minimumProfit', 4)), rounding_mode: String(ov.rounding_mode ?? roundingMode) as typeof roundingMode };
    const timer = window.setTimeout(() => void calculationsApi.previewBatch(operationInputs, commercial).then(setPreview).catch(() => setPreview(null)), 250);
    return () => window.clearTimeout(timer);
  }, [draft.commercial_overrides, draft.quantity, dryers, printers, selected, settings]);
  const save = async () => { setSaving(true); setMessage(null); setConflict(false); try { if (calculation) await calculationsApi.update(calculation.id, { ...draft, expected_version: calculation.version }); else await calculationsApi.create(draft); onSaved(); } catch (error) { const stale = error instanceof ApiError && error.status === 409; setConflict(stale); setMessage(stale ? (de ? 'Die Serverversion ist neuer. Deine Eingaben bleiben erhalten.' : 'The server version is newer. Your input is preserved.') : error instanceof Error ? error.message : 'Error'); } finally { setSaving(false); } };
  const reloadServerVersion = async () => { if (!calculation) return; const current = await calculationsApi.get(calculation.id); setDraft({ business_profile_id: current.business_profile_id, customer_id: current.customer_id, project_id: current.project_id, request_kind: current.request_kind, quantity: current.quantity, title: current.title, position_description: current.position_description, special_terms: current.special_terms, commercial_overrides: { ...current.commercial_overrides }, currency: current.currency, notes: current.notes, variants: structuredClone(current.variants) }); setConflict(false); setMessage(null); };
  const resetOverrides = () => { if (window.confirm(de ? 'Kalkulationswerte auf die zentralen Standards zurücksetzen?' : 'Reset calculation values to central defaults?')) setDraft(current => ({ ...current, commercial_overrides: {} })); };
  const approve = async () => { if (!calculation) return; setSaving(true); setMessage(null); try { const validation = await calculationsApi.validate(calculation.id); if (validation.blockers.length) { setMessage(`${de ? 'Freigabe blockiert' : 'Approval blocked'}: ${validation.blockers.join(', ')}`); return; } if (validation.warnings.length && approvalWarnings.length === 0) { setApprovalWarnings(validation.warnings); return; } await calculationsApi.approve(calculation.id, calculation.version, warningReasons); onSaved(); } catch (error) { setMessage(error instanceof Error ? error.message : 'Error'); } finally { setSaving(false); } };
  const revise = async () => { if (!calculation) return; setSaving(true); try { const created = await calculationsApi.revise(calculation.id); setMessage(`${de ? 'Folgeversion angelegt' : 'Follow-up version created'}: K-${String(created.id).padStart(6, '0')}`); onSaved(); } catch (error) { setMessage(error instanceof Error ? error.message : 'Error'); } finally { setSaving(false); } };
  const archive = async () => { if (!calculation || !window.confirm(de ? 'Kalkulation wirklich archivieren?' : 'Archive this calculation?')) return; setSaving(true); try { await calculationsApi.archive(calculation.id, calculation.version); onSaved(); } catch (error) { setMessage(error instanceof Error ? error.message : 'Error'); } finally { setSaving(false); } };
  const template = async () => { if (!calculation || !templateName.trim()) return; await calculationsApi.createTemplate(calculation.id, templateName.trim()); setTemplateName(''); setMessage(de ? 'Vorlage gespeichert.' : 'Template saved.'); };
  return <div className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden bg-black/70 p-3 md:p-8"><div role="dialog" aria-modal="true" aria-labelledby={titleId} className="mx-auto flex max-h-full w-full max-w-7xl flex-col overflow-hidden rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary shadow-2xl">
    <header className="flex shrink-0 items-center justify-between border-b border-bambu-dark-tertiary bg-bambu-dark-secondary px-5 py-4"><div><h2 id={titleId} className="text-xl font-bold text-white">{calculation ? calculation.title : de ? 'Kalkulation hinzufügen' : 'Add calculation'}</h2><p className="text-sm text-bambu-gray">{calculation ? `K-${String(calculation.id).padStart(6, '0')} · v${calculation.version}` : de ? 'Konkrete Kundenanfrage' : 'Concrete customer request'}</p></div><button onClick={onClose} aria-label={de ? 'Schließen' : 'Close'} className="rounded p-2 text-bambu-gray hover:bg-bambu-dark"><X /></button></header>
    <ScrollArea data-testid="calculation-scroll-viewport" className="min-h-0 flex-1" scrollbar="thin" stableGutter>
    <main className="space-y-5 p-5">
      {message && <div className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-sm text-amber-200"><span>{message}</span>{conflict && <button onClick={() => void reloadServerVersion()} className="rounded bg-amber-500/20 px-3 py-2 font-medium">{de ? 'Serverversion laden' : 'Load server version'}</button>}</div>}
      {blockers.length > 0 && <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200"><strong>{de ? 'Vor der Freigabe erforderlich:' : 'Required before approval:'}</strong><ul className="mt-1 list-disc pl-5">{blockers.map(blocker => <li key={blocker}>{blocker}</li>)}</ul></div>}
      {approvalWarnings.length > 0 && <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-100"><strong>{de ? 'Hinweise vor der Freigabe begründen' : 'Explain warnings before approval'}</strong><div className="mt-3 space-y-3">{approvalWarnings.map(code => <label key={code} className="block"><span className="mb-1 block">{({ manual_source_values: de ? 'Manuell erfasste Produktionswerte' : 'Manually entered production values', missing_machine_rate: de ? 'Maschinenstundensatz fehlt' : 'Machine hourly rate is missing', incomplete_production_values: de ? 'Produktionswerte sind unvollständig' : 'Production values are incomplete' } as Record<string, string>)[code] ?? code}</span><TextField value={warningReasons[code] ?? ''} onChange={event => setWarningReasons(current => ({ ...current, [code]: event.target.value }))} placeholder={de ? 'Begründung (Pflichtfeld)' : 'Reason (required)'} className="h-10 w-full rounded border border-amber-500/40 bg-bambu-dark px-3 text-white" /></label>)}</div></div>}
      <RequestEditor draft={draft} profiles={profiles} customers={customers} projects={projects} locale={locale} onChange={setDraft} />
      <VariantStrip variants={draft.variants} activeIndex={selectedIndex} locale={locale} onActiveChange={setActiveVariantIndex} onPreferredChange={(index) => setDraft((current) => ({ ...current, variants: current.variants.map((variant, itemIndex) => ({ ...variant, is_preferred: itemIndex === index })) }))} onClone={() => setDraft((current) => { const clone = { ...structuredClone(selected), name: `${selected.name} ${current.variants.length + 1}`, is_preferred: false, sort_order: current.variants.length }; setActiveVariantIndex(current.variants.length); return { ...current, variants: [...current.variants, clone] }; })} />
      <div className="flex items-end gap-3 rounded-lg bg-bambu-dark p-3"><label className="flex-1 text-xs text-bambu-gray">{de ? 'Name der aktiven Variante' : 'Active variant name'}<TextField aria-label={de ? 'Variantenname' : 'Variant name'} value={selected.name} onChange={(event) => changeVariant(selectedIndex, (variant) => ({ ...variant, name: event.target.value }))} className={inputClass} /></label>{draft.variants.length > 1 && <button type="button" aria-label={de ? 'Aktive Variante löschen' : 'Delete active variant'} onClick={() => setDraft((current) => { const variants = current.variants.filter((_, index) => index !== selectedIndex).map((variant, index) => ({ ...variant, sort_order: index })); if (!variants.some((variant) => variant.is_preferred)) variants[0] = { ...variants[0], is_preferred: true }; setActiveVariantIndex(Math.max(0, selectedIndex - 1)); return { ...current, variants }; })} className="mb-2 rounded p-2 text-red-300"><Trash2 className="h-4 w-4" /></button>}</div>
      <ProjectFileSection calculationId={calculation?.id ?? null} plates={selected.plates} printers={printers} dryers={dryers} spools={spools} locale={locale} onChange={(plates) => changeVariant(selectedIndex, (variant) => ({ ...variant, plates }))} />
      <SmallPartsEditor parts={selected.small_parts} locale={locale} currency={draft.currency} onChange={(small_parts) => changeVariant(selectedIndex, (variant) => ({ ...variant, small_parts }))} />
      <AvailabilityPanel calculationId={calculation && calculation.status !== 'draft' ? calculation.id : null} variant={selected} locale={locale} />
      <CommercialOverridesEditor values={draft.commercial_overrides} defaults={effectiveDefaults} locale={locale} onChange={commercial_overrides => setDraft(current => ({ ...current, commercial_overrides }))} onReset={resetOverrides} />
      <section><h3 className="mb-3 font-semibold text-white">6. {de ? 'Kosten & Preise' : 'Costs & prices'}</h3>
        <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><label className="text-sm text-bambu-gray">{de ? 'Preisverfahren' : 'Pricing method'}<LegacySelect value={selected.price_method} onChange={e => changeVariant(selectedIndex, v => ({ ...v, price_method: e.target.value as CalculationVariant['price_method'] }))} className={inputClass}><option value="target_margin">{de ? 'Zielmarge' : 'Target margin'}</option><option value="markup">{de ? 'Aufschlag' : 'Markup'}</option><option value="explicit_price">{de ? 'Fester Zielpreis' : 'Explicit price'}</option></LegacySelect></label><label className="text-sm text-bambu-gray">{selected.price_method === 'target_margin' ? (de ? 'Zielmarge' : 'Target margin') : selected.price_method === 'markup' ? (de ? 'Aufschlag' : 'Markup') : (de ? 'Zielpreis' : 'Target price')}<NumberField min="0" step="0.01" value={selected.price_rate} onChange={e => changeVariant(selectedIndex, v => ({ ...v, price_rate: e.target.value }))} containerClassName="mt-1" className={numberInputClass} /></label></div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[[de ? 'Druckläufe' : 'Print runs', preview?.total_runs ?? totals.runs], ['Material', preview ? new Intl.NumberFormat(locale, { style: 'currency', currency: draft.currency }).format(Number(preview.material_cost)) : `${totals.grams.toFixed(2)} g`], [de ? 'Herstellkosten' : 'Production cost', preview ? new Intl.NumberFormat(locale, { style: 'currency', currency: draft.currency }).format(Number(preview.production_cost)) : '–'], [de ? 'Netto' : 'Net', preview ? new Intl.NumberFormat(locale, { style: 'currency', currency: draft.currency }).format(Number(preview.net_price)) : new Intl.NumberFormat(locale, { style: 'currency', currency: draft.currency }).format(totals.sell)], [de ? 'Deckungsbeitrag' : 'Contribution', preview ? new Intl.NumberFormat(locale, { style: 'currency', currency: draft.currency }).format(Number(preview.contribution)) : '–'], [de ? 'Effektive Marge' : 'Effective margin', preview ? `${(Number(preview.effective_margin) * 100).toFixed(1)} %` : '–'], [de ? 'Steuer' : 'Tax', preview ? new Intl.NumberFormat(locale, { style: 'currency', currency: draft.currency }).format(Number(preview.tax)) : '–'], [de ? 'Brutto' : 'Gross', preview ? new Intl.NumberFormat(locale, { style: 'currency', currency: draft.currency }).format(Number(preview.gross_price)) : '–']].map(([label, value]) => <div key={String(label)} className="rounded-lg bg-bambu-dark p-4"><span className="text-xs text-bambu-gray">{label}</span><strong className="mt-1 block text-lg text-white">{value}</strong></div>)}</div></section>
      {calculation && <section className="grid gap-4 lg:grid-cols-2"><div><h3 className="mb-3 font-semibold text-white">6. {de ? 'Vorlage' : 'Template'}</h3><div className="flex gap-2 rounded-lg bg-bambu-dark p-3"><TextField value={templateName} onChange={e => setTemplateName(e.target.value)} placeholder={de ? 'Name der Vorlage' : 'Template name'} className="h-10 flex-1 rounded border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 text-white" /><button onClick={() => void template()} disabled={!templateName.trim()} className="rounded bg-bambu-green px-4 font-medium text-black disabled:opacity-50">{de ? 'Speichern' : 'Save'}</button></div></div><div><h3 className="mb-3 font-semibold text-white">{de ? 'Revisionshistorie' : 'Revision history'}</h3><div className="space-y-2">{revisions.length === 0 ? <p className="rounded-lg bg-bambu-dark p-3 text-sm text-bambu-gray">{de ? 'Noch keine freigegebene Revision.' : 'No approved revision yet.'}</p> : revisions.map(revision => <div key={revision.id} className="flex items-center justify-between rounded-lg bg-bambu-dark p-3 text-sm"><div><strong className="text-white">Revision {revision.revision_number}</strong><span className="ml-2 text-bambu-gray">{new Date(revision.approved_at).toLocaleString(locale)}</span></div><div className="text-right"><span className="block text-xs text-bambu-gray">{de ? 'Herstellkosten / Verkauf' : 'Production / selling'}</span><strong className="text-white">{new Intl.NumberFormat(locale, { style: 'currency', currency: revision.currency }).format(Number(revision.production_cost))} / {new Intl.NumberFormat(locale, { style: 'currency', currency: revision.currency }).format(Number(revision.selling_price))}</strong></div></div>)}</div></div></section>}
      <div className="grid items-start gap-4 lg:grid-cols-2"><CostBreakdown preview={preview} locale={locale} currency={draft.currency} /><PriceDecision preview={preview} locale={locale} currency={draft.currency} /></div>
      <FollowUpActions locale={locale} calculationRevisionId={calculation && calculation.status === 'approved' ? revisions[0]?.id ?? null : null} />
    </main>
    </ScrollArea>
    <footer className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-bambu-dark-tertiary bg-bambu-dark-secondary px-5 py-4">{calculation && calculation.status !== 'archived' && <button onClick={() => void archive()} disabled={saving} className="mr-auto inline-flex h-10 items-center gap-2 rounded-lg border border-bambu-dark-tertiary px-4 text-bambu-gray hover:text-white disabled:opacity-50"><Archive className="h-4 w-4" />{de ? 'Archivieren' : 'Archive'}</button>}{calculation && ['approved', 'superseded'].includes(calculation.status) && <button onClick={() => void revise()} disabled={saving} className="inline-flex h-10 items-center gap-2 rounded-lg border border-bambu-green px-4 text-bambu-green disabled:opacity-50"><GitBranch className="h-4 w-4" />{de ? 'Neue Version' : 'New version'}</button>}<button onClick={onClose} className="h-10 rounded-lg bg-bambu-dark px-4 text-white">{de ? 'Abbrechen' : 'Cancel'}</button>{calculation?.status === 'draft' && <button onClick={() => void approve()} disabled={saving || blockers.length > 0 || (approvalWarnings.length > 0 && approvalWarnings.some(code => !warningReasons[code]?.trim()))} className="inline-flex h-10 items-center gap-2 rounded-lg border border-bambu-green px-4 text-bambu-green disabled:opacity-50"><Check className="h-4 w-4" />{de ? 'Freigeben' : 'Approve'}</button>}{(!calculation || calculation.status === 'draft') && <button onClick={() => void save()} disabled={saving} className="inline-flex h-10 items-center gap-2 rounded-lg bg-bambu-green px-4 font-medium text-black disabled:opacity-50"><Save className="h-4 w-4" />{de ? 'Speichern' : 'Save'}</button>}</footer>
  </div></div>;
}
