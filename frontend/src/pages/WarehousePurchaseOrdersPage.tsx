import { useEffect, useId, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ClipboardList, History, Plus } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { ApiError } from '../api/client';
import {
  PURCHASE_ORDERS_QUERY, SHOPPING_LIST_QUERY, warehousePurchaseOrdersApi, type WarehousePurchaseOrder,
} from '../api/procurement';
import { useAuth } from '../contexts/AuthContext';
import { Button, Modal, NumberField } from '../components/ui';
import { TablePagination } from '../components/ui/TablePagination';
import { tableBodyCellClass, tableHeaderClass, tableHeaderRowClass } from '../components/ui/tableStyles';
import { OrderSortHeader } from '../components/orders/OrderSortHeader';
import { WarehouseHeader, WarehouseTable, WarehouseTableScroll } from '../components/warehouse/WarehouseLayout';
import { WarehouseActionHeader, WarehouseRowActions, type WarehouseAction } from '../components/warehouse/WarehouseRowActions';
import {
  warehousePageClass, warehouseTableDescriptionClass, warehouseTableIdentifierClass,
  warehouseTableQuantityClass, warehouseTableRowClass,
} from '../components/warehouse/warehouseStyles';
import { focusWarehouseRow, stockMicroUnits, warehouseUnit } from '../components/warehouse/warehouseTableValues';
import { useWarehouseCopy, warehouseQuantity } from '../components/warehouse/warehouseGoodsCopy';
import { useTablePagination } from '../hooks/useTablePagination';
import { formatDateTime } from '../utils/date';
import { nextOrderSort, orderValueComparator, type OrderSort } from '../utils/orderSorting';
import { cryptoRandomUuid } from '../utils/random';

const COPY_KEY = 'orders.runtimeDomain.warehouseReorder';
const ERROR_CLASS = 'flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-100 p-3 text-sm text-red-900 dark:bg-red-950/50 dark:text-red-300';

type OrderColumn = 'number' | 'name' | 'supplier_name' | 'quantity' | 'received_quantity' | 'open_quantity';

function sortValue(order: WarehousePurchaseOrder, key: OrderColumn) {
  switch (key) {
    case 'quantity':
    case 'received_quantity':
    case 'open_quantity':
      return stockMicroUnits(order[key]);
    default:
      return order[key];
  }
}

