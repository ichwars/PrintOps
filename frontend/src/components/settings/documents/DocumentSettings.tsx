import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Loader2, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { ApiError, api } from '../../../api/client';
import {
  documentManagementApi,
  type DocumentConfigurationDraft,
  type DocumentConfigurationDetail,
} from '../../../api/documentManagement';
import { useAuth } from '../../../contexts/AuthContext';
import { useToast } from '../../../contexts/ToastContext';
import { ConfirmModal } from '../../ConfirmModal';
import { Button, Modal, TextField } from '../../ui';
import { DocumentActionBar } from './DocumentActionBar';
import { DocumentContextHeader } from './DocumentContextHeader';
import {
  initialDocumentContext,
  stableStringify,
  type DocumentContext,
  updateDocumentDraft,
} from './documentSettingsState';
import { BasicPolicySection } from './BasicPolicySection';
import { PaymentPolicySection } from './PaymentPolicySection';
import { TextBlocksSection } from './TextBlocksSection';
import { TaxPolicySection } from './TaxPolicySection';
import { EInvoicePolicySection } from './EInvoicePolicySection';
import { ReadinessPanel } from './ReadinessPanel';
import { VersionHistoryPanel } from './VersionHistoryPanel';

function todayKey(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60_000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : fallback;
}

