import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Building2, Check, Loader2, Pencil, Plus, Power, RefreshCw, Star, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ApiError, api, type BusinessProfile, type BusinessProfileCreate, type BusinessProfileUpdate } from '../../api/client';
import { useAuth } from '../../contexts/AuthContext';
import { BusinessProfileEditorModal } from './BusinessProfileEditorModal';

function withoutResponseId<T extends { id: number }>(value: T): Omit<T, 'id'> {
  const result: Partial<T> = { ...value };
  delete result.id;
  return result as Omit<T, 'id'>;
}

function profilePayload(profile: BusinessProfile): BusinessProfileCreate {
  return {
    name: profile.name, legal_name: profile.legal_name, trading_name: profile.trading_name,
    country_code: profile.country_code, default_currency: profile.default_currency, timezone: profile.timezone,
    default_locale: profile.default_locale, billing_mode: profile.billing_mode, is_active: profile.is_active,
    is_default: profile.is_default,
    addresses: profile.addresses.map(withoutResponseId),
    tax_identifiers: profile.tax_identifiers.map(withoutResponseId),
    bank_accounts: profile.bank_accounts.map(withoutResponseId),
  };
}

type RowActionOperation = 'set-default' | 'delete' | 'toggle-active';

interface RowActionIdentity {
  operation: RowActionOperation;
  profileId: number;
}

interface PersistentServerError {
  message: string;
  action: RowActionIdentity;
}

