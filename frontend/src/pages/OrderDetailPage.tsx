import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Boxes, CircleX, PackageCheck, Scale } from 'lucide-react';
import { Link, useParams } from 'react-router';
import { useTranslation } from 'react-i18next';

import { ordersApi, type CustomerOrder, type OrderDetail } from '../api/offers';
import { DocumentAmounts } from '../components/orders/DocumentAmounts';
import { Button, NumberField } from '../components/ui';
import { OrderHeader, OrderStatus, orderActionClass, orderPageClass, orderPanelClass } from '../components/orders/OrderLayout';
import { dashboardStyles } from '../components/dashboardStyles';
import { formatCount, formatGrams } from '../utils/calculationFormatting';
import { snapshotPart } from '../utils/offerSnapshot';

export function OrderDetailPage() {
  const { id } = useParams();
  const { t, i18n } = useTranslation();
  const text = (key: string, options?: Record<string, unknown>) => t(`orders.runtimeDomain.orderDetail.${key}`, options);
  const locale = i18n.resolvedLanguage || i18n.language || 'en-US';
  const queryClient = useQueryClient();
  const orderId = Number(id);
  const orderKey = ['orders', 'detail', orderId];
  const detail = useQuery({ queryKey: orderKey, queryFn: () => ordersApi.get(orderId), enabled: !!id });
  const production = useQuery({ queryKey: ['order-production', id], queryFn: () => ordersApi.getProduction(orderId), enabled: !!id, refetchInterval: 30000 });
  const order = detail.data;
  const [values, setValues] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const updateOrder = (updated: CustomerOrder) => {
    queryClient.setQueryData<OrderDetail>(orderKey, current => current && { ...current, ...updated });
    setError(null);
  };
  const command = async (kind: 'issue' | 'reconcile', allocationId: number) => {
    if (!order || !values[allocationId]) return;
    try {
      const key = `${kind}-${order.id}-${allocationId}-${Date.now()}`;
      const updated = kind === 'issue' ? await ordersApi.issueSmallPart(order.id, allocationId, values[allocationId], key) : await ordersApi.reconcileFilament(order.id, allocationId, values[allocationId], key);
      updateOrder(updated);
      setValues((current) => ({ ...current, [allocationId]: '' }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  const cancel = async () => {
    if (!order || !window.confirm(text('cancelConfirm'))) return;
    try { updateOrder(await ordersApi.cancel(order.id, `cancel-${order.id}-${Date.now()}`)); } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
  };
  if (!order) return <div className={`${dashboardStyles.page} text-table-secondary`}>{detail.error?.message ?? text('loading')}</div>;

  const confirmation = order.confirmation;
  const revision = snapshotPart(order.accepted_snapshot, 'revision');
  const calculation = snapshotPart(order.accepted_snapshot, 'calculation');
  const rawCurrency = confirmation?.currency ?? revision.currency ?? calculation.currency;
  const currency = typeof rawCurrency === 'string' ? rawCurrency : null;
  const snapshotPrice = revision.selling_price;
  const subtotal = typeof snapshotPrice === 'string' || typeof snapshotPrice === 'number' ? snapshotPrice : null;
  const customer = order.customer_display_name
    || (order.customer_id ? `#${order.customer_id}` : t('orders.runtimeCalculation.noCustomerOffersPage'));
  const tone = order.status === 'completed' ? 'positive' : order.status === 'cancelled' ? 'danger' : 'neutral';

  return (
    <div className={orderPageClass}>
      <Link to="/orders/offers" className={`${orderActionClass} -ml-2.5`}>
        <ArrowLeft aria-hidden="true" className="h-4 w-4" />
        {text('back')}
      </Link>
      <OrderHeader icon={Boxes} title={order.number} description={text('subtitle')}>
        <Link to={`/projects/${order.project_id}`} className={`${orderActionClass} bg-bambu-dark-tertiary`}>
          {text('openProject')}
        </Link>
        {order.status === 'active' && (
          <Button type="button" variant="ghost" onClick={() => void cancel()} className="text-red-700! dark:text-red-300!">
            <CircleX aria-hidden="true" className="h-4 w-4" />{text('cancel')}
          </Button>
        )}
      </OrderHeader>
      {error && <div role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-red-700 dark:text-red-300">{error}</div>}
      <div className={`${orderPanelClass} space-y-5 text-sm text-table-secondary`}>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="min-w-0">
            <dt>{t('orders.customers.customer')}</dt>
            <dd className="wrap-break-word font-semibold text-white">{customer}</dd>
          </div>
          <div>
            <dt>{text('status')}</dt>
            <dd><OrderStatus tone={tone}>{t(`orders.runtimeDomain.orderStatus.${order.status}`, { defaultValue: order.status })}</OrderStatus></dd>
          </div>
          <div>
            <dt>{text('offer')}</dt>
            <dd className="text-white">#{order.offer_id}</dd>
          </div>
          <div>
            <dt>{text('project')}</dt>
            <dd className="text-white">#{order.project_id}</dd>
          </div>
        </dl>
        <DocumentAmounts lines={confirmation?.lines ?? []} currency={currency} locale={locale}
          positionsLabel={t('orders.documentDetails.orderPositions')} amounts={confirmation
            ? { subtotal: confirmation.subtotal_amount, tax: confirmation.tax_amount, total: confirmation.total_amount }
            : { subtotal }} />
      </div>

      <section className={orderPanelClass}>
        <h2 className={dashboardStyles.cardTitle}>{t('productionQuality.production')}</h2>
        {production.data && <p className="mt-2 text-sm text-table-secondary">{t('productionQuality.partCounts', { good: production.data.good_quantity, reject: production.data.reject_quantity })} · {t('productionQuality.awaitingRuns', { count: production.data.unconfirmed_runs })}</p>}
        {production.isError && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{t('productionQuality.loadFailed')}</p>}
        <p className="mt-1 text-xs text-table-secondary">{t('productionQuality.deliverySeparate')}</p>
      </section>

      <section className="space-y-3">
        <h2 className={dashboardStyles.cardTitle}>{text('reservations')}</h2>
        {order.reservations.map((reservation) => {
          const isFilament = reservation.resource_kind === 'filament';
          const isActive = order.status === 'active' && reservation.status === 'active';
          const quantity = (value: string | number) => isFilament
            ? formatGrams(value, locale)
            : `${formatCount(value, locale)} ${reservation.unit_code}`;
          return (
            <article key={reservation.id} className={orderPanelClass}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0 wrap-break-word text-sm">
                  <strong className="font-medium text-white">{isFilament ? reservation.material_code : reservation.source_key}</strong>
                  <span className="ml-2 text-xs text-table-secondary">{quantity(reservation.requested_quantity)}</span>
                </div>
                <OrderStatus tone={reservation.status === 'active' ? 'positive' : 'neutral'}>
                  {t(`orders.runtimeDomain.reservationStatus.${reservation.status}`, { defaultValue: reservation.status })}
                </OrderStatus>
              </div>
              <div className="mt-3 space-y-2">
                {reservation.allocations.map((allocation) => {
                  const remaining = Number(allocation.allocated_quantity) - Number(allocation.consumed_quantity);
                  const ActionIcon = isFilament ? Scale : PackageCheck;
                  return (
                    <div key={allocation.id} className="grid grid-cols-1 items-center gap-3 rounded-lg bg-bambu-dark p-3 lg:grid-cols-[minmax(0,1fr)_160px_130px_auto]">
                      <div className="text-sm text-white">{allocation.small_part_id ? text('material', { id: allocation.small_part_id }) : text('spool', { id: allocation.spool_id ?? allocation.external_spool_id })}</div>
                      <div className="text-xs text-table-secondary">{text('remaining')}: {quantity(remaining)}</div>
                      {isActive && (
                        <>
                          <NumberField aria-label={text('quantity')} min="0.001" step={isFilament ? '0.1' : '1'} value={values[allocation.id] ?? ''} onValueChange={(value) => setValues((current) => ({ ...current, [allocation.id]: value }))} placeholder={text('quantity')} />
                          <Button type="button" size="sm" variant="secondary" disabled={!values[allocation.id]} onClick={() => void command(reservation.resource_kind === 'small_part' ? 'issue' : 'reconcile', allocation.id)}>
                            <ActionIcon aria-hidden="true" className="h-4 w-4" />{isFilament ? text('reconcile') : text('issue')}
                          </Button>
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </article>
          );
        })}
      </section>
    </div>
  );
}
