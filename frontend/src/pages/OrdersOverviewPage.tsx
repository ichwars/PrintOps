import { TablePagination } from '../components/ui/TablePagination';
import { useTablePagination } from '../hooks/useTablePagination';
import { TableActionHeader, TableRowActions, type TableAction } from '../components/ui/TableRowActions';
import { useAuth } from '../contexts/AuthContext';
import { ConfirmModal } from '../components/ConfirmModal';
import { OrderSortHeader } from '../components/orders/OrderSortHeader';
import { nextOrderSort, orderValueComparator, type OrderSort } from '../utils/orderSorting';
import { useEffect, useState } from 'react';
import { CircleX, ClipboardList, Eye, FileText, FolderOpen } from 'lucide-react';
import { Link, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { ordersApi, type CustomerOrder } from '../api/offers';
import { OrderHeader, OrderStatus, OrderTable, OrderTableRow, orderPageClass } from '../components/orders/OrderLayout';
import {
  tableBodyCellClass,
  tableIdentifierClass,
  tableHeaderClass,
  tableHeaderRowClass,
} from '../components/ui/tableStyles';

const orderColumns = ['order', 'status', 'project', 'reservations', 'created'] as const;
type OrderColumn = typeof orderColumns[number];

function activeReservations(order: CustomerOrder) {
  return order.reservations.filter(item => item.status === 'active').length;
}

export function OrdersOverviewPage() {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canOpenProject = hasPermission('projects:read');
  const canOpenOffer = hasPermission('commercial_documents:read');
  const canCancel = hasPermission('orders:cancel');
  const [cancelTarget, setCancelTarget] = useState<CustomerOrder | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const text = (key: string) => t(`orders.runtimeDomain.orderOverview.${key}`);
  const locale = i18n.resolvedLanguage || i18n.language || 'en-US';
  const [orders, setOrders] = useState<CustomerOrder[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [sort, setSort] = useState<OrderSort<OrderColumn>>({ key: 'created', direction: 'desc' });
  const statusLabel = (status: string) => t(`orders.runtimeDomain.orderStatus.${status}`, { defaultValue: status });
  const sortValues = {
    order: (order: CustomerOrder) => order.number,
    status: (order: CustomerOrder) => statusLabel(order.status),
    project: (order: CustomerOrder) => order.project_id,
    reservations: activeReservations,
    created: (order: CustomerOrder) => Date.parse(order.created_at),
  };
  const sortedOrders = [...orders].sort(orderValueComparator(sortValues[sort.key], sort.direction, locale));

  useEffect(() => {
    void ordersApi.list()
      .then(setOrders)
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  const openOrder = (id: number) => navigate(`/orders/${id}`);

  function rowActions(order: CustomerOrder): TableAction[] {
    return [
      { icon: Eye, label: t('orders.rowActions.openOrder'), onSelect: () => openOrder(order.id) },
      ...(canOpenProject ? [{ icon: FolderOpen, label: t('orders.runtimeDomain.orderDetail.openProject'), onSelect: () => navigate(`/projects/${order.project_id}`) }] : []),
      ...(canOpenOffer ? [{ icon: FileText, label: t('orders.rowActions.openOffer'), onSelect: () => navigate(`/orders/offers?offer=${order.offer_id}`) }] : []),
      ...(canCancel && order.status === 'active' ? [{
        icon: CircleX, label: t('orders.rowActions.cancelOrder'), destructive: true, onSelect: () => setCancelTarget(order),
      }] : []),
    ];
  }

  async function cancelOrder(order: CustomerOrder) {
    if (!canCancel || cancelling) return;
    setCancelling(true);
    setError(null);
    try {
      const updated = await ordersApi.cancel(order.id, `cancel-${order.id}-${Date.now()}`);
      setOrders(current => current.map(item => item.id === updated.id ? updated : item));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setCancelling(false);
      setCancelTarget(null);
    }
  }

  const pagination = useTablePagination(sortedOrders, JSON.stringify(sort));
  return (
    <div className={orderPageClass}>
      <OrderHeader icon={ClipboardList} title={text('title')} description={text('subtitle')} />
      {error && <div role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-red-700 dark:text-red-300">{error}</div>}
      <OrderTable label={text('title')} footer={<TablePagination {...pagination.footer} label={text('title')} />}>
        <table className="w-full min-w-[680px] text-sm">
          <thead className={tableHeaderClass}>
            <tr className={tableHeaderRowClass}>
              {orderColumns.map(key => (
                <OrderSortHeader key={key} label={text(key)} align={key === 'order' ? 'left' : 'center'}
                  direction={sort.key === key ? sort.direction : undefined}
                  onSort={() => setSort(current => nextOrderSort(current, key, key === 'created' ? 'desc' : 'asc'))} />
              ))}
              <TableActionHeader />
            </tr>
          </thead>
          <tbody>
            {orders.length === 0 ? (
              <tr>
                <td colSpan={6} className="p-10 text-center text-table-secondary">{text('empty')}</td>
              </tr>
            ) : pagination.rows.map((order) => (
              <OrderTableRow key={order.id} onOpen={() => openOrder(order.id)}>
                <td className={tableBodyCellClass}><span className={`${tableIdentifierClass} text-white`}>{order.number}</span></td>
                <td className={`${tableBodyCellClass} text-center`}>
                  <OrderStatus tone={order.status === 'completed' ? 'positive' : 'neutral'}>
                    {statusLabel(order.status)}
                  </OrderStatus>
                </td>
                <td className={`${tableBodyCellClass} text-center`}>
                  {canOpenProject
                    ? <Link to={`/projects/${order.project_id}`} className="text-accent-foreground hover:underline">#{order.project_id}</Link>
                    : `#${order.project_id}`}
                </td>
                <td className={`${tableBodyCellClass} text-center tabular-nums`}>
                  {activeReservations(order)} / {order.reservations.length}
                </td>
                <td className={`${tableBodyCellClass} whitespace-nowrap text-center tabular-nums`}>{new Date(order.created_at).toLocaleString(locale)}</td>
                <TableRowActions subject={order.number} actions={rowActions(order)} />
              </OrderTableRow>
            ))}
          </tbody>
        </table>
      </OrderTable>
      {cancelTarget && canCancel && (
        <ConfirmModal variant="danger" title={t('orders.rowActions.cancelOrder')}
          message={t('orders.runtimeDomain.orderDetail.cancelConfirm')}
          confirmText={t('orders.rowActions.cancelOrder')} isLoading={cancelling}
          onConfirm={() => void cancelOrder(cancelTarget)} onCancel={() => setCancelTarget(null)} />
      )}
    </div>
  );
}
