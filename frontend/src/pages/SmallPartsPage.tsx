import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  Archive,
  Boxes,
  Columns,
  LayoutGrid,
  Package,
  PackageCheck,
  PackagePlus,
  Pencil,
  Plus,
  Search,
  TableProperties,
  TrendingUp,
  X,
} from 'lucide-react';
import { useMemo, useState } from 'react';

import { smallPartsApi, type SmallPart } from '../api/smallParts';
import { Card, CardContent } from '../components/Card';
import { ColumnConfigModal, type ColumnConfig } from '../components/ColumnConfigModal';
import { Button, IconButton, TextField } from '../components/ui';
import {
  tableHeaderActionCellClass,
  tableHeaderCellClass,
  tableHeaderClass,
  tableHeaderRowClass,
} from '../components/ui/tableStyles';
import { SmallPartEditor } from '../components/warehouse/SmallPartEditor';
import { SmallPartStockDialog } from '../components/warehouse/SmallPartStockDialog';

type ActiveFilter = 'active' | 'inactive';
type MaterialFilter = 'all' | 'new' | 'lowstock';
type ViewMode = 'table' | 'cards' | 'forecast';

const COLUMN_CONFIG_KEY = 'printops-material-columns';

const DEFAULT_COLUMNS: ColumnConfig[] = [
  { id: 'sku', label: 'Artikelnummer', visible: true },
  { id: 'name', label: 'Bezeichnung', visible: true },
  { id: 'category', label: 'Kategorie', visible: true },
  { id: 'location', label: 'Lagerort', visible: true },
  { id: 'physical', label: 'Physisch', visible: true },
  { id: 'reserved', label: 'Reserviert', visible: true },
  { id: 'available', label: 'Verfügbar', visible: true },
  { id: 'minimum_stock', label: 'Mindestbestand', visible: true },
  { id: 'unit_cost', label: 'Einzelpreis', visible: true },
  { id: 'supplier', label: 'Lieferant', visible: true },
  { id: 'status', label: 'Status', visible: true },
];

const EMPTY_PARTS: SmallPart[] = [];

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

function quantity(value: string, part: SmallPart): string {
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: part.unit.decimal_places,
  }).format(Number(value));
}

function wholeQuantity(value: string): string {
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(Number(value)));
}

