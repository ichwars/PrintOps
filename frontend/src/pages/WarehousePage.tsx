import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Archive, ArrowRight, Boxes, Package, Warehouse } from 'lucide-react';
import { api } from '../api/client';
import { Card, CardContent, CardHeader } from '../components/Card';

const COPY = {
  en: {
    title: 'Warehouse',
    subtitle: 'Stock areas for filament, materials, parts, and finished goods.',
    openFilament: 'Open filament',
    open: 'Open',
    planned: 'Planned',
    dataModelNext: 'Data model follows in the next step',
    metrics: {
      activeSpools: 'Active spools',
      lowStock: 'Low stock',
      remaining: 'Remaining filament',
    },
    areas: {
      filament: {
        title: 'Filament stock',
        body: 'Uses the existing PrintOps inventory as the first warehouse area.',
      },
      material: {
        title: 'Materials and parts',
        body: 'Reserved for purchased parts, packaging, hardware, and consumables.',
      },
      goods: {
        title: 'Finished goods',
        body: 'Reserved for produced articles, customer stock, and dispatchable items.',
      },
    },
  },
  de: {
    title: 'Lager',
    subtitle: 'Bestandsbereiche für Filament, Material, Teile und fertige Waren.',
    openFilament: 'Filament öffnen',
    open: 'Öffnen',
    planned: 'Geplant',
    dataModelNext: 'Datenmodell folgt im nächsten Schritt',
    metrics: {
      activeSpools: 'Aktive Spulen',
      lowStock: 'Niedriger Bestand',
      remaining: 'Restfilament',
    },
    areas: {
      filament: {
        title: 'Filamentbestand',
        body: 'Nutzt das vorhandene PrintOps-Inventar als ersten Lagerbereich.',
      },
      material: {
        title: 'Material und Teile',
        body: 'Vorgesehen für Zukaufteile, Verpackung, Hardware und Verbrauchsmaterial.',
      },
      goods: {
        title: 'Fertige Waren',
        body: 'Vorgesehen für produzierte Artikel, Kundenbestand und versandfähige Ware.',
      },
    },
  },
} as const;

export function WarehousePage() {
  const { i18n } = useTranslation();
  const copy = i18n.resolvedLanguage?.startsWith('de') ? COPY.de : COPY.en;

  const { data: spools = [] } = useQuery({
    queryKey: ['warehouse', 'spools', false],
    queryFn: () => api.getSpools(false),
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

  const areas = [
    {
      title: copy.areas.filament.title,
      body: copy.areas.filament.body,
      to: '/warehouse/filament',
      icon: Package,
      active: true,
    },
    {
      title: copy.areas.material.title,
      body: copy.areas.material.body,
      to: '/warehouse/material',
      icon: Boxes,
      active: false,
    },
    {
      title: copy.areas.goods.title,
      body: copy.areas.goods.body,
      to: '/warehouse/goods',
      icon: Archive,
      active: false,
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
        {areas.map(({ title, body, to, icon: Icon, active }) => (
          <Card key={to} className={!active ? 'opacity-75' : ''}>
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <Icon className="w-5 h-5 text-bambu-green" />
                  <h2 className="text-base font-semibold text-white">{title}</h2>
                </div>
                {!active && (
                  <span className="text-xs px-2 py-1 rounded-full bg-bambu-dark-tertiary text-bambu-gray">
                    {copy.planned}
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-bambu-gray min-h-10">{body}</p>
              {active ? (
                <Link
                  to={to}
                  className="inline-flex items-center gap-2 text-sm font-medium text-bambu-green hover:text-bambu-green-light"
                >
                  {copy.open}
                  <ArrowRight className="w-4 h-4" />
                </Link>
              ) : (
                <span className="inline-flex items-center gap-2 text-sm text-bambu-gray/70">
                  {copy.dataModelNext}
                </span>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
