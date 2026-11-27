import { TablePagination } from '../components/ui/TablePagination';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Archive, ArrowDown, ArrowUp, ArrowUpDown, Boxes, ClipboardCheck, Columns, Copy, Group, Info, Minus, Package, PackagePlus, Pencil, Plus, RotateCcw } from 'lucide-react';
import { api } from '../api/client';
import { smallPartsApi } from '../api/smallParts';
import { canArchiveWarehouseArticle, warehouseArticlesApi, type WarehouseArticle, type WarehouseArticleKind, type WarehouseArticleListParams, type WarehouseArticleSortColumn, type WarehouseStockSource } from '../api/client/warehouse-articles';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent } from '../components/Card';
import { Button } from '../components/ui';
import { ColumnConfigModal, type ColumnConfig } from '../components/ColumnConfigModal';
import {
  WarehouseFilterResults, WarehouseFilters, WarehouseFilterSelect, WarehouseHeader, WarehousePage, WarehouseRemainingSort,
  WarehouseSegment, WarehouseSegments, WarehouseTable, WarehouseTableGroupHeading, WarehouseTableScroll,
  WarehouseToolbar, WarehouseToolbarButton, WarehouseUsageOptions, WarehouseViewOptions, type WarehouseUsageFilter,
} from '../components/warehouse/WarehouseLayout';
import { WarehouseActionHeader, WarehouseActionMenu, WarehouseRowActions, type WarehouseAction } from '../components/warehouse/WarehouseRowActions';
import { warehouseTableDescriptionClass, warehouseTableIdentifierClass, warehouseTableRowClass } from '../components/warehouse/warehouseStyles';
import { tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../components/ui/tableStyles';
import { WarehouseGoodsForecast } from '../components/warehouse/WarehouseGoodsForecast';
import { SmallPartStockDialog } from '../components/warehouse/SmallPartStockDialog';
import { WarehouseStockPanel } from '../components/warehouse/WarehouseStockPanel';
import { WarehouseArticleDetail } from '../components/warehouse/WarehouseArticleDetail';
import { WarehouseArticleEditor } from '../components/warehouse/WarehouseArticleEditor';
import { WarehouseStatusDialog } from '../components/warehouse/WarehouseStatusDialog';
import { useWarehouseCopy, warehouseQuantity } from '../components/warehouse/warehouseGoodsCopy';
import { WarehouseRemaining, WarehouseSelectionCell, WarehouseSelectionHeader, WarehouseStockCheckDialog } from '../components/warehouse/WarehouseStocktake';
import { focusWarehouseRow, groupWarehouseItems, useWarehouseRowTarget, useWarehouseSelection, warehouseDate, warehouseFilterOptions, warehouseUnit } from '../components/warehouse/warehouseTableValues';

const SORT_KEY = 'printops-warehouse-goods-sort';
const COLUMNS_KEY = 'printops-warehouse-goods-columns';
const PAGE_SIZE_KEY = 'printops-warehouse-goods-pageSize';
const PAGE_SIZES = [15, 25, 30, 50, 100, 200];

function loadPageSize() {
  try {
    const saved = Number(localStorage.getItem(PAGE_SIZE_KEY));
    return PAGE_SIZES.includes(saved) ? saved : 50;
  } catch {
    return 50;
  }
}
const SORT_COLUMNS = ['id', 'sku', 'name', 'created_at', 'last_used_at', 'kind', 'physical', 'reserved', 'available', 'consumed', 'remaining', 'minimum_stock', 'stock_checked_at'] as const;
const CONFIGURABLE_COLUMNS = SORT_COLUMNS.filter(column => column !== 'id');
const TEXT_COLUMNS = new Set(['id', 'sku', 'name', 'kind']);
type Sort = { column: WarehouseArticleSortColumn; direction: 'asc' | 'desc' };
type FilterState = {
  search: string; active: 'active' | 'archived' | 'all'; kind: WarehouseArticleKind | '';
  source: WarehouseStockSource | ''; usage: WarehouseUsageFilter; location: string; unit: string;
};
const DEFAULT_FILTERS: FilterState = { search: '', active: 'active', kind: '', source: '', usage: 'all', location: '', unit: '' };

function loadColumns(): ColumnConfig[] {
  const defaults = CONFIGURABLE_COLUMNS.map(id => ({ id, label: id, visible: true }));
  try {
    const raw = localStorage.getItem(COLUMNS_KEY);
    if (!raw) return defaults;
    const stored = (JSON.parse(raw) as ColumnConfig[]).filter(column => defaults.some(item => item.id === column.id));
    return [...stored, ...defaults.filter(column => !stored.some(item => item.id === column.id))];
  } catch {
    return defaults;
  }
}

function loadSort(): Sort | null {
  try {
    const saved = localStorage.getItem(SORT_KEY);
    if (!saved) return null;
    const sort = JSON.parse(saved);
    if (SORT_COLUMNS.includes(sort?.column) && (sort.direction === 'asc' || sort.direction === 'desc')) return sort;
  } catch {
    // Invalid saved preferences or unavailable storage.
  }
  return null;
}

export function WarehouseGoodsPage() {
  const copy = useWarehouseCopy();
  const { t, i18n } = useTranslation();
  const { hasPermission } = useAuth();
  const queryClient = useQueryClient();
  const { focusedId, clearRowTarget } = useWarehouseRowTarget();
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const { search, active, kind, source, usage, location, unit } = filters;
  const [viewMode, setViewMode] = useState<'table' | 'cards' | 'forecast'>('table');
  const forecast = viewMode === 'forecast';
  const [quick, setQuick] = useState<{ id: number; kind: 'receipt' | 'issue' } | null>(null);
  const [quickBusy, setQuickBusy] = useState(false);
  const [materialBooking, setMaterialBooking] = useState<{ partId: number; kind: 'receipt' | 'issue' } | null>(null);
  const quickTrigger = useRef<HTMLButtonElement>(null);
  function cancelQuick() {
    setQuick(null);
    quickTrigger.current?.focus();
  }
  const [groupByKind, setGroupByKind] = useState(false);
  const [columnConfig, setColumnConfig] = useState(loadColumns);
  const [showColumns, setShowColumns] = useState(false);
  const [offset, setOffset] = useState(0);
  const [pageSize, setPageSize] = useState(loadPageSize);
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => {
    const next = searchInput.trim();
    if (next === search) return;
    const timer = window.setTimeout(() => {
      setFilters(current => ({ ...current, search: next }));
      setOffset(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput, search]);
  const [sort, setSort] = useState(loadSort);
  const [selected, setSelected] = useState<{ id: number; stockOnly?: boolean } | null>(null);
  const [editor, setEditor] = useState<{ article: WarehouseArticle | null; copyFrom?: WarehouseArticle } | null>(null);
  const [statusArticle, setStatusArticle] = useState<WarehouseArticle | null>(null);
  const [checkingIds, setCheckingIds] = useState<number[]>([]);
  const canCreate = hasPermission('inventory:create');
  const canArchive = hasPermission('inventory:delete');
  const canEdit = hasPermission('inventory:update');
  const canRead = hasPermission('inventory:read');
  const params: WarehouseArticleListParams = focusedId !== null ? { article_id: focusedId, limit: 1 } : {
    q: search, active: active === 'all' ? undefined : active === 'active',
    kind: kind || undefined, stock_source: source || undefined,
    usage: usage === 'used' || usage === 'new' ? usage : undefined,
    location_id: location ? Number(location) : undefined, unit_code: unit || undefined,
    low_stock: usage === 'lowstock', sort_by: sort?.column, sort_dir: sort?.direction, offset, limit: pageSize,
  };
  const query = useQuery({
    queryKey: ['warehouse-articles', params] as const,
    queryFn: () => warehouseArticlesApi.list(params),
    enabled: canRead && !forecast,
    placeholderData: (previous, previousQuery) => {
      const old = previousQuery?.queryKey[1];
      if (old && old.article_id === params.article_id && old.q === search && old.active === params.active && old.kind === params.kind
        && old.stock_source === params.stock_source && old.low_stock === params.low_stock && old.usage === params.usage
        && old.location_id === params.location_id && old.unit_code === params.unit_code) return previous;
    },
  });
  const locations = useQuery({ queryKey: ['warehouse', 'locations'], queryFn: api.getLocations, enabled: canRead });
  const units = useQuery({ queryKey: ['small-parts', 'units'], queryFn: smallPartsApi.units.list, enabled: canRead });
  const rows = query.data?.items ?? [];
  const total = query.data?.total;
  useEffect(() => {
    if (total !== undefined && !query.isPlaceholderData && offset > 0 && offset >= total) {
      setOffset(total > 0 ? Math.floor((total - 1) / pageSize) * pageSize : 0);
    }
  }, [offset, pageSize, query.isPlaceholderData, total]);
  const groups = groupWarehouseItems(rows, groupByKind ? article => copy[article.kind] : undefined);
  const selectableIds = query.isPlaceholderData || viewMode !== 'table' ? [] : rows.filter(article => article.is_active && article.stock_source !== 'none').map(article => article.id);
  const selection = useWarehouseSelection(selectableIds);
  const selectedArticles = rows.filter(article => selection.selected.has(article.id));
  const openAfterBooking = (open: () => void) => {
    if (quickBusy) return;
    setQuick(null);
    open();
  };
  const openArticle = (article: WarehouseArticle) => openAfterBooking(() => {
    if (canEdit) setEditor({ article });
    else setSelected({ id: article.id });
  });
  const labels = {
    ...copy,
    id: '#',
    created_at: t('orders.runtimeInterface.inventoryColumns.added'),
    last_used_at: t('orders.runtimeInterface.inventoryColumns.lastUsed'),
    consumed: t('inventory.weightUsed'),
    remaining: t('inventory.remaining'),
    minimum_stock: copy.minimum,
    stock_checked_at: t('common.stockChecked'),
  };
  const defaultColumns = CONFIGURABLE_COLUMNS.map(id => ({ id, label: labels[id], visible: true }));
  const columns = ['id' as const, ...columnConfig.filter(column => column.visible).map(column => column.id as WarehouseArticleSortColumn)];
  const saveColumns = (config: ColumnConfig[]) => {
    setColumnConfig(config);
    try { localStorage.setItem(COLUMNS_KEY, JSON.stringify(config)); } catch { /* Storage may be unavailable. */ }
  };
  const changeFilters = (changes: Partial<FilterState>) => {
    clearRowTarget();
    setFilters(previous => ({ ...previous, ...changes }));
    setOffset(0);
  };
  const hasActiveFilters = focusedId !== null || Boolean(searchInput || kind || source || location || unit) || active !== 'active' || usage !== 'all';
  const sortBy = (column: WarehouseArticleSortColumn) => {
    const next: Sort | null = sort?.column === column
      ? sort.direction === 'asc' ? { column, direction: 'desc' } : null
      : { column, direction: 'asc' };
    setSort(next);
    setOffset(0);
    try {
      if (next) localStorage.setItem(SORT_KEY, JSON.stringify(next));
      else localStorage.removeItem(SORT_KEY);
    } catch {
      // Sorting still works for this visit when storage is unavailable.
    }
  };
  const openDetails = (article: WarehouseArticle) => openAfterBooking(() => setSelected({ id: article.id }));
  const quantity = (article: WarehouseArticle, value: string) => `${warehouseQuantity(value)} ${warehouseUnit(article.unit_code, t('common.unitShortPiece'))}`;
  const remaining = (article: WarehouseArticle) => <WarehouseRemaining physical={article.balance.physical} consumed={article.consumed ?? '0'} label={quantity(article, article.balance.physical)} />;
  const rowActions = (article: WarehouseArticle, allowQuickBooking = false): WarehouseAction[] => [
    { label: t('projects.viewDetails'), icon: Info, onSelect: () => openDetails(article) },
    ...(canEdit ? [{ label: copy.edit, icon: Pencil, onSelect: () => openArticle(article) }] : []),
    ...(canCreate ? [{ label: t('common.duplicate'), icon: Copy, onSelect: () => setEditor({ article: null, copyFrom: article }) }] : []),
    ...(canEdit && article.is_active && article.stock_source !== 'none' ? [{ label: t('common.confirmStockCheck'), icon: ClipboardCheck, onSelect: () => setCheckingIds([article.id]) }] : []),
    ...(canEdit && article.is_active && article.stock_source === 'own'
      ? [{ label: copy.book, icon: PackagePlus, onSelect: () => openAfterBooking(() => setSelected({ id: article.id, stockOnly: true })), disabled: quickBusy }]
      : []),
    ...(allowQuickBooking && canEdit && article.is_active &&
      (article.stock_source === 'own' || (article.stock_source === 'material' && article.small_part_id !== null)) ? ([
      { kind: 'receipt', icon: Plus },
      { kind: 'issue', icon: Minus },
    ] as const).map(({ kind, icon }): WarehouseAction => ({
      label: copy[kind],
      icon,
      disabled: quickBusy || query.isPlaceholderData,
      onSelect: (trigger) => {
        if (article.stock_source === 'material' && article.small_part_id !== null) {
          const partId = article.small_part_id;
          openAfterBooking(() => setMaterialBooking({ partId, kind }));
          return;
        }
        if (quick?.id === article.id && quick.kind === kind) {
          cancelQuick();
          return;
        }
        quickTrigger.current = trigger;
        setQuick({ id: article.id, kind });
      },
    })) : []),
    ...((article.is_active ? canArchive : canEdit) ? [{
      label: article.is_active ? copy.archive : copy.restore,
      icon: article.is_active ? Archive : RotateCcw,
      onSelect: () => setStatusArticle(article),
      disabled: article.is_active && !canArchiveWarehouseArticle(article),
    }] : []),
  ];
  const tableViewport = useRef<HTMLDivElement>(null);
  const warehousePage = !forecast && query.data?.items.length ? query.data : null;
  const footer = warehousePage && (
    <TablePagination total={warehousePage.total} offset={warehousePage.offset} pageSize={pageSize}
      busy={query.isPlaceholderData} sizes={PAGE_SIZES} onOffsetChange={setOffset}
      viewportRef={viewMode === 'table' ? tableViewport : undefined}
      onPageSizeChange={value => {
        setPageSize(value);
        setOffset(0);
        try { localStorage.setItem(PAGE_SIZE_KEY, String(value)); } catch { /* Storage may be unavailable. */ }
      }} />
  );
  if (!canRead) return <p role="alert" className="p-4 text-sm text-bambu-gray md:p-8">{copy.noRead}</p>;
  return (
    <WarehousePage footer={footer}>
      <WarehouseHeader icon={Boxes} title={copy.title} description={copy.subtitle}>
        {canCreate && <Button type="button" onClick={() => setEditor({ article: null })}><Plus className="h-4 w-4" aria-hidden />{copy.create}</Button>}
      </WarehouseHeader>

      <WarehouseToolbar hideSearch={forecast} searchLabel={copy.search} value={searchInput} onSearch={value => {
        setSearchInput(value);
        if (!value.trim()) changeFilters({ search: '' });
        else clearRowTarget();
      }}>
        {viewMode === 'table' && <WarehouseToolbarButton label={t('inventory.columns')} icon={Columns} onClick={() => setShowColumns(true)} />}
        {!forecast && <WarehouseToolbarButton label={t('inventory.groupSimilar')} icon={Group} pressed={groupByKind} onClick={() => setGroupByKind(value => !value)} />}
        {!forecast && <WarehouseRemainingSort direction={sort?.column === 'remaining' ? sort.direction : undefined} onClick={() => sortBy('remaining')} />}
        <WarehouseViewOptions view={viewMode} onChange={value => { setQuick(null); setViewMode(value); }} options={['table', 'cards', 'forecast']} />
      </WarehouseToolbar>

      {forecast && <WarehouseGoodsForecast />}
      <WarehouseFilters hidden={forecast}>
        <WarehouseSegments label={t('orders.runtimeDomain.smallParts.status')}>
          <WarehouseSegment active={active === 'active'} onClick={() => changeFilters({ active: 'active' })}>
            <Package aria-hidden className="h-3.5 w-3.5" />{copy.active}
          </WarehouseSegment>
          <WarehouseSegment active={active === 'archived'} onClick={() => changeFilters({ active: 'archived' })}>
            <Archive aria-hidden className="h-3.5 w-3.5" />{copy.archived}
          </WarehouseSegment>
          <WarehouseSegment active={active === 'all'} onClick={() => changeFilters({ active: 'all' })}>{copy.all}</WarehouseSegment>
        </WarehouseSegments>
        <div aria-hidden="true" className="hidden h-5 w-px bg-bambu-dark-tertiary sm:block" />
        <WarehouseUsageOptions value={usage} onChange={value => changeFilters({ usage: value })} lowLabel={copy.low} />
        <div className="grid w-full grid-cols-2 gap-2 sm:w-auto sm:min-w-60 sm:flex-1 xl:min-w-96 xl:grid-cols-4">
          <WarehouseFilterSelect label={copy.kind} value={kind} onChange={value => changeFilters({ kind: value })}
            options={(['finished', 'trade', 'service'] as const).map(value => ({ value, label: copy[value] }))} />
          <WarehouseFilterSelect label={copy.source} value={source} onChange={value => changeFilters({ source: value })}
            options={(['own', 'material', 'none'] as const).map(value => ({ value, label: copy[value] }))} />
          <WarehouseFilterSelect label={copy.location} value={location} onChange={value => changeFilters({ location: value })}
            options={warehouseFilterOptions((locations.data ?? []).map(item => ({ value: String(item.id), label: item.name })), i18n.language)} />
          <WarehouseFilterSelect label={t('orders.runtimeDomain.smallParts.unit')} value={unit} onChange={value => changeFilters({ unit: value })}
            options={warehouseFilterOptions((units.data ?? []).map(item => ({ value: item.code, label: item.label })), i18n.language)} />
        </div>
        <WarehouseFilterResults total={query.data ? t('orders.runtimeDomain.warehouseGoods.articleCount', { count: query.data.total }) : undefined}
          onReset={hasActiveFilters ? () => {
            setSearchInput('');
            changeFilters(DEFAULT_FILTERS);
          } : undefined} />
      </WarehouseFilters>

      {!forecast && query.isLoading && <p role="status" className="py-10 text-center text-sm text-bambu-gray">{copy.loading}</p>}
      {!forecast && query.isError && <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-950/50 p-3 text-sm text-red-300">{copy.error}<Button type="button" size="sm" variant="secondary" onClick={() => void query.refetch()}>{copy.retry}</Button></div>}
      {!forecast && query.isSuccess && query.data.items.length === 0 && <Card><CardContent><p className="py-4 text-center text-sm text-bambu-gray">{copy.empty}</p></CardContent></Card>}
      {selectedArticles.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-auto text-sm text-table-secondary">{t('inventory.bulk.selectionCount', { count: selectedArticles.length })}</span>
          {canEdit && (
            <Button size="sm" variant="secondary" onClick={() => setCheckingIds(selectedArticles.map(article => article.id))}><ClipboardCheck className="h-4 w-4" aria-hidden />{t('common.confirmStockCheck')}</Button>
          )}
        </div>
      )}
      {warehousePage && (
        <WarehouseTable>
          {viewMode === 'table' ? (
          <WarehouseTableScroll label={copy.title} viewportRef={tableViewport}>
            <table aria-busy={query.isPlaceholderData} className="w-full min-w-[800px] text-sm">
              <thead className={tableHeaderClass}>
                <tr className={tableHeaderRowClass}>
                  <WarehouseSelectionHeader checked={selection.all} partial={!selection.all && selection.selected.size > 0} disabled={!selectableIds.length} onChange={selection.toggleAll} />
                  {columns.map((column) => {
                    const direction = sort?.column === column ? sort.direction : null;
                    const Icon = direction === 'asc' ? ArrowUp : direction === 'desc' ? ArrowDown : ArrowUpDown;
                    return (
                      <th
                        key={column}
                        scope="col"
                        className={`${tableHeaderCellClass} select-none ${TEXT_COLUMNS.has(column) ? '' : 'text-center'} ${direction ? 'text-accent-foreground!' : ''}`}
                        aria-sort={direction === 'asc' ? 'ascending' : direction === 'desc' ? 'descending' : undefined}
                      >
                        <Button type="button" variant="unstyled" className="inline-flex items-center gap-1 hover:text-accent-foreground max-[768px]:min-h-[44px]" onClick={() => sortBy(column)}>
                          {labels[column]}
                          <Icon aria-hidden className={`h-3 w-3 shrink-0 ${direction ? '' : 'opacity-30'}`} />
                        </Button>
                      </th>
                    );
                  })}
                  <WarehouseActionHeader />
                </tr>
              </thead>
              {groups.map(group => (
              <tbody key={group.title}>
                {group.title && <WarehouseTableGroupHeading title={group.title} colSpan={columns.length + 2} />}
                {group.items.map(article => {
                  const hasStock = article.stock_source !== 'none';
                  const numeric = (value: string) => hasStock ? quantity(article, value) : '—';
                  const cells: Record<WarehouseArticleSortColumn, ReactNode> = {
                    id: <span className="font-medium text-white">{article.id}</span>,
                    sku: <Button variant="unstyled" className={`${warehouseTableIdentifierClass} rounded text-accent-foreground hover:underline`} onClick={event => { event.stopPropagation(); openDetails(article); }}>{article.sku}</Button>,
                    name: <><Button variant="unstyled" className={`${warehouseTableDescriptionClass} text-left hover:underline`} onClick={event => { event.stopPropagation(); openArticle(article); }}>{article.name}</Button><p className="mt-1 text-xs text-table-secondary">{copy[article.stock_source]} · {article.is_active ? copy.active : copy.archived}</p></>,
                    created_at: warehouseDate(article.created_at),
                    last_used_at: warehouseDate(article.last_used_at),
                    kind: copy[article.kind],
                    physical: <span className="text-white">{numeric(article.balance.physical)}</span>,
                    reserved: numeric(article.balance.reserved),
                    available: <span className={`font-medium ${article.balance.is_low_stock ? 'text-amber-800 dark:text-amber-300' : 'text-accent-foreground'}`}>{numeric(article.balance.available)}</span>,
                    consumed: numeric(article.consumed ?? '0'),
                    remaining: hasStock ? remaining(article) : '—',
                    minimum_stock: numeric(article.minimum_stock),
                    stock_checked_at: warehouseDate(article.stock_checked_at),
                  };
                  return (
                    <Fragment key={article.id}>
                    <tr ref={article.id === focusedId ? focusWarehouseRow : undefined}
                      tabIndex={article.id === focusedId ? -1 : undefined}
                      aria-current={article.id === focusedId ? true : undefined}
                      className={`${warehouseTableRowClass} cursor-pointer text-table-secondary ${article.id === focusedId || selection.selected.has(article.id) ? 'bg-bambu-green/10' : ''}`}
                      onClick={() => openArticle(article)}>
                      <WarehouseSelectionCell checked={selection.selected.has(article.id)} disabled={!article.is_active || !hasStock || query.isPlaceholderData} onChange={checked => selection.toggle(article.id, checked)} />
                      {columns.map(column => (
                        <td key={column} className={`px-4 py-3 align-middle ${TEXT_COLUMNS.has(column) ? '' : 'whitespace-nowrap text-center tabular-nums'} ${column === 'name' ? 'min-w-52' : ''}`}>
                          {cells[column]}
                        </td>
                      ))}
                      <WarehouseRowActions subject={article.sku} actions={rowActions(article, true)} />
                    </tr>
                    {quick?.id === article.id && canEdit && article.is_active && article.stock_source === 'own' && (
                      <tr id={`warehouse-movement-${article.id}`} className="border-b border-bambu-dark-tertiary bg-bambu-dark-secondary">
                        <td colSpan={columns.length + 2} className="p-0">
                          <div className="sticky left-0 w-[min(36rem,calc(100vw-2rem))] p-4">
                            <WarehouseStockPanel key={quick.kind} article={article} canBook quickKind={quick.kind}
                              onBusyChange={setQuickBusy} onCancel={cancelQuick} />
                          </div>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                })}
              </tbody>
              ))}
            </table>
          </WarehouseTableScroll>
          ) : (
            <div className="space-y-4 p-4" aria-busy={query.isPlaceholderData}>
              {groups.map(group => (
                <section key={group.title}>
                  {group.title && <h2 className="mb-2 text-sm font-semibold text-table-secondary">{group.title}</h2>}
                  <div className="grid gap-3 xl:grid-cols-2">
                    {group.items.map(article => (
                      <article key={article.id} className="space-y-3 rounded-lg border border-bambu-dark-tertiary p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <Button variant="unstyled" className="break-all text-left font-mono text-xs text-accent-foreground hover:underline" onClick={() => openDetails(article)}>{article.sku}</Button>
                            <h3><Button variant="unstyled" className="text-left font-semibold text-white hover:underline" onClick={() => openArticle(article)}>{article.name}</Button></h3>
                            <p className="mt-1 text-xs text-table-secondary">{copy[article.kind]} · {copy[article.stock_source]} · {article.is_active ? copy.active : copy.archived}</p>
                          </div>
                          <WarehouseActionMenu subject={article.sku} actions={rowActions(article)} />
                        </div>
                        {article.stock_source !== 'none' && (
                          <dl className="grid grid-cols-2 gap-2 border-t border-bambu-dark-tertiary pt-3 text-sm">
                            <div><dt className="text-table-secondary">{copy.available}</dt><dd className="font-medium text-white">{quantity(article, article.balance.available)}</dd></div>
                            <div><dt className="text-table-secondary">{copy.reserved}</dt><dd className="font-medium text-white">{quantity(article, article.balance.reserved)}</dd></div>
                            <div className="col-span-2"><dt className="text-table-secondary">{t('inventory.remaining')}</dt><dd className="mt-1 max-w-48 [&>div]:ml-0">{remaining(article)}</dd></div>
                          </dl>
                        )}
                      </article>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </WarehouseTable>
      )}
      <ColumnConfigModal isOpen={showColumns} onClose={() => setShowColumns(false)}
        columns={columnConfig.map(column => ({ ...column, label: labels[column.id as WarehouseArticleSortColumn] }))}
        defaultColumns={defaultColumns} onSave={saveColumns} />
      {selected && <WarehouseArticleDetail key={selected.id} id={selected.id} stockOnly={selected.stockOnly} onClose={() => setSelected(null)} />}
      {materialBooking && canEdit && <SmallPartStockDialog partId={materialBooking.partId} quickKind={materialBooking.kind}
        onClose={() => setMaterialBooking(null)} />}
      {editor && (editor.article ? canEdit : canCreate) && (
        <WarehouseArticleEditor article={editor.article} copyFrom={editor.copyFrom} onClose={() => setEditor(null)} />
      )}
      {statusArticle && (statusArticle.is_active ? canArchive : canEdit) && (
        <WarehouseStatusDialog
          action={statusArticle.is_active ? copy.archive : copy.restore}
          subject={`${statusArticle.sku} · ${statusArticle.name}`}
          deactivate={statusArticle.is_active}
          onChange={async () => {
            await warehouseArticlesApi.setActive(statusArticle, !statusArticle.is_active);
            await queryClient.invalidateQueries({ queryKey: ['warehouse-articles'] });
          }}
          onClose={() => setStatusArticle(null)}
        />
      )}
      {canEdit && checkingIds.length > 0 && (
        <WarehouseStockCheckDialog ids={checkingIds} confirm={warehouseArticlesApi.confirmStockCheck} onClose={() => setCheckingIds([])}
          onSaved={async () => {
            selection.clear();
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: ['warehouse-articles'] }),
              queryClient.invalidateQueries({ queryKey: ['small-parts'] }),
            ]);
          }} />
      )}
    </WarehousePage>
  );
}
