import { TablePagination } from '../components/ui/TablePagination';
import { useTablePagination } from '../hooks/useTablePagination';
import { smallPartsText as text, smallPartsLocale } from '../components/warehouse/smallPartsCopy';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Archive,
  Copy,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Boxes,
  ClipboardCheck,
  Columns,
  Download,
  Group,
  Info,
  MapPin,
  Minus,
  Package,
  PackageCheck,
  PackagePlus,
  Pencil,
  Plus,
  Printer,
  RotateCcw,
  TrendingUp,
  Upload,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type RefObject } from 'react';

import { smallPartsApi, type SmallPart } from '../api/smallParts';
import { api } from '../api/client';
import { Card, CardContent } from '../components/Card';
import { ColumnConfigModal, type ColumnConfig } from '../components/ColumnConfigModal';
import { LabelTemplatePickerModal } from '../components/LabelTemplatePickerModal';
import { LocationsModal } from '../components/LocationsModal';
import { MaterialCsvImportModal } from '../components/MaterialCsvImportModal';
import { useAuth } from '../contexts/AuthContext';
import { WarehouseStatusDialog } from '../components/warehouse/WarehouseStatusDialog';
import { Button, IconButton } from '../components/ui';
import {
  WarehouseFilterResults, WarehouseFilters, WarehouseFilterSelect, WarehouseHeader, WarehousePage, WarehouseRemainingSort,
  WarehouseSegment, WarehouseSegments, WarehouseTable, WarehouseTableGroupHeading, WarehouseTableScroll,
  WarehouseToolbar, WarehouseToolbarButton, WarehouseUsageOptions, WarehouseViewOptions, type WarehouseUsageFilter,
} from '../components/warehouse/WarehouseLayout';
import { WarehouseActionHeader, WarehouseRowActions, type WarehouseAction } from '../components/warehouse/WarehouseRowActions';
import { warehouseMetricsClass, warehouseMetricClass, warehouseTableDescriptionClass, warehouseTableIdentifierClass, warehouseTableRowClass } from '../components/warehouse/warehouseStyles';
import {
  tableHeaderCellClass,
  tableHeaderClass,
  tableHeaderRowClass,
} from '../components/ui/tableStyles';
import { SmallPartEditor } from '../components/warehouse/SmallPartEditor';
import { SmallPartStockDialog } from '../components/warehouse/SmallPartStockDialog';
import { useWarehouseCopy } from '../components/warehouse/warehouseGoodsCopy';
import { WarehouseRemaining, WarehouseSelectionCell, WarehouseSelectionHeader, WarehouseStockCheckDialog } from '../components/warehouse/WarehouseStocktake';
import { focusWarehouseRow, groupWarehouseItems, useWarehouseRowTarget, useWarehouseSelection, warehouseDate, warehouseFilterOptions, warehouseUnit } from '../components/warehouse/warehouseTableValues';

type ActiveFilter = 'active' | 'inactive';
type ViewMode = 'table' | 'cards' | 'forecast';
type SortDirection = 'asc' | 'desc';
type SortState = { column: string; direction: SortDirection } | null;

const COLUMN_CONFIG_KEY = 'printops-material-columns';
const SORT_STATE_KEY = 'printops-material-sort';
const REMAINING_COLUMN: ColumnConfig = { id: 'remaining', label: 'inventory.remaining', visible: true };

const DEFAULT_COLUMNS: ColumnConfig[] = [
  { id: 'sku', label: 'sku', visible: true },
  { id: 'name', label: 'name', visible: true },
  { id: 'created_at', label: 'orders.runtimeInterface.inventoryColumns.added', visible: true },
  { id: 'last_used_at', label: 'orders.runtimeInterface.inventoryColumns.lastUsed', visible: true },
  { id: 'category', label: 'category', visible: true },
  { id: 'location', label: 'location', visible: true },
  { id: 'physical', label: 'physical', visible: true },
  { id: 'reserved', label: 'reserved', visible: true },
  { id: 'available', label: 'available', visible: true },
  { id: 'consumed', label: 'inventory.weightUsed', visible: true },
  { id: 'stock_checked_at', label: 'common.stockChecked', visible: true },
  { id: 'minimum_stock', label: 'minimumStock', visible: true },
  { id: 'unit_cost', label: 'unitCost', visible: true },
  { id: 'supplier', label: 'supplier', visible: true },
  REMAINING_COLUMN,
];

const EMPTY_PARTS: SmallPart[] = [];

function materialColumnLabel(label: string, t: TFunction) {
  return t(label.includes('.') ? label : `orders.runtimeDomain.smallParts.${label}`);
}

