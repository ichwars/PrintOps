import { useMemo } from 'react';
import { Link } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Boxes, ClipboardList, Package, PackageCheck, Warehouse } from 'lucide-react';
import { api } from '../api/client';
import { warehouseArticlesApi, type WarehouseArticle } from '../api/client/warehouse-articles';
import { smallPartsApi, type SmallPart } from '../api/smallParts';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent, CardHeader } from '../components/Card';
import { formatCount, formatMoney } from '../utils/calculationFormatting';

type WarehousePageCopy = { "title": string; "subtitle": string; "openFilament": string; "open": string; "metrics": { "activeSpools": string; "lowStock": string; "remaining": string; }; "areas": { "filament": { "title": string; "body": string; }; "parts": { "title": string; "body": string; }; "stock": { "title": string; "body": string; }; }; "stats": { "activeItems": string; "reserved": string; "stockValue": string; }; "reorder": { "title": string; "items": string; "open": string; }; };

interface AreaStat {
  label: string;
  value: string;
}

// balance/price fields are Decimal strings from the backend.
const asNumber = (value: string | number | null | undefined): number => {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
};

// Warehouse articles have no listAll helper — page through list() until the
// accumulated items cover the reported total (same loop shape as
// smallPartsApi.listAll).
async function listAllWarehouseArticles(): Promise<WarehouseArticle[]> {
  const limit = 200;
  const items: WarehouseArticle[] = [];
  let offset = 0;
  while (true) {
    const page = await warehouseArticlesApi.list({ active: true, limit, offset });
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) {
      return items;
    }
    offset = page.offset + page.items.length;
  }
}

function sumParts(parts: SmallPart[]) {
  return {
    active: parts.length,
    reserved: parts.reduce((sum, part) => sum + asNumber(part.balance.reserved), 0),
    value: parts.reduce((sum, part) => sum + asNumber(part.balance.physical) * asNumber(part.unit_cost), 0),
  };
}

function sumArticles(articles: WarehouseArticle[]) {
  return {
    active: articles.length,
    reserved: articles.reduce((sum, article) => sum + asNumber(article.balance.reserved), 0),
    value: articles.reduce((sum, article) => sum + asNumber(article.balance.physical) * asNumber(article.unit_cost), 0),
  };
}

