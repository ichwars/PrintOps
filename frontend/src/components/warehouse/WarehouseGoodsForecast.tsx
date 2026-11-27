import { TablePagination } from '../ui/TablePagination';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { warehouseArticlesApi } from '../../api/client/warehouse-articles';
import { Button } from '../ui';
import { tableBodyCellClass, tableHeaderCellClass, tableHeaderClass, tableHeaderRowClass } from '../ui/tableStyles';
import { useWarehouseCopy, warehouseQuantity } from './warehouseGoodsCopy';
import { WarehouseTable, WarehouseTableScroll } from './WarehouseLayout';
import { warehouseTableDescriptionClass, warehouseTableIdentifierClass, warehouseTableQuantityClass, warehouseTableRowClass } from './warehouseStyles';
import { warehouseUnit } from './warehouseTableValues';

const GOODS = 'orders.runtimeDomain.warehouseGoods';
const MINIMUM_REACHED_CLASS = 'font-medium text-amber-900 dark:text-amber-200';

export function WarehouseGoodsForecast() {
  const { t, i18n } = useTranslation();
  const copy = useWarehouseCopy();
  const [pageSize, setPageSize] = useState(50);
  const [offset, setOffset] = useState(0);
  const forecast = useQuery({
    queryKey: ['warehouse-articles', 'forecast', offset, pageSize],
    queryFn: () => warehouseArticlesApi.forecast(offset, pageSize),
    placeholderData: keepPreviousData,
    staleTime: 0,
  });
  const data = forecast.data;
  const total = data?.total;
  useEffect(() => {
    if (!forecast.isPlaceholderData && total !== undefined && offset > 0 && offset >= total) {
      setOffset(Math.max(0, Math.ceil(total / pageSize) - 1) * pageSize);
    }
  }, [forecast.isPlaceholderData, offset, pageSize, total]);
  const locale = i18n.resolvedLanguage;
  const formatDayCount = new Intl.NumberFormat(locale).format;
  const title = t('forecast.title');

  return (
    <section aria-label={title} className="min-w-0 space-y-3">
      <div>
        <h2 className="text-base font-semibold text-white">{title}</h2>
        {data && <p className="mt-1 text-sm text-table-secondary">{t(`${GOODS}.forecastPeriod`, { days: formatDayCount(data.window_days) })}</p>}
      </div>
      {forecast.isPending && <p role="status" className="py-10 text-center text-sm text-table-secondary">{copy.loading}</p>}
      {forecast.isError && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-100 p-3 text-sm text-red-900 dark:bg-red-950/50 dark:text-red-300">
          {copy.error}
          <Button type="button" size="sm" variant="secondary" onClick={() => void forecast.refetch()}>{copy.retry}</Button>
        </div>
      )}
      {data && (data.total > 0 || offset > 0 ? (
        <WarehouseTable>
          <WarehouseTableScroll label={title}>
            <table aria-label={title} aria-busy={forecast.isPlaceholderData} className="w-full min-w-[800px] text-sm">
              <thead className={tableHeaderClass}>
                <tr className={tableHeaderRowClass}>
                  <th scope="col" className={tableHeaderCellClass}>{copy.sku}</th>
                  <th scope="col" className={tableHeaderCellClass}>{copy.name}</th>
                  {[
                    copy.available,
                    copy.minimum,
                    t(`${GOODS}.forecastDailyUsage`),
                    t(`${GOODS}.forecastProjectedStock`, { days: formatDayCount(data.window_days) }),
                    t(`${GOODS}.forecastDaysToMinimum`),
                  ].map(label => <th key={label} scope="col" className={`${tableHeaderCellClass} text-center`}>{label}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.items.map(row => {
                  const unit = warehouseUnit(row.unit_code, t('common.unitShortPiece'));
                  const quantity = (value: string) => `${warehouseQuantity(value, locale)} ${unit}`;
                  return (
                    <tr key={row.id} className={`${warehouseTableRowClass} text-table-secondary`}>
                      <td className={tableBodyCellClass}><span className={`${warehouseTableIdentifierClass} text-accent-foreground wrap-anywhere`}>{row.sku}</span></td>
                      <th scope="row" className={`${warehouseTableDescriptionClass} min-w-52 wrap-anywhere px-4 py-3 text-left align-middle`}>{row.name}</th>
                      <td className={`${warehouseTableQuantityClass} font-medium text-accent-foreground`}>{quantity(row.available)}</td>
                      <td className={warehouseTableQuantityClass}>{quantity(row.minimum_stock)}</td>
                      <td className={warehouseTableQuantityClass}>{row.daily_usage === null ? '—' : quantity(row.daily_usage)}</td>
                      <td className={`${tableBodyCellClass} text-center tabular-nums`}>
                        {row.projected_available === null ? t(`${GOODS}.forecastNoConsumption`) : <span className="whitespace-nowrap">{quantity(row.projected_available)}</span>}
                      </td>
                      <td className={`${tableBodyCellClass} text-center tabular-nums`}>
                        {row.days_until_minimum === 0 ? (
                          <span className={MINIMUM_REACHED_CLASS}>{t(`${GOODS}.forecastMinimumReached`)}</span>
                        ) : row.days_until_minimum !== null ? (
                          <span className={MINIMUM_REACHED_CLASS}>{formatDayCount(row.days_until_minimum)}</span>
                        ) : row.daily_usage === null ? '—' : `> ${formatDayCount(data.window_days)}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </WarehouseTableScroll>
          <TablePagination total={data.total} offset={data.offset} pageSize={pageSize}
            busy={forecast.isPlaceholderData} label={title} onOffsetChange={setOffset}
            onPageSizeChange={value => { setPageSize(value); setOffset(0); }} />
        </WarehouseTable>
      ) : <p className="rounded-lg bg-bambu-dark-secondary px-4 py-8 text-center text-sm text-table-secondary">{t(`${GOODS}.forecastEmpty`)}</p>)}
    </section>
  );
}
