import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowUp, ArrowUpDown, Boxes, Columns, Plus, Search, X } from 'lucide-react';
import { warehouseArticlesApi, type WarehouseArticle, type WarehouseArticleKind, type WarehouseStockSource } from '../api/client/warehouse-articles';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent } from '../components/Card';
import { Button, Checkbox, Select, TextField } from '../components/ui';
import { tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../components/ui/tableStyles';
import { ColumnConfigModal, type ColumnConfig } from '../components/ColumnConfigModal';
import { WarehouseArticleDetail } from '../components/warehouse/WarehouseArticleDetail';
import { WarehouseArticleEditor } from '../components/warehouse/WarehouseArticleEditor';
import { useWarehouseCopy, warehouseQuantity } from '../components/warehouse/warehouseGoodsCopy';

type SortDirection = 'asc' | 'desc';
type SortState = { column: string; direction: SortDirection } | null;

const SORT_STATE_KEY = 'printops-warehouse-goods-sort';
const COLUMN_CONFIG_KEY = 'printops-warehouse-goods-columns';
const PAGE_SIZE_KEY = 'printops-warehouse-goods-pageSize';
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200];
const SEARCH_DEBOUNCE_MS = 300;

type ColumnLabelKey = 'sku' | 'name' | 'kind' | 'physical' | 'reserved' | 'available' | 'minimum';

const DEFAULT_COLUMNS: ColumnConfig[] = [
  { id: 'sku', label: 'sku', visible: true },
  { id: 'name', label: 'name', visible: true },
  { id: 'kind', label: 'kind', visible: true },
  { id: 'physical', label: 'physical', visible: true },
  { id: 'reserved', label: 'reserved', visible: true },
  { id: 'available', label: 'available', visible: true },
  { id: 'minimum', label: 'minimum', visible: true },
];

const CENTERED_COLUMNS = new Set(['physical', 'reserved', 'available', 'minimum']);
const SORTABLE_COLUMNS = new Set(DEFAULT_COLUMNS.map((column) => column.id));
// Frontend column ids that map to a different backend sort_by value.
const SORT_COLUMN_MAP: Record<string, string> = { minimum: 'minimum_stock' };

function loadSortState(): SortState {
  try {
    const stored = localStorage.getItem(SORT_STATE_KEY);
    if (stored) return JSON.parse(stored) as SortState;
  } catch { /* ignore */ }
  return null;
}

function saveSortState(state: SortState) {
  try {
    if (state) {
      localStorage.setItem(SORT_STATE_KEY, JSON.stringify(state));
    } else {
      localStorage.removeItem(SORT_STATE_KEY);
    }
  } catch { /* ignore */ }
}

function loadColumnConfig(): ColumnConfig[] {
  try {
    const stored = localStorage.getItem(COLUMN_CONFIG_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as ColumnConfig[];
      const defaultIds = new Set(DEFAULT_COLUMNS.map((column) => column.id));
      const storedIds = new Set(parsed.map((column) => column.id));
      return [
        ...parsed.filter((column) => defaultIds.has(column.id)),
        ...DEFAULT_COLUMNS.filter((column) => !storedIds.has(column.id)),
      ];
    }
  } catch { /* ignore */ }
  return DEFAULT_COLUMNS.map((column) => ({ ...column }));
}

function saveColumnConfig(config: ColumnConfig[]) {
  try {
    localStorage.setItem(COLUMN_CONFIG_KEY, JSON.stringify(config));
  } catch { /* ignore */ }
}

function loadPageSize(): number {
  try {
    const stored = Number(localStorage.getItem(PAGE_SIZE_KEY));
    if (PAGE_SIZE_OPTIONS.includes(stored)) return stored;
  } catch { /* ignore */ }
  return 50;
}