function loadColumnConfig(): ColumnConfig[] {
  try {
    const stored = localStorage.getItem(COLUMN_CONFIG_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as ColumnConfig[];
      const remaining = parsed.find(column => column.id === 'remaining');
      const columns = parsed.some(column => column.id === 'status')
        ? parsed
          .filter(column => column.id !== 'remaining')
          .map(column => column.id === 'status'
            ? { ...REMAINING_COLUMN, visible: column.visible || remaining?.visible === true }
            : column)
        : parsed;
      const defaultIds = new Set(DEFAULT_COLUMNS.map((column) => column.id));
      const storedIds = new Set(columns.map((column) => column.id));
      return [
        ...columns.filter((column) => defaultIds.has(column.id)),
        ...DEFAULT_COLUMNS.filter((column) => !storedIds.has(column.id)),
      ];
    }
  } catch {
    // Ignore local storage failures.
  }
  return DEFAULT_COLUMNS.map((column) => ({ ...column }));
}

function saveColumnConfig(config: ColumnConfig[]) {
  try {
    localStorage.setItem(COLUMN_CONFIG_KEY, JSON.stringify(config));
  } catch {
    // Ignore local storage failures.
  }
}

function loadSortState(): SortState {
  try {
    const stored = localStorage.getItem(SORT_STATE_KEY);
    if (stored) {
      const sort = JSON.parse(stored) as SortState;
      return sort?.column === 'status' ? { ...sort, column: 'remaining' } : sort;
    }
  } catch {
    // Ignore local storage failures.
  }
  return null;
}

function saveSortState(state: SortState) {
  try {
    if (state) {
      localStorage.setItem(SORT_STATE_KEY, JSON.stringify(state));
    } else {
      localStorage.removeItem(SORT_STATE_KEY);
    }
  } catch {
    // Ignore local storage failures.
  }
}

function quantity(value: string, part: SmallPart): string {
  return new Intl.NumberFormat(smallPartsLocale(), {
    minimumFractionDigits: 0,
    maximumFractionDigits: part.unit.decimal_places,
  }).format(Number(value));
}

