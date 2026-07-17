import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, ChevronLeft, ChevronRight, Eye, Pencil, Plus, Search, Trash2, Users } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ApiError, api, type CustomerCreate, type CustomerDetail, type CustomerKind, type CustomerStatus, type CustomerUpdate } from '../api/client';
import { Button } from '../components/Button';
import { ConfirmModal } from '../components/ConfirmModal';
import { CustomerDetailsModal } from '../components/orders/CustomerDetailsModal';
import { CustomerEditorModal } from '../components/orders/CustomerEditorModal';
import { useAuth } from '../contexts/AuthContext';
import { useModalFocusLifecycle } from '../hooks/useModalFocusLifecycle';
import { normalizeOrderTags } from '../lib/orderTagNormalization';
import { LegacySelect, TextField } from '../components/ui';

const limit = 25;
const emptyProfiles: import('../api/client').BusinessProfileOption[] = [];
const controlClass = 'h-10 rounded-md border border-bambu-dark-tertiary bg-bambu-dark px-3 text-sm text-white focus:border-bambu-green focus:outline-none';

function localizedOrderError(error: unknown, t: (key: string) => string, language: string, fallback: string): string {
  if (!(error instanceof ApiError)) return error instanceof Error ? error.message : fallback;
  const knownKey = error.code ? ({
    resource_in_use: 'orderUi.operationBlocked',
    version_conflict: 'orderMessages.errors.customer_version_conflict',
    duplicate_business_key: 'orderUi.duplicateRecord',
    not_found: 'orderUiNotFound',
  } as Record<string, string | null>)[error.code] : undefined;
  if (knownKey === null) return fallback;
  if (knownKey) return t(knownKey);
  if (language.startsWith('de') && error.status === 409) return t('orderMessages.errors.conflict');
  return error.message;
}

