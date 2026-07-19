import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Pencil, Plus, Search, Trash2, Truck } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

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

async function loadAllSuppliers(q: string, active: boolean | undefined): Promise<Supplier[]> {
  const items: Supplier[] = [];
  let offset = 0;
  while (true) {
    const page = await suppliersApi.list({
      q: q || undefined,
      active,
      limit: SUPPLIER_PAGE_SIZE,
      offset,
    });
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
    offset = page.offset + page.items.length;
  }
}

export function SuppliersPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { hasPermission, loading: authLoading } = useAuth();
  const [query, setQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('active');
  const [editor, setEditor] = useState<EditorState | null>(null);
  const canRead = hasPermission('inventory:read');
  const canCreate = hasPermission('inventory:create');
  const canUpdate = hasPermission('inventory:update');
  const canDelete = hasPermission('inventory:delete');
  const active = activeFilter === 'all' ? undefined : activeFilter === 'active';
  const suppliers = useQuery({
    queryKey: ['suppliers', { q: query, active }],
    queryFn: () => loadAllSuppliers(query, active),
    enabled: !authLoading && canRead,
  });
  const items = suppliers.data ?? [];

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
            <div className="relative"><Search aria-hidden="true" className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-bambu-gray" /><TextField type="search" aria-label={t('suppliers.searchLabel')} value={query} onValueChange={setQuery} placeholder={t('suppliers.searchPlaceholder')} className="pl-9" /></div>
            <Select value={activeFilter} label={t('suppliers.activeFilter')} onValueChange={setActiveFilter} options={[
              { value: 'active', label: t('suppliers.filters.active') },
              { value: 'inactive', label: t('suppliers.filters.inactive') },
              { value: 'all', label: t('suppliers.filters.all') },
            ]} />
          </div>

          {suppliers.isLoading ? <p className="py-10 text-center text-bambu-gray">{t('suppliers.loading')}</p> : null}
          {suppliers.isError ? <p role="alert" className="rounded-lg border border-red-500/50 bg-red-950/30 px-3 py-2 text-sm text-red-300">{t('suppliers.errors.load')}</p> : null}
          {!suppliers.isLoading && !suppliers.isError && items.length === 0 ? <p className="py-10 text-center text-bambu-gray">{t('suppliers.empty')}</p> : null}
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
        </CardContent>
      </Card>

      {editor ? <SupplierEditor supplier={editor.supplier} onClose={() => setEditor(null)} onSubmit={save} onDelete={editor.supplier && canDelete ? remove : undefined} canEdit={editor.canEdit && (editor.supplier ? canUpdate : canCreate)} canDelete={canDelete} /> : null}
    </div>
  );
}
