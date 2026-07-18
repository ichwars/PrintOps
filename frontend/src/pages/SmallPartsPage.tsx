import { useQuery } from '@tanstack/react-query';
import { Boxes, PackagePlus, Pencil, Plus, Search } from 'lucide-react';
import { useState } from 'react';

import { smallPartsApi, type SmallPart } from '../api/smallParts';
import { Card, CardContent } from '../components/Card';
import { SmallPartEditor } from '../components/warehouse/SmallPartEditor';
import { SmallPartStockDialog } from '../components/warehouse/SmallPartStockDialog';

function quantity(value: string, part: SmallPart): string {
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: part.unit.decimal_places,
  }).format(Number(value));
}

export function SmallPartsPage() {
  const [query, setQuery] = useState('');
  const [lowStock, setLowStock] = useState(false);
  const [editorPart, setEditorPart] = useState<SmallPart | null | undefined>(undefined);
  const [stockPart, setStockPart] = useState<SmallPart | null>(null);
  const parts = useQuery({
    queryKey: ['small-parts', { q: query, low_stock: lowStock }],
    queryFn: () => smallPartsApi.list({ q: query, low_stock: lowStock, limit: 100 }),
  });
  const items = parts.data?.items ?? [];

  return (
    <div className="space-y-6 p-4 md:p-8">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="flex items-center gap-3 text-2xl font-bold text-white">
            <Boxes className="h-7 w-7 text-bambu-green" /> Kleinteile
          </h1>
          <p className="mt-1 text-bambu-gray">Zukaufteile, Hardware und Verbrauchsmaterial mit geprüftem Bestand.</p>
        </div>
        <button
          type="button"
          onClick={() => setEditorPart(null)}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-bambu-green px-4 py-2 text-sm font-medium text-white"
        >
          <Plus className="h-4 w-4" /> Kleinteil anlegen
        </button>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card><CardContent><p className="text-sm text-bambu-gray">Artikel</p><p className="mt-1 text-2xl font-semibold text-white">{parts.data?.total ?? 0}</p></CardContent></Card>
        <Card><CardContent><p className="text-sm text-bambu-gray">Niedriger Bestand</p><p className="mt-1 text-2xl font-semibold text-amber-300">{items.filter((item) => item.balance.is_low_stock).length}</p></CardContent></Card>
        <Card><CardContent><p className="text-sm text-bambu-gray">Reservierungen</p><p className="mt-1 text-2xl font-semibold text-white">{items.filter((item) => Number(item.balance.reserved) > 0).length}</p></CardContent></Card>
      </div>

      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            <label className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
              <input
                type="search"
                aria-label="Kleinteile durchsuchen"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Artikelnummer, Bezeichnung, Kategorie …"
                className="w-full rounded-lg border border-gray-600 bg-gray-800 py-2 pl-9 pr-3 text-white outline-none focus:border-bambu-green"
              />
            </label>
            <label className="flex min-h-10 items-center gap-2 rounded-lg border border-gray-700 px-3 text-sm text-gray-200">
              <input type="checkbox" checked={lowStock} onChange={(event) => setLowStock(event.target.checked)} /> Nur niedriger Bestand
            </label>
          </div>

          {parts.isLoading && <p className="py-10 text-center text-bambu-gray">Kleinteile werden geladen …</p>}
          {parts.isError && <p role="alert" className="rounded-lg bg-red-950/50 p-3 text-red-300">Kleinteile konnten nicht geladen werden.</p>}
          {!parts.isLoading && !items.length && <p className="py-10 text-center text-bambu-gray">Noch keine passenden Kleinteile vorhanden.</p>}
          <div className="grid gap-3 xl:grid-cols-2">
            {items.map((part) => (
              <article key={part.id} className={`rounded-xl border p-4 ${part.balance.is_low_stock ? 'border-amber-500/60 bg-amber-950/10' : 'border-gray-700 bg-gray-900/30'}`}>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-bambu-green">{part.sku}</span>
                      {!part.is_active && <span className="rounded-full bg-gray-700 px-2 py-0.5 text-xs text-gray-300">Inaktiv</span>}
                      {part.balance.is_low_stock && <span className="rounded-full bg-amber-900/70 px-2 py-0.5 text-xs text-amber-200">Meldebestand</span>}
                    </div>
                    <h2 className="mt-1 font-semibold text-white">{part.name}</h2>
                    <p className="mt-1 text-sm text-gray-400">{part.category?.name ?? 'Ohne Kategorie'} · {part.location_id ? `Lagerort #${part.location_id}` : 'Kein Lagerort'}</p>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" aria-label="Kleinteil bearbeiten" onClick={() => setEditorPart(part)} className="rounded-lg border border-gray-600 p-2 text-gray-200 hover:bg-gray-700"><Pencil className="h-4 w-4" /></button>
                    <button type="button" aria-label="Bestand buchen" onClick={() => setStockPart(part)} className="inline-flex items-center gap-2 rounded-lg bg-green-700 px-3 py-2 text-sm font-medium text-white"><PackagePlus className="h-4 w-4" /> Bestand buchen</button>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
                  <div><p className="text-gray-500">Physisch</p><p className="text-white">{quantity(part.balance.physical, part)}</p></div>
                  <div><p className="text-gray-500">Reserviert</p><p className="text-white">{quantity(part.balance.reserved, part)}</p></div>
                  <div className="col-span-2 sm:col-span-1"><p className="text-gray-500">Verfügbar</p><p className="font-semibold text-green-300">{quantity(part.balance.available, part)} {part.unit.label} verfügbar</p></div>
                  <div><p className="text-gray-500">Meldebestand</p><p className="text-white">{quantity(part.minimum_stock, part)}</p></div>
                  <div><p className="text-gray-500">Preis</p><p className="text-white">{Number(part.unit_cost).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</p></div>
                </div>
              </article>
            ))}
          </div>
        </CardContent>
      </Card>

      {editorPart !== undefined && <SmallPartEditor part={editorPart} onClose={() => setEditorPart(undefined)} />}
      {stockPart && <SmallPartStockDialog part={stockPart} onClose={() => setStockPart(null)} />}
    </div>
  );
}
