import { Link, useLocation } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Boxes, Package, PackageCheck, Warehouse } from 'lucide-react';
import { api } from '../api/client';
import { Card, CardContent, CardHeader } from '../components/Card';
import { tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../components/ui/tableStyles';

type WarehousePageCopy = { "title": string; "subtitle": string; "openFilament": string; "open": string; "planned": string; "dataModelNext": string; "empty": string; "foundation": string; "metrics": { "activeSpools": string; "lowStock": string; "remaining": string; }; "areas": { "filament": { "title": string; "body": string; }; "parts": { "title": string; "body": string; }; "stock": { "title": string; "body": string; }; }; "page": { "overview": { "title": string; "subtitle": string; "columns": string[]; }; "parts": { "title": string; "subtitle": string; "columns": string[]; }; "stock": { "title": string; "subtitle": string; "columns": string[]; }; }; };

type WarehouseSectionId = 'overview' | 'parts' | 'stock';

function getSection(pathname: string): WarehouseSectionId {
  if (pathname.endsWith('/parts')) return 'parts';
  if (pathname.endsWith('/stock')) return 'stock';
  return 'overview';
}

export function WarehousePage() {
  const { t } = useTranslation();
  const location = useLocation();
  const activeSection = getSection(location.pathname);
  const copy = t('orders.runtimeDomain.warehousePage', { returnObjects: true }) as unknown as WarehousePageCopy;
  const columns = copy.page[activeSection].columns;

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
      title: copy.areas.parts.title,
      body: copy.areas.parts.body,
      to: '/warehouse/parts',
      icon: Boxes,
      active: activeSection === 'parts',
    },
    {
      title: copy.areas.stock.title,
      body: copy.areas.stock.body,
      to: '/warehouse/stock',
      icon: PackageCheck,
      active: activeSection === 'stock',
    },
  ];

  const ActiveIcon = activeSection === 'parts' ? Boxes : activeSection === 'stock' ? PackageCheck : Warehouse;

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
                {!active && to !== '/warehouse/filament' && (
                  <span className="text-xs px-2 py-1 rounded-full bg-bambu-dark-tertiary text-bambu-gray">
                    {copy.planned}
                  </span>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-bambu-gray min-h-10">{body}</p>
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

      {activeSection !== 'overview' && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <ActiveIcon className="w-5 h-5 text-bambu-green" />
                <div>
                  <h2 className="text-lg font-semibold text-white">
                    {copy.page[activeSection].title}
                  </h2>
                  <p className="text-sm text-bambu-gray">
                    {copy.page[activeSection].subtitle}
                  </p>
                </div>
              </div>
              <span className="text-xs px-2 py-1 rounded-full bg-bambu-dark-tertiary text-bambu-gray">
                {copy.foundation}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="overflow-hidden rounded-lg border border-bambu-dark-tertiary">
              <table className="w-full text-sm">
                <thead className={tableHeaderClass}>
                  <tr className={tableHeaderRowClass}>
                    {columns.map((column) => (
                      <th key={column} className={tableHeaderCellClass}>
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td colSpan={3} className="px-4 py-10 text-center text-bambu-gray">
                      {copy.empty}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
