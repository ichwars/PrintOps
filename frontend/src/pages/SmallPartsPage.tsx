import { useQuery } from '@tanstack/react-query';
import { Boxes, PackagePlus, Pencil, Plus, Search } from 'lucide-react';
import { useState } from 'react';

import { smallPartsApi, type SmallPart } from '../api/smallParts';
import { Card, CardContent } from '../components/Card';
import { Button, Checkbox, IconButton, TextField } from '../components/ui';
import { SmallPartEditor } from '../components/warehouse/SmallPartEditor';
import { SmallPartStockDialog } from '../components/warehouse/SmallPartStockDialog';

function quantity(value: string, part: SmallPart): string {
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: part.unit.decimal_places,
  }).format(Number(value));
}

function netPrice(value: string): string {
  return `${Number(value).toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} € netto`;
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
            <Boxes className="h-7 w-7 text-bambu-green" /> Material
          </h1>
          <p className="mt-1 text-bambu-gray">Zukaufteile, Hardware und Verbrauchsmaterial mit geprüftem Bestand.</p>
        </div>
        <Button type="button" onClick={() => setEditorPart(null)}>
          <Plus className="h-4 w-4" /> Material hinzufügen
        </Button>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card><CardContent><p className="text-sm text-bambu-gray">Artikel</p><p className="mt-1 text-2xl font-semibold text-white">{parts.data?.total ?? 0}</p></CardContent></Card>
        <Card><CardContent><p className="text-sm text-bambu-gray">Niedriger Bestand</p><p className="mt-1 text-2xl font-semibold text-amber-300">{items.filter((item) => item.balance.is_low_stock).length}</p></CardContent></Card>
        <Card><CardContent><p className="text-sm text-bambu-gray">Reservierungen</p><p className="mt-1 text-2xl font-semibold text-white">{items.filter((item) => Number(item.balance.reserved) > 0).length}</p></CardContent></Card>
      </div>

      <Card>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-bambu-gray" />
              <TextField
                type="search"
                aria-label="Material durchsuchen"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Artikelnummer, Bezeichnung, Kategorie …"
                className="pl-9"
              />
            </div>
            <Checkbox checked={lowStock} onCheckedChange={setLowStock} label="Nur niedriger Bestand" />
          </div>

          {parts.isLoading && <p className="py-10 text-center text-bambu-gray">Material wird geladen …</p>}
          {parts.isError && <p role="alert" className="rounded-lg bg-red-950/50 p-3 text-red-300">Material konnte nicht geladen werden.</p>}
          {!parts.isLoading && !items.length && <p className="py-10 text-center text-bambu-gray">Noch kein passendes Material vorhanden.</p>}
          <div className="grid gap-3 xl:grid-cols-2">
            {items.map((part) => (
              <article key={part.id} className={`rounded-xl border p-4 ${part.balance.is_low_stock ? 'border-amber-500/60 bg-amber-950/10' : 'border-bambu-dark-tertiary bg-bambu-dark/30'}`}>
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-bambu-green">{part.sku}</span>
                      {!part.is_active && <span className="rounded-full bg-bambu-dark-tertiary px-2 py-0.5 text-xs text-bambu-gray-light">Inaktiv</span>}
                      {part.balance.is_low_stock && <span className="rounded-full bg-amber-900/70 px-2 py-0.5 text-xs text-amber-200">Meldebestand</span>}
                    </div>
                    <h2 className="mt-1 font-semibold text-white">{part.name}</h2>
                    <p className="mt-1 text-sm text-bambu-gray">{part.category?.name ?? 'Ohne Kategorie'} · {part.location_id ? `Lagerort #${part.location_id}` : 'Kein Lagerort'}</p>
                  </div>
                  <div className="flex gap-2">
                    <IconButton label="Material bearbeiten" icon={Pencil} onClick={() => setEditorPart(part)} />
                    <Button type="button" size="sm" onClick={() => setStockPart(part)}>
                      <PackagePlus className="h-4 w-4" /> Bestand buchen
                    </Button>
                  </div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
                  <div><p className="text-bambu-gray">Physisch</p><p className="text-white">{quantity(part.balance.physical, part)}</p></div>
                  <div><p className="text-bambu-gray">Reserviert</p><p className="text-white">{quantity(part.balance.reserved, part)}</p></div>
                  <div className="col-span-2 sm:col-span-1"><p className="text-bambu-gray">Verfügbar</p><p className="font-semibold text-bambu-green-light">{quantity(part.balance.available, part)} {part.unit.label} verfügbar</p></div>
                  <div><p className="text-bambu-gray">Mindestbestand</p><p className="text-white">{quantity(part.minimum_stock, part)}</p></div>
                  <div><p className="text-bambu-gray">Standardpreis</p><p className="text-white">{Number(part.unit_cost).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })}</p></div>
                </div>
                {part.preferred_offer ? (
                  <div className="mt-4 flex flex-wrap gap-x-5 gap-y-1 border-t border-bambu-dark-tertiary pt-3 text-sm">
                    <span className="font-medium text-white">{part.preferred_offer.supplier.name}</span>
                    <span className="text-bambu-gray-light">{netPrice(part.preferred_offer.net_price)}</span>
                    <span className="text-bambu-gray-light">{part.preferred_offer.lead_time_days} Tage Lieferzeit</span>
                  </div>
                ) : null}
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
