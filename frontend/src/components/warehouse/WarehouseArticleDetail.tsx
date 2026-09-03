import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { Link } from 'react-router';
import { warehouseArticlesApi } from '../../api/client/warehouse-articles';
import { useAuth } from '../../contexts/AuthContext';
import { Card, CardContent } from '../Card';
import { Button, Modal } from '../ui';
import { tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../ui/tableStyles';
import { WarehouseArticleEditor } from './WarehouseArticleEditor';
import { WarehouseStockPanel } from './WarehouseStockPanel';
import { useWarehouseCopy, warehouseQuantity } from './warehouseGoodsCopy';

export function WarehouseArticleDetail({ id, onClose }: { id: number; onClose: () => void }) {
  const copy = useWarehouseCopy();
  const { hasPermission } = useAuth();
  const cache = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [stockBusy, setStockBusy] = useState(false);
  const stockBusyRef = useRef(false);
  const articleBusyRef = useRef(false);
  const detail = useQuery({ queryKey: ['warehouse-articles', id], queryFn: () => warehouseArticlesApi.get(id) });
  const article = detail.data;
  const mutation = useMutation({
    mutationFn: () => article!.is_active ? warehouseArticlesApi.archive(id, article!.version) : warehouseArticlesApi.update(id, { version: article!.version, is_active: true }),
    onSuccess: () => cache.invalidateQueries({ queryKey: ['warehouse-articles'] }),
    onSettled: () => { articleBusyRef.current = false; },
  });
  const canEdit = hasPermission('inventory:update');
  const busy = mutation.isPending || stockBusy;
  const close = () => { if (!articleBusyRef.current && !stockBusyRef.current) onClose(); };
  const setStockOperationBusy = (value: boolean) => { stockBusyRef.current = value; setStockBusy(value); };
  return <>
    <Modal open onClose={close} closeOnBackdrop={!busy} closeDisabled={busy} title={article ? `${article.sku} · ${article.name}` : copy.title} closeLabel={copy.close} className="max-w-4xl">
      {detail.isLoading && <p role="status" className="text-sm text-bambu-gray">{copy.loading}</p>}
      {detail.isError && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-950/50 p-3 text-sm text-red-300">{copy.error}<Button type="button" size="sm" variant="secondary" onClick={() => void detail.refetch()}>{copy.retry}</Button></div>}
      {article && <div className="space-y-6 text-sm">
        <p className="text-sm text-bambu-gray">{copy[article.kind]} · {copy[article.stock_source]} · {article.is_active ? copy.active : copy.archived} · {copy.updated}: {new Date(article.updated_at).toLocaleString()}</p>
        {article.description && <p className="whitespace-pre-wrap text-bambu-gray-light">{article.description}</p>}
        <div className="grid gap-3 sm:grid-cols-3">
          {([['physical', copy.physical], ['reserved', copy.reserved], ['available', copy.available]] as const).map(([key, label]) => (
            <Card key={key}>
              <CardContent dense className="space-y-1">
                <p className="text-xs font-medium uppercase text-bambu-gray">{label}</p>
                <p className={`text-xl font-bold tabular-nums ${key === 'available' ? article.balance.is_low_stock ? 'text-amber-300' : 'text-bambu-green-light' : 'text-white'}`}>
                  {warehouseQuantity(article.balance[key])} <span className="text-sm font-normal text-bambu-gray">{article.unit_code}</span>
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
        {article.balance.is_low_stock && <p className="rounded-lg border border-amber-500/30 bg-amber-950/10 p-3 text-amber-300">{copy.low} · {copy.minimum}: {warehouseQuantity(article.minimum_stock)} {article.unit_code}</p>}
        <dl className="grid gap-4 border-y border-bambu-dark-tertiary py-4 sm:grid-cols-2">
          {([[copy.sale, article.sale_price], [copy.cost, article.unit_cost], [copy.tax, article.tax_rate], [copy.minimum, article.minimum_stock]] as const).map(([label, value]) => <div key={label}><dt className="text-xs text-bambu-gray">{label}</dt><dd className="mt-1 font-medium tabular-nums text-white">{warehouseQuantity(value)}</dd></div>)}
          {article.project_id && <div><dt className="text-xs text-bambu-gray">{copy.project}</dt><dd className="mt-1 font-medium text-white">#{article.project_id}</dd></div>}
          {article.calculation_revision_id && <div><dt className="text-xs text-bambu-gray">{copy.revision}</dt><dd className="mt-1 font-medium text-white">#{article.calculation_revision_id}</dd></div>}
        </dl>
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {canEdit && <Button type="button" size="sm" variant="secondary" disabled={busy} onClick={() => setEditing(true)}>{copy.edit}</Button>}
            {(article.is_active ? hasPermission('inventory:delete') : canEdit) && <Button type="button" size="sm" variant="secondary" loading={mutation.isPending} disabled={stockBusy || article.is_active && (Number(article.balance.physical) !== 0 || Number(article.balance.reserved) !== 0)} onClick={() => { if (articleBusyRef.current) return; articleBusyRef.current = true; mutation.mutate(); }}>{article.is_active ? copy.archive : copy.restore}</Button>}
          </div>
          <p className="text-xs text-bambu-gray">{copy.archiveNote}</p>
        </div>
        {mutation.isError && <p role="alert" className="rounded-lg bg-red-950/50 p-3 text-red-300">{mutation.error.message}</p>}
        {article.locations.length > 0 && (
          <div className="overflow-x-auto rounded-lg border border-bambu-dark-tertiary">
            <table className="w-full min-w-[480px] text-sm">
              <thead className={tableHeaderClass}>
                <tr className={tableHeaderRowClass}>
                  <th scope="col" className={tableHeaderCellClass}>{copy.location}</th>
                  {[copy.physical, copy.reserved, copy.available].map((label) => <th key={label} scope="col" className={`${tableHeaderCellClass} text-center`}>{label}</th>)}
                </tr>
              </thead>
              <tbody>{article.locations.map((location) => (
                <tr key={location.location_id ?? 'none'} className="border-b border-bambu-dark-tertiary/50 text-bambu-gray last:border-b-0 hover:bg-bambu-dark-tertiary/30">
                  <td className="px-4 py-3 text-white">{location.location_name}</td>
                  <td className="px-4 py-3 text-center tabular-nums text-white">{warehouseQuantity(location.physical)}</td>
                  <td className="px-4 py-3 text-center tabular-nums">{warehouseQuantity(location.reserved)}</td>
                  <td className={`px-4 py-3 text-center font-medium tabular-nums ${location.is_low_stock ? 'text-amber-300' : 'text-bambu-green-light'}`}>{warehouseQuantity(location.available)}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
        {article.stock_source === 'material' && <div className="space-y-2 rounded-lg border border-bambu-dark-tertiary p-4 text-bambu-gray"><p>{copy.materialNote}</p><Link className="inline-flex font-medium text-bambu-green hover:text-bambu-green-light hover:underline" to={`/warehouse/parts?part=${article.small_part_id}`}>{copy.materialLink}</Link></div>}
        {article.stock_source === 'none' && <p className="text-bambu-gray">{copy.serviceNote}</p>}
        {article.stock_source === 'own' && <WarehouseStockPanel article={article} canBook={canEdit} disabled={mutation.isPending} onBusyChange={setStockOperationBusy} />}
      </div>}
    </Modal>
    {editing && article && <WarehouseArticleEditor article={article} onClose={() => setEditing(false)} />}
  </>;
}