export function DocumentSettings() {
  const { t } = useTranslation();
  const { hasPermission, loading: authLoading } = useAuth();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const canRead = hasPermission('document_templates:read');
  const canManage = hasPermission('document_templates:manage');
  const canOverrideTax = hasPermission('commercial_documents:tax_override');
  const canExportDocuments = hasPermission('commercial_documents:export');
  const [context, setContext] = useState<DocumentContext>(() => initialDocumentContext([]));
  const [pendingContext, setPendingContext] = useState<DocumentContext | null>(null);
  const [draft, setDraft] = useState<DocumentConfigurationDraft | null>(null);
  const [changeReason, setChangeReason] = useState('');
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [publishOpen, setPublishOpen] = useState(false);
  const [effectiveFrom, setEffectiveFrom] = useState(todayKey);
  const [actionError, setActionError] = useState<unknown>(null);

  const profilesQuery = useQuery({
    queryKey: ['business-profile-options'],
    queryFn: api.getBusinessProfileOptions,
    enabled: !authLoading && canRead,
  });
  const catalogQuery = useQuery({
    queryKey: ['document-configuration-catalog'],
    queryFn: documentManagementApi.getCatalog,
    enabled: !authLoading && canRead,
  });
  const placeholdersQuery = useQuery({
    queryKey: ['document-configuration-placeholders'],
    queryFn: documentManagementApi.getPlaceholders,
    enabled: !authLoading && canRead,
  });

  useEffect(() => {
    if (context.profileId === 0 && profilesQuery.data?.length) {
      setContext(initialDocumentContext(profilesQuery.data));
    }
  }, [context.profileId, profilesQuery.data]);

  const configurationQuery = useQuery({
    queryKey: ['document-configuration', context.profileId, context.documentType, context.language],
    queryFn: () => documentManagementApi.getSelectedConfiguration({
      businessProfileId: context.profileId,
      documentType: context.documentType,
      language: context.language,
    }),
    enabled: canRead && context.profileId > 0,
  });
  const configuration = configurationQuery.data ?? null;
  const displayContext = context.profileId === 0 && profilesQuery.data?.length
    ? initialDocumentContext(profilesQuery.data)
    : context;

  const readinessQuery = useQuery({
    queryKey: ['document-configuration-readiness', configuration?.id],
    queryFn: () => documentManagementApi.getConfigurationReadiness(configuration!.id),
    enabled: Boolean(configuration?.id),
  });
  const historyQuery = useQuery({
    queryKey: ['document-configuration-history', configuration?.id],
    queryFn: () => documentManagementApi.getConfigurationHistory(configuration!.id),
    enabled: Boolean(configuration?.id),
  });
  const auditQuery = useQuery({
    queryKey: ['document-configuration-audit', configuration?.id],
    queryFn: () => documentManagementApi.getConfigurationAudit(configuration!.id),
    enabled: Boolean(configuration?.id),
  });
  const effectivePolicyQuery = useQuery({
    queryKey: ['document-effective-policy', context.profileId, context.documentType, context.language, configuration?.lock_version],
    queryFn: () => documentManagementApi.getEffectivePolicy({
      business_profile_id: context.profileId,
      document_type: context.documentType,
      language: context.language,
    }),
    enabled: Boolean(configuration?.id),
  });

  useEffect(() => {
    setDraft(configuration?.policy ?? null);
    setChangeReason('');
  }, [configuration?.id, configuration?.lock_version, configuration?.policy]);

  const policyDirty = draft !== null && stableStringify(draft) !== stableStringify(configuration?.policy);
  const dirty = policyDirty || changeReason.trim().length > 0;

  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [dirty]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['document-configuration'] }),
      queryClient.invalidateQueries({ queryKey: ['document-configuration-readiness'] }),
      queryClient.invalidateQueries({ queryKey: ['document-configuration-history'] }),
      queryClient.invalidateQueries({ queryKey: ['document-configuration-audit'] }),
      queryClient.invalidateQueries({ queryKey: ['document-effective-policy'] }),
    ]);
  };

  const runAction = async (name: string, action: () => Promise<DocumentConfigurationDetail | void>) => {
    setPendingAction(name);
    setActionError(null);
    try {
      await action();
      await refresh();
      setChangeReason('');
      showToast(t(`settings.documents.messages.${name}Success`, `${name} completed.`), 'success');
    } catch (error) {
      setActionError(error);
      showToast(errorMessage(error, t('settings.documents.messages.actionFailed', 'The action failed.')), 'error');
    } finally {
      setPendingAction(null);
    }
  };

  const createMutation = useMutation({
    mutationFn: () => documentManagementApi.createConfiguration({
      business_profile_id: context.profileId,
      document_type: context.documentType,
      language: context.language,
      change_reason: changeReason.trim() || null,
    }),
  });
  const saveMutation = useMutation({
    mutationFn: () => documentManagementApi.updateConfiguration(configuration!.id, configuration!.lock_version, {
      change_reason: changeReason.trim(),
      basic: draft!.basic,
      payment: draft!.payment,
      dunning: draft!.dunning,
      content: draft!.content,
      tax: draft!.tax,
      einvoice: draft!.einvoice,
      text_blocks: draft!.text_blocks,
    }),
  });
  const publishMutation = useMutation({
    mutationFn: () => documentManagementApi.publishConfiguration(
      configuration!.id,
      configuration!.lock_version,
      effectiveFrom,
      changeReason.trim(),
    ),
  });
  const cloneMutation = useMutation({ mutationFn: () => documentManagementApi.cloneConfiguration(configuration!.id) });
  const withdrawMutation = useMutation({
    mutationFn: () => documentManagementApi.withdrawConfiguration(
      configuration!.id,
      configuration!.lock_version,
      changeReason.trim(),
    ),
  });

  const requestContextChange = (next: DocumentContext) => {
    if (dirty) setPendingContext(next);
    else setContext(next);
  };

  const discardAndChangeContext = () => {
    if (!pendingContext) return;
    setDraft(null);
    setChangeReason('');
    setContext(pendingContext);
    setPendingContext(null);
  };

  if (authLoading) {
    return <div className="flex items-center gap-2 text-sm text-gray-400"><Loader2 className="h-4 w-4 animate-spin" />{t('common.loading', 'Loading...')}</div>;
  }
  if (!canRead) {
    return <section id="card-document-settings" className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">{t('settings.documents.permissionDenied', 'You do not have permission to view document settings.')}</section>;
  }

  const initialLoading = profilesQuery.isPending || catalogQuery.isPending || placeholdersQuery.isPending || (context.profileId > 0 && configurationQuery.isPending);
  const queryError = profilesQuery.error ?? catalogQuery.error ?? placeholdersQuery.error ?? configurationQuery.error;
  const capability = catalogQuery.data?.document_types.find((item) => item.key === context.documentType);
  const readOnly = !canManage || configuration?.status !== 'draft' || pendingAction !== null;
  const changePolicy = (path: string, value: unknown) => setDraft((current) => current ? updateDocumentDraft(current, path, value) : current);

  return (
    <section id="card-document-settings" className="w-full space-y-4" aria-labelledby="document-settings-heading">
      <h2 id="document-settings-heading" className="sr-only">{t('settings.documents.title', 'Document settings')}</h2>
      {!profilesQuery.isPending && !catalogQuery.isPending ? (
        <DocumentContextHeader
          context={displayContext}
          profiles={profilesQuery.data ?? []}
          catalog={catalogQuery.data?.document_types ?? []}
          configuration={configuration}
          readiness={readinessQuery.data?.status ?? null}
          disabled={pendingAction !== null}
          onChange={requestContextChange}
        />
      ) : null}

      {initialLoading ? (
        <div className="flex items-center gap-2 rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4 text-sm text-gray-400">
          <Loader2 className="h-4 w-4 animate-spin" />{t('settings.documents.loading', 'Loading document configuration...')}
        </div>
      ) : null}
      {queryError ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-200">
          <AlertTriangle className="h-4 w-4" />
          <span>{errorMessage(queryError, t('settings.documents.loadError', 'Document settings could not be loaded.'))}</span>
          <Button variant="secondary" size="sm" onClick={() => configurationQuery.refetch()}><RefreshCw className="h-4 w-4" />{t('common.retry', 'Retry')}</Button>
        </div>
      ) : null}

      {!initialLoading && !queryError && context.profileId > 0 ? (
        <>
          <DocumentActionBar
            canManage={canManage}
            hasConfiguration={Boolean(configuration)}
            status={configuration?.status ?? null}
            readiness={readinessQuery.data?.status ?? null}
            dirty={dirty}
            policyDirty={policyDirty}
            changeReason={changeReason}
            pendingAction={pendingAction}
            onChangeReason={setChangeReason}
            onCreate={() => void runAction('create', () => createMutation.mutateAsync())}
            onSave={() => void runAction('save', () => saveMutation.mutateAsync())}
            onCheck={() => void runAction('check', async () => { await readinessQuery.refetch(); })}
            onPublish={() => setPublishOpen(true)}
            onClone={() => void runAction('clone', () => cloneMutation.mutateAsync())}
            onWithdraw={() => void runAction('withdraw', () => withdrawMutation.mutateAsync())}
          />

          {configuration ? (
            <>
              <div className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4 text-sm text-gray-300">
                <p className="font-medium text-white">{t('settings.documents.policy.title', 'Configuration')}</p>
                <p className="mt-1 text-gray-400">{t('settings.documents.policy.hint', 'The policy sections below are saved as a versioned draft. Published versions remain immutable.')}</p>
              </div>
              {draft && capability && placeholdersQuery.data ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    <BasicPolicySection
                      basic={draft.basic}
                      content={draft.content}
                      capability={capability}
                      effectiveBasic={effectivePolicyQuery.data?.basic}
                      effectiveContent={effectivePolicyQuery.data?.content}
                      findings={configuration.validation_findings}
                      disabled={readOnly}
                      onChange={changePolicy}
                    />
                    {capability.has_payment_terms ? (
                      <PaymentPolicySection
                        payment={draft.payment}
                        dunning={draft.dunning}
                        effectivePayment={effectivePolicyQuery.data?.payment}
                        findings={configuration.validation_findings}
                        disabled={readOnly}
                        onChange={changePolicy}
                      />
                    ) : null}
                  </div>
                  <TextBlocksSection
                    documentType={context.documentType}
                    blocks={draft.text_blocks}
                    catalog={placeholdersQuery.data}
                    findings={configuration.validation_findings}
                    disabled={readOnly}
                    onChange={(blocks) => setDraft((current) => current ? { ...current, text_blocks: blocks } : current)}
                  />
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                    {capability.has_tax ? (
                      <TaxPolicySection
                        tax={draft.tax}
                        ruleVersion={catalogQuery.data?.tax_rule_version ?? configuration.rule_versions.tax ?? '—'}
                        canOverride={canOverrideTax}
                        disabled={readOnly}
                        findings={configuration.validation_findings}
                        onChange={changePolicy}
                      />
                    ) : null}
                    {capability.einvoice ? (
                      <EInvoicePolicySection
                        policy={draft.einvoice}
                        ruleVersions={catalogQuery.data?.einvoice_rule_versions ?? configuration.rule_versions}
                        disabled={readOnly}
                        findings={configuration.validation_findings}
                        canExport={canExportDocuments}
                        onChange={changePolicy}
                      />
                    ) : null}
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <div className="rounded-xl border border-dashed border-bambu-dark-tertiary bg-bambu-dark-secondary p-6 text-center">
              <p className="font-medium text-white">{t('settings.documents.empty.title', 'No configuration for this context')}</p>
              <p className="mt-1 text-sm text-gray-400">{t('settings.documents.empty.description', 'Create a draft from the system defaults, then review it before publication.')}</p>
            </div>
          )}

          {configuration ? (
            <ReadinessPanel
              report={readinessQuery.data}
              error={actionError ?? readinessQuery.error}
              loading={readinessQuery.isPending}
              onReload={() => { setActionError(null); void refresh(); }}
            />
          ) : null}

          <VersionHistoryPanel
            items={historyQuery.data ?? []}
            auditEvents={auditQuery.data ?? []}
            loading={historyQuery.isPending || auditQuery.isPending}
          />
        </>
      ) : null}

      {pendingContext ? (
        <ConfirmModal
          title={t('settings.documents.unsaved.title', 'Unsaved changes')}
          message={t('settings.documents.unsaved.message', 'Changing the document context would discard the current changes.')}
          confirmText={t('settings.documents.unsaved.discard', 'Discard changes')}
          variant="warning"
          onConfirm={discardAndChangeContext}
          onCancel={() => setPendingContext(null)}
        />
      ) : null}

      <Modal
        open={publishOpen}
        onClose={() => setPublishOpen(false)}
        title={t('settings.documents.publish.title', 'Publish configuration')}
        description={t('settings.documents.publish.description', 'The published version becomes immutable and applies from the selected date.')}
      >
        <div className="space-y-4">
          <TextField
            type="date"
            value={effectiveFrom}
            label={t('settings.documents.publish.effectiveFrom', 'Effective from')}
            onValueChange={setEffectiveFrom}
          />
          <p className="text-sm text-gray-300">{t('settings.documents.publish.reason', { reason: changeReason, defaultValue: `Reason: ${changeReason}` })}</p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setPublishOpen(false)}>{t('common.cancel', 'Cancel')}</Button>
            <Button
              loading={pendingAction === 'publish'}
              disabled={!effectiveFrom || changeReason.trim().length < 3}
              onClick={() => {
                setPublishOpen(false);
                void runAction('publish', () => publishMutation.mutateAsync());
              }}
            >
              {t('settings.documents.actions.publish', 'Publish')}
            </Button>
          </div>
        </div>
      </Modal>
    </section>
  );
}