export function WarehouseGoodsPage() {
  const copy = useWarehouseCopy();
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [active, setActive] = useState('active');
  const [kind, setKind] = useState<WarehouseArticleKind | ''>('');
  const [source, setSource] = useState<WarehouseStockSource | ''>('');
  const [low, setLow] = useState(false);
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState<number>(loadPageSize);
  const [sort, setSort] = useState<SortState>(loadSortState);
  const [columnConfig, setColumnConfig] = useState<ColumnConfig[]>(loadColumnConfig);
  const [showColumnModal, setShowColumnModal] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const canRead = hasPermission('inventory:read');

  // Debounced search: one request per pause, not per keystroke (OrdersCustomersPage pattern).
  useEffect(() => {
    const nextSearch = searchInput.trim();
    if (nextSearch === search) return;
    const timer = window.setTimeout(() => {
      setSearch(nextSearch);
      setOffset(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [searchInput, search]);

  useEffect(() => {
    try {
      localStorage.setItem(PAGE_SIZE_KEY, String(pageSize));
    } catch { /* ignore */ }
  }, [pageSize]);

  const localizedDefaultColumns = useMemo(
    () => DEFAULT_COLUMNS.map((column) => ({ ...column, label: copy[column.label as ColumnLabelKey] })),
    [copy],
  );
  const localizedColumns = useMemo(() => {
    const labels = new Map(localizedDefaultColumns.map((column) => [column.id, column.label]));
    return columnConfig.map((column) => ({ ...column, label: labels.get(column.id) ?? column.label }));
  }, [columnConfig, localizedDefaultColumns]);
  const visibleColumns = useMemo(() => localizedColumns.filter((column) => column.visible), [localizedColumns]);

  const saveColumns = (config: ColumnConfig[]) => {
    setColumnConfig(config);
    saveColumnConfig(config);
  };

  const handleSort = (column: string) => {
    if (!SORTABLE_COLUMNS.has(column)) return;
    setSort((previous) => {
      // Toggle asc -> desc -> cleared.
      const next: SortState = previous?.column === column
        ? previous.direction === 'asc'
          ? { column, direction: 'desc' }
          : null
        : { column, direction: 'asc' };
      saveSortState(next);
      return next;
    });
    setOffset(0);
  };

  const params = {
    q: search,
    active: active === 'all' ? undefined : active === 'active',
    kind: kind || undefined,
    stock_source: source || undefined,
    low_stock: low,
    sort_by: sort ? (SORT_COLUMN_MAP[sort.column] ?? sort.column) : undefined,
    sort_dir: sort?.direction,
    offset,
    limit: pageSize,
  };
  const query = useQuery({ queryKey: ['warehouse-articles', params], queryFn: () => warehouseArticlesApi.list(params), enabled: canRead });
  if (!canRead) return <p role="alert" className="p-4 text-sm text-bambu-gray md:p-8">{copy.noRead}</p>;

  const renderCell = (article: WarehouseArticle, columnId: string) => {
    switch (columnId) {
      case 'sku':
        return (
          <td key={columnId} className="px-4 py-3 align-middle">
            <button type="button" className="rounded font-mono text-xs text-bambu-green hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green" onClick={() => setSelected(article.id)}>{article.sku}</button>
          </td>
        );
      case 'name':
        return (
          <td key={columnId} className="min-w-52 px-4 py-3 align-middle">
            <button type="button" className="rounded text-left font-medium text-white hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-bambu-green" onClick={() => setSelected(article.id)}>{article.name}</button>
            <p className="mt-1 text-xs text-bambu-gray">{copy[article.stock_source]} · {article.is_active ? copy.active : copy.archived}</p>
          </td>
        );
      case 'kind':
        return <td key={columnId} className="px-4 py-3 align-middle">{copy[article.kind]}</td>;
      case 'physical':
      case 'reserved':
      case 'available':
        return (
          <td key={columnId} className={`whitespace-nowrap px-4 py-3 text-center align-middle tabular-nums ${columnId === 'available' ? `font-medium ${article.balance.is_low_stock ? 'text-amber-300' : 'text-bambu-green-light'}` : columnId === 'physical' ? 'text-white' : ''}`}>
            {article.kind === 'service' ? '—' : `${warehouseQuantity(article.balance[columnId])} ${article.unit_code}`}
          </td>
        );
      case 'minimum':
        return (
          <td key={columnId} className="px-4 py-3 text-center align-middle tabular-nums">
            {article.kind === 'service' ? '—' : warehouseQuantity(article.minimum_stock)}
          </td>
        );
      default:
        return null;
    }
  };

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
        <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1 w-full max-w-md">
            <Search aria-hidden className="pointer-events-none absolute bottom-3 left-3 h-4 w-4 text-bambu-gray md:bottom-[11px]" />
            <TextField type="search" label={copy.search} className="pl-9 pr-9" value={searchInput} onValueChange={setSearchInput} />
            {searchInput && (
              <button
                type="button"
                onClick={() => { setSearchInput(''); setSearch(''); setOffset(0); }}
                className="absolute bottom-3 right-3 text-bambu-gray hover:text-white md:bottom-[11px]"
                aria-label={t('orders.runtimeDomain.smallParts.clearSearch')}
              >
                <X className="h-4 w-4" aria-hidden />
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={() => setShowColumnModal(true)}
            className="flex items-center gap-1.5 rounded-lg border border-bambu-dark-tertiary px-3 py-1.5 text-sm font-medium text-bambu-gray transition-colors hover:bg-bambu-dark-tertiary"
            title={t('inventory.configureColumns')}
          >
            <Columns className="h-4 w-4" aria-hidden />
            <span className="hidden sm:inline">{t('inventory.columns')}</span>
          </button>
        </div>
        <div className="grid items-end gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
          <Select label={copy.active} value={active} onValueChange={(value) => { setActive(value); setOffset(0); }} options={[{ value: 'active', label: copy.active }, { value: 'archived', label: copy.archived }, { value: 'all', label: copy.all }]} />
          <Select<WarehouseArticleKind | ''> label={copy.kind} value={kind} onValueChange={(value) => { setKind(value); setOffset(0); }} options={[{ value: '', label: copy.all }, ...(['finished', 'trade', 'service'] as const).map((value) => ({ value, label: copy[value] }))]} />
          <Select<WarehouseStockSource | ''> label={copy.source} value={source} onValueChange={(value) => { setSource(value); setOffset(0); }} options={[{ value: '', label: copy.all }, ...(['own', 'material', 'none'] as const).map((value) => ({ value, label: copy[value] }))]} />
          <Select<number> label={t('archives.log.rowsPerPage')} value={pageSize} onValueChange={(value) => { setPageSize(value); setOffset(0); }} options={PAGE_SIZE_OPTIONS.map((value) => ({ value, label: String(value) }))} />
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
                {visibleColumns.map((column) => {
                  const isActive = sort?.column === column.id;
                  return (
                    <th
                      key={column.id}
                      scope="col"
                      className={`${tableHeaderCellClass} select-none ${CENTERED_COLUMNS.has(column.id) ? 'text-center' : ''} cursor-pointer transition-colors hover:text-bambu-green ${isActive ? '!text-bambu-green' : ''}`}
                      aria-sort={isActive ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}
                    >
                      <button
                        type="button"
                        onClick={() => handleSort(column.id)}
                        className="inline-flex min-h-11 min-w-11 items-center gap-1"
                        title={t('archives.log.sortBy', { column: column.label })}
                      >
                        {column.label}
                        {isActive
                          ? sort.direction === 'asc'
                            ? <ArrowUp className="h-3 w-3" aria-hidden />
                            : <ArrowDown className="h-3 w-3" aria-hidden />
                          : <ArrowUpDown className="h-3 w-3 opacity-30" aria-hidden />}
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((article) => (
                <tr key={article.id} className="border-b border-bambu-dark-tertiary/50 text-bambu-gray transition-colors last:border-b-0 hover:bg-bambu-dark-tertiary/30">
                  {visibleColumns.map((column) => renderCell(article, column.id))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {query.data && (
        <div className="flex flex-wrap items-center justify-end gap-3 text-sm text-bambu-gray">
          <span className="tabular-nums">{query.data.total ? offset + 1 : 0}–{Math.min(offset + pageSize, query.data.total)} / {query.data.total}</span>
          <div className="flex gap-2">
            <Button type="button" size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>{copy.previous}</Button>
            <Button type="button" size="sm" variant="secondary" disabled={offset + pageSize >= query.data.total} onClick={() => setOffset(offset + pageSize)}>{copy.next}</Button>
          </div>
        </div>
      )}
      <ColumnConfigModal
        isOpen={showColumnModal}
        onClose={() => setShowColumnModal(false)}
        columns={localizedColumns}
        defaultColumns={localizedDefaultColumns}
        onSave={saveColumns}
      />
      {selected !== null && <WarehouseArticleDetail key={selected} id={selected} onClose={() => setSelected(null)} />}
      {creating && <WarehouseArticleEditor article={null} onClose={() => setCreating(false)} />}
    </div>
  );
}
