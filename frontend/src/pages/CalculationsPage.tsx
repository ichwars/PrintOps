import { useCallback, useEffect, useMemo, useState } from 'react';
import { Calculator, Plus, RefreshCw, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { calculationsApi, type CalculationCreate, type CalculationDetail, type CalculationStatus, type CalculationTemplate } from '../api/calculations';
import { offersApi } from '../api/offers';
import { CalculationList } from '../components/orders/CalculationList';
import { CalculationWorkspace } from '../components/orders/CalculationWorkspace';
import { LegacySelect, TextField } from '../components/ui';

function duplicatePayload(item: CalculationDetail, title: string): CalculationCreate {
  return {
    business_profile_id: item.business_profile_id,
    customer_id: item.customer_id,
    project_id: item.project_id,
    request_kind: item.request_kind,
    quantity: item.quantity,
    title,
    position_description: item.position_description,
    special_terms: item.special_terms,
    commercial_overrides: { ...item.commercial_overrides },
    currency: item.currency,
    notes: item.notes,
    variants: structuredClone(item.variants).map(variant => ({ ...variant, plates: [] })),
  };
}

export function CalculationsPage() {
  const { i18n } = useTranslation();
  const de = i18n.resolvedLanguage?.startsWith('de') ?? false;
  const locale = de ? 'de-DE' : 'en-US';
  const [items, setItems] = useState<CalculationDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<CalculationStatus | ''>('');
  const [editor, setEditor] = useState<'create' | CalculationDetail | null>(null);
  const [templates, setTemplates] = useState<CalculationTemplate[]>([]);
  const [templateId, setTemplateId] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [actionMessage, setActionMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setItems((await calculationsApi.list({ status: status || undefined })).items); }
    catch { setError(de ? 'Kalkulationen konnten nicht geladen werden.' : 'Calculations could not be loaded.'); }
    finally { setLoading(false); }
  }, [de, status]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void calculationsApi.templates().then(setTemplates); }, []);
  const instantiate = async (selectedTemplateId: string) => { if (!selectedTemplateId) return; const template = templates.find(item => item.id === Number(selectedTemplateId)); if (!template) return; const created = await calculationsApi.instantiateTemplate(template.id, template.name); setTemplateId(''); setEditor(created); void load(); };
  const visible = useMemo(() => items.filter(item => `${item.id} ${item.title}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())), [items, search]);
  const runAction = async (item: CalculationDetail, action: () => Promise<void>) => {
    setBusyId(item.id); setActionMessage(null);
    try { await action(); }
    catch (reason) { setActionMessage({ kind: 'error', text: reason instanceof Error ? reason.message : String(reason) }); }
    finally { setBusyId(null); }
  };
  const duplicate = (item: CalculationDetail) => runAction(item, async () => {
    const created = await calculationsApi.create(duplicatePayload(item, `${item.title} ${de ? 'Kopie' : 'copy'}`));
    setEditor(created);
    setActionMessage({ kind: 'success', text: de ? 'Kalkulation wurde dupliziert.' : 'Calculation duplicated.' });
    await load();
  });
  const createOffer = (item: CalculationDetail) => runAction(item, async () => {
    const revisions = await calculationsApi.revisions(item.id);
    const revision = revisions.find(candidate => candidate.revision_number === item.current_revision) ?? revisions.at(-1);
    if (!revision) throw new Error(de ? 'Keine freigegebene Revision gefunden.' : 'No approved revision found.');
    const offer = await offersApi.create(revision.id);
    setActionMessage({ kind: 'success', text: de ? `Angebotsentwurf ${offer.number} erstellt.` : `Offer draft ${offer.number} created.` });
  });
  const revise = (item: CalculationDetail) => runAction(item, async () => {
    const revised = await calculationsApi.revise(item.id);
    setEditor(revised);
    await load();
  });
  const archive = (item: CalculationDetail) => {
    if (!window.confirm(de ? 'Kalkulation archivieren?' : 'Archive calculation?')) return;
    void runAction(item, async () => {
      await calculationsApi.archive(item.id, item.version);
      setActionMessage({ kind: 'success', text: de ? 'Kalkulation wurde archiviert.' : 'Calculation archived.' });
      await load();
    });
  };
  const remove = (item: CalculationDetail) => {
    if (!window.confirm(de ? 'Entwurf endgültig löschen?' : 'Permanently delete draft?')) return;
    void runAction(item, async () => {
      await calculationsApi.remove(item.id, item.version);
      setActionMessage({ kind: 'success', text: de ? 'Kalkulation wurde gelöscht.' : 'Calculation deleted.' });
      await load();
    });
  };

  return (
    <div className="w-full space-y-5 p-4 md:p-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0"><h1 className="flex items-center gap-3 text-2xl font-bold text-white"><Calculator className="h-7 w-7 shrink-0 text-bambu-green" />{de ? 'Kalkulationen' : 'Calculations'}</h1><p className="mt-1 text-bambu-gray">{de ? 'Kundenanfragen kalkulieren, Varianten vergleichen und Revisionen freigeben.' : 'Cost customer requests, compare variants, and approve revisions.'}</p></div>
        <div className="flex min-w-0 flex-wrap items-center gap-2 xl:flex-nowrap xl:justify-end"><div className="min-w-[260px] flex-1 xl:w-[420px] xl:flex-none"><LegacySelect value={templateId} onChange={event => { const next = event.target.value; setTemplateId(next); void instantiate(next); }} aria-label={de ? 'Vorlage auswählen' : 'Select template'} className="h-10 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white"><option value="">{de ? 'Vorlage auswählen…' : 'Select template…'}</option>{templates.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}</LegacySelect></div><button type="button" onClick={() => setEditor('create')} className="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg bg-bambu-green px-4 font-medium text-black"><Plus className="h-4 w-4" />{de ? 'Kalkulation hinzufügen' : 'Add calculation'}</button></div>
      </div>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <label className="relative min-w-64 flex-1"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-bambu-gray" /><span className="sr-only">{de ? 'Kalkulationen durchsuchen' : 'Search calculations'}</span><TextField value={search} onChange={event => setSearch(event.target.value)} placeholder={de ? 'Kalkulationen durchsuchen…' : 'Search calculations…'} className="h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark pl-10 pr-3 text-white outline-none focus:border-bambu-green" /></label>
        <div className="lg:w-56"><LegacySelect value={status} onChange={event => setStatus(event.target.value as CalculationStatus | '')} aria-label={de ? 'Status filtern' : 'Filter status'} className="h-10 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white outline-none focus:border-bambu-green"><option value="">{de ? 'Alle Status' : 'All statuses'}</option><option value="draft">{de ? 'Entwurf' : 'Draft'}</option><option value="approved">{de ? 'Freigegeben' : 'Approved'}</option><option value="archived">{de ? 'Archiviert' : 'Archived'}</option></LegacySelect></div>
      </div>
      {actionMessage && <div className={`rounded-lg border px-4 py-3 text-sm ${actionMessage.kind === 'success' ? 'border-bambu-green/40 bg-bambu-green/10 text-bambu-green' : 'border-red-500/40 bg-red-500/10 text-red-200'}`}>{actionMessage.text}</div>}
      {loading && <div className="rounded-lg border border-bambu-dark-tertiary p-10 text-center text-bambu-gray">{de ? 'Kalkulationen werden geladen…' : 'Loading calculations…'}</div>}
      {!loading && error && <div className="rounded-lg border border-red-500/40 p-8 text-center text-red-300"><p>{error}</p><button onClick={() => void load()} className="mt-3 inline-flex items-center gap-2 rounded bg-bambu-dark px-3 py-2 text-white"><RefreshCw className="h-4 w-4" />{de ? 'Erneut versuchen' : 'Retry'}</button></div>}
      {!loading && !error && visible.length === 0 && <div className="rounded-lg border border-bambu-dark-tertiary p-12 text-center"><Calculator className="mx-auto h-9 w-9 text-bambu-gray" /><h2 className="mt-3 font-semibold text-white">{de ? 'Noch keine Kalkulationen' : 'No calculations yet'}</h2><p className="mt-1 text-sm text-bambu-gray">{de ? 'Beginne mit einer konkreten Kundenanfrage.' : 'Start with a concrete customer request.'}</p></div>}
      {!loading && !error && visible.length > 0 && <CalculationList items={visible} locale={locale} onOpen={item => setEditor(item)} onDuplicate={duplicate} onCreateOffer={createOffer} onRevise={revise} onArchive={archive} onDelete={remove} busyId={busyId} />}
      {editor && <CalculationWorkspace calculation={editor === 'create' ? null : editor} locale={locale} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); void load(); }} />}
    </div>
  );
}
