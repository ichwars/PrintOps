import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, FilePlus2, LoaderCircle, RefreshCw } from 'lucide-react';
import { Component, Suspense, lazy, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { api } from '../../../api/client';
import {
  documentLayoutsApi,
  LayoutVersionConflictError,
  type EffectiveDocumentLayout,
  type LayoutDetail,
  type LayoutLanguage,
  type LayoutPatch,
  type LayoutSummary,
} from '../../../api/documentLayouts';
import { useAuth } from '../../../contexts/AuthContext';
import { useAutosaveDraft } from '../../../hooks/useAutosaveDraft';
import { Button } from '../../ui/Button';
import { TextField } from '../../ui/TextField';
import { LayoutContextBar, type LayoutPreviewSourceOption } from './LayoutContextBar';
import {
  LayoutControlPanel,
  type EditableLayoutSection,
  type LayoutEditorSection,
  type LayoutRuleChange,
  type LayoutRuleReset,
} from './LayoutControlPanel';
import { LayoutFindings } from './LayoutFindings';
import { LayoutHistoryDrawer } from './LayoutHistoryDrawer';
import { LayoutLifecycleBar } from './LayoutLifecycleBar';
import type { PdfPreviewSource } from './PdfPreviewPane';

type DraftPatch = Omit<LayoutPatch, 'expected_lock_version' | 'edit_session_id'>;

const PdfPreviewPane = lazy(() => import('./PdfPreviewPane').then((module) => ({ default: module.PdfPreviewPane })));

interface AutosaveLayoutDraft {
  layoutId: number;
  expectedLockVersion: number;
  editSessionId: string;
  changes: DraftPatch;
}

function newEditSessionId(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `layout-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const editableSections: EditableLayoutSection[] = ['page', 'typography', 'header', 'title', 'positions', 'totals', 'technical', 'notes', 'footer'];

function deriveOverrides(detail: LayoutDetail): DraftPatch {
  const result: DraftPatch = {};
  for (const section of editableSections) {
    const values = detail.effective[section] as unknown as Record<string, unknown>;
    const sources = detail.sourced[section].sources as unknown as Record<string, { configuration_id: number | null }>;
    const current: Record<string, unknown> = {};
    for (const [key, source] of Object.entries(sources)) {
      if (source.configuration_id === detail.summary.id) current[key] = values[key];
    }
    if (Object.keys(current).length) {
      (result as Record<string, unknown>)[section] = current;
    }
  }
  return result;
}

function withRuleChange<S extends EditableLayoutSection, K extends keyof EffectiveDocumentLayout[S]>(
  patch: DraftPatch,
  section: S,
  key: K,
  value: EffectiveDocumentLayout[S][K] | null,
): DraftPatch {
  const current = (patch[section] ?? {}) as unknown as Record<string, unknown>;
  return {
    ...patch,
    [section]: { ...current, [String(key)]: value },
  };
}

function layoutPriority(layout: LayoutSummary, documentType: string, language: LayoutLanguage): number {
  let score = layout.status === 'draft' ? 1000 : layout.status === 'active' || layout.status === 'scheduled' ? 500 : 0;
  if (layout.scope.document_type === documentType) score += 100;
  else if (layout.scope.document_type !== null) return -1;
  if (layout.scope.language === language) score += 20;
  else if (layout.scope.language !== null) return -1;
  return score + layout.version;
}

function matchingVersions(layouts: LayoutSummary[], selected: LayoutSummary): LayoutSummary[] {
  return layouts.filter((layout) =>
    layout.scope.business_profile_id === selected.scope.business_profile_id
    && layout.scope.document_type === selected.scope.document_type
    && layout.scope.language === selected.scope.language,
  );
}

class PreviewBoundary extends Component<{ resetKey: string; children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch() {
    // The preview has its own retry path. This boundary protects the editor draft.
  }

  componentDidUpdate(previous: { resetKey: string }) {
    if (previous.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (this.state.error) {
      return <div role="alert" className="flex min-h-[520px] items-center justify-center rounded-xl border border-red-500/40 bg-bambu-dark-secondary p-6 text-center text-sm text-red-300">
        PDF preview failed. Your layout draft is still available in the controls.
      </div>;
    }
    return this.props.children;
  }
}

function LoadingState() {
  return <div className="flex min-h-64 items-center justify-center rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary"><LoaderCircle className="h-6 w-6 animate-spin text-bambu-green" aria-label="Loading" /></div>;
}

export function DocumentLayoutSettings() {
  const { t } = useTranslation();
  const { hasPermission, loading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const canRead = hasPermission('document_layouts:read');
  const canManage = hasPermission('document_layouts:manage');
  const canReadCommercialDocuments = hasPermission('commercial_documents:read');
  const canReadAudit = hasPermission('order_audit:read');

  const [businessProfileId, setBusinessProfileId] = useState<number | null>(null);
  const [documentType, setDocumentType] = useState<string | null>(null);
  const [language, setLanguage] = useState<LayoutLanguage>('de');
  const [source, setSource] = useState<PdfPreviewSource | null>(null);
  const [patch, setPatch] = useState<DraftPatch>({});
  const [dirty, setDirty] = useState(false);
  const [confirmedLockVersion, setConfirmedLockVersion] = useState<number | null>(null);
  const [editSessionId, setEditSessionId] = useState(newEditSessionId);
  const [focusSection, setFocusSection] = useState<LayoutEditorSection | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [createReason, setCreateReason] = useState('');
  const initializedLayoutId = useRef<number | null>(null);

  const profilesQuery = useQuery({
    queryKey: ['business-profile-options'],
    queryFn: api.getBusinessProfileOptions,
    enabled: !authLoading && canRead,
  });
  const catalogQuery = useQuery({
    queryKey: ['document-layout-catalog'],
    queryFn: documentLayoutsApi.getCatalog,
    enabled: !authLoading && canRead,
  });
  const samplesQuery = useQuery({
    queryKey: ['document-layout-samples'],
    queryFn: documentLayoutsApi.getSamples,
    enabled: !authLoading && canRead,
  });

  useEffect(() => {
    const profiles = profilesQuery.data;
    if (businessProfileId === null && profiles?.length) {
      const profile = profiles.find((item) => item.is_default) ?? profiles[0];
      setBusinessProfileId(profile.id);
      setLanguage(profile.default_locale.toLowerCase().startsWith('de') ? 'de' : 'en');
    }
  }, [businessProfileId, profilesQuery.data]);

  useEffect(() => {
    if (documentType === null && catalogQuery.data?.document_types.length) {
      setDocumentType(catalogQuery.data.document_types[0]);
    }
  }, [catalogQuery.data, documentType]);

  const layoutsQuery = useQuery({
    queryKey: ['document-layouts', businessProfileId],
    queryFn: () => documentLayoutsApi.listLayouts(businessProfileId!),
    enabled: canRead && businessProfileId !== null,
  });

  const selectedLayout = useMemo(() => {
    if (!documentType) return null;
    return [...(layoutsQuery.data ?? [])]
      .map((layout) => ({ layout, score: layoutPriority(layout, documentType, language) }))
      .filter((item) => item.score >= 0)
      .sort((a, b) => b.score - a.score)[0]?.layout ?? null;
  }, [documentType, language, layoutsQuery.data]);

  const detailQuery = useQuery({
    queryKey: ['document-layout', selectedLayout?.id],
    queryFn: () => documentLayoutsApi.getLayout(selectedLayout!.id),
    enabled: canRead && Boolean(selectedLayout?.id),
  });
  const detail = detailQuery.data;

  useEffect(() => {
    if (!detail || initializedLayoutId.current === detail.summary.id) return;
    initializedLayoutId.current = detail.summary.id;
    setPatch(deriveOverrides(detail));
    setDirty(false);
    setConfirmedLockVersion(detail.summary.lock_version);
    setEditSessionId(newEditSessionId());
    setActionError(null);
  }, [detail]);

  const autosaveDraft: AutosaveLayoutDraft = {
    layoutId: detail?.summary.id ?? 0,
    expectedLockVersion: confirmedLockVersion ?? detail?.summary.lock_version ?? 0,
    editSessionId,
    changes: patch,
  };

  const autosave = useAutosaveDraft({
    draft: autosaveDraft,
    enabled: Boolean(detail && detail.summary.status === 'draft' && canManage && dirty),
    debounceMs: 500,
    fingerprint: (draft) => JSON.stringify(draft),
    adapter: (draft, signal) => documentLayoutsApi.patchLayout(draft.layoutId, {
      expected_lock_version: draft.expectedLockVersion,
      edit_session_id: draft.editSessionId,
      ...draft.changes,
    }, signal),
    onConfirmed: (confirmation) => {
      setConfirmedLockVersion(confirmation.lock_version);
      setDirty(false);
      void queryClient.invalidateQueries({ queryKey: ['document-layout', confirmation.id] });
      void queryClient.invalidateQueries({ queryKey: ['document-layout-readiness', confirmation.id] });
      void queryClient.invalidateQueries({ queryKey: ['document-layouts', confirmation.scope.business_profile_id] });
    },
  });

  const readinessQuery = useQuery({
    queryKey: ['document-layout-readiness', detail?.summary.id, confirmedLockVersion],
    queryFn: ({ signal }) => documentLayoutsApi.getReadiness(detail!.summary.id, signal),
    enabled: Boolean(detail && confirmedLockVersion && !dirty && autosave.status !== 'saving' && autosave.status !== 'pending'),
  });

  const documentsQuery = useQuery({
    queryKey: ['layout-preview-documents', businessProfileId, documentType],
    queryFn: () => documentLayoutsApi.getPreviewDocuments(businessProfileId!, documentType),
    enabled: canReadCommercialDocuments && businessProfileId !== null && documentType !== null,
  });

  const sourceOptions = useMemo<LayoutPreviewSourceOption[]>(() => {
    const samples = (samplesQuery.data ?? [])
      .filter((sample) => sample.document_type === documentType && sample.language === language)
      .map((sample) => ({ value: { kind: 'sample' as const, id: sample.key }, label: sample.title, detail: t('settings.documentLayout.context.sampleData', 'Sample data') }));
    const documents = (documentsQuery.data ?? [])
      .filter((document) => document.language === language)
      .map((document) => ({
        value: { kind: 'document' as const, id: String(document.id) },
        label: document.number ?? `#${document.id}`,
        detail: document.issue_date ?? document.technical_status,
        requiresCommercialDocumentRead: true,
      }));
    return [...samples, ...documents];
  }, [documentType, documentsQuery.data, language, samplesQuery.data, t]);

  useEffect(() => {
    const currentKey = source ? `${source.kind}:${source.id}` : null;
    if (!currentKey || !sourceOptions.some((option) => `${option.value.kind}:${option.value.id}` === currentKey)) {
      setSource(sourceOptions[0]?.value ?? null);
    }
  }, [source, sourceOptions]);

  const auditQuery = useQuery({
    queryKey: ['document-layout-audit', detail?.summary.id],
    queryFn: () => documentLayoutsApi.getAudit(detail!.summary.id),
    enabled: canReadAudit && Boolean(detail?.summary.id) && historyOpen,
    retry: false,
  });

  const onChange: LayoutRuleChange = (section, key, value) => {
    setPatch((current) => withRuleChange(current, section, key, value));
    setDirty(true);
  };
  const onReset: LayoutRuleReset = (section, key) => {
    setPatch((current) => withRuleChange(current, section, key, null));
    setDirty(true);
  };

  const refreshDetail = async () => {
    if (!detail) return;
    const latest = await queryClient.fetchQuery({
      queryKey: ['document-layout', detail.summary.id],
      queryFn: () => documentLayoutsApi.getLayout(detail.summary.id),
    });
    setPatch(deriveOverrides(latest));
    setConfirmedLockVersion(latest.summary.lock_version);
    setEditSessionId(newEditSessionId());
    setDirty(false);
    setActionError(null);
  };

  const runAction = async (action: () => Promise<LayoutSummary>) => {
    setActionBusy(true);
    setActionError(null);
    try {
      const result = await action();
      initializedLayoutId.current = null;
      await queryClient.invalidateQueries({ queryKey: ['document-layouts', result.scope.business_profile_id] });
      await queryClient.invalidateQueries({ queryKey: ['document-layout', result.id] });
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      setActionError(message);
      throw cause;
    } finally {
      setActionBusy(false);
    }
  };

  if (authLoading) return <LoadingState />;
  if (!canRead) return <div role="alert" className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-5 text-amber-200">{t('settings.documentLayout.access.unavailable', 'Layout settings are unavailable without read permission.')}</div>;
  if (profilesQuery.isLoading || catalogQuery.isLoading || samplesQuery.isLoading) return <LoadingState />;
  if (profilesQuery.isError || catalogQuery.isError || samplesQuery.isError || layoutsQuery.isError || detailQuery.isError) {
    return <div role="alert" className="rounded-xl border border-red-500/40 bg-red-500/10 p-5 text-red-200">
      <p>{t('settings.documentLayout.errors.load', 'The layout workspace could not be loaded.')}</p>
      <Button className="mt-3" variant="secondary" onClick={() => void Promise.all([profilesQuery.refetch(), catalogQuery.refetch(), samplesQuery.refetch(), layoutsQuery.refetch(), detailQuery.refetch()])}><RefreshCw className="h-4 w-4" />{t('settings.documentLayout.actions.retry', 'Retry')}</Button>
    </div>;
  }

  const profiles = profilesQuery.data ?? [];
  const catalog = catalogQuery.data;
  const previewKey = `${detail?.summary.id ?? 0}:${confirmedLockVersion ?? 0}:${source?.kind ?? ''}:${source?.id ?? ''}`;
  const visibleAutosaveStatus = !dirty && autosave.status === 'error' ? 'idle' : autosave.status;
  const conflict = dirty && autosave.error instanceof LayoutVersionConflictError;
  const readOnly = !canManage || detail?.summary.status !== 'draft';

  return <div id="document-layout-workspace" className="w-full space-y-3">
    <header>
      <h1 className="text-xl font-semibold text-white">{t('settings.documentLayout.title', 'Format & Preview')}</h1>
      <p className="mt-1 text-sm text-bambu-gray">{t('settings.documentLayout.description', 'Design versioned PDF layouts, inspect real documents and publish only validated configurations.')}</p>
    </header>

    <LayoutContextBar
      businessProfileId={businessProfileId}
      businessProfiles={profiles.map((profile) => ({ value: profile.id, label: profile.name, disabled: !profile.is_active }))}
      documentType={documentType}
      documentTypes={(catalog?.document_types ?? []).map((type) => ({ value: type, label: t(`settings.documents.documentTypes.${type}`, type) }))}
      language={language}
      languages={(catalog?.languages ?? ['de', 'en']).map((item) => ({ value: item, label: item === 'de' ? 'Deutsch' : 'English' }))}
      source={source}
      sources={sourceOptions}
      canReadCommercialDocuments={canReadCommercialDocuments}
      disabled={autosave.status === 'pending' || autosave.status === 'saving'}
      onBusinessProfileChange={(value) => { initializedLayoutId.current = null; setBusinessProfileId(value); }}
      onDocumentTypeChange={(value) => { initializedLayoutId.current = null; setDocumentType(value); }}
      onLanguageChange={(value) => { initializedLayoutId.current = null; setLanguage(value); }}
      onSourceChange={setSource}
    />

    {!canManage ? <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-sm text-blue-200"><strong>{t('settings.documentLayout.access.readOnly', 'Read only')}</strong> - {t('settings.documentLayout.access.readOnlyHint', 'Layouts and previews can be inspected. Changes and publication require management permission.')}</div> : null}

    {!detail && selectedLayout ? <LoadingState /> : !detail ? <section className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-5">
      <h2 className="font-semibold text-white">No layout exists for this context</h2>
      <p className="mt-1 text-sm text-bambu-gray">Create a versioned draft from the selected base template.</p>
      {canManage ? <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <TextField className="min-h-11 flex-1" value={createReason} placeholder="Reason for creating the draft" aria-label="Reason for creating the draft" onValueChange={setCreateReason} />
        <Button loading={actionBusy} disabled={createReason.trim().length < 3 || !businessProfileId || !documentType} onClick={() => void runAction(() => documentLayoutsApi.createLayout({ scope: { business_profile_id: businessProfileId!, document_type: documentType, language }, template_key: 'classic', reason: createReason.trim() }))}><FilePlus2 className="h-4 w-4" />Create draft</Button>
      </div> : null}
    </section> : <>
      <LayoutLifecycleBar
        detail={detail}
        confirmedLockVersion={confirmedLockVersion}
        autosaveStatus={visibleAutosaveStatus}
        readiness={readinessQuery.data}
        readinessLoading={readinessQuery.isLoading || dirty}
        readOnly={!canManage}
        actionBusy={actionBusy}
        onRetrySave={autosave.retry}
        onClone={(reason) => runAction(() => documentLayoutsApi.cloneLayout({ source_layout_id: detail.summary.id, reason }))}
        onPublish={(reason, effectiveFrom) => runAction(() => documentLayoutsApi.publishLayout(detail.summary.id, { expected_lock_version: confirmedLockVersion ?? detail.summary.lock_version, reason, effective_from: effectiveFrom }))}
        onWithdraw={(reason) => runAction(() => documentLayoutsApi.withdrawLayout(detail.summary.id, { reason }))}
        onOpenHistory={() => setHistoryOpen(true)}
      />

      {conflict ? <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm text-amber-200"><AlertTriangle className="h-4 w-4" /><span className="min-w-0 flex-1">{t('settings.documentLayout.errors.conflict', 'This draft was changed in another session.')}</span><Button size="sm" variant="secondary" onClick={() => void refreshDetail()}>{t('settings.documentLayout.errors.reload', 'Load latest version')}</Button></div> : null}
      {actionError && !conflict ? <div role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">{actionError}</div> : null}

      <main className="grid min-w-0 gap-4 min-[900px]:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)]">
        <div className="min-w-0 min-[900px]:min-w-[680px]">
          <PreviewBoundary resetKey={previewKey}>
            <Suspense fallback={<LoadingState />}>
              <PdfPreviewPane
                layoutId={detail.summary.id}
                confirmedLockVersion={confirmedLockVersion}
                source={source}
                pageFormat={detail.effective.page.page_format}
                className="min-h-[620px]"
              />
            </Suspense>
          </PreviewBoundary>
        </div>
        <aside className="min-w-0 space-y-3 min-[900px]:sticky min-[900px]:top-4 min-[900px]:max-h-[calc(100vh-2rem)] min-[900px]:overflow-y-auto min-[900px]:pr-1">
          <LayoutControlPanel
            detail={detail}
            patch={patch}
            findings={readinessQuery.data?.findings ?? []}
            readOnly={readOnly}
            focusSection={focusSection}
            onChange={onChange}
            onReset={onReset}
            onAssetsChanged={() => {
              void detailQuery.refetch();
              void readinessQuery.refetch();
            }}
          />
          <LayoutFindings findings={readinessQuery.data?.findings ?? []} stale={dirty || autosave.status === 'pending' || autosave.status === 'saving'} onNavigate={(section) => { setFocusSection(null); window.setTimeout(() => setFocusSection(section), 0); }} />
        </aside>
      </main>

      <LayoutHistoryDrawer
        open={historyOpen}
        versions={matchingVersions(layoutsQuery.data ?? [], detail.summary)}
        audit={auditQuery.data ?? []}
        canReadAudit={canReadAudit}
        onClose={() => setHistoryOpen(false)}
      />
    </>}
  </div>;
}
