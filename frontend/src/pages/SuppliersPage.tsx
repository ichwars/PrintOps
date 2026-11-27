import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Search, Trash2, Truck, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router';

import { suppliersApi, type Supplier, type SupplierInput } from '../api/procurement';
import { Card, CardContent } from '../components/Card';
import { SupplierEditor } from '../components/warehouse/SupplierEditor';
import { Button, Select, TextField } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';

type ActiveFilter = 'active' | 'inactive' | 'all';

interface EditorState {
  supplier: Supplier | null;
  canEdit: boolean;
}

const SUPPLIER_PAGE_SIZE = 50;

function isActiveFilter(value: string | null): value is ActiveFilter {
  return value === 'active' || value === 'inactive' || value === 'all';
}

function parseOffset(value: string | null): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 0;
}

export function SuppliersPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { hasPermission, loading: authLoading } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchInput, setSearchInput] = useState(() => searchParams.get('q') ?? '');
  const [search, setSearch] = useState(() => (searchParams.get('q') ?? '').trim());
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>(() => {
    const activeParam = searchParams.get('active');
    return isActiveFilter(activeParam) ? activeParam : 'active';
  });
  const [offset, setOffset] = useState(() => parseOffset(searchParams.get('offset')));
  const supplierSearchKey = searchParams.toString();
  const supplierUrlState = useMemo(() => {
    const params = new URLSearchParams(supplierSearchKey);
    const activeParam = params.get('active');
    return {
      query: params.get('q') ?? '',
      activeFilter: isActiveFilter(activeParam) ? activeParam : 'active',
      offset: parseOffset(params.get('offset')),
    };
  }, [supplierSearchKey]);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const canRead = hasPermission('inventory:read');
  const canCreate = hasPermission('inventory:create');
  const canUpdate = hasPermission('inventory:update');
  const canDelete = hasPermission('inventory:delete');
  const active = activeFilter === 'all' ? undefined : activeFilter === 'active';

  const updateSupplierParams = useCallback(
    (changes: { q?: string; active?: ActiveFilter; offset?: number }) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (changes.q !== undefined) {
            const trimmedQuery = changes.q.trim();
            if (trimmedQuery) {
              next.set('q', trimmedQuery);
            } else {
              next.delete('q');
            }
          }
          if (changes.active !== undefined) {
            if (changes.active === 'active') {
              next.delete('active');
            } else {
              next.set('active', changes.active);
            }
          }
          if (changes.offset !== undefined) {
            if (changes.offset > 0) {
              next.set('offset', String(changes.offset));
            } else {
              next.delete('offset');
            }
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  // Debounce the search box: only the trimmed value becomes the query
  // (and is mirrored into the URL) 300ms after the last keystroke.
  useEffect(() => {
    const nextSearch = searchInput.trim();
    if (nextSearch === search) return;
    const timer = window.setTimeout(() => {
      setSearch(nextSearch);
      setOffset(0);
      updateSupplierParams({ q: nextSearch, offset: 0 });
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput, search, updateSupplierParams]);

  const suppliers = useQuery({
    queryKey: ['suppliers', { q: search, active, limit: SUPPLIER_PAGE_SIZE, offset }],
    queryFn: () => suppliersApi.list({ q: search || undefined, active, limit: SUPPLIER_PAGE_SIZE, offset }),
    enabled: !authLoading && canRead,
    placeholderData: keepPreviousData,
  });
  const page = suppliers.data;
  const items = page?.items ?? [];

  // Follow external URL changes (back/forward navigation). The search box is
  // only reset when the URL query diverges from the applied search, so a
  // pending debounced edit is never wiped by an unrelated URL update.
  useEffect(() => {
    const urlQuery = supplierUrlState.query.trim();
    if (urlQuery !== search) {
      setSearch(urlQuery);
      setSearchInput(supplierUrlState.query);
    }
    setActiveFilter((current) => (
      current === supplierUrlState.activeFilter ? current : supplierUrlState.activeFilter
    ));
    setOffset((current) => (
      current === supplierUrlState.offset ? current : supplierUrlState.offset
    ));
  }, [supplierUrlState, search]);

  // Clamp the offset when the current page ran empty (e.g. after deletions).
  useEffect(() => {
    if (!page || page.items.length > 0 || page.offset <= 0 || page.total <= 0) return;
    const lastValidOffset = Math.max(0, Math.floor((page.total - 1) / page.limit) * page.limit);
    if (lastValidOffset !== page.offset) {
      setOffset(lastValidOffset);
      updateSupplierParams({ offset: lastValidOffset });
    }
  }, [page, updateSupplierParams]);

  const handleQueryChange = (value: string) => {
    setSearchInput(value);
  };

  const handleActiveFilterChange = (value: ActiveFilter) => {
    setActiveFilter(value);
    setOffset(0);
    updateSupplierParams({ active: value, offset: 0 });
  };

  const goToOffset = (nextOffset: number) => {
    setOffset(nextOffset);
    updateSupplierParams({ offset: nextOffset });
  };

  const refresh = () => queryClient.invalidateQueries({ queryKey: ['suppliers'] });
  const save = async (input: SupplierInput) => {
    if (editor?.supplier) {
      if (!canUpdate) return;
      await suppliersApi.update(editor.supplier.id, input);
    } else {
      if (!canCreate) return;
      await suppliersApi.create(input);
    }
    await refresh();
  };
  const remove = async () => {
    if (!editor?.supplier || !canDelete) return;
    await suppliersApi.remove(editor.supplier.id);
    await refresh();
  };

  if (!authLoading && !canRead) {
    return <div className="p-4 text-bambu-gray md:p-8" role="alert">{t('suppliers.errors.noReadPermission')}</div>;
  }

  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold text-white"><Truck className="h-7 w-7 text-bambu-green" />{t('suppliers.title')}</h1>
          <p className="mt-1 text-bambu-gray">{t('suppliers.subtitle')}</p>
        </div>
        {canCreate ? <Button type="button" onClick={() => setEditor({ supplier: null, canEdit: true })}><Plus aria-hidden="true" className="h-4 w-4" />{t('suppliers.actions.create')}</Button> : null}
      </header>

      <Card>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
            <div className="relative"><Search aria-hidden="true" className="pointer-events-none absolute left-3 top-[34px] h-4 w-4 text-bambu-gray" /><TextField type="search" label={t('suppliers.searchLabel')} value={searchInput} onValueChange={handleQueryChange} placeholder={t('suppliers.searchPlaceholder')} className={`pl-9 ${searchInput ? 'pr-9' : ''}`} />{searchInput ? <button type="button" onClick={() => setSearchInput('')} className="absolute right-2 top-[34px] flex h-[38px] items-center text-bambu-gray hover:text-white" aria-label={t('suppliers.clearSearch')}><X aria-hidden="true" className="h-4 w-4" /></button> : null}</div>
            <Select value={activeFilter} label={t('suppliers.activeFilter')} onValueChange={(value) => handleActiveFilterChange(value as ActiveFilter)} options={[
              { value: 'active', label: t('suppliers.filters.active') },
              { value: 'inactive', label: t('suppliers.filters.inactive') },
              { value: 'all', label: t('suppliers.filters.all') },
            ]} />
          </div>

          {suppliers.isLoading ? <p className="py-10 text-center text-bambu-gray">{t('suppliers.loading')}</p> : null}
          {suppliers.isError ? <p role="alert" className="rounded-lg border border-red-500/50 bg-red-950/30 px-3 py-2 text-sm text-red-300">{t('suppliers.errors.load')}</p> : null}
          {!suppliers.isLoading && !suppliers.isError && items.length === 0 ? <p className="py-10 text-center text-bambu-gray">{search ? t('suppliers.emptyFiltered') : t('suppliers.empty')}</p> : null}
          <div className="grid gap-3 xl:grid-cols-2">
            {items.map((supplier) => (
              <article key={supplier.id} className="rounded-xl border border-bambu-dark-tertiary bg-bambu-dark p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold text-white">{supplier.name}</h2>{!supplier.is_active ? <span className="rounded-full bg-bambu-dark-tertiary px-2 py-0.5 text-xs text-bambu-gray-light">{t('suppliers.filters.inactive')}</span> : null}</div>
                    <p className="mt-1 text-sm text-bambu-gray">{[supplier.contact_name, supplier.email, supplier.city].filter(Boolean).join(' · ') || t('suppliers.noContact')}</p>
                    <p className="mt-3 text-sm text-bambu-gray-light">{t('suppliers.leadTime', { count: supplier.default_lead_time_days })}</p>
                  </div>
                  <div className="flex items-center gap-1">
                    {canUpdate ? <Button type="button" variant="ghost" size="sm" aria-label={t('suppliers.actions.edit', { name: supplier.name })} onClick={() => setEditor({ supplier, canEdit: true })}><Pencil aria-hidden="true" className="h-4 w-4" /></Button> : null}
                    {canDelete ? <Button type="button" variant="ghost" size="sm" aria-label={`${t('suppliers.actions.delete')}: ${supplier.name}`} onClick={() => setEditor({ supplier, canEdit: false })}><Trash2 aria-hidden="true" className="h-4 w-4 text-red-400" /></Button> : null}
                  </div>
                </div>
              </article>
            ))}
          </div>

          {page ? (
            <div className="flex flex-wrap items-center justify-end gap-3 text-sm text-bambu-gray">
              <span className="tabular-nums">{t('suppliers.pagination', { start: page.total > 0 ? page.offset + 1 : 0, end: Math.min(page.offset + page.limit, page.total), total: page.total })}</span>
              <div className="flex gap-2">
                <Button type="button" size="sm" variant="secondary" disabled={page.offset <= 0} onClick={() => goToOffset(Math.max(0, page.offset - page.limit))}>{t('suppliers.previous')}</Button>
                <Button type="button" size="sm" variant="secondary" disabled={page.offset + page.limit >= page.total} onClick={() => goToOffset(page.offset + page.limit)}>{t('suppliers.next')}</Button>
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      {editor ? <SupplierEditor supplier={editor.supplier} onClose={() => setEditor(null)} onSubmit={save} onDelete={editor.supplier && canDelete ? remove : undefined} canEdit={editor.canEdit && (editor.supplier ? canUpdate : canCreate)} canDelete={canDelete} /> : null}
    </div>
  );
}