function money(value: string): string {
  return Number(value).toLocaleString('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function netPrice(value: string): string {
  return `${Number(value).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} € netto`;
}

function isNewMaterial(part: SmallPart): boolean {
  return Number(part.balance.physical) === 0 && Number(part.balance.reserved) === 0;
}

function locationLabel(part: SmallPart): string {
  return part.location_id ? `Lagerort #${part.location_id}` : 'Kein Lagerort';
}

function statusLabels(part: SmallPart): string[] {
  const labels: string[] = [];
  if (!part.is_active) labels.push('Inaktiv');
  if (isNewMaterial(part)) labels.push('Neu');
  if (part.balance.is_low_stock) labels.push('Niedrig');
  if (labels.length === 0) labels.push('OK');
  return labels;
}

function MaterialCard({ part, onEdit, onStock }: { part: SmallPart; onEdit: () => void; onStock: () => void }) {
  return (
    <article className={`rounded-xl border p-4 ${part.balance.is_low_stock ? 'border-amber-500/60 bg-amber-950/10' : 'border-bambu-dark-tertiary bg-bambu-dark/30'}`}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-bambu-green">{part.sku}</span>
            {!part.is_active && <span className="rounded-full bg-bambu-dark-tertiary px-2 py-0.5 text-xs text-bambu-gray-light">Inaktiv</span>}
            {isNewMaterial(part) && <span className="rounded-full bg-bambu-dark-tertiary px-2 py-0.5 text-xs text-bambu-gray-light">Neu</span>}
            {part.balance.is_low_stock && <span className="rounded-full bg-amber-900/70 px-2 py-0.5 text-xs text-amber-200">Meldebestand</span>}
          </div>
          <h2 className="mt-1 font-semibold text-white">{part.name}</h2>
          <p className="mt-1 text-sm text-bambu-gray">{part.category?.name ?? 'Ohne Kategorie'} · {locationLabel(part)}</p>
        </div>
        <div className="flex gap-2">
          <IconButton label="Material bearbeiten" icon={Pencil} onClick={onEdit} />
          <Button type="button" size="sm" onClick={onStock}>
            <PackagePlus className="h-4 w-4" /> Bestand buchen
          </Button>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        <div><p className="text-bambu-gray">Physisch</p><p className="text-white">{quantity(part.balance.physical, part)}</p></div>
        <div><p className="text-bambu-gray">Reserviert</p><p className="text-white">{quantity(part.balance.reserved, part)}</p></div>
        <div className="col-span-2 sm:col-span-1"><p className="text-bambu-gray">Verfügbar</p><p className="font-semibold text-bambu-green-light">{quantity(part.balance.available, part)} {part.unit.label} verfügbar</p></div>
        <div><p className="text-bambu-gray">Mindestbestand</p><p className="text-white">{wholeQuantity(part.minimum_stock)}</p></div>
        <div><p className="text-bambu-gray">Standardpreis</p><p className="text-white">{money(part.unit_cost)}</p></div>
      </div>
      {part.preferred_offer ? (
        <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-bambu-dark-tertiary pt-3 text-sm">
          <span className="font-medium text-white">{part.preferred_offer.supplier.name}</span>
          <span className="text-bambu-gray-light">{netPrice(part.preferred_offer.net_price)}</span>
          <span className="text-bambu-gray-light">{part.preferred_offer.lead_time_days} Tage Lieferzeit</span>
        </div>
      ) : null}
    </article>
  );
}

function MaterialTable({
  items,
  visibleColumns,
  onEdit,
  onStock,
}: {
  items: SmallPart[];
  visibleColumns: string[];
  onEdit: (part: SmallPart) => void;
  onStock: (part: SmallPart) => void;
}) {
  const columnLabel = new Map(DEFAULT_COLUMNS.map((column) => [column.id, column.label]));
  const cell = (part: SmallPart, column: string) => {
    if (column === 'sku') return <span className="font-mono text-xs text-bambu-green">{part.sku}</span>;
    if (column === 'name') return <span className="font-medium text-white">{part.name}</span>;
    if (column === 'category') return <span>{part.category?.name ?? 'Ohne Kategorie'}</span>;
    if (column === 'location') return <span>{locationLabel(part)}</span>;
    if (column === 'physical') return <span className="text-white">{quantity(part.balance.physical, part)}</span>;
    if (column === 'reserved') return <span>{quantity(part.balance.reserved, part)}</span>;
    if (column === 'available') return <span className="font-medium text-bambu-green-light">{quantity(part.balance.available, part)}</span>;
    if (column === 'minimum_stock') return <span>{wholeQuantity(part.minimum_stock)}</span>;
    if (column === 'unit_cost') return <span>{money(part.unit_cost)}</span>;
    if (column === 'supplier') return <span>{part.preferred_offer?.supplier.name ?? '-'}</span>;
    if (column === 'status') {
      return (
        <div className="flex flex-wrap gap-1">
          {statusLabels(part).map((label) => (
            <span key={label} className={`rounded px-1.5 py-0.5 text-xs ${label === 'Niedrig' ? 'bg-amber-500/20 text-amber-200' : 'bg-bambu-dark-tertiary text-bambu-gray-light'}`}>
              {label}
            </span>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="overflow-hidden rounded-lg border border-bambu-dark-tertiary">
      <table className="w-full text-sm">
        <thead className={tableHeaderClass}>
          <tr className={tableHeaderRowClass}>
            {visibleColumns.map((column) => (
              <th key={column} className={tableHeaderCellClass}>{columnLabel.get(column) ?? column}</th>
            ))}
            <th className={tableHeaderActionCellClass}>Aktionen</th>
          </tr>
        </thead>
        <tbody>
          {items.map((part) => (
            <tr key={part.id} className="border-b border-bambu-dark-tertiary/50 text-bambu-gray hover:bg-bambu-dark-tertiary/30">
              {visibleColumns.map((column) => (
                <td key={column} className="px-4 py-3 align-middle">{cell(part, column)}</td>
              ))}
              <td className="px-4 py-3">
                <div className="flex items-center justify-end gap-1">
                  <IconButton label="Material bearbeiten" icon={Pencil} onClick={() => onEdit(part)} />
                  <Button type="button" size="sm" variant="secondary" onClick={() => onStock(part)}>
                    <PackagePlus className="h-4 w-4" /> Bestand
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
          <h2 className="text-lg font-semibold text-white">Bestandsprognose</h2>
        </div>
        {watchlist.length === 0 ? (
          <p className="py-10 text-center text-bambu-gray">Keine kritischen Materialbestände.</p>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {watchlist.map((part) => (
              <div key={part.id} className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark/30 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-mono text-xs text-bambu-green">{part.sku}</p>
                    <h3 className="mt-1 font-semibold text-white">{part.name}</h3>
                  </div>
                  <span className={`rounded px-2 py-1 text-xs ${part.balance.is_low_stock ? 'bg-amber-500/20 text-amber-200' : 'bg-bambu-dark-tertiary text-bambu-gray-light'}`}>
                    {part.balance.is_low_stock ? 'Nachbestellen' : 'Beobachten'}
                  </span>
                </div>
                <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
                  <div><p className="text-bambu-gray">Verfügbar</p><p className="text-white">{quantity(part.balance.available, part)}</p></div>
                  <div><p className="text-bambu-gray">Meldebestand</p><p className="text-white">{wholeQuantity(part.minimum_stock)}</p></div>
                  <div><p className="text-bambu-gray">Lieferzeit</p><p className="text-white">{part.preferred_offer?.lead_time_days ?? '-'} Tage</p></div>
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
  const [query, setQuery] = useState('');
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('active');
  const [materialFilter, setMaterialFilter] = useState<MaterialFilter>('all');
  const [viewMode, setViewMode] = useState<ViewMode>('cards');
  const [columnConfig, setColumnConfig] = useState<ColumnConfig[]>(loadColumnConfig);
  const [showColumnModal, setShowColumnModal] = useState(false);
  const [editorPart, setEditorPart] = useState<SmallPart | null | undefined>(undefined);
  const [stockPart, setStockPart] = useState<SmallPart | null>(null);
  const parts = useQuery({
    queryKey: ['small-parts', { q: query }],
    queryFn: () => smallPartsApi.list({ q: query, limit: 200 }),
  });

  const allItems = parts.data?.items ?? EMPTY_PARTS;
  const items = useMemo(() => allItems.filter((part) => {
    if (activeFilter === 'active' && !part.is_active) return false;
    if (activeFilter === 'inactive' && part.is_active) return false;
    if (materialFilter === 'new' && !isNewMaterial(part)) return false;
    if (materialFilter === 'lowstock' && !part.balance.is_low_stock) return false;
    return true;
  }), [activeFilter, allItems, materialFilter]);
  const visibleColumns = useMemo(() => columnConfig.filter((column) => column.visible).map((column) => column.id), [columnConfig]);
  const lowStockCount = allItems.filter((item) => item.is_active && item.balance.is_low_stock).length;
  const reservedCount = allItems.filter((item) => Number(item.balance.reserved) > 0).length;
  const availableCount = allItems.reduce((sum, item) => sum + Math.max(0, Math.round(Number(item.balance.available))), 0);
  const stockValue = allItems.reduce((sum, item) => sum + Math.max(0, Number(item.balance.available)) * Number(item.unit_cost), 0);
  const hasActiveFilters = query || activeFilter !== 'active' || materialFilter !== 'all';

  const resetFilters = () => {
    setQuery('');
    setActiveFilter('active');
    setMaterialFilter('all');
  };

  const saveColumns = (config: ColumnConfig[]) => {
    setColumnConfig(config);
    saveColumnConfig(config);
  };

  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold text-white">
            <Boxes className="h-7 w-7 text-bambu-green" /> Material
          </h1>
          <p className="mt-1 text-bambu-gray">Zukaufteile, Hardware und Verbrauchsmaterial mit geprüftem Bestand.</p>
        </div>
        <Button type="button" onClick={() => setEditorPart(null)}>
          <Plus className="h-4 w-4" /> Material hinzufügen
        </Button>
      </header>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
        <div className="rounded-lg bg-bambu-dark-secondary p-4">
          <div className="mb-1 flex items-center gap-2"><Package className="h-4 w-4 text-bambu-green" /><span className="text-xs font-medium uppercase text-bambu-gray">Artikel</span></div>
          <div className="text-xl font-bold text-white">{allItems.filter((item) => item.is_active).length}</div>
          <div className="mt-1 text-xs text-bambu-gray">aktive Materialien</div>
        </div>
        <div className="rounded-lg bg-bambu-dark-secondary p-4">
          <div className="mb-1 flex items-center gap-2"><AlertTriangle className="h-4 w-4 text-amber-300" /><span className="text-xs font-medium uppercase text-bambu-gray">Niedrig</span></div>
          <div className={`text-xl font-bold ${lowStockCount > 0 ? 'text-amber-300' : 'text-white'}`}>{lowStockCount}</div>
          <div className="mt-1 text-xs text-bambu-gray">unter Meldebestand</div>
        </div>
        <div className="rounded-lg bg-bambu-dark-secondary p-4">
          <div className="mb-1 flex items-center gap-2"><PackageCheck className="h-4 w-4 text-sky-300" /><span className="text-xs font-medium uppercase text-bambu-gray">Reserviert</span></div>
          <div className="text-xl font-bold text-white">{reservedCount}</div>
          <div className="mt-1 text-xs text-bambu-gray">mit Reservierung</div>
        </div>
        <div className="rounded-lg bg-bambu-dark-secondary p-4">
          <div className="mb-1 flex items-center gap-2"><Boxes className="h-4 w-4 text-bambu-green" /><span className="text-xs font-medium uppercase text-bambu-gray">Verfügbar</span></div>
          <div className="text-xl font-bold text-white">{availableCount.toLocaleString('de-DE')}</div>
          <div className="mt-1 text-xs text-bambu-gray">ganze Einheiten</div>
        </div>
        <div className="rounded-lg bg-bambu-dark-secondary p-4">
          <div className="mb-1 flex items-center gap-2"><TrendingUp className="h-4 w-4 text-bambu-green" /><span className="text-xs font-medium uppercase text-bambu-gray">Wert</span></div>
          <div className="text-xl font-bold text-white">{stockValue.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</div>
          <div className="mt-1 text-xs text-bambu-gray">verfügbarer Bestand</div>
        </div>
      </div>

      <div className="flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <div className={`relative flex-1 max-w-md ${viewMode === 'forecast' ? 'invisible pointer-events-none' : ''}`}>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-bambu-gray/50" />
          <TextField
            type="search"
            aria-label="Material durchsuchen"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Artikelnummer, Bezeichnung, Kategorie …"
            className="w-full pl-10 pr-8"
          />
          {query ? (
            <button type="button" onClick={() => setQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-bambu-gray hover:text-white" aria-label="Suche löschen">
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          {viewMode === 'table' ? (
            <button
              type="button"
              onClick={() => setShowColumnModal(true)}
              className="flex items-center gap-1.5 rounded-lg border border-bambu-dark-tertiary px-3 py-1.5 text-sm font-medium text-bambu-gray transition-colors hover:bg-bambu-dark-tertiary"
              title="Spalten konfigurieren"
            >
              <Columns className="h-4 w-4" />
              <span className="hidden sm:inline">Spalten</span>
            </button>
          ) : null}
          <div className="flex overflow-hidden rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-primary">
            <button type="button" onClick={() => setViewMode('table')} className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium transition-colors ${viewMode === 'table' ? 'bg-bambu-green text-white' : 'text-bambu-gray hover:bg-bambu-dark-tertiary'}`}>
              <TableProperties className="h-4 w-4" /><span className="hidden sm:inline">Tabelle</span>
            </button>
            <button type="button" onClick={() => setViewMode('cards')} className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium transition-colors ${viewMode === 'cards' ? 'bg-bambu-green text-white' : 'text-bambu-gray hover:bg-bambu-dark-tertiary'}`}>
              <LayoutGrid className="h-4 w-4" /><span className="hidden sm:inline">Karten</span>
            </button>
            <button type="button" onClick={() => setViewMode('forecast')} className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium transition-colors ${viewMode === 'forecast' ? 'bg-bambu-green text-white' : 'text-bambu-gray hover:bg-bambu-dark-tertiary'}`}>
              <TrendingUp className="h-4 w-4" /><span className="hidden sm:inline">Bestandsprognose</span>
            </button>
          </div>
        </div>
      </div>

      <div className={`flex flex-wrap items-center gap-2 ${viewMode === 'forecast' ? 'hidden' : ''}`}>
        <div className="flex overflow-hidden rounded-lg border border-bambu-dark-tertiary">
          <button type="button" onClick={() => setActiveFilter('active')} className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${activeFilter === 'active' ? 'bg-bambu-green/20 text-bambu-green' : 'text-bambu-gray hover:bg-bambu-dark-tertiary'}`}>
            <Package className="h-3.5 w-3.5" /> Aktiv
          </button>
          <button type="button" onClick={() => setActiveFilter('inactive')} className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${activeFilter === 'inactive' ? 'bg-bambu-green/20 text-bambu-green' : 'text-bambu-gray hover:bg-bambu-dark-tertiary'}`}>
            <Archive className="h-3.5 w-3.5" /> Inaktiv
          </button>
        </div>
        <div className="h-5 w-px bg-bambu-dark-tertiary" />
        <div className="flex overflow-hidden rounded-lg border border-bambu-dark-tertiary">
          <button type="button" onClick={() => setMaterialFilter('all')} className={`px-3 py-1.5 text-xs font-medium transition-colors ${materialFilter === 'all' ? 'bg-bambu-green/20 text-bambu-green' : 'text-bambu-gray hover:bg-bambu-dark-tertiary'}`}>Alle</button>
          <button type="button" onClick={() => setMaterialFilter('new')} className={`px-3 py-1.5 text-xs font-medium transition-colors ${materialFilter === 'new' ? 'bg-bambu-green/20 text-bambu-green' : 'text-bambu-gray hover:bg-bambu-dark-tertiary'}`}>Neu</button>
          <button type="button" onClick={() => setMaterialFilter('lowstock')} className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${materialFilter === 'lowstock' ? 'bg-amber-500/20 text-amber-200' : 'text-bambu-gray hover:bg-bambu-dark-tertiary'}`}>
            <AlertTriangle className="h-3.5 w-3.5" /> Niedrig Bestand
          </button>
        </div>
        {hasActiveFilters ? (
          <>
            <div className="h-5 w-px bg-bambu-dark-tertiary" />
            <button type="button" onClick={resetFilters} className="flex items-center gap-1 text-xs text-bambu-gray transition-colors hover:text-bambu-green">
              <X className="h-3.5 w-3.5" /> Filter zurücksetzen
            </button>
          </>
        ) : null}
        <span className="ml-auto text-xs text-bambu-gray">{items.length} Materialien</span>
      </div>

      {parts.isLoading && <p className="py-10 text-center text-bambu-gray">Material wird geladen …</p>}
      {parts.isError && <p role="alert" className="rounded-lg bg-red-950/50 p-3 text-red-300">Material konnte nicht geladen werden.</p>}
      {!parts.isLoading && !parts.isError && viewMode !== 'forecast' && !items.length && <p className="py-10 text-center text-bambu-gray">Noch kein passendes Material vorhanden.</p>}
      {!parts.isLoading && !parts.isError && viewMode === 'forecast' && <MaterialForecast items={items} />}
      {!parts.isLoading && !parts.isError && viewMode === 'cards' && items.length > 0 && (
        <div className="grid gap-3 xl:grid-cols-2">
          {items.map((part) => (
            <MaterialCard key={part.id} part={part} onEdit={() => setEditorPart(part)} onStock={() => setStockPart(part)} />
          ))}
        </div>
      )}
      {!parts.isLoading && !parts.isError && viewMode === 'table' && items.length > 0 && (
        <MaterialTable items={items} visibleColumns={visibleColumns} onEdit={setEditorPart} onStock={setStockPart} />
      )}

      {editorPart !== undefined && <SmallPartEditor part={editorPart} onClose={() => setEditorPart(undefined)} />}
      {stockPart && <SmallPartStockDialog part={stockPart} onClose={() => setStockPart(null)} />}
      <ColumnConfigModal
        isOpen={showColumnModal}
        onClose={() => setShowColumnModal(false)}
        columns={columnConfig}
        defaultColumns={DEFAULT_COLUMNS}
        onSave={saveColumns}
      />
    </div>
  );
}
