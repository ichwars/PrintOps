import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { smallPartsApi } from '../../../api/smallParts';
import { Button, Select, TextField } from '../../ui';
import { lexwareError, useLexwareMessages } from './lexwareMessages';
import { articleSetupOptions, type ArticleSetupDraft } from './lexwareState';

export function LexwareArticleSetup({ draft, onChange, sourceUnit, sourceType, disabled }: {
  draft: ArticleSetupDraft;
  onChange: (draft: ArticleSetupDraft) => void;
  sourceUnit: unknown;
  sourceType: unknown;
  disabled: boolean;
}) {
  const { text } = useLexwareMessages();
  const [input, setInput] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [selectedMaterial, setSelectedMaterial] = useState<{ value: number; label: string } | null>(null);
  const units = useQuery({ queryKey: ['small-parts', 'units'], queryFn: smallPartsApi.units.list, staleTime: 60_000, retry: false });
  const materials = useQuery({
    queryKey: ['lexware', 'material-targets', search, offset],
    queryFn: () => smallPartsApi.list({ q: search, active: true, limit: 25, offset }),
    enabled: draft.stock_source === 'material', staleTime: 30_000, retry: false,
  });
  const materialOptions = materials.data?.items.map((row) => ({ value: row.id, label: `${row.sku} — ${row.name} (${row.unit_code})`, disabled: row.unit_code !== draft.unit_code })) ?? [];

  return (
    <fieldset className="space-y-3 rounded-lg border border-bambu-dark-tertiary p-4" disabled={disabled}>
      <legend className="px-2 font-medium">{text.articleOptions}</legend>
      <p className="text-sm text-bambu-gray">{text.articleHelp}</p>
      <p className="text-sm">{text.sourceUnit}: {typeof sourceUnit === 'string' && sourceUnit ? sourceUnit : '—'}</p>
      <TextField label={text.sku} value={draft.sku} onValueChange={(sku) => onChange({ ...draft, sku })} required />
      <Select label={text.kind} value={draft.kind} options={[
        { value: '', label: text.choose }, { value: 'finished', label: text.finished, disabled: sourceType !== 'PRODUCT' },
        { value: 'trade', label: text.trade, disabled: sourceType !== 'PRODUCT' }, { value: 'service', label: text.service, disabled: sourceType !== 'SERVICE' },
      ]} onValueChange={(kind) => onChange({ ...draft, kind: kind as ArticleSetupDraft['kind'], stock_source: kind === 'service' ? 'none' : '', small_part_id: null })} />
      {units.isPending && <p role="status">{text.loading}</p>}
      {units.isError && <div role="alert"><p>{lexwareError(units.error, text)}</p><Button type="button" variant="secondary" onClick={() => void units.refetch()}>{text.retry}</Button></div>}
      <Select label={text.unit} value={draft.unit_code} disabled={units.isPending || units.isError}
        options={[{ value: '', label: text.choose }, ...(units.data ?? []).filter((unit) => unit.is_active).map((unit) => ({ value: unit.code, label: `${unit.label} (${unit.code})` }))]}
        onValueChange={(unit_code) => { setSelectedMaterial(null); onChange({ ...draft, unit_code, small_part_id: null }); }} />
      <Select label={text.stockSource} value={draft.stock_source} disabled={!draft.kind || draft.kind === 'service'}
        options={draft.kind === 'service' ? [{ value: 'none', label: text.none }] : [
          { value: '', label: text.choose }, { value: 'own', label: text.own }, { value: 'material', label: text.material },
        ]} onValueChange={(stock_source) => onChange({ ...draft, stock_source: stock_source as ArticleSetupDraft['stock_source'], small_part_id: null })} />
      {draft.stock_source === 'material' && <>
        <p className="text-sm text-bambu-gray">{text.materialHelp}</p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1"><TextField label={text.materialSearch} value={input} onValueChange={setInput} /></div>
          <Button type="button" variant="secondary" onClick={() => { setSearch(input); setOffset(0); }}>{text.materialSearch}</Button>
        </div>
        {materials.isPending && <p role="status">{text.loading}</p>}
        {materials.isError && <div role="alert"><p>{lexwareError(materials.error, text)}</p><Button type="button" variant="secondary" onClick={() => void materials.refetch()}>{text.retry}</Button></div>}
        <Select label={text.materialTarget} value={draft.small_part_id ?? 0} options={[
          { value: 0, label: text.choose },
          ...(selectedMaterial && selectedMaterial.value === draft.small_part_id && !materialOptions.some((item) => item.value === selectedMaterial.value) ? [selectedMaterial] : []),
          ...materialOptions,
        ]} onValueChange={(id) => { setSelectedMaterial(materialOptions.find((item) => item.value === id) ?? null); onChange({ ...draft, small_part_id: id || null }); }} />
        {materials.isSuccess && materials.data.items.length === 0 && <p>{text.noTargets}</p>}
        <div className="flex gap-2">
          <Button type="button" variant="ghost" disabled={!offset || materials.isFetching} onClick={() => setOffset(Math.max(0, offset - 25))}>{text.previous}</Button>
          <Button type="button" variant="ghost" disabled={materials.isFetching || offset + 25 >= (materials.data?.total ?? 0)} onClick={() => setOffset(offset + 25)}>{text.next}</Button>
        </div>
      </>}
      {!articleSetupOptions(draft) && <p className="text-sm text-amber-300">{text.missingOptions}</p>}
    </fieldset>
  );
}