export function OrdersCustomersPage() {
  const { t, i18n } = useTranslation();
  const { loading: authLoading, hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const canRead = !authLoading && hasPermission('customers:read');
  const canManage = !authLoading && hasPermission('customers:manage');
  const [profileId, setProfileId] = useState<number | undefined>();
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<CustomerStatus | ''>('');
  const [kind, setKind] = useState<CustomerKind | ''>('');
  const [offset, setOffset] = useState(0);
  const [detailsId, setDetailsId] = useState<number | null>(null);
  const [editor, setEditor] = useState<'create' | number | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: number; name: string } | null>(null);

  const profilesQuery = useQuery({
    queryKey: ['business-profile-options'],
    queryFn: () => api.getBusinessProfileOptions(),
    enabled: canRead,
  });
  const profiles = profilesQuery.data ?? emptyProfiles;
  const activeProfiles = useMemo(() => profiles.filter((profile) => profile.is_active), [profiles]);
  const selectedProfileId = activeProfiles.some((profile) => profile.id === profileId) ? profileId : undefined;

  useEffect(() => {
    if (activeProfiles.length === 0) {
      if (profileId !== undefined) setProfileId(undefined);
      setDetailsId(null);
      setEditor(null);
      setDeleteTarget(null);
      return;
    }
    if (selectedProfileId !== undefined) return;
    setProfileId((activeProfiles.find((profile) => profile.is_default) ?? activeProfiles[0]).id);
    setOffset(0);
    setDetailsId(null);
    setEditor(null);
    setDeleteTarget(null);
  }, [activeProfiles, profileId, selectedProfileId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(searchInput.trim());
      setOffset(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const queryKey = ['customers', selectedProfileId, search, status, kind, limit, offset] as const;
  const customersQuery = useQuery({
    queryKey,
    queryFn: () => api.getCustomers({ businessProfileId: selectedProfileId!, search: search || undefined, status: status || undefined, kind: kind || undefined, limit, offset }),
    enabled: canRead && selectedProfileId !== undefined,
  });
  const detailsQuery = useQuery({
    queryKey: ['customer', detailsId],
    queryFn: () => api.getCustomer(detailsId!),
    enabled: canRead && detailsId !== null,
  });
  const editorId = typeof editor === 'number' ? editor : null;
  const editorQuery = useQuery({
    queryKey: ['customer', editorId],
    queryFn: () => api.getCustomer(editorId!),
    enabled: canManage && editorId !== null,
  });

  const closeEditor = () => setEditor(null);
  const createMutation = useMutation({
    mutationFn: (data: CustomerCreate) => api.createCustomer(data),
    onSuccess: async (customer) => {
      queryClient.setQueryData(['customer', customer.id], customer);
      await queryClient.invalidateQueries({ queryKey: ['customers'] });
      closeEditor();
    },
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: CustomerUpdate }) => api.updateCustomer(id, data),
    onSuccess: async (customer) => {
      queryClient.setQueryData(['customer', customer.id], customer);
      await queryClient.invalidateQueries({ queryKey: ['customers'], refetchType: 'active' });
      closeEditor();
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteCustomer(id),
    onSuccess: async () => {
      setDetailsId(null);
      setEditor(null);
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ['customers'] });
    },
  });

  const submitEditor = async (data: CustomerCreate | CustomerUpdate) => {
    const normalizedData = { ...data, tags: normalizeOrderTags(data.tags ?? []) };
    if (editor === 'create') await createMutation.mutateAsync(normalizedData as CustomerCreate);
    else if (typeof editor === 'number') await updateMutation.mutateAsync({ id: editor, data: normalizedData as CustomerUpdate });
  };
  const reloadCurrent = async (): Promise<CustomerDetail> => {
    if (typeof editor !== 'number') throw new Error('Cannot reload a new customer.');
    return api.getCustomer(editor);
  };
  const acceptReload = async (customer: CustomerDetail) => {
    const queryKey = ['customer', customer.id] as const;
    await queryClient.cancelQueries({ queryKey, exact: true });
    queryClient.setQueryData(queryKey, customer);
  };
  const mutationPending = createMutation.isPending || updateMutation.isPending;
  const openDetails = (id: number) => { setEditor(null); setDeleteTarget(null); setDetailsId(id); };
  const openEditor = (target: 'create' | number) => { setDetailsId(null); setDeleteTarget(null); setEditor(target); };
  const openDelete = (target: { id: number; name: string }) => { setDetailsId(null); setEditor(null); deleteMutation.reset(); setDeleteTarget(target); };

  const setProfile = (value: number) => { setProfileId(value); setOffset(0); setDetailsId(null); setEditor(null); setDeleteTarget(null); };
  const setStatusFilter = (value: CustomerStatus | '') => { setStatus(value); setOffset(0); };
  const setKindFilter = (value: CustomerKind | '') => { setKind(value); setOffset(0); };
  const page = customersQuery.data;
  useEffect(() => {
    if (!page || page.items.length > 0 || page.offset <= 0 || page.total <= 0) return;
    const lastValidOffset = Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit);
    if (lastValidOffset !== page.offset) setOffset(lastValidOffset);
  }, [page]);
  const pageStart = page && page.total > 0 ? page.offset + 1 : 0;
  const pageEnd = page ? Math.min(page.offset + page.limit, page.total) : 0;

  if (authLoading) return <Loading label={t('orders.customers.loading')} />;
  if (!canRead) return <State icon={<AlertTriangle className="h-5 w-5" />} text={t('orders.customers.permissionDenied')} />;

  return (
    <div className="space-y-5 p-4 md:p-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold text-white"><Users className="h-7 w-7 text-bambu-green" />{t('orders.customers.title')}</h1>
          <p className="mt-1 text-sm text-bambu-gray">{t('orders.customers.subtitle')}</p>
        </div>
        {canManage && selectedProfileId !== undefined && <Button onClick={() => openEditor('create')}><Plus className="mr-2 h-4 w-4" />{t('orders.customers.add')}</Button>}
      </header>

      {profilesQuery.isPending ? <Loading label={t('orders.businessProfile.loading')} /> : profilesQuery.isError ? (
        <State icon={<AlertTriangle className="h-5 w-5" />} text={t('orders.businessProfile.error')} action={<Button size="sm" variant="secondary" onClick={() => profilesQuery.refetch()}>{t('common.retry')}</Button>} />
      ) : activeProfiles.length === 0 ? (
        <State text={t('orders.customers.noBusinessProfile')} action={<Link className="text-bambu-green hover:underline" to="/settings?tab=orders-calculation&sub=business-profile">{t('orders.customers.configureProfiles')}</Link>} />
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-3 border-y border-bambu-dark-tertiary py-3">
            <label className="min-w-52 text-xs text-bambu-gray">{t('orders.customers.businessProfile')}<LegacySelect aria-label={t('orders.customers.businessProfile')} value={selectedProfileId} onChange={(event) => setProfile(Number(event.target.value))} className={`${controlClass} mt-1 w-full`}>{profiles.map((profile) => <option key={profile.id} value={profile.id} disabled={!profile.is_active}>{profile.name}</option>)}</LegacySelect></label>
            <label className="relative min-w-60 flex-1 text-xs text-bambu-gray">{t('orders.customers.search')}<Search className="pointer-events-none absolute bottom-2.5 left-3 h-4 w-4 text-bambu-gray" /><TextField type="search" aria-label={t('orders.customers.search')} value={searchInput} onChange={(event) => setSearchInput(event.target.value)} className={`${controlClass} mt-1 w-full pl-9`} /></label>
            <label className="min-w-40 text-xs text-bambu-gray">{t('orders.customers.statusFilter')}<LegacySelect aria-label={t('orders.customers.statusFilter')} value={status} onChange={(event) => setStatusFilter(event.target.value as CustomerStatus | '')} className={`${controlClass} mt-1 w-full`}><option value="">{t('common.all')}</option>{(['active', 'inactive', 'blocked'] as const).map((item) => <option key={item} value={item}>{t(`orders.status.${item}`)}</option>)}</LegacySelect></label>
            <div className="inline-flex h-10 items-center rounded-md border border-bambu-dark-tertiary bg-bambu-dark p-1" aria-label={t('orders.customers.kindFilter')}>{(['', 'company', 'person'] as const).map((item) => <button key={item || 'all'} type="button" aria-pressed={kind === item} onClick={() => setKindFilter(item)} className={`h-8 rounded px-3 text-sm ${kind === item ? 'bg-bambu-green text-black' : 'text-bambu-gray hover:text-white'}`}>{item ? t(`orders.customerEditor.${item}`) : t('common.all')}</button>)}</div>
          </div>

          {customersQuery.isPending ? <Loading label={t('orders.customers.loading')} /> : customersQuery.isError ? (
            <State icon={<AlertTriangle className="h-5 w-5" />} text={t('orders.customers.error')} action={<Button size="sm" variant="secondary" onClick={() => customersQuery.refetch()}>{t('common.retry')}</Button>} />
          ) : page === undefined ? <Loading label={t('orders.customers.loading')} /> : page.items.length === 0 ? <State text={search || status || kind ? t('orders.customers.emptyFiltered') : t('orders.customers.empty')} /> : (
            <>
              <div className="overflow-x-auto rounded-md border border-bambu-dark-tertiary">
                <table className="w-full min-w-[940px] table-fixed text-sm">
                  <thead className="bg-bambu-dark text-left text-xs uppercase text-bambu-gray"><tr><Th width="w-28">{t('orders.customers.number')}</Th><Th width="w-52">{t('orders.customers.name')}</Th><Th width="w-52">{t('orders.customers.primaryContact')}</Th><Th width="w-36">{t('orders.customers.billingAddress')}</Th><Th width="w-24">{t('common.status')}</Th><Th>{t('orders.customerEditor.tags')}</Th><Th width="w-32" align="text-right">{t('orders.customers.actions')}</Th></tr></thead>
                  <tbody>{page.items.map((customer) => <tr key={customer.id} className="border-t border-bambu-dark-tertiary text-white hover:bg-bambu-dark/50">
                    <Td>{customer.account_number || '-'}</Td><Td><strong>{customer.display_name}</strong><span className="block text-xs text-bambu-gray">{t(`orders.customerEditor.${customer.kind}`)}</span></Td>
                    <Td>{customer.primary_contact_name || '-'}{customer.primary_contact_email && <span className="block truncate text-xs text-bambu-gray">{customer.primary_contact_email}</span>}</Td>
                    <Td>{customer.billing_city ? `${customer.billing_city}${customer.billing_country_code ? `, ${customer.billing_country_code}` : ''}` : '-'}</Td>
                    <Td>{t(`orders.status.${customer.status}`)}</Td><Td><div className="flex flex-wrap gap-1">{customer.tags.map((tag) => <span key={tag} className="rounded bg-bambu-dark px-1.5 py-0.5 text-xs text-bambu-gray-light">{tag}</span>)}</div></Td>
                    <Td><div className="flex justify-end gap-1"><IconButton label={t('orders.customers.viewAria', { name: customer.display_name })} title={t('orders.customers.view')} onClick={() => openDetails(customer.id)}><Eye className="h-4 w-4" /></IconButton>{canManage && <><IconButton label={t('orders.customers.editAria', { name: customer.display_name })} title={t('orders.customers.editCustomer')} onClick={() => openEditor(customer.id)}><Pencil className="h-4 w-4" /></IconButton><IconButton danger label={t('orders.customers.deleteAria', { name: customer.display_name })} title={t('orders.customers.deleteCustomer')} onClick={() => openDelete({ id: customer.id, name: customer.display_name })}><Trash2 className="h-4 w-4" /></IconButton></>}</div></Td>
                  </tr>)}</tbody>
                </table>
              </div>
              <div className="flex items-center justify-end gap-3 text-sm text-bambu-gray"><span>{t('orders.customers.pagination', { start: pageStart, end: pageEnd, total: page.total })}</span><IconButton label={t('orders.customers.previous')} title={t('orders.customers.previous')} disabled={page.offset <= 0} onClick={() => setOffset(Math.max(0, page.offset - page.limit))}><ChevronLeft className="h-4 w-4" /></IconButton><IconButton label={t('orders.customers.next')} title={t('orders.customers.next')} disabled={page.offset + page.limit >= page.total} onClick={() => setOffset(page.offset + page.limit)}><ChevronRight className="h-4 w-4" /></IconButton></div>
            </>
          )}
        </>
      )}

      {detailsId !== null && !detailsQuery.data && detailsQuery.isPending && <ModalLoading label={t('orders.customerDetails.loading')} />}
      {detailsId !== null && !detailsQuery.data && detailsQuery.isError && <ModalQueryError title={t('orders.customerDetails.loadError')} onClose={() => setDetailsId(null)} onRetry={() => detailsQuery.refetch()} />}
      {detailsId !== null && detailsQuery.data && selectedProfileId !== undefined && <CustomerDetailsModal customer={detailsQuery.data} profiles={profiles} selectedProfileId={selectedProfileId} canManage={canManage} loadError={detailsQuery.isRefetchError && detailsQuery.error instanceof Error ? detailsQuery.error : null} onRetryLoad={() => detailsQuery.refetch()} onClose={() => setDetailsId(null)} onEdit={() => openEditor(detailsId)} onDelete={() => openDelete({ id: detailsQuery.data.id, name: detailsQuery.data.display_name })} />}
      {editor === 'create' && selectedProfileId !== undefined && <CustomerEditorModal customer={null} profiles={activeProfiles} selectedProfileId={selectedProfileId} isSubmitting={mutationPending} onClose={closeEditor} onSubmit={submitEditor} onReloadCurrent={reloadCurrent} />}
      {editorId !== null && !editorQuery.data && editorQuery.isPending && <ModalLoading label={t('orders.customerEditor.loading')} />}
      {editorId !== null && !editorQuery.data && editorQuery.isError && <ModalQueryError title={t('orders.customerEditor.loadError')} onClose={closeEditor} onRetry={() => editorQuery.refetch()} />}
      {editorId !== null && editorQuery.data && selectedProfileId !== undefined && <CustomerEditorModal customer={editorQuery.data} profiles={activeProfiles} selectedProfileId={selectedProfileId} isSubmitting={mutationPending} loadError={editorQuery.isRefetchError && editorQuery.error instanceof Error ? editorQuery.error : null} onRetryLoad={() => editorQuery.refetch()} onClose={closeEditor} onSubmit={submitEditor} onReloadCurrent={reloadCurrent} onReloadAccepted={acceptReload} />}
      {deleteTarget && <ConfirmModal title={t('orders.customers.deleteTitle', { name: deleteTarget.name })} message={t('orders.customers.deleteConfirm')} confirmText={t('orders.customers.deleteCustomer')} variant="danger" isLoading={deleteMutation.isPending} onCancel={() => { deleteMutation.reset(); setDeleteTarget(null); }} onConfirm={() => deleteMutation.mutate(deleteTarget.id)}>{deleteMutation.isError && <div role="alert" className="space-y-3 border-t border-red-500/30 pt-3 text-sm text-red-200"><p>{localizedOrderError(deleteMutation.error, t, i18n.language, t('orders.customers.deleteError'))}</p><div className="flex gap-2"><Button size="sm" variant="secondary" onClick={() => deleteMutation.mutate(deleteTarget.id)}>{t('common.retry')}</Button><Button size="sm" variant="ghost" onClick={() => { deleteMutation.reset(); setDeleteTarget(null); }}>{t('common.dismiss')}</Button></div></div>}</ConfirmModal>}
    </div>
  );
}

