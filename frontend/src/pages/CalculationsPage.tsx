import { useCallback, useEffect, useMemo, useState } from 'react';
import { Calculator, FileText, Plus, RefreshCw, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { calculationsApi, type CalculationDetail, type CalculationStatus, type CalculationTemplate } from '../api/calculations';
import { CalculationList } from '../components/orders/CalculationList';
import { CalculationWorkspace } from '../components/orders/CalculationWorkspace';

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

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try { setItems((await calculationsApi.list({ status: status || undefined })).items); }
    catch { setError(de ? 'Kalkulationen konnten nicht geladen werden.' : 'Calculations could not be loaded.'); }
    finally { setLoading(false); }
  }, [de, status]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void calculationsApi.templates().then(setTemplates); }, []);
  const instantiate = async () => { if (!templateId) return; const template = templates.find(item => item.id === Number(templateId)); if (!template) return; const created = await calculationsApi.instantiateTemplate(template.id, template.name); setEditor(created); void load(); };
  const visible = useMemo(() => items.filter(item => `${item.id} ${item.title}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())), [items, search]);

  return (
    <div className="w-full space-y-5 p-4 md:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h1 className="flex items-center gap-3 text-2xl font-bold text-white"><Calculator className="h-7 w-7 text-bambu-green" />{de ? 'Kalkulationen' : 'Calculations'}</h1><p className="mt-1 text-bambu-gray">{de ? 'Kundenanfragen kalkulieren, Varianten vergleichen und Revisionen freigeben.' : 'Cost customer requests, compare variants, and approve revisions.'}</p></div>
        <div className="flex flex-wrap gap-2"><select value={templateId} onChange={event => setTemplateId(event.target.value)} aria-label={de ? 'Vorlage auswählen' : 'Select template'} className="h-10 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white"><option value="">{de ? 'Vorlage auswählen…' : 'Select template…'}</option>{templates.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}</select><button type="button" onClick={() => void instantiate()} disabled={!templateId} className="inline-flex h-10 items-center gap-2 rounded-lg bg-bambu-dark px-4 text-white disabled:opacity-50"><FileText className="h-4 w-4" />{de ? 'Aus Vorlage' : 'From template'}</button><button type="button" onClick={() => setEditor('create')} className="inline-flex h-10 items-center gap-2 rounded-lg bg-bambu-green px-4 font-medium text-black"><Plus className="h-4 w-4" />{de ? 'Kalkulation hinzufügen' : 'Add calculation'}</button></div>
      </div>
      <div className="flex flex-wrap gap-3">
        <label className="relative min-w-64 flex-1"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-bambu-gray" /><span className="sr-only">{de ? 'Kalkulationen durchsuchen' : 'Search calculations'}</span><input value={search} onChange={event => setSearch(event.target.value)} placeholder={de ? 'Kalkulationen durchsuchen…' : 'Search calculations…'} className="h-10 w-full rounded-lg border border-bambu-dark-tertiary bg-bambu-dark pl-10 pr-3 text-white outline-none focus:border-bambu-green" /></label>
        <select value={status} onChange={event => setStatus(event.target.value as CalculationStatus | '')} aria-label={de ? 'Status filtern' : 'Filter status'} className="h-10 rounded-lg border border-bambu-dark-tertiary bg-bambu-dark px-3 text-white outline-none focus:border-bambu-green"><option value="">{de ? 'Alle Status' : 'All statuses'}</option><option value="draft">{de ? 'Entwurf' : 'Draft'}</option><option value="approved">{de ? 'Freigegeben' : 'Approved'}</option><option value="archived">{de ? 'Archiviert' : 'Archived'}</option></select>
      </div>
      {loading && <div className="rounded-lg border border-bambu-dark-tertiary p-10 text-center text-bambu-gray">{de ? 'Kalkulationen werden geladen…' : 'Loading calculations…'}</div>}
      {!loading && error && <div className="rounded-lg border border-red-500/40 p-8 text-center text-red-300"><p>{error}</p><button onClick={() => void load()} className="mt-3 inline-flex items-center gap-2 rounded bg-bambu-dark px-3 py-2 text-white"><RefreshCw className="h-4 w-4" />{de ? 'Erneut versuchen' : 'Retry'}</button></div>}
      {!loading && !error && visible.length === 0 && <div className="rounded-lg border border-bambu-dark-tertiary p-12 text-center"><Calculator className="mx-auto h-9 w-9 text-bambu-gray" /><h2 className="mt-3 font-semibold text-white">{de ? 'Noch keine Kalkulationen' : 'No calculations yet'}</h2><p className="mt-1 text-sm text-bambu-gray">{de ? 'Beginne mit einer konkreten Kundenanfrage.' : 'Start with a concrete customer request.'}</p></div>}
      {!loading && !error && visible.length > 0 && <CalculationList items={visible} locale={locale} onOpen={item => setEditor(item)} />}
      {editor && <CalculationWorkspace calculation={editor === 'create' ? null : editor} locale={locale} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); void load(); }} />}
    </div>
  );
}