function PurchaseOrderTable({ id, title, empty, orders, targetId, actionsFor }: {
  id: string;
  title: string;
  empty: string;
  orders: WarehousePurchaseOrder[];
  targetId: number | null;
  actionsFor: (order: WarehousePurchaseOrder) => WarehouseAction[];
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const [sort, setSort] = useState<OrderSort<OrderColumn> | null>(null);
  const targetRow = useRef<HTMLTableRowElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const sorted = sort ? [...orders].sort(orderValueComparator(order => sortValue(order, sort.key), sort.direction, locale)) : orders;
  const pagination = useTablePagination(sorted, sort ? `${sort.key}:${sort.direction}` : '', 15,
    sorted.findIndex(order => order.id === targetId));

  useEffect(() => {
    focusWarehouseRow(targetRow.current);
  }, []);

  const columns: { key: OrderColumn; label: string; align?: 'center' }[] = [
    { key: 'number', label: t(`${COPY_KEY}.orderNumber`) },
    { key: 'name', label: t('orders.runtimeDomain.warehouseGoods.name') },
    { key: 'supplier_name', label: t('orders.runtimeDomain.smallParts.supplier') },
    { key: 'quantity', label: t(`${COPY_KEY}.orderedQuantity`), align: 'center' },
    { key: 'received_quantity', label: t(`${COPY_KEY}.receivedQuantity`), align: 'center' },
    { key: 'open_quantity', label: t(`${COPY_KEY}.openQuantity`), align: 'center' },
  ];

  return (
    <section aria-labelledby={id} className="min-w-0 space-y-3">
      <h2 id={id} className="text-base font-semibold text-white">{title}</h2>
      {orders.length === 0 ? (
        <div className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-4 text-sm text-table-secondary">{empty}</div>
      ) : (
        <WarehouseTable>
          <WarehouseTableScroll label={`${t('inventory.table')} · ${title}`} viewportRef={viewport}>
            <table aria-label={title} className="w-full min-w-[820px] text-sm">
              <thead className={`${tableHeaderClass} sticky top-0 z-20 [background-color:color-mix(in_srgb,var(--bg-tertiary)_60%,var(--bg-secondary))]`}>
                <tr className={tableHeaderRowClass}>
                  {columns.map(({ key, label, align }) => (
                    <OrderSortHeader key={key} label={label} align={align} normalCase
                      direction={sort?.key === key ? sort.direction : undefined}
                      onSort={() => setSort(previous => nextOrderSort(previous, key))} />
                  ))}
                  <WarehouseActionHeader />
                </tr>
              </thead>
              <tbody>
                {pagination.rows.map(order => {
                  const unit = warehouseUnit(order.unit_code, t('common.unitShortPiece'), order.unit_label);
                  const quantity = (value: string) => `${warehouseQuantity(value, locale)} ${unit}`;

                  return (
                    <tr key={order.id} id={`purchase-order-${order.id}`} tabIndex={-1}
                      ref={order.id === targetId ? targetRow : undefined}
                      className={`${warehouseTableRowClass} focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-foreground`}>
                      <th scope="row" className={`${tableBodyCellClass} text-left`}>
                        <span className={`${warehouseTableIdentifierClass} whitespace-nowrap text-accent-foreground`}>{order.number}</span>
                      </th>
                      <td className={`${tableBodyCellClass} min-w-44 wrap-anywhere`}>
                        <div className={warehouseTableDescriptionClass}>{order.name}</div>
                        <div className="font-mono text-xs">{order.sku}</div>
                      </td>
                      <td className={`${tableBodyCellClass} wrap-anywhere`}>{order.supplier_name || '—'}</td>
                      <td className={`${warehouseTableQuantityClass} text-white`}>{quantity(order.quantity)}</td>
                      <td className={`${warehouseTableQuantityClass} text-table-secondary`}>{quantity(order.received_quantity)}</td>
                      <td className={`${warehouseTableQuantityClass} text-table-secondary`}>
                        {quantity(order.open_quantity)}
                        {Number(order.open_quantity) === 0 && (
                          <div className="text-xs font-medium text-accent-foreground">{t(`${COPY_KEY}.fullyReceived`)}</div>
                        )}
                      </td>
                      <WarehouseRowActions subject={order.number} actions={actionsFor(order)} />
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </WarehouseTableScroll>
          <TablePagination {...pagination.footer} label={title} viewportRef={viewport} />
        </WarehouseTable>
      )}
    </section>
  );
}

export function WarehousePurchaseOrdersPage() {
  const { t, i18n } = useTranslation();
  const goods = useWarehouseCopy();
  const { hasPermission } = useAuth();
  const canRead = hasPermission('inventory:read');
  const canUpdate = hasPermission('inventory:update');
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const unitFor = (code: string, label: string) => warehouseUnit(code, t('common.unitShortPiece'), label);
  const [receiptHistoryOrderId, setReceiptHistoryOrderId] = useState<number | null>(null);
  const [receiptDraft, setReceiptDraft] = useState<{ id: number; quantity: string; key: string; uncertain?: boolean } | null>(null);
  const receiptFormId = useId();
  const receiptBusy = useRef(false);
  const historyTitle = useRef<HTMLParagraphElement>(null);
  const queryClient = useQueryClient();
  const { hash } = useLocation();

  const ordersQuery = useQuery({
    queryKey: PURCHASE_ORDERS_QUERY,
    queryFn: warehousePurchaseOrdersApi.list,
    enabled: canRead,
  });
  const receiptHistory = useQuery({
    queryKey: [...PURCHASE_ORDERS_QUERY, 'receipts', receiptHistoryOrderId],
    queryFn: () => warehousePurchaseOrdersApi.receipts(receiptHistoryOrderId as number),
    enabled: canRead && receiptHistoryOrderId !== null,
  });
  const receiveOrder = useMutation({
    mutationFn: ({ id, quantity, key }: NonNullable<typeof receiptDraft>) =>
      warehousePurchaseOrdersApi.receive(id, quantity, key),
    onSuccess: async ({ order }) => {
      setReceiptDraft(null);
      queryClient.setQueryData<WarehousePurchaseOrder[]>(PURCHASE_ORDERS_QUERY, (orders = []) =>
        orders.map((item) => item.id === order.id ? order : item));
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: PURCHASE_ORDERS_QUERY }),
        queryClient.invalidateQueries({ queryKey: SHOPPING_LIST_QUERY }),
        queryClient.invalidateQueries({ queryKey: ['small-parts'] }),
        queryClient.invalidateQueries({ queryKey: ['small-part'] }),
        queryClient.invalidateQueries({ queryKey: ['warehouse-articles'] }),
        queryClient.invalidateQueries({ queryKey: ['warehouse'] }),
        queryClient.invalidateQueries({ queryKey: ['warehouse-number-sequences'] }),
      ]);
    },
    onError: (error) => {
      if (!(error instanceof ApiError && error.status >= 400 && error.status < 500 && error.status !== 408 && error.status !== 429)) {
        setReceiptDraft((draft) => draft && { ...draft, uncertain: true });
      } else {
        void queryClient.invalidateQueries({ queryKey: PURCHASE_ORDERS_QUERY });
      }
    },
    onSettled: () => { receiptBusy.current = false; },
  });
  if (!canRead) return <p role="alert" className="p-4 text-sm text-table-secondary md:p-8">{goods.noRead}</p>;

  const orders = ordersQuery.data ?? [];
  const target = /^#purchase-order-(\d+)$/.exec(hash);
  const targetId = target ? Number(target[1]) : null;
  const historyOrder = orders.find(order => order.id === receiptHistoryOrderId);
  const draftOrder = orders.find(order => order.id === receiptDraft?.id);
  const bookingLocked = receiveOrder.isPending || Boolean(receiptDraft?.uncertain);
  const cancelBooking = () => {
    if (receiptBusy.current || bookingLocked) return;
    setReceiptDraft(null);
    receiveOrder.reset();
  };
  const actionsFor = (order: WarehousePurchaseOrder): WarehouseAction[] => {
    const actions: WarehouseAction[] = [
      { label: t(`${COPY_KEY}.receiptHistory`), icon: History, onSelect: () => setReceiptHistoryOrderId(order.id) },
    ];
    if (canUpdate && order.can_receive) {
      actions.push({ label: goods.receipt, icon: Plus, onSelect: () => {
        receiveOrder.reset();
        setReceiptDraft({ id: order.id, quantity: '', key: cryptoRandomUuid() });
      } });
    }
    return actions;
  };
  const sections = [
    { id: 'open', title: t(`${COPY_KEY}.openOrders`), empty: t(`${COPY_KEY}.noOpenOrders`),
      orders: orders.filter((order) => Number(order.open_quantity) > 0) },
    { id: 'complete', title: t(`${COPY_KEY}.completedOrders`), empty: t(`${COPY_KEY}.noCompletedOrders`),
      orders: orders.filter((order) => Number(order.open_quantity) === 0) },
  ];

  return (
    <div className={warehousePageClass}>
      <WarehouseHeader icon={ClipboardList} title={t(`${COPY_KEY}.purchaseOrders`)} description={t(`${COPY_KEY}.purchaseOrdersDescription`)} />
      {ordersQuery.isLoading && <p role="status" className="py-8 text-center text-table-secondary">{goods.loading}</p>}
      {ordersQuery.isError && (
        <div role="alert" className={ERROR_CLASS}>
          {goods.error}
          <Button type="button" size="sm" variant="secondary" onClick={() => void ordersQuery.refetch()}>{goods.retry}</Button>
        </div>
      )}
      {receiveOrder.isSuccess && (
        <p role="status" className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary px-4 py-3 text-sm text-accent-foreground">
          {t('orders.runtimeDomain.warehouseGoods.quickBookingSaved')} · {receiveOrder.data.receipt_number}
        </p>
      )}
      {ordersQuery.isSuccess && sections.map(section => (
        <PurchaseOrderTable key={section.id + hash} id={`purchase-orders-${section.id}`} title={section.title}
          empty={section.empty} orders={section.orders} targetId={targetId} actionsFor={actionsFor} />
      ))}

      <Modal open={Boolean(historyOrder)} title={t(`${COPY_KEY}.receiptHistory`)} closeLabel={goods.close}
        onClose={() => setReceiptHistoryOrderId(null)} initialFocusRef={historyTitle}>
        {historyOrder && (
          <div className="space-y-3 text-sm text-table-secondary">
            <p ref={historyTitle} tabIndex={-1} className="font-medium text-white">{historyOrder.number} · {historyOrder.name}</p>
            {receiptHistory.isLoading && <p role="status">{goods.loading}</p>}
            {receiptHistory.isError && (
              <div role="alert" className={ERROR_CLASS}>
                {goods.error}
                <Button type="button" size="sm" variant="secondary" onClick={() => void receiptHistory.refetch()}>{goods.retry}</Button>
              </div>
            )}
            {receiptHistory.data?.length === 0 && <p>{t(`${COPY_KEY}.noReceipts`)}</p>}
            {Boolean(receiptHistory.data?.length) && (
              <ul className="divide-y divide-bambu-dark-tertiary rounded-lg border border-bambu-dark-tertiary">
                {receiptHistory.data?.map(receipt => (
                  <li key={receipt.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 tabular-nums">
                    <span className="font-mono text-xs text-accent-foreground">{receipt.receipt_number ?? `#${receipt.id}`}</span>
                    <span className="font-medium text-white">
                      {warehouseQuantity(receipt.quantity, locale)} {unitFor(historyOrder.unit_code, historyOrder.unit_label)}
                    </span>
                    <span className="sm:ml-auto">{formatDateTime(receipt.created_at)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Modal>

      <Modal open={Boolean(draftOrder && receiptDraft)} title={goods.receipt} closeLabel={goods.close}
        description={draftOrder && `${draftOrder.number} · ${draftOrder.name}`}
        onClose={cancelBooking} closeDisabled={bookingLocked} closeOnBackdrop={!bookingLocked}
        footer={
          <>
            <Button type="button" variant="secondary" disabled={bookingLocked} onClick={cancelBooking}>{goods.cancel}</Button>
            <Button type="submit" form={receiptFormId} className="text-black!" loading={receiveOrder.isPending}>{goods.book}</Button>
          </>
        }>
        {draftOrder && receiptDraft && (
          <form id={receiptFormId} className="space-y-3" onSubmit={(event) => {
            event.preventDefault();
            if (receiptBusy.current) return;
            receiptBusy.current = true;
            receiveOrder.mutate(receiptDraft);
          }}>
            <NumberField label={goods.quantity} min="0.000001" max={draftOrder.open_quantity} step="any"
              required value={receiptDraft.quantity}
              disabled={bookingLocked}
              onValueChange={(quantity) => setReceiptDraft({ ...receiptDraft, quantity })} />
            {receiveOrder.isError && (
              <p role="alert" className="text-sm text-red-800 dark:text-red-300">
                {receiptDraft.uncertain ? goods.uncertainMovement : receiveOrder.error.message}
              </p>
            )}
          </form>
        )}
      </Modal>
    </div>
  );
}
