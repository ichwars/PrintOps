import { useAuth } from '../contexts/AuthContext';
import { CalculationHistoryDialog } from '../components/orders/CalculationHistoryDialog';
import { orderRecordId } from '../utils/orderLinks';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Calculator, Plus, RefreshCw } from 'lucide-react';
import { useSearchParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { calculationsApi, type CalculationCreate, type CalculationDetail, type CalculationStatus, type CalculationTemplate } from '../api/calculations';
import { offersApi } from '../api/offers';
import { CalculationList } from '../components/orders/CalculationList';
import { CalculationWorkspace } from '../components/orders/CalculationWorkspace';
import { Button, LegacySelect } from '../components/ui';
import { OrderHeader, orderControlClass, orderPageClass } from '../components/orders/OrderLayout';
import { WarehouseToolbar } from '../components/warehouse/WarehouseLayout';

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
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language ?? 'en';
  const { hasPermission, loading: authLoading } = useAuth();
  const canRead = hasPermission('calculations:read');
  const canUpdate = hasPermission('calculations:update');
  const canApprove = hasPermission('calculations:approve');
  const canCreateOffer = hasPermission('commercial_documents:draft');
  const canReadOffers = hasPermission('commercial_documents:read');
  const canReadProjects = hasPermission('projects:read');
  const [params, setParams] = useSearchParams();
  const [history, setHistory] = useState<CalculationDetail | null>(null);
  const linkedId = orderRecordId(params.get('open'));
  const linked = useQuery({
    queryKey: ['calculations', 'detail', linkedId],
    queryFn: () => calculationsApi.get(linkedId!),
    enabled: canRead && linkedId !== null,
    staleTime: 0,
  });
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
    if (!canRead) return;
    setLoading(true); setError(null);
    try { setItems((await calculationsApi.list({ status: status || undefined })).items); }
    catch { setError(t('orders.runtimeCalculation.calculationsCouldNotBeLoaded', { lng: locale })); }
    finally { setLoading(false); }
  }, [t, locale, status, canRead]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (canRead && canUpdate) void calculationsApi.templates().then(setTemplates).catch(() => setTemplates([]));
  }, [canRead, canUpdate]);
  const instantiate = async (selectedTemplateId: string) => { if (!selectedTemplateId) return; const template = templates.find(item => item.id === Number(selectedTemplateId)); if (!template) return; const created = await calculationsApi.instantiateTemplate(template.id, template.name); setTemplateId(''); setEditor(created); void load(); };
  const visible = useMemo(() => items.filter(item => `${item.id} ${item.title}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())), [items, search]);
  const runAction = async (item: CalculationDetail, action: () => Promise<void>) => {
    setBusyId(item.id); setActionMessage(null);
    try { await action(); }
    catch (reason) { setActionMessage({ kind: 'error', text: reason instanceof Error ? reason.message : String(reason) }); }
    finally { setBusyId(null); }
  };
  const duplicate = (item: CalculationDetail) => runAction(item, async () => {
    const created = await calculationsApi.create(duplicatePayload(item, `${item.title} ${t('orders.runtimeCalculation.copy', { lng: locale })}`));
    setEditor(created);
    setActionMessage({ kind: 'success', text: t('orders.runtimeCalculation.calculationDuplicated', { lng: locale }) });
    await load();
  });
  const createOffer = (item: CalculationDetail) => runAction(item, async () => {
    const revisions = await calculationsApi.revisions(item.id);
    const revision = revisions.find(candidate => candidate.revision_number === item.current_revision) ?? revisions.at(-1);
    if (!revision) throw new Error(t('orders.runtimeCalculation.noApprovedRevisionFound', { lng: locale }));
    const offer = await offersApi.create(revision.id);
    setActionMessage({ kind: 'success', text: t('orders.runtimeCalculation.offerDraftCreatedCalculationsPage', { lng: locale, number: offer.number }) });
  });
  const revise = (item: CalculationDetail) => runAction(item, async () => {
    const revised = await calculationsApi.revise(item.id);
    setEditor(revised);
    await load();
  });
  const archive = (item: CalculationDetail) => {
    if (!window.confirm(t('orders.runtimeCalculation.archiveCalculationCalculationsPage', { lng: locale }))) return;
    void runAction(item, async () => {
      await calculationsApi.archive(item.id, item.version);
      setActionMessage({ kind: 'success', text: t('orders.runtimeCalculation.calculationArchived', { lng: locale }) });
      await load();
    });
  };
  const remove = (item: CalculationDetail) => {
    if (!window.confirm(t('orders.runtimeCalculation.permanentlyDeleteDraft', { lng: locale }))) return;
    void runAction(item, async () => {
      await calculationsApi.remove(item.id, item.version);
      setActionMessage({ kind: 'success', text: t('orders.runtimeCalculation.calculationDeleted', { lng: locale }) });
      await load();
    });
  };

  function closeLinked() {
    if (linkedId === null) return;
    const next = new URLSearchParams(params);
    next.delete('open');
    setParams(next, { replace: true });
  }
  function closeEditor() { setEditor(null); closeLinked(); }
  function closeHistory() { setHistory(null); closeLinked(); }
  const activeEditor = canRead && canUpdate ? editor : null;
  const activeHistory = canRead ? history ?? linked.data : null;

  return (
    <div className={orderPageClass}>
      <OrderHeader
        icon={Calculator}
        title={t('orders.runtimeCalculation.calculations', { lng: locale })}
        description={t('orders.runtimeCalculation.costCustomerRequestsCompareVariantsAndApproveRevisions', { lng: locale })}
      >
        {canRead && canUpdate && <><LegacySelect value={templateId} onChange={event => { const next = event.target.value; setTemplateId(next); void instantiate(next); }}
          aria-label={t('orders.runtimeCalculation.selectTemplate', { lng: locale })}
          className={`${orderControlClass} min-w-0 xl:w-64`}>
          <option value="">{t('orders.runtimeCalculation.selectTemplateCalculationsPage', { lng: locale })}</option>
          {templates.map(template => <option key={template.id} value={template.id}>{template.name}</option>)}
        </LegacySelect>
        <Button type="button" onClick={() => setEditor('create')} className="text-black! max-[768px]:min-h-[44px]!">
          <Plus aria-hidden="true" className="h-4 w-4" />{t('orders.runtimeCalculation.addCalculation', { lng: locale })}
        </Button></>}
      </OrderHeader>
      <WarehouseToolbar searchLabel={t('orders.runtimeCalculation.searchCalculations', { lng: locale })}
        placeholder={t('orders.runtimeCalculation.searchCalculationsCalculationsPage', { lng: locale })}
        value={search} onSearch={setSearch}>
        <LegacySelect value={status} onChange={event => setStatus(event.target.value as CalculationStatus | '')}
          aria-label={t('orders.runtimeCalculation.filterStatus', { lng: locale })} className={`${orderControlClass} sm:w-52`}>
          <option value="">{t('printers.filter.allStatuses', { lng: locale })}</option>
          <option value="draft">{t('settings.documentLayout.statuses.draft', { lng: locale })}</option>
          <option value="approved">{t('orders.runtimeCalculation.approved', { lng: locale })}</option>
          <option value="archived">{t('projects.statusArchived', { lng: locale })}</option>
        </LegacySelect>
      </WarehouseToolbar>
      {actionMessage && <div className={`rounded-lg border px-4 py-3 text-sm ${actionMessage.kind === 'success' ? 'border-bambu-green/40 bg-bambu-green/10 text-accent-foreground' : 'border-red-500/40 bg-red-500/10 text-red-700 dark:text-red-200'}`}>{actionMessage.text}</div>}
      {canRead && linkedId !== null && linked.isPending && <p role="status">{t('common.loading')}</p>}
      {canRead && linkedId !== null && linked.isError && <div role="alert" className="flex items-center gap-2">
        <span>{t('common.errorLoading')}</span>
        <Button variant="ghost" onClick={() => void linked.refetch()}>{t('common.retry')}</Button>
        <Button variant="ghost" onClick={closeLinked}>{t('common.dismiss')}</Button>
      </div>}
      {authLoading && <p role="status">{t('common.loading')}</p>}
      {!authLoading && !canRead && <p className="text-table-secondary">{t('orders.runtimeDashboard.permissionDenied')}</p>}
      {canRead && loading && <div className="rounded-lg border border-bambu-dark-tertiary p-10 text-center text-table-secondary">{t('orders.runtimeCalculation.loadingCalculations', { lng: locale })}</div>}
      {canRead && !loading && error && <div className="rounded-lg border border-red-500/40 p-8 text-center text-red-700 dark:text-red-300"><p>{error}</p><button onClick={() => void load()} className="mt-3 inline-flex items-center gap-2 rounded bg-bambu-dark px-3 py-2 text-white"><RefreshCw className="h-4 w-4" />{t('common.retry', { lng: locale })}</button></div>}
      {canRead && !loading && !error && visible.length === 0 && <div className="rounded-lg border border-bambu-dark-tertiary p-12 text-center"><Calculator className="mx-auto h-9 w-9 text-table-secondary" /><h2 className="mt-3 font-semibold text-white">{t('orders.runtimeCalculation.noCalculationsYet', { lng: locale })}</h2><p className="mt-1 text-sm text-table-secondary">{t('orders.runtimeCalculation.startWithAConcreteCustomerRequest', { lng: locale })}</p></div>}
      {canRead && !loading && !error && visible.length > 0 && (
        <CalculationList items={visible} locale={locale} canReadOffers={canReadOffers} canReadProjects={canReadProjects}
          onOpen={canUpdate ? setEditor : undefined} onHistory={setHistory}
          onDuplicate={canUpdate ? duplicate : undefined} onCreateOffer={canCreateOffer ? createOffer : undefined}
          onRevise={canUpdate ? revise : undefined} onArchive={canApprove ? archive : undefined}
          onDelete={canUpdate ? remove : undefined} busyId={busyId} />
      )}
      {activeEditor && <CalculationWorkspace calculation={activeEditor === 'create' ? null : activeEditor} locale={locale}
        onClose={closeEditor} onSaved={() => { closeEditor(); void load(); }} />}
      {activeHistory && <CalculationHistoryDialog key={activeHistory.id} item={activeHistory} locale={locale} onClose={closeHistory} />}
    </div>
  );
}
