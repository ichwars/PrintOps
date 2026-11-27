import { Link } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ArrowRight, FileText, ShoppingCart, Truck } from 'lucide-react';
import { smallPartsApi, type SmallPart } from '../api/smallParts';
import { warehouseArticlesApi, type WarehouseArticle } from '../api/client/warehouse-articles';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent } from '../components/Card';
import { Button } from '../components/ui';
import { tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../components/ui/tableStyles';
import { useWarehouseCopy, warehouseQuantity } from '../components/warehouse/warehouseGoodsCopy';

type WarehouseReorderCopy = { "title": string; "subtitle": string; "empty": string; "open": string; "summaryWarehouse": string; "summaryMaterial": string; "summaryTotal": string; "colArea": string; "colSuggested": string; "colAction": string; "areaWarehouse": string; "areaMaterial": string; };

const PAGE_SIZE = 200;

type Page<T> = { items: T[]; total: number; limit: number; offset: number };

async function fetchAllPages<T>(fetchPage: (offset: number) => Promise<Page<T>>): Promise<T[]> {
  const items: T[] = [];
  let offset = 0;
  for (;;) {
    const page = await fetchPage(offset);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
    offset = page.offset + page.items.length;
  }
}

type ReorderRow = {
  key: string;
  area: 'warehouse' | 'material';
  sku: string;
  name: string;
  available: string;
  minimum: string;
  suggested: number;
  unit: string;
  to: string;
};

function suggestedQuantity(minimum: string, available: string): number {
  // Decimal strings from the API are subtracted via Number(); toFixed(6) keeps
  // the result stable for the backend's 6-decimal values without float noise.
  return Math.max(0, Number((Number(minimum) - Number(available)).toFixed(6)));
}

function toReorderRows(articles: WarehouseArticle[], parts: SmallPart[]): ReorderRow[] {
  const rows: ReorderRow[] = articles.map((article) => ({
    key: `warehouse-${article.id}`,
    area: 'warehouse' as const,
    sku: article.sku,
    name: article.name,
    available: article.balance.available,
    minimum: article.minimum_stock,
    suggested: suggestedQuantity(article.minimum_stock, article.balance.available),
    unit: article.unit_code,
    to: '/warehouse/stock',
  }));
  rows.push(...parts.map((part) => ({
    key: `material-${part.id}`,
    area: 'material' as const,
    sku: part.sku,
    name: part.name,
    available: part.balance.available,
    minimum: part.minimum_stock,
    suggested: suggestedQuantity(part.minimum_stock, part.balance.available),
    unit: part.unit_code,
    to: '/warehouse/parts',
  })));
  return rows;
}

export function WarehouseReorderPage() {
  const { t } = useTranslation();
  const goods = useWarehouseCopy();
  const { hasPermission } = useAuth();
  const canRead = hasPermission('inventory:read');
  const rawCopy = t('orders.runtimeDomain.warehouseReorder', { returnObjects: true });
  const copy = (typeof rawCopy === 'object' && rawCopy !== null ? rawCopy : {}) as unknown as WarehouseReorderCopy;

  const articlesQuery = useQuery({
    queryKey: ['warehouse-articles', 'reorder', { active: true, low_stock: true }],
    queryFn: () => fetchAllPages<WarehouseArticle>((offset) => warehouseArticlesApi.list({ active: true, low_stock: true, limit: PAGE_SIZE, offset })),
    enabled: canRead,
  });
  const partsQuery = useQuery({
    queryKey: ['small-parts', 'reorder', { active: true, low_stock: true }],
    queryFn: () => fetchAllPages<SmallPart>((offset) => smallPartsApi.list({ active: true, low_stock: true, limit: PAGE_SIZE, offset })),
    enabled: canRead,
  });

  if (!canRead) return <p role="alert" className="p-4 text-sm text-bambu-gray md:p-8">{goods.noRead}</p>;

  const loaded = articlesQuery.isSuccess && partsQuery.isSuccess;
  const rows = loaded ? toReorderRows(articlesQuery.data, partsQuery.data) : [];
  const loading = articlesQuery.isLoading || partsQuery.isLoading;
  const failed = articlesQuery.isError || partsQuery.isError;
  const retry = () => {
    void articlesQuery.refetch();
    void partsQuery.refetch();
  };

  return (
    <div className="min-w-0 space-y-6 p-4 md:p-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold text-white">
            <ShoppingCart aria-hidden className="h-7 w-7 shrink-0 text-bambu-green" />{copy.title}
          </h1>
          <p className="mt-1 text-bambu-gray">{copy.subtitle}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/warehouse/suppliers"
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-bambu-dark-tertiary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-bambu-gray-dark md:min-h-0"
          >
            <Truck aria-hidden className="h-4 w-4" />{t('suppliers.navTitle')}
          </Link>
          <Link
            to="/orders/offers"
            className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-bambu-green px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-bambu-green-light md:min-h-0"
          >
            <FileText aria-hidden className="h-4 w-4" />{t('printops.nav.offers')}
          </Link>
        </div>
      </header>

      {loaded && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <CardContent className="space-y-1">
              <p className="text-sm text-bambu-gray">{copy.summaryWarehouse}</p>
              <p className="text-2xl font-semibold text-white">{articlesQuery.data.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-1">
              <p className="text-sm text-bambu-gray">{copy.summaryMaterial}</p>
              <p className="text-2xl font-semibold text-white">{partsQuery.data.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-1">
              <p className="text-sm text-bambu-gray">{copy.summaryTotal}</p>
              <p className="text-2xl font-semibold text-white">{rows.length}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {loading && <p role="status" className="py-10 text-center text-sm text-bambu-gray">{goods.loading}</p>}
      {failed && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-950/50 p-3 text-sm text-red-300">
          {goods.error}
          <Button type="button" size="sm" variant="secondary" onClick={retry}>{goods.retry}</Button>
        </div>
      )}
      {loaded && rows.length === 0 && (
        <Card>
          <CardContent>
            <p className="py-4 text-center text-sm text-bambu-gray">{copy.empty}</p>
          </CardContent>
        </Card>
      )}
      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-bambu-dark-tertiary">
          <table className="w-full min-w-[900px] text-sm">
            <thead className={tableHeaderClass}>
              <tr className={tableHeaderRowClass}>
                {[copy.colArea, goods.sku, goods.name, goods.available, goods.minimum, copy.colSuggested, copy.colAction].map((label) => (
                  <th key={label} scope="col" className={tableHeaderCellClass}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-b border-bambu-dark-tertiary/50 text-bambu-gray transition-colors last:border-b-0 hover:bg-bambu-dark-tertiary/30">
                  <td className="px-4 py-3 align-middle">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${row.area === 'warehouse' ? 'bg-bambu-green/15 text-bambu-green-light' : 'bg-amber-400/15 text-amber-300'}`}>
                      {row.area === 'warehouse' ? copy.areaWarehouse : copy.areaMaterial}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 align-middle font-mono text-xs text-bambu-green">{row.sku}</td>
                  <td className="min-w-52 px-4 py-3 align-middle font-medium text-white">{row.name}</td>
                  <td className="whitespace-nowrap px-4 py-3 align-middle text-center tabular-nums text-amber-300">{warehouseQuantity(row.available)} {row.unit}</td>
                  <td className="whitespace-nowrap px-4 py-3 align-middle text-center tabular-nums">{warehouseQuantity(row.minimum)}</td>
                  <td className="whitespace-nowrap px-4 py-3 align-middle text-center font-medium tabular-nums text-white">{warehouseQuantity(String(row.suggested))} {row.unit}</td>
                  <td className="px-4 py-3 align-middle">
                    <Link to={row.to} className="inline-flex items-center gap-1 rounded text-sm font-medium text-bambu-green hover:text-bambu-green-light hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green">
                      {copy.open}<ArrowRight aria-hidden className="h-4 w-4" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