export function BusinessProfileSettings() {
  const { t, i18n } = useTranslation();
  const { hasPermission, loading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  const [includeInactive, setIncludeInactive] = useState(false);
  const [editorProfile, setEditorProfile] = useState<BusinessProfile | null | undefined>(undefined);
  const [serverError, setServerError] = useState<PersistentServerError | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const canRead = hasPermission('order_settings:read');
  const canManage = hasPermission('order_settings:manage');

  const invalidateProfiles = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['business-profiles', false], exact: true }),
      queryClient.invalidateQueries({ queryKey: ['business-profiles', true], exact: true }),
      queryClient.invalidateQueries({ queryKey: ['business-profile-options'], exact: true }),
    ]);
  };
  const localizedError = (error: unknown) => {
    if (!(error instanceof ApiError)) return error instanceof Error ? error.message : t('orders.businessProfile.error');
    const knownKey = error.code ? ({
      resource_in_use: 'orderUi.operationBlocked',
      version_conflict: 'orderMessages.errors.business_profile_version_conflict',
      duplicate_business_key: 'orderUi.duplicateRecord',
      not_found: 'orderUiNotFound',
    } as Record<string, string>)[error.code] : undefined;
    if (knownKey) return t(knownKey);
    if (i18n.language.startsWith('de') && error.status === 409) return t('orderMessages.errors.conflict');
    return error.message;
  };
  const showActionError = (error: unknown, action: RowActionIdentity) => setServerError({
    message: localizedError(error),
    action,
  });
  const clearActionError = (action: RowActionIdentity) => setServerError((current) => (
    current?.action.operation === action.operation && current.action.profileId === action.profileId ? null : current
  ));

  const profilesQuery = useQuery({
    queryKey: ['business-profiles', includeInactive],
    queryFn: async () => {
      try {
        const profiles = await api.getBusinessProfiles(includeInactive);
        setListError(null);
        return profiles;
      } catch (error) {
        setListError(localizedError(error));
        throw error;
      }
    },
    enabled: !authLoading && canRead,
  });
  const createMutation = useMutation({ mutationFn: api.createBusinessProfile });
  const updateMutation = useMutation({ mutationFn: ({ id, data }: { id: number; data: BusinessProfileUpdate }) => api.updateBusinessProfile(id, data) });
  const defaultMutation = useMutation({ mutationFn: api.setDefaultBusinessProfile });
  const deleteMutation = useMutation({ mutationFn: api.deleteBusinessProfile });
  const isMutating = createMutation.isPending || updateMutation.isPending || defaultMutation.isPending || deleteMutation.isPending;

  const submitEditor = async (data: BusinessProfileCreate | BusinessProfileUpdate) => {
    if (editorProfile) {
      await updateMutation.mutateAsync({ id: editorProfile.id, data: data as BusinessProfileUpdate });
    } else {
      await createMutation.mutateAsync(data as BusinessProfileCreate);
    }
    await invalidateProfiles();
    setEditorProfile(undefined);
  };

  const toggleActive = async (profile: BusinessProfile) => {
    const action: RowActionIdentity = { operation: 'toggle-active', profileId: profile.id };
    try {
      await updateMutation.mutateAsync({
        id: profile.id,
        data: { ...profilePayload(profile), version: profile.version, is_active: !profile.is_active },
      });
      clearActionError(action);
      await invalidateProfiles();
    } catch (error) {
      showActionError(error, action);
    }
  };

  const setDefault = async (profile: BusinessProfile) => {
    const action: RowActionIdentity = { operation: 'set-default', profileId: profile.id };
    try {
      await defaultMutation.mutateAsync(profile.id);
      clearActionError(action);
      await invalidateProfiles();
    } catch (error) {
      showActionError(error, action);
    }
  };

  const remove = async (profile: BusinessProfile) => {
    if (!window.confirm(t('orders.businessProfile.deleteConfirm', { name: profile.name }))) return;
    const action: RowActionIdentity = { operation: 'delete', profileId: profile.id };
    try {
      await deleteMutation.mutateAsync(profile.id);
      clearActionError(action);
      await invalidateProfiles();
    } catch (error) {
      showActionError(error, action);
    }
  };

  if (!canRead) {
    return <section id="card-business-profile" className="max-w-5xl text-sm text-red-300">{t('orders.businessProfile.permissionDenied')}</section>;
  }

  return (
    <section id="card-business-profile" className="max-w-5xl space-y-3" aria-labelledby="business-profile-heading">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-bambu-dark-tertiary pb-3">
        <div className="flex min-w-0 items-center gap-2">
          <Building2 className="h-5 w-5 shrink-0 text-bambu-green" aria-hidden="true" />
          <h2 id="business-profile-heading" className="text-lg font-semibold text-white">{t('orders.businessProfile.title')}</h2>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex items-center gap-2 text-sm text-bambu-gray-light">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(event) => setIncludeInactive(event.target.checked)}
              className="h-4 w-4 accent-bambu-green"
            />
            {t('orders.businessProfile.includeInactive')}
          </label>
          {canManage && (
            <button type="button" onClick={() => setEditorProfile(null)} disabled={isMutating} title={t('orders.businessProfile.add')} aria-label={t('orders.businessProfile.add')} className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-bambu-green text-white hover:bg-bambu-green-light disabled:cursor-not-allowed disabled:opacity-50">
              <Plus className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>

      {serverError && (
        <div role="alert" className="flex items-start justify-between gap-3 border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
          <span className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{serverError.message}</span>
          <button type="button" onClick={() => setServerError(null)} title={t('orders.businessProfile.dismiss')} aria-label={t('orders.businessProfile.dismiss')} className="shrink-0"><X className="h-4 w-4" /></button>
        </div>
      )}

      {profilesQuery.isPending && !listError && <div className="flex items-center gap-2 text-sm text-bambu-gray"><Loader2 className="h-4 w-4 animate-spin" />{t('orders.businessProfile.loading')}</div>}
      {listError && (
        <div className="flex flex-wrap items-center gap-3 text-sm text-red-300">
          <AlertTriangle className="h-4 w-4" />
          <span>{listError}</span>
          <button type="button" onClick={() => profilesQuery.refetch()} title={t('common.retry')} aria-label={t('common.retry')} className="inline-flex h-9 w-9 items-center justify-center rounded-md text-bambu-gray-light hover:bg-bambu-dark-tertiary"><RefreshCw className="h-4 w-4" /></button>
          <button type="button" onClick={() => setListError(null)} title={t('orders.businessProfile.dismiss')} aria-label={t('orders.businessProfile.dismiss')} className="inline-flex h-9 w-9 items-center justify-center rounded-md text-bambu-gray-light hover:bg-bambu-dark-tertiary"><X className="h-4 w-4" /></button>
        </div>
      )}
      {profilesQuery.isSuccess && profilesQuery.data.length === 0 && <p className="text-sm text-bambu-gray">{t('orders.businessProfile.empty')}</p>}
      {profilesQuery.isSuccess && profilesQuery.data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead className="border-b border-bambu-dark-tertiary text-xs uppercase text-bambu-gray">
              <tr><th className="px-2 py-2">{t('orders.businessProfile.profile')}</th><th className="px-2 py-2">{t('orders.businessProfile.country')}</th><th className="px-2 py-2">{t('orders.businessProfile.currency')}</th><th className="px-2 py-2">{t('orders.businessProfile.timezone')}</th><th className="px-2 py-2">{t('orders.businessProfile.billingMode')}</th><th className="px-2 py-2">{t('orders.businessProfile.status')}</th><th className="px-2 py-2 text-right">{t('orders.businessProfile.actions')}</th></tr>
            </thead>
            <tbody className="divide-y divide-bambu-dark-tertiary">
              {profilesQuery.data.map((profile) => (
                <tr key={profile.id} className="text-bambu-gray-light">
                  <td className="max-w-56 px-2 py-3"><p className="truncate font-medium text-white">{profile.name}</p><p className="truncate text-xs text-bambu-gray">{profile.legal_name}</p></td>
                  <td className="px-2 py-3">{profile.country_code}</td><td className="px-2 py-3">{profile.default_currency}</td><td className="px-2 py-3">{profile.timezone}</td><td className="px-2 py-3">{t(`orderUi.billingModes.${profile.billing_mode}`)}</td>
                  <td className="px-2 py-3"><span className={profile.is_active ? 'text-bambu-green' : 'text-bambu-gray'}>{profile.is_active ? t('orders.businessProfile.active') : t('orders.businessProfile.inactive')}</span>{profile.is_default && <span className="ml-2 inline-flex items-center gap-1 text-xs text-bambu-green"><Check className="h-3 w-3" />{t('orders.default')}</span>}</td>
                  <td className="px-2 py-3"><div className="flex justify-end gap-1">
                    {canManage && <button type="button" onClick={() => setEditorProfile(profile)} disabled={isMutating} title={t('orders.businessProfile.edit', { name: profile.name })} aria-label={t('orders.businessProfile.edit', { name: profile.name })} className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-bambu-dark-tertiary disabled:opacity-50"><Pencil className="h-4 w-4" /></button>}
                    {canManage && !profile.is_default && <button type="button" onClick={() => setDefault(profile)} disabled={isMutating} title={t('orders.businessProfile.setDefault', { name: profile.name })} aria-label={t('orders.businessProfile.setDefault', { name: profile.name })} className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-bambu-dark-tertiary disabled:opacity-50"><Star className="h-4 w-4" /></button>}
                    {canManage && <button type="button" onClick={() => toggleActive(profile)} disabled={isMutating} title={profile.is_active ? t('orders.businessProfile.deactivate', { name: profile.name }) : t('orders.businessProfile.activate', { name: profile.name })} aria-label={profile.is_active ? t('orders.businessProfile.deactivate', { name: profile.name }) : t('orders.businessProfile.activate', { name: profile.name })} className="inline-flex h-8 w-8 items-center justify-center rounded-md hover:bg-bambu-dark-tertiary disabled:opacity-50"><Power className="h-4 w-4" /></button>}
                    {canManage && !profile.is_default && <button type="button" onClick={() => remove(profile)} disabled={isMutating} title={t('orders.businessProfile.delete', { name: profile.name })} aria-label={t('orders.businessProfile.delete', { name: profile.name })} className="inline-flex h-8 w-8 items-center justify-center rounded-md text-red-300 hover:bg-red-500/10 disabled:opacity-50"><Trash2 className="h-4 w-4" /></button>}
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editorProfile !== undefined && <BusinessProfileEditorModal profile={editorProfile} isSubmitting={isMutating} onClose={() => setEditorProfile(undefined)} onSubmit={submitEditor} />}
    </section>
  );
}