export function WarehousePage() {
  const { t, i18n } = useTranslation();
  const { hasPermission } = useAuth();
  const canReadInventory = hasPermission('inventory:read');
  const copy = t('orders.runtimeDomain.warehousePage', { returnObjects: true }) as unknown as WarehousePageCopy;
  const locale = i18n.language || 'de-DE';

  const { data: spools = [] } = useQuery({
    queryKey: ['warehouse-overview', 'spools'],
    queryFn: () => api.getSpools(false),
  });

  // /warehouse/stock is gated behind inventory:read — without this the list
  // calls would 403 for users who may only see the filament inventory.
  const partsQuery = useQuery({
    queryKey: ['warehouse-overview', 'parts'],
    queryFn: () => smallPartsApi.listAll({ active: true }),
    enabled: canReadInventory,
  });
  const partsLowQuery = useQuery({
    queryKey: ['warehouse-overview', 'parts-low'],
    queryFn: () => smallPartsApi.list({ active: true, low_stock: true, limit: 200 }),
    enabled: canReadInventory,
  });
  const articlesQuery = useQuery({
    queryKey: ['warehouse-overview', 'articles'],
    queryFn: listAllWarehouseArticles,
    enabled: canReadInventory,
  });
  const articlesLowQuery = useQuery({
    queryKey: ['warehouse-overview', 'articles-low'],
    queryFn: () => warehouseArticlesApi.list({ active: true, low_stock: true, limit: 200 }),
    enabled: canReadInventory,
  });

  const activeSpools = spools.filter((spool) => !spool.archived_at);
  const lowStockSpools = activeSpools.filter((spool) => {
    const remaining = Math.max(0, spool.label_weight - spool.weight_used);
    return spool.label_weight > 0 && remaining / spool.label_weight <= 0.2;
  });
  const remainingGrams = activeSpools.reduce(
    (sum, spool) => sum + Math.max(0, spool.label_weight - spool.weight_used),
    0,
  );

  const partsStats = useMemo(() => (partsQuery.data ? sumParts(partsQuery.data) : null), [partsQuery.data]);
  const articlesStats = useMemo(() => (articlesQuery.data ? sumArticles(articlesQuery.data) : null), [articlesQuery.data]);

  const formatReserved = (value: number) =>
    new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value);

  // Low-stock totals are filtered server-side, so `total` is the exact count.
  const reorderTotal = partsLowQuery.data && articlesLowQuery.data
    ? partsLowQuery.data.total + articlesLowQuery.data.total
    : null;

  const buildAreaStats = (
    stats: { active: number; reserved: number; value: number } | null,
    lowStockTotal: number | undefined,
  ): AreaStat[] | undefined => {
    if (!canReadInventory) return undefined;
    return [
      { label: copy.stats.activeItems, value: stats ? formatCount(stats.active, locale) : '–' },
      { label: copy.metrics.lowStock, value: lowStockTotal !== undefined ? formatCount(lowStockTotal, locale) : '–' },
      { label: copy.stats.reserved, value: stats ? formatReserved(stats.reserved) : '–' },
      { label: copy.stats.stockValue, value: stats ? formatMoney(stats.value, locale) : '–' },
    ];
  };

  const areas: Array<{
    title: string;
    body: string;
    to: string;
    icon: typeof Package;
    stats?: AreaStat[];
  }> = [
    {
      title: copy.areas.filament.title,
      body: copy.areas.filament.body,
      to: '/warehouse/filament',
      icon: Package,
    },
    {
      title: copy.areas.parts.title,
      body: copy.areas.parts.body,
      to: '/warehouse/parts',
      icon: Boxes,
      stats: buildAreaStats(partsStats, partsLowQuery.data?.total),
    },
    {
      title: copy.areas.stock.title,
      body: copy.areas.stock.body,
      to: '/warehouse/stock',
      icon: PackageCheck,
      stats: buildAreaStats(articlesStats, articlesLowQuery.data?.total),
    },
  ];

  return (
    <div className="p-4 md:p-8 space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-3">
            <Warehouse className="w-7 h-7 text-bambu-green" />
            {copy.title}
          </h1>
          <p className="text-bambu-gray mt-1">{copy.subtitle}</p>
        </div>
        <Link
          to="/warehouse/filament"
          className="inline-flex items-center justify-center gap-2 px-4 py-2 min-h-[44px] md:min-h-0 rounded-lg bg-bambu-green hover:bg-bambu-green-light text-white text-sm font-medium transition-colors w-fit"
        >
          <Package className="w-4 h-4" />
          {copy.openFilament}
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="space-y-1">
            <p className="text-sm text-bambu-gray">{copy.metrics.activeSpools}</p>
            <p className="text-2xl font-semibold text-white">{activeSpools.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1">
            <p className="text-sm text-bambu-gray">{copy.metrics.lowStock}</p>
            <p className="text-2xl font-semibold text-white">{lowStockSpools.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1">
            <p className="text-sm text-bambu-gray">{copy.metrics.remaining}</p>
            <p className="text-2xl font-semibold text-white">{Math.round(remainingGrams / 1000)} kg</p>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {areas.map(({ title, body, to, icon: Icon, stats }) => (
          <Card key={to}>
            <CardHeader>
              <div className="flex items-center gap-3">
                <Icon className="w-5 h-5 text-bambu-green" />
                <h2 className="text-base font-semibold text-white">{title}</h2>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-bambu-gray min-h-10">{body}</p>
              {stats && (
                <dl className="grid grid-cols-2 gap-2">
                  {stats.map((stat) => (
                    <div key={stat.label} className="rounded-lg bg-bambu-dark px-3 py-2">
                      <dt className="text-xs text-bambu-gray">{stat.label}</dt>
                      <dd className="text-lg font-semibold tabular-nums text-white">{stat.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
              <Link
                to={to}
                className="inline-flex items-center gap-2 text-sm font-medium text-bambu-green hover:text-bambu-green-light"
              >
                {copy.open}
                <ArrowRight className="w-4 h-4" />
              </Link>
            </CardContent>
          </Card>
        ))}
      </div>

      <Link
        to="/warehouse/reorder"
        className="block rounded-xl border border-bambu-green/50 bg-bambu-dark-secondary card-shadow p-6 transition-colors hover:border-bambu-green"
      >
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-4">
            <ClipboardList className="w-8 h-8 shrink-0 text-bambu-green" />
            <div>
              <h2 className="text-lg font-semibold text-white">{copy.reorder.title}</h2>
              <p className="text-sm text-bambu-gray">
                <span className="mr-2 text-2xl font-semibold tabular-nums text-white">
                  {reorderTotal === null ? '–' : formatCount(reorderTotal, locale)}
                </span>
                {copy.reorder.items}
              </p>
            </div>
          </div>
          <span className="inline-flex w-fit items-center gap-2 text-sm font-medium text-bambu-green">
            {copy.reorder.open}
            <ArrowRight className="w-4 h-4" />
          </span>
        </div>
      </Link>
    </div>
  );
}