function Loading({ label }: { label: string }) { const accessibleLabel = label.replace(/\.\.\.$/, ''); return <div aria-label={accessibleLabel} className="space-y-2 py-6"><div className="h-10 animate-pulse rounded bg-bambu-dark-tertiary" /><div className="h-10 animate-pulse rounded bg-bambu-dark-tertiary/70" /><span className="sr-only">{accessibleLabel}</span></div>; }
function State({ icon, text, action }: { icon?: React.ReactNode; text: string; action?: React.ReactNode }) { return <div className="flex min-h-28 flex-col items-center justify-center gap-3 border-y border-bambu-dark-tertiary py-6 text-center text-sm text-bambu-gray"><div className="flex items-center gap-2">{icon}{text}</div>{action}</div>; }
function ModalLoading({ label }: { label: string }) {
  const accessibleLabel = label.replace(/\.\.\.$/, '');
  const { dialogRef, onKeyDown } = useModalFocusLifecycle<HTMLDivElement>({ onClose: () => {}, canClose: false });
  return <div role="presentation" className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3"><div ref={dialogRef} onKeyDown={onKeyDown} role="dialog" aria-modal="true" aria-label={accessibleLabel} tabIndex={-1} className="w-full max-w-md rounded-md border border-bambu-dark-tertiary bg-bambu-dark-secondary p-5"><div role="status" aria-live="polite" aria-label={accessibleLabel}><Loading label={label} /></div></div></div>;
}
function ModalQueryError({ title, onClose, onRetry }: { title: string; onClose: () => void; onRetry: () => void }) {
  const { t } = useTranslation();
  const { dialogRef, onKeyDown } = useModalFocusLifecycle<HTMLDivElement>({ onClose });
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3"><div ref={dialogRef} onKeyDown={onKeyDown} role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-md rounded-md border border-bambu-dark-tertiary bg-bambu-dark-secondary p-5"><div className="flex items-center gap-2 text-red-200"><AlertTriangle className="h-5 w-5" /><p>{title}</p></div><div className="mt-4 flex justify-end gap-2"><Button size="sm" variant="secondary" onClick={onRetry}>{t('common.retry')}</Button><Button size="sm" variant="ghost" onClick={onClose}>{t('common.close')}</Button></div></div></div>;
}
function Th({ children, width = '', align = '' }: { children: React.ReactNode; width?: string; align?: string }) { return <th className={`${width} ${align} px-3 py-2 font-medium`}>{children}</th>; }
function Td({ children }: { children: React.ReactNode }) { return <td className="px-3 py-3 align-top">{children}</td>; }
function IconButton({ label, title, danger = false, disabled = false, onClick, children }: { label: string; title: string; danger?: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode }) { return <button type="button" aria-label={label} title={title} disabled={disabled} onClick={onClick} className={`rounded p-2 disabled:cursor-not-allowed disabled:opacity-40 ${danger ? 'text-bambu-gray hover:bg-red-500/10 hover:text-red-300' : 'text-bambu-gray hover:bg-bambu-dark-tertiary hover:text-white'}`}>{children}</button>; }
