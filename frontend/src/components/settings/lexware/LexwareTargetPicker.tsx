import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../../api/client';
import type { LexwareResourceKind } from '../../../api/client/lexware';
import { warehouseArticlesApi } from '../../../api/client/warehouse-articles';
import { Button, Select, TextField } from '../../ui';
import { lexwareError, useLexwareMessages } from './lexwareMessages';

interface Props {
  kind: LexwareResourceKind;
  profileId: number;
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
}

export function LexwareTargetPicker({ kind, profileId, value, onChange, disabled }: Props) {
  const { text } = useLexwareMessages();
  const [input, setInput] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const [selectedName, setSelectedName] = useState('');
  const targets = useQuery({
    queryKey: ['lexware', 'targets', kind, profileId, search, offset],
    queryFn: async () => {
      if (kind === 'contacts') {
        const page = await api.getCustomers({ businessProfileId: profileId, search, limit: 25, offset });
        return { total: page.total, items: page.items.map((row) => ({ value: row.id, label: `${row.account_number} — ${row.display_name}` })) };
      }
      const page = await warehouseArticlesApi.list({ q: search, limit: 25, offset });
      return { total: page.total, items: page.items.map((row) => ({ value: row.id, label: `${row.sku} — ${row.name}` })) };
    },
    staleTime: 30_000, retry: false,
  });
  const options = targets.data?.items ?? [];
  return (
    <div className="space-y-3">
      <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => { event.preventDefault(); setSearch(input); setOffset(0); }}>
        <div className="min-w-48 flex-1"><TextField label={text.targetSearch} value={input} onValueChange={setInput} disabled={disabled} /></div>
        <Button variant="secondary" disabled={disabled} type="submit">{text.targetSearch}</Button>
      </form>
      {targets.isPending && <p role="status">{text.loading}</p>}
      {targets.isError && <div role="alert"><p>{lexwareError(targets.error, text)}</p><Button variant="secondary" onClick={() => void targets.refetch()}>{text.retry}</Button></div>}
      <Select label={text.target} value={value ?? 0} disabled={disabled}
        options={[{ value: 0, label: text.createNew }, ...(value && !options.some((option) => option.value === value) ? [{ value, label: selectedName || `#${value}` }] : []), ...options]}
        onValueChange={(id) => { setSelectedName(options.find((option) => option.value === id)?.label ?? ''); onChange(id || null); }} />
      <p className="text-xs text-bambu-gray">{text.targetHelp}</p>
      {targets.isSuccess && targets.data.items.length === 0 && <p>{text.noTargets}</p>}
      <div className="flex gap-2">
        <Button variant="ghost" disabled={disabled || offset === 0 || targets.isFetching} onClick={() => setOffset(Math.max(0, offset - 25))}>{text.previous}</Button>
        <Button variant="ghost" disabled={disabled || targets.isFetching || offset + 25 >= (targets.data?.total ?? 0)} onClick={() => setOffset(offset + 25)}>{text.next}</Button>
      </div>
    </div>
  );
}
