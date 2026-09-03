import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Boxes, Plus, Search } from 'lucide-react';
import { warehouseArticlesApi, type WarehouseArticleKind, type WarehouseStockSource } from '../api/client/warehouse-articles';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent } from '../components/Card';
import { Button, Checkbox, Select, TextField } from '../components/ui';
import { tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../components/ui/tableStyles';
import { WarehouseArticleDetail } from '../components/warehouse/WarehouseArticleDetail';
import { WarehouseArticleEditor } from '../components/warehouse/WarehouseArticleEditor';
import { useWarehouseCopy, warehouseQuantity } from '../components/warehouse/warehouseGoodsCopy';

export function WarehouseGoodsPage() {
  const copy = useWarehouseCopy();
  const { hasPermission } = useAuth();
  const [search, setSearch] = useState('');
  const [active, setActive] = useState('active');
  const [kind, setKind] = useState<WarehouseArticleKind | ''>('');
  const [source, setSource] = useState<WarehouseStockSource | ''>('');
  const [low, setLow] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const canRead = hasPermission('inventory:read');
  const params = { q: search, active: active === 'all' ? undefined : active === 'active', kind: kind || undefined, stock_source: source || undefined, low_stock: low, offset, limit: 50 };
  const query = useQuery({ queryKey: ['warehouse-articles', params], queryFn: () => warehouseArticlesApi.list(params), enabled: canRead });
  if (!canRead) return <p role="alert" className="p-4 text-sm text-bambu-gray md:p-8">{copy.noRead}</p>;
  return (
    <div className="min-w-0 space-y-6 p-4 md:p-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold text-white">
            <Boxes aria-hidden className="h-7 w-7 shrink-0 text-bambu-green" />{copy.title}
          </h1>
          <p className="mt-1 text-bambu-gray">{copy.subtitle}</p>
        </div>
        {hasPermission('inventory:create') && <Button type="button" onClick={() => setCreating(true)}><Plus className="h-4 w-4" aria-hidden />{copy.create}</Button>}
      </header>

      <div className="space-y-3 border-y border-bambu-dark-tertiary py-3">
        <div className="grid items-end gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
          <div className="relative">
            <Search aria-hidden className="pointer-events-none absolute bottom-3 left-3 h-4 w-4 text-bambu-gray md:bottom-[11px]" />
            <TextField type="search" label={copy.search} className="pl-9" value={search} onValueChange={(value) => { setSearch(value); setOffset(0); }} />
          </div>
          <Select label={copy.active} value={active} onValueChange={(value) => { setActive(value); setOffset(0); }} options={[{ value: 'active', label: copy.active }, { value: 'archived', label: copy.archived }, { value: 'all', label: copy.all }]} />
          <Select<WarehouseArticleKind | ''> label={copy.kind} value={kind} onValueChange={(value) => { setKind(value); setOffset(0); }} options={[{ value: '', label: copy.all }, ...(['finished', 'trade', 'service'] as const).map((value) => ({ value, label: copy[value] }))]} />
          <Select<WarehouseStockSource | ''> label={copy.source} value={source} onValueChange={(value) => { setSource(value); setOffset(0); }} options={[{ value: '', label: copy.all }, ...(['own', 'material', 'none'] as const).map((value) => ({ value, label: copy[value] }))]} />
        </div>
        <Checkbox label={copy.low} checked={low} onCheckedChange={(value) => { setLow(value); setOffset(0); }} />
      </div>

      {query.isLoading && <p role="status" className="py-10 text-center text-sm text-bambu-gray">{copy.loading}</p>}
      {query.isError && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-950/50 p-3 text-sm text-red-300">{copy.error}<Button type="button" size="sm" variant="secondary" onClick={() => void query.refetch()}>{copy.retry}</Button></div>}
      {query.isSuccess && query.data.items.length === 0 && <Card><CardContent><p className="py-4 text-center text-sm text-bambu-gray">{copy.empty}</p></CardContent></Card>}
      {query.data && query.data.items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-bambu-dark-tertiary">
          <table className="w-full min-w-[800px] text-sm">
            <thead className={tableHeaderClass}>
              <tr className={tableHeaderRowClass}>
                {[copy.sku, copy.name, copy.kind].map((label) => <th key={label} scope="col" className={tableHeaderCellClass}>{label}</th>)}
                {[copy.physical, copy.reserved, copy.available, copy.minimum].map((label) => <th key={label} scope="col" className={`${tableHeaderCellClass} text-center`}>{label}</th>)}
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((article) => (
                <tr key={article.id} className="border-b border-bambu-dark-tertiary/50 text-bambu-gray transition-colors last:border-b-0 hover:bg-bambu-dark-tertiary/30">
                  <td className="px-4 py-3 align-middle">
                    <button type="button" className="rounded font-mono text-xs text-bambu-green hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green" onClick={() => setSelected(article.id)}>{article.sku}</button>
                  </td>
                  <td className="min-w-52 px-4 py-3 align-middle">
                    <button type="button" className="rounded text-left font-medium text-white hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green" onClick={() => setSelected(article.id)}>{article.name}</button>
                    <p className="mt-1 text-xs text-bambu-gray">{copy[article.stock_source]} · {article.is_active ? copy.active : copy.archived}</p>
                  </td>
                  <td className="px-4 py-3 align-middle">{copy[article.kind]}</td>
                  {(['physical', 'reserved', 'available'] as const).map((key) => (
                    <td key={key} className={`whitespace-nowrap px-4 py-3 text-center align-middle tabular-nums ${key === 'available' ? `font-medium ${article.balance.is_low_stock ? 'text-amber-300' : 'text-bambu-green-light'}` : key === 'physical' ? 'text-white' : ''}`}>
                      {article.kind === 'service' ? '—' : `${warehouseQuantity(article.balance[key])} ${article.unit_code}`}
                    </td>
                  ))}
                  <td className="px-4 py-3 text-center align-middle tabular-nums">{article.kind === 'service' ? '—' : warehouseQuantity(article.minimum_stock)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {query.data && (
        <div className="flex flex-wrap items-center justify-end gap-3 text-sm text-bambu-gray">
          <span className="tabular-nums">{query.data.total ? offset + 1 : 0}–{Math.min(offset + 50, query.data.total)} / {query.data.total}</span>
          <div className="flex gap-2">
            <Button type="button" size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>{copy.previous}</Button>
            <Button type="button" size="sm" variant="secondary" disabled={offset + 50 >= query.data.total} onClick={() => setOffset(offset + 50)}>{copy.next}</Button>
          </div>
        </div>
      )}
      {selected !== null && <WarehouseArticleDetail key={selected} id={selected} onClose={() => setSelected(null)} />}
      {creating && <WarehouseArticleEditor article={null} onClose={() => setCreating(false)} />}
    </div>
  );
}