function wholeQuantity(value: string): string {
  return new Intl.NumberFormat(smallPartsLocale(), {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(Number(value)));
}

function money(value: string): string {
  return Number(value).toLocaleString(smallPartsLocale(), {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function netPrice(value: string): string {
  return text('netAmount', { amount: Number(value).toLocaleString(smallPartsLocale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 }) });
}

function isNewMaterial(part: SmallPart): boolean {
  return !part.last_used_at && !(Number(part.consumed ?? 0) > 0);
}

function locationLabel(part: SmallPart): string {
  return part.location_id ? text('locationNumber', { id: part.location_id }) : text('noLocation');
}

function matchesQuery(part: SmallPart, query: string): boolean {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return true;
  return [
    part.sku,
    part.name,
    part.category?.name,
    part.description,
    part.search_terms,
  ].some((value) => (value ?? '').toLocaleLowerCase().includes(normalized));
}

const columnSortValues: Record<string, (part: SmallPart) => string | number> = {
  id: (part) => part.id,
  sku: (part) => part.sku.toLocaleLowerCase(),
  name: (part) => part.name.toLocaleLowerCase(),
  category: (part) => (part.category?.name ?? '').toLocaleLowerCase(),
  location: (part) => part.location_id ?? 0,
  physical: (part) => Number(part.balance.physical),
  reserved: (part) => Number(part.balance.reserved),
  available: (part) => Number(part.balance.available),
  created_at: (part) => part.created_at,
  last_used_at: (part) => part.last_used_at ?? '',
  consumed: (part) => Number(part.consumed ?? 0),
  remaining: (part) => Number(part.balance.physical),
  stock_checked_at: (part) => part.stock_checked_at ?? '',
  minimum_stock: (part) => Number(part.minimum_stock),
  unit_cost: (part) => Number(part.unit_cost),
  supplier: (part) => (part.preferred_offer?.supplier.name ?? '').toLocaleLowerCase(),
};

const columnAlignment: Record<string, string> = {
  created_at: 'text-center',
  last_used_at: 'text-center',
  consumed: 'text-center',
  remaining: 'text-center',
  stock_checked_at: 'text-center',
  physical: 'text-center',
  reserved: 'text-center',
  available: 'text-center',
  minimum_stock: 'text-center',
  unit_cost: 'text-center',
  supplier: 'text-center',
};

function MaterialCard({ part, onEdit, onStock }: { part: SmallPart; onEdit?: () => void; onStock?: () => void }) {
  return (
    <article className={`rounded-xl border p-4 ${part.balance.is_low_stock ? 'border-amber-500/60 bg-amber-950/10' : 'border-bambu-dark-tertiary bg-bambu-dark/30'}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-bambu-green">{part.sku}</span>
            {!part.is_active && <span className="rounded-full bg-bambu-dark-tertiary px-2 py-0.5 text-xs text-bambu-gray-light">{text('inactive')}</span>}
            {isNewMaterial(part) && <span className="rounded-full bg-bambu-dark-tertiary px-2 py-0.5 text-xs text-bambu-gray-light">{text('new')}</span>}
            {part.balance.is_low_stock && <span className="rounded-full bg-amber-900/70 px-2 py-0.5 text-xs text-amber-200">{text('reorderLevel')}</span>}
          </div>
          <h2 className="mt-1 font-semibold text-white">{part.name}</h2>
          <p className="mt-1 text-sm text-bambu-gray">{part.category?.name ?? text('noCategory')} · {locationLabel(part)}</p>
        </div>
        <div className="flex gap-2">
          {onEdit && <IconButton label={text('editMaterial')} icon={Pencil} onClick={onEdit} />}
          {onStock && <Button type="button" size="sm" onClick={onStock}>
            <PackagePlus className="h-4 w-4" />{text('postStock')}
          </Button>}
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        <div><p className="text-bambu-gray">{text('physical')}</p><p className="text-white">{quantity(part.balance.physical, part)}</p></div>
        <div><p className="text-bambu-gray">{text('reserved')}</p><p className="text-white">{quantity(part.balance.reserved, part)}</p></div>
        <div className="col-span-2 sm:col-span-1"><p className="text-bambu-gray">{text('available')}</p><p className="font-semibold text-bambu-green-light">{quantity(part.balance.available, part)} {part.unit.label} {text('availableSuffix')}</p></div>
        <div><p className="text-bambu-gray">{text('minimumStock')}</p><p className="text-white">{wholeQuantity(part.minimum_stock)}</p></div>
        <div><p className="text-bambu-gray">{text('standardPrice')}</p><p className="text-white">{money(part.unit_cost)}</p></div>
      </div>
      {part.preferred_offer ? (
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-bambu-dark-tertiary pt-3 text-sm">
          <span className="font-medium text-white">{part.preferred_offer.supplier.name}</span>
          <span className="text-bambu-gray-light">{netPrice(part.preferred_offer.net_price)}</span>
          <span className="text-bambu-gray-light">{text('daysLeadTime', { count: part.preferred_offer.lead_time_days })}</span>
        </div>
      ) : null}
    </article>
  );
}

function MaterialTable({
  items,
  visibleColumns,
  groupByCategory,
  sortState,
  onSort,
  onOpen,
  selection,
  rowActions,
  focusedId,
  viewportRef,
}: {
  items: SmallPart[];
  visibleColumns: string[];
  groupByCategory: boolean;
  sortState: SortState;
  onSort: (column: string) => void;
  onOpen: (part: SmallPart) => void;
  selection: ReturnType<typeof useWarehouseSelection>;
  rowActions: (part: SmallPart) => WarehouseAction[];
  focusedId: number | null;
  viewportRef: RefObject<HTMLDivElement | null>;
}) {
  const { t } = useTranslation();
  const columnLabel = new Map(DEFAULT_COLUMNS.map((column) => [column.id, materialColumnLabel(column.label, t)]));
  columnLabel.set('id', '#');
  const columns = ['id', ...visibleColumns];
  const visibleIds = items.map(part => part.id);
  const visibleSelection = visibleIds.filter(id => selection.selected.has(id)).length;
  const allVisibleSelected = visibleIds.length > 0 && visibleSelection === visibleIds.length;
  const groups = groupWarehouseItems(items, groupByCategory ? part => part.category?.name ?? text('noCategory') : undefined);
  const cell = (part: SmallPart, column: string) => {
    const unit = (value: string) => `${quantity(value, part)} ${warehouseUnit(part.unit_code, t('common.unitShortPiece'), part.unit.label)}`;
    if (column === 'id') return <span className="font-medium text-white">{part.id}</span>;
    if (column === 'sku') return <span className={`${warehouseTableIdentifierClass} text-accent-foreground`}>{part.sku}</span>;
    if (column === 'name') return <Button variant="unstyled" className={`${warehouseTableDescriptionClass} text-left hover:underline`} onClick={event => { event.stopPropagation(); onOpen(part); }}>{part.name}</Button>;
    if (column === 'category') return <span>{part.category?.name ?? text('noCategory')}</span>;
    if (column === 'location') return <span>{locationLabel(part)}</span>;
    if (column === 'physical') return <span className="whitespace-nowrap text-white">{unit(part.balance.physical)}</span>;
    if (column === 'reserved') return <span className="whitespace-nowrap">{unit(part.balance.reserved)}</span>;
    if (column === 'available') return <span className="whitespace-nowrap font-medium text-accent-foreground">{unit(part.balance.available)}</span>;
    if (column === 'minimum_stock') return <span className="whitespace-nowrap">{unit(part.minimum_stock)}</span>;
    if (column === 'created_at' || column === 'last_used_at' || column === 'stock_checked_at') return <span className="whitespace-nowrap">{warehouseDate(part[column])}</span>;
    if (column === 'consumed') return <span className="whitespace-nowrap">{unit(part.consumed ?? '0')}</span>;
    if (column === 'remaining') return <WarehouseRemaining physical={part.balance.physical} consumed={part.consumed ?? '0'} label={unit(part.balance.physical)} />;
    if (column === 'unit_cost') return <span>{money(part.unit_cost)}</span>;
    if (column === 'supplier') return <span>{part.preferred_offer?.supplier.name ?? '-'}</span>;
    return null;
  };

  return (
    <WarehouseTable>
      <WarehouseTableScroll label={text('material')} viewportRef={viewportRef}>
        <table className="w-full min-w-[53rem] text-sm">
          <thead className={tableHeaderClass}>
            <tr className={tableHeaderRowClass}>
              <WarehouseSelectionHeader checked={allVisibleSelected} partial={!allVisibleSelected && visibleSelection > 0}
                onChange={checked => selection.toggleAll(checked, visibleIds)} />
              {columns.map((column) => {
                const sortable = Boolean(columnSortValues[column]);
                const isActive = sortState?.column === column;
                const alignClass = columnAlignment[column] ?? 'text-left';
                return (
                  <th
                    key={column}
                    className={`${tableHeaderCellClass} select-none ${alignClass} ${
                      sortable ? 'cursor-pointer transition-colors hover:text-accent-foreground' : ''
                    } ${isActive ? 'text-accent-foreground!' : ''}`}
                    aria-sort={sortable ? isActive ? sortState.direction === 'asc' ? 'ascending' : 'descending' : 'none' : undefined}
                    onClick={sortable ? () => onSort(column) : undefined}
                  >
                    {sortable ? (
                      <Button type="button" variant="unstyled" className="inline-flex items-center gap-1 max-[768px]:min-h-[44px]">
                        {columnLabel.get(column) ?? column}
                        {isActive
                          ? sortState.direction === 'asc'
                            ? <ArrowUp aria-hidden className="h-3 w-3" />
                            : <ArrowDown aria-hidden className="h-3 w-3" />
                          : <ArrowUpDown aria-hidden className="h-3 w-3 opacity-30" />}
                      </Button>
                    ) : columnLabel.get(column) ?? column}
                  </th>
                );
              })}
              <WarehouseActionHeader />
            </tr>
          </thead>
          {groups.map(group => (
          <tbody key={group.title}>
            {group.title && <WarehouseTableGroupHeading title={group.title} colSpan={columns.length + 2} />}
            {group.items.map((part) => (
              <tr key={part.id} ref={part.id === focusedId ? focusWarehouseRow : undefined}
                tabIndex={part.id === focusedId ? -1 : undefined}
                aria-current={part.id === focusedId ? true : undefined}
                className={`${warehouseTableRowClass} cursor-pointer text-table-secondary ${part.id === focusedId || selection.selected.has(part.id) ? 'bg-bambu-green/10' : ''}`}
                onClick={() => onOpen(part)}>
                <WarehouseSelectionCell checked={selection.selected.has(part.id)} onChange={checked => selection.toggle(part.id, checked)} />
                {columns.map((column) => (
                  <td key={column} className={`px-4 py-3 align-middle ${columnAlignment[column] ?? 'text-left'}`}>{cell(part, column)}</td>
                ))}
                <WarehouseRowActions
                  subject={part.sku}
                  actions={rowActions(part)}
                />
              </tr>
            ))}
          </tbody>
          ))}
        </table>
      </WarehouseTableScroll>
    </WarehouseTable>
  );
}

function MaterialForecast({ items }: { items: SmallPart[] }) {
  const watchlist = [...items]
    .filter((item) => item.balance.is_low_stock || Number(item.balance.available) <= Number(item.minimum_stock) * 1.5)
    .sort((a, b) => Number(a.balance.available) - Number(b.balance.available));

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5 text-bambu-green" />
          <h2 className="text-lg font-semibold text-white">{text('forecast')}</h2>
        </div>
        {watchlist.length === 0 ? (
          <p className="py-10 text-center text-bambu-gray">{text('noCriticalStock')}</p>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {watchlist.map((part) => (
              <div key={part.id} className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark/30 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-xs text-bambu-green">{part.sku}</p>
                    <h3 className="mt-1 font-semibold text-white">{part.name}</h3>
                  </div>
                  <span className={`rounded px-2 py-1 text-xs ${part.balance.is_low_stock ? 'bg-amber-500/20 text-amber-900 dark:text-amber-200' : 'bg-bambu-dark-tertiary text-bambu-gray-light'}`}>
                    {part.balance.is_low_stock ? text('reorder') : text('watch')}
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
                  <div><p className="text-bambu-gray">{text('available')}</p><p className="text-white">{quantity(part.balance.available, part)}</p></div>
                  <div><p className="text-bambu-gray">{text('reorderLevel')}</p><p className="text-white">{wholeQuantity(part.minimum_stock)}</p></div>
                  <div><p className="text-bambu-gray">{text('leadTime')}</p><p className="text-white">{text('days', { count: part.preferred_offer?.lead_time_days ?? '-' })}</p></div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function SmallPartsPage() {
  const { t } = useTranslation();
  const copy = useWarehouseCopy();
  const queryClient = useQueryClient();
  const { focusedId, clearRowTarget } = useWarehouseRowTarget();
  const { hasPermission } = useAuth();
  const canCreate = hasPermission('inventory:create');
  const canUpdate = hasPermission('inventory:update');
  const [targetPartId, setTargetPartId] = useState(() => Number(new URLSearchParams(window.location.search).get('part') ?? 0));
  const [query, setQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('active');
  const [materialFilter, setMaterialFilter] = useState<WarehouseUsageFilter>('all');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [supplierFilter, setSupplierFilter] = useState('');
  const [locationFilter, setLocationFilter] = useState('');
  const [unitFilter, setUnitFilter] = useState('');
  const [groupByCategory, setGroupByCategory] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('table');
  const [sortState, setSortState] = useState<SortState>(loadSortState);
  const [columnConfig, setColumnConfig] = useState<ColumnConfig[]>(loadColumnConfig);
  const localizedDefaultColumns = useMemo(() => DEFAULT_COLUMNS.map(column => ({ ...column, label: materialColumnLabel(column.label, t) })), [t]);
  const localizedColumns = useMemo(() => {
    const labels = new Map(localizedDefaultColumns.map(column => [column.id, column.label]));
    return columnConfig.map(column => ({ ...column, label: labels.get(column.id) ?? column.label }));
  }, [columnConfig, localizedDefaultColumns]);
  const [showColumnModal, setShowColumnModal] = useState(false);
  const [locationsModalOpen, setLocationsModalOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [labelParts, setLabelParts] = useState<SmallPart[] | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [editor, setEditor] = useState<{ part: SmallPart | null; copyFrom?: SmallPart } | null>(null);
  const [statusPart, setStatusPart] = useState<SmallPart | null>(null);
  const [stock, setStock] = useState<{ part: SmallPart; quickKind?: 'receipt' | 'issue' } | null>(null);
  const [checkingIds, setCheckingIds] = useState<number[]>([]);
  const parts = useQuery({
    queryKey: ['small-parts', 'all'],
    queryFn: () => smallPartsApi.listAll(),
  });
  const locations = useQuery({ queryKey: ['warehouse', 'locations'], queryFn: api.getLocations });

  const allItems = parts.data ?? EMPTY_PARTS;
  const locationNames = useMemo(() => new Map(locations.data?.map(location => [location.id, location.name])), [locations.data]);
  const locale = smallPartsLocale();
  const filterOptions = useMemo(() => ({
    categories: warehouseFilterOptions(allItems.flatMap(part => part.category ? [{ value: String(part.category.id), label: part.category.name }] : []), locale),
    suppliers: warehouseFilterOptions(allItems.flatMap(part => part.preferred_offer ? [{ value: String(part.preferred_offer.supplier.id), label: part.preferred_offer.supplier.name }] : []), locale),
    locations: warehouseFilterOptions(allItems.flatMap(part => part.location_id ? [{ value: String(part.location_id), label: locationNames.get(part.location_id) ?? locationLabel(part) }] : []), locale),
    units: warehouseFilterOptions(allItems.map(part => ({ value: part.unit_code, label: part.unit.label })), locale),
  }), [allItems, locale, locationNames]);
  const closeEditor = () => {
    setEditor(null);
    if (targetPartId) {
      const next = new URLSearchParams(window.location.search);
      next.delete('part');
      const search = next.toString();
      window.history.replaceState(null, '', `${window.location.pathname}${search ? `?${search}` : ''}${window.location.hash}`);
      setTargetPartId(0);
    }
  };
  useEffect(() => {
    if (!targetPartId || !allItems.length) return;
    const target = allItems.find((part) => part.id === targetPartId);
    if (target && canUpdate) setEditor({ part: target });
  }, [allItems, canUpdate, targetPartId]);
  const items = useMemo(() => allItems.filter((part) => {
    if (focusedId !== null) return part.id === focusedId;
    if (!matchesQuery(part, query)) return false;
    if (activeFilter === 'active' && !part.is_active) return false;
    if (activeFilter === 'inactive' && part.is_active) return false;
    if (materialFilter === 'used' && isNewMaterial(part)) return false;
    if (materialFilter === 'new' && !isNewMaterial(part)) return false;
    if (materialFilter === 'lowstock' && !part.balance.is_low_stock) return false;
    if (categoryFilter && String(part.category_id) !== categoryFilter) return false;
    if (supplierFilter && String(part.preferred_offer?.supplier.id) !== supplierFilter) return false;
    if (locationFilter && String(part.location_id) !== locationFilter) return false;
    if (unitFilter && part.unit_code !== unitFilter) return false;
    return true;
  }), [activeFilter, allItems, materialFilter, query, categoryFilter, supplierFilter, locationFilter, unitFilter, focusedId]);
  const sortedItems = useMemo(() => {
    if (!sortState) return items;
    const extractor = columnSortValues[sortState.column];
    if (!extractor) return items;
    return [...items].sort((left, right) => {
      const leftValue = extractor(left);
      const rightValue = extractor(right);
      if (leftValue < rightValue) return sortState.direction === 'asc' ? -1 : 1;
      if (leftValue > rightValue) return sortState.direction === 'asc' ? 1 : -1;
      return left.id - right.id;
    });
  }, [items, sortState]);
  const forecastItems = useMemo(() => allItems.filter((part) => part.is_active), [allItems]);
  const groupLabel = groupByCategory ? (part: SmallPart) => part.category?.name ?? text('noCategory') : undefined;
  const tableItems = groupByCategory ? groupWarehouseItems(sortedItems, groupLabel).flatMap(group => group.items) : sortedItems;
  const pagination = useTablePagination(tableItems, JSON.stringify([focusedId, query, materialFilter, activeFilter, categoryFilter, supplierFilter, locationFilter, unitFilter, sortState, groupByCategory]));
  const selection = useWarehouseSelection(viewMode === 'table' ? sortedItems.map(part => part.id) : []);
  const selectedParts = sortedItems.filter(part => selection.selected.has(part.id));
  const openPart = (part: SmallPart) => canUpdate ? setEditor({ part }) : setStock({ part });
  const visibleColumns = useMemo(() => columnConfig.filter((column) => column.visible).map((column) => column.id), [columnConfig]);
  const lowStockCount = allItems.filter((item) => item.is_active && item.balance.is_low_stock).length;
  const reservedCount = allItems.filter((item) => Number(item.balance.reserved) > 0).length;
  const availableCount = allItems.reduce((sum, item) => sum + Math.max(0, Math.round(Number(item.balance.available))), 0);
  const stockValue = allItems.reduce((sum, item) => sum + Math.max(0, Number(item.balance.available)) * Number(item.unit_cost), 0);
  const hasActiveFilters = focusedId !== null || Boolean(query || categoryFilter || supplierFilter || locationFilter || unitFilter)
    || activeFilter !== 'active' || materialFilter !== 'all';

  const resetFilters = () => {
    clearRowTarget();
    setQuery('');
    setActiveFilter('active');
    setMaterialFilter('all');
    setCategoryFilter('');
    setSupplierFilter('');
    setLocationFilter('');
    setUnitFilter('');
  };

  const saveColumns = (config: ColumnConfig[]) => {
    setColumnConfig(config);
    saveColumnConfig(config);
  };

  const handleSort = (column: string) => {
    if (!columnSortValues[column]) return;
    setSortState((previous) => {
      const next: SortState = previous?.column === column
        ? previous.direction === 'asc'
          ? { column, direction: 'desc' }
          : null
        : { column, direction: 'asc' };
      saveSortState(next);
      return next;
    });
  };

  const refreshMaterials = () => {
    queryClient.invalidateQueries({ queryKey: ['small-parts'] });
  };

  const handleExportCsv = async () => {
    setActionMessage(null);
    try {
      await smallPartsApi.exportCsv();
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : text('csvExportFailed'));
    }
  };

  const handleImported = (created: number, updated: number) => {
    setImportModalOpen(false);
    setActionMessage(text('importSummary', { created, updated }));
    refreshMaterials();
  };

  const tableViewport = useRef<HTMLDivElement>(null);
  const showMaterialTable = !parts.isLoading && !parts.isError && viewMode === 'table' && sortedItems.length > 0;
  const footer = showMaterialTable && <TablePagination {...pagination.footer} label={text('material')} viewportRef={tableViewport} />;

  return (
    <WarehousePage footer={footer}>
      <WarehouseHeader icon={Boxes} title={text('material')} description={text('subtitle')}>
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            setActionMessage(null);
            setImportModalOpen(true);
          }}
        >
          <Upload className="h-4 w-4" />{text('importCsv')}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={allItems.length === 0}
          onClick={handleExportCsv}
          title={allItems.length === 0 ? text('noExportMaterials') : undefined}
        >
          <Download className="h-4 w-4" />{text('exportCsv')}
        </Button>
        <Button type="button" variant="secondary" onClick={() => setLocationsModalOpen(true)}>
          <MapPin className="h-4 w-4" />{text('locations')}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={sortedItems.length === 0}
          onClick={() => setLabelParts(sortedItems)}
          title={sortedItems.length === 0 ? text('noLabelMaterials') : undefined}
        >
          <Printer className="h-4 w-4" />{text('printLabels')}
        </Button>
        {canCreate && <Button type="button" onClick={() => setEditor({ part: null })}>
          <Plus className="h-4 w-4" />{text('addMaterial')}
        </Button>}
      </WarehouseHeader>
      {actionMessage ? (
        <p className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-3 py-2 text-sm text-bambu-gray-light">
          {actionMessage}
        </p>
      ) : null}

      <div className={`${warehouseMetricsClass} xl:grid-cols-5`}>
        <div className={warehouseMetricClass}>
          <div className="mb-1 flex items-center gap-2"><Package className="h-4 w-4 text-bambu-green" /><span className="text-xs font-medium uppercase text-bambu-gray">{text('article')}</span></div>
          <div className="text-xl font-bold text-white">{allItems.filter((item) => item.is_active).length}</div>
          <div className="mt-1 text-xs text-bambu-gray">{text('activeMaterials')}</div>
        </div>
        <div className={warehouseMetricClass}>
          <div className="mb-1 flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-amber-300" /><span className="text-xs font-medium uppercase text-bambu-gray">{text('low')}</span></div>
          <div className={`text-xl font-bold ${lowStockCount > 0 ? 'text-amber-300' : 'text-white'}`}>{lowStockCount}</div>
          <div className="mt-1 text-xs text-bambu-gray">{text('belowReorder')}</div>
        </div>
        <div className={warehouseMetricClass}>
          <div className="mb-1 flex items-center gap-2"><PackageCheck className="h-4 w-4 text-sky-300" /><span className="text-xs font-medium uppercase text-bambu-gray">{text('reserved')}</span></div>
          <div className="text-xl font-bold text-white">{reservedCount}</div>
          <div className="mt-1 text-xs text-bambu-gray">{text('withReservation')}</div>
        </div>
        <div className={warehouseMetricClass}>
          <div className="mb-1 flex items-center gap-2"><Boxes className="h-4 w-4 text-bambu-green" /><span className="text-xs font-medium uppercase text-bambu-gray">{text('available')}</span></div>
          <div className="text-xl font-bold text-white">{availableCount.toLocaleString(smallPartsLocale())}</div>
          <div className="mt-1 text-xs text-bambu-gray">{text('wholeUnits')}</div>
        </div>
        <div className={warehouseMetricClass}>
          <div className="mb-1 flex items-center gap-2"><TrendingUp className="h-4 w-4 text-bambu-green" /><span className="text-xs font-medium uppercase text-bambu-gray">{text('value')}</span></div>
          <div className="text-xl font-bold text-white">{stockValue.toLocaleString(smallPartsLocale(), { style: 'currency', currency: 'EUR' })}</div>
          <div className="mt-1 text-xs text-bambu-gray">{text('availableStock')}</div>
        </div>
      </div>

      <WarehouseToolbar
        searchLabel={text('searchMaterials')}
        placeholder={text('searchPlaceholder')}
        value={query}
        onSearch={value => { clearRowTarget(); setQuery(value); }}
        hideSearch={viewMode === 'forecast'}
      >
        {viewMode === 'table' && <WarehouseToolbarButton label={text('columns')} icon={Columns} onClick={() => setShowColumnModal(true)} />}
        {viewMode !== 'forecast' && (
          <>
            <WarehouseToolbarButton label={t('inventory.groupSimilar')} icon={Group} pressed={groupByCategory} onClick={() => setGroupByCategory(value => !value)} />
            <WarehouseRemainingSort direction={sortState?.column === 'remaining' ? sortState.direction : undefined} onClick={() => handleSort('remaining')} />
          </>
        )}
        <WarehouseViewOptions view={viewMode} onChange={setViewMode} options={['table', 'cards', 'forecast']} />
      </WarehouseToolbar>

      <WarehouseFilters hidden={viewMode === 'forecast'}>
        <WarehouseSegments label={text('status')}>
          <WarehouseSegment active={activeFilter === 'active'} onClick={() => { clearRowTarget(); setActiveFilter('active'); }}>
            <Package aria-hidden className="h-3.5 w-3.5" />{text('active')}
          </WarehouseSegment>
          <WarehouseSegment active={activeFilter === 'inactive'} onClick={() => { clearRowTarget(); setActiveFilter('inactive'); }}>
            <Archive aria-hidden className="h-3.5 w-3.5" />{text('inactive')}
          </WarehouseSegment>
        </WarehouseSegments>
        <div aria-hidden="true" className="hidden h-5 w-px bg-bambu-dark-tertiary sm:block" />
        <WarehouseUsageOptions value={materialFilter} onChange={value => { clearRowTarget(); setMaterialFilter(value); }} />
        <div className="grid w-full grid-cols-2 gap-2 sm:w-auto sm:min-w-60 sm:flex-1 xl:min-w-96 xl:grid-cols-4">
          <WarehouseFilterSelect label={text('category')} value={categoryFilter} onChange={value => { clearRowTarget(); setCategoryFilter(value); }} options={filterOptions.categories} />
          <WarehouseFilterSelect label={text('supplier')} value={supplierFilter} onChange={value => { clearRowTarget(); setSupplierFilter(value); }} options={filterOptions.suppliers} />
          <WarehouseFilterSelect label={text('location')} value={locationFilter} onChange={value => { clearRowTarget(); setLocationFilter(value); }} options={filterOptions.locations} />
          <WarehouseFilterSelect label={text('unit')} value={unitFilter} onChange={value => { clearRowTarget(); setUnitFilter(value); }} options={filterOptions.units} />
        </div>
        <WarehouseFilterResults total={parts.isSuccess ? text('materialCount', { count: sortedItems.length }) : undefined}
          onReset={hasActiveFilters ? resetFilters : undefined} />
      </WarehouseFilters>

      {parts.isLoading && <p className="py-10 text-center text-bambu-gray">{text('loadingMaterial')}</p>}
      {parts.isError && <p role="alert" className="rounded-lg bg-red-950/50 p-3 text-red-300">{text('loadMaterialFailed')}</p>}
      {!parts.isLoading && !parts.isError && viewMode !== 'forecast' && !sortedItems.length && <p className="py-10 text-center text-bambu-gray">{text('noMaterial')}</p>}
      {!parts.isLoading && !parts.isError && viewMode === 'forecast' && <MaterialForecast items={forecastItems} />}
      {!parts.isLoading && !parts.isError && viewMode === 'cards' && sortedItems.length > 0 && (
        <div className="space-y-4">
          {groupWarehouseItems(sortedItems, groupByCategory ? part => part.category?.name ?? text('noCategory') : undefined).map(group => (
            <section key={group.title}>
              {group.title && <h2 className="mb-2 text-sm font-semibold text-table-secondary">{group.title}</h2>}
              <div className="grid gap-3 xl:grid-cols-2">
                {group.items.map(part => (
                  <MaterialCard key={part.id} part={part} onEdit={canUpdate ? () => setEditor({ part }) : undefined} onStock={canUpdate ? () => setStock({ part }) : undefined} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
      {showMaterialTable && (
        <>
        {selectedParts.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="mr-auto text-sm text-table-secondary">{t('inventory.bulk.selectionCount', { count: selectedParts.length })}</span>
            <Button size="sm" variant="secondary" onClick={() => setLabelParts(selectedParts)}><Printer className="h-4 w-4" aria-hidden />{text('printLabels')}</Button>
            {canUpdate && selectedParts.every(part => part.is_active) && (
              <Button size="sm" variant="secondary" onClick={() => setCheckingIds(selectedParts.map(part => part.id))}><ClipboardCheck className="h-4 w-4" aria-hidden />{t('common.confirmStockCheck')}</Button>
            )}
          </div>
        )}
        <MaterialTable
          items={pagination.rows}
          viewportRef={tableViewport}
          visibleColumns={visibleColumns}
          groupByCategory={groupByCategory}
          sortState={sortState}
          onSort={handleSort}
          onOpen={openPart}
          selection={selection}
          focusedId={focusedId}
          rowActions={(part) => [
            ...(canUpdate ? [
              { label: text('editMaterial'), icon: Pencil, onSelect: () => setEditor({ part }) },
              { label: text('stock'), icon: PackagePlus, onSelect: () => setStock({ part }) },
              ...(part.is_active ? [
                { label: copy.receipt, icon: Plus, onSelect: () => setStock({ part, quickKind: 'receipt' }) },
                { label: copy.issue, icon: Minus, onSelect: () => setStock({ part, quickKind: 'issue' }) },
                { label: t('common.confirmStockCheck'), icon: ClipboardCheck, onSelect: () => setCheckingIds([part.id]) },
              ] : []),
            ] : [{ label: t('projects.viewDetails'), icon: Info, onSelect: () => openPart(part) }]),
            ...(canCreate ? [{ label: t('common.duplicate'), icon: Copy, onSelect: () => setEditor({ part: null, copyFrom: part }) }] : []),
            { label: text('printLabels'), icon: Printer, onSelect: () => setLabelParts([part]) },
            ...(canUpdate ? [{
              label: t(part.is_active ? 'common.disable' : 'common.enable'),
              icon: part.is_active ? Archive : RotateCcw,
              onSelect: () => setStatusPart(part),
            }] : []),
          ]}
        />
        </>
      )}

      {editor && (editor.part ? canUpdate : canCreate) && (
        <SmallPartEditor part={editor.part} copyFrom={editor.copyFrom} canEditOffers={canUpdate} onClose={closeEditor} />
      )}
      {statusPart && canUpdate && (
        <WarehouseStatusDialog
          action={t(statusPart.is_active ? 'common.disable' : 'common.enable')}
          subject={`${statusPart.sku} · ${statusPart.name}`}
          deactivate={statusPart.is_active}
          onChange={async () => {
            await smallPartsApi.update(statusPart.id, { is_active: !statusPart.is_active });
            await refreshMaterials();
          }}
          onClose={() => setStatusPart(null)}
        />
      )}
      {stock && <SmallPartStockDialog part={stock.part} quickKind={stock.quickKind} readOnly={!canUpdate} onClose={() => setStock(null)} />}
      {canUpdate && checkingIds.length > 0 && (
        <WarehouseStockCheckDialog ids={checkingIds} confirm={smallPartsApi.confirmStockCheck} onClose={() => setCheckingIds([])}
          onSaved={async () => {
            selection.clear();
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: ['small-parts'] }),
              queryClient.invalidateQueries({ queryKey: ['warehouse-articles'] }),
            ]);
          }} />
      )}
      {importModalOpen && (
        <MaterialCsvImportModal
          onClose={() => setImportModalOpen(false)}
          onImported={handleImported}
        />
      )}
      {labelParts && (
        <LabelTemplatePickerModal
          isOpen
          onClose={() => setLabelParts(null)}
          availableMaterials={labelParts}
          initialSelectedIds={labelParts.map((part) => part.id)}
          resourceType="material"
        />
      )}
      <ColumnConfigModal
        isOpen={showColumnModal}
        onClose={() => setShowColumnModal(false)}
        columns={localizedColumns}
        defaultColumns={localizedDefaultColumns}
        onSave={saveColumns}
      />
      {locationsModalOpen && (
        <LocationsModal
          open={locationsModalOpen}
          onClose={() => {
            setLocationsModalOpen(false);
            refreshMaterials();
          }}
        />
      )}
    </WarehousePage>
  );
}
