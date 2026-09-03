import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { smallPartsApi } from '../../api/smallParts';
import { warehouseArticlesApi, type WarehouseArticle, type WarehouseArticleInput, type WarehouseArticleKind, type WarehouseStockSource } from '../../api/client/warehouse-articles';
import { Button, Modal, NumberField, Select, TextArea, TextField } from '../ui';
import { useWarehouseCopy } from './warehouseGoodsCopy';

function FormSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="space-y-4" aria-label={title}>
    <div className="flex items-center gap-3">
      <h3 className="shrink-0 text-sm font-semibold text-white">{title}</h3>
      <div className="h-px flex-1 bg-bambu-dark-tertiary" />
    </div>
    {children}
  </section>;
}

export function WarehouseArticleEditor({ article, onClose }: { article: WarehouseArticle | null; onClose: () => void }) {
  const copy = useWarehouseCopy();
  const cache = useQueryClient();
  const [reviewedVersion] = useState(article?.version);
  const [form, setForm] = useState<WarehouseArticleInput>(() => ({
    sku: article?.sku ?? '', name: article?.name ?? '', description: article?.description ?? '',
    kind: article?.kind ?? 'finished', unit_code: article?.unit_code ?? '',
    stock_source: article?.stock_source ?? 'own', small_part_id: article?.small_part_id ?? null,
    sale_price: article?.sale_price ?? '0', tax_rate: article?.tax_rate ?? '19',
    unit_cost: article?.unit_cost ?? '0', minimum_stock: article?.minimum_stock ?? '0',
    project_id: article?.project_id ?? null, calculation_revision_id: article?.calculation_revision_id ?? null,
  }));
  const [materialSearch, setMaterialSearch] = useState('');
  const units = useQuery({ queryKey: ['small-parts', 'units'], queryFn: smallPartsApi.units.list });
  const materials = useQuery({ queryKey: ['warehouse-material-options', materialSearch], queryFn: () => smallPartsApi.search(materialSearch), enabled: form.stock_source === 'material' });
  const mutation = useMutation({
    mutationFn: () => article ? warehouseArticlesApi.update(article.id, { ...form, version: reviewedVersion! }) : warehouseArticlesApi.create(form),
    onSuccess: async () => { await cache.invalidateQueries({ queryKey: ['warehouse-articles'] }); onClose(); },
  });
  function field<K extends keyof WarehouseArticleInput>(key: K, value: WarehouseArticleInput[K]) {
    setForm((previous) => ({ ...previous, [key]: value }));
  }
  function kind(value: WarehouseArticleKind) {
    setForm((previous) => ({ ...previous, kind: value,
      stock_source: value === 'service' ? 'none' : previous.stock_source === 'none' ? 'own' : previous.stock_source,
      small_part_id: value === 'service' ? null : previous.small_part_id,
      minimum_stock: value === 'service' ? '0' : previous.minimum_stock,
      project_id: value === 'finished' ? previous.project_id : null,
      calculation_revision_id: value === 'finished' ? previous.calculation_revision_id : null,
    }));
  }
  const frozen = article?.has_history ?? false;
  const moneyFields = [['sale_price', copy.sale], ['unit_cost', copy.cost], ['tax_rate', copy.tax]] as const;
  return <Modal open onClose={onClose} closeDisabled={mutation.isPending} title={article ? copy.edit : copy.create} closeLabel={copy.close} className="max-w-3xl">
    <form className="space-y-6 text-sm" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
      <FormSection title={copy.articleDetails}>
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label={copy.sku} required maxLength={120} value={form.sku} onValueChange={(value) => field('sku', value)} />
          <TextField label={copy.name} required maxLength={255} value={form.name} onValueChange={(value) => field('name', value)} />
          <Select<WarehouseArticleKind> label={copy.kind} value={form.kind} onValueChange={kind} disabled={frozen} options={(['finished', 'trade', 'service'] as const).map((value) => ({ value, label: copy[value] }))} />
          <div className="sm:col-span-2">
            <TextArea label={copy.description} className="min-h-20" maxLength={20000} value={form.description ?? ''} onValueChange={(value) => field('description', value)} />
          </div>
        </div>
      </FormSection>

      <FormSection title={copy.stock}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label={copy.unit} required value={form.unit_code} disabled={frozen || form.stock_source === 'material'} onValueChange={(value) => field('unit_code', value)} options={(units.data ?? []).filter((unit) => unit.is_active || unit.code === form.unit_code).map((unit) => ({ value: unit.code, label: `${unit.label} (${unit.code})` }))} placeholder={copy.choose} />
          <Select<WarehouseStockSource> label={copy.source} value={form.stock_source ?? 'own'} disabled={frozen || form.kind === 'service'} onValueChange={(value) => setForm((previous) => ({ ...previous, stock_source: value, small_part_id: null }))} options={(form.kind === 'service' ? ['none'] as const : ['own', 'material'] as const).map((value) => ({ value, label: copy[value] }))} />
          <NumberField label={copy.minimum} min="0" step="any" required value={form.minimum_stock ?? '0'} disabled={form.kind === 'service'} onValueChange={(value) => field('minimum_stock', value)} />
        </div>
        {units.isLoading && <p role="status" className="text-bambu-gray">{copy.loading}</p>}
        {units.isError && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-950/50 p-3 text-red-300">{copy.error}<Button type="button" size="sm" variant="secondary" onClick={() => void units.refetch()}>{copy.retry}</Button></div>}
        {units.isSuccess && !units.data.some((unit) => unit.is_active) && <p role="alert" className="text-amber-300">{copy.noUnits}</p>}
        {frozen && <p className="text-bambu-gray">{copy.frozen}</p>}
        {form.stock_source === 'material' && <div className="space-y-3 rounded-lg border border-bambu-dark-tertiary p-4">
          <p className="text-bambu-gray">{copy.materialNote}</p>
          {!frozen && <>
            <TextField label={copy.materialSearch} value={materialSearch} onValueChange={setMaterialSearch} />
            <Select label={copy.material} value={form.small_part_id ?? 0} placeholder={copy.choose} onValueChange={(id) => {
              const material = materials.data?.find((item) => item.id === id);
              if (material) setForm((previous) => ({ ...previous, small_part_id: id, unit_code: material.unit_code }));
            }} options={(materials.data ?? []).map((item) => ({ value: item.id, label: `${item.sku} · ${item.name} (${item.unit_code})` }))} />
            {materials.isError && <p role="alert" className="text-red-300">{copy.error}</p>}
          </>}
          {form.small_part_id && <p className="text-bambu-gray-light">#{form.small_part_id} · {form.unit_code}</p>}
        </div>}
      </FormSection>

      <FormSection title={copy.prices}>
        <div className="grid gap-4 sm:grid-cols-2">
          {moneyFields.map(([key, label]) => <NumberField key={key} label={label} min="0" max={key === 'tax_rate' ? '100' : undefined} step="any" required value={form[key] ?? '0'} onValueChange={(value) => field(key, value)} />)}
        </div>
      </FormSection>
      {form.kind === 'finished' && <FormSection title={copy.projectLinks}>
        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField label={copy.project} min="1" step="1" value={form.project_id?.toString() ?? ''} onValueChange={(value) => field('project_id', value ? Number(value) : null)} />
          <NumberField label={copy.revision} min="1" step="1" value={form.calculation_revision_id?.toString() ?? ''} onValueChange={(value) => field('calculation_revision_id', value ? Number(value) : null)} />
        </div>
      </FormSection>}
      {mutation.isError && <p role="alert" className="rounded-lg bg-red-950/50 p-3 text-red-300">{mutation.error.message}</p>}
      <div className="sticky bottom-0 flex justify-end gap-3 border-t border-bambu-dark-tertiary bg-bambu-dark-secondary pt-4">
        <Button type="button" variant="secondary" disabled={mutation.isPending} onClick={onClose}>{copy.cancel}</Button>
        <Button type="submit" loading={mutation.isPending} disabled={!form.unit_code || !form.sku.trim() || !form.name.trim() || (form.stock_source === 'material' && !form.small_part_id)}>{copy.save}</Button>
      </div>
    </form>
  </Modal>;
}
