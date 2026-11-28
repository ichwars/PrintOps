import { TablePagination } from '../components/ui/TablePagination';
import { useTablePagination } from '../hooks/useTablePagination';
import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Check, Factory, ListChecks, LoaderCircle, ShoppingCart, Trash2, Truck } from 'lucide-react';
import { PURCHASE_ORDERS_QUERY, SHOPPING_LIST_QUERY, warehousePurchaseOrdersApi, warehouseShoppingListApi, type WarehousePurchaseOrder, type WarehouseShoppingItem } from '../api/procurement';
import { smallPartsApi, type SmallPart } from '../api/smallParts';
import { needsWarehouseProduction, productionDemandFilter, warehouseArticlesApi, type WarehouseArticle } from '../api/client/warehouse-articles';
import { useAuth } from '../contexts/AuthContext';
import { Card, CardContent } from '../components/Card';
import { Button, IconButton, Modal } from '../components/ui';
import { tableBodyCellClass, tableHeaderClass, tableHeaderRowClass } from '../components/ui/tableStyles';
import { WarehouseHeader, WarehouseTable, WarehouseTableScroll } from '../components/warehouse/WarehouseLayout';
import { WarehouseActionHeader, WarehouseRowActions, type WarehouseAction } from '../components/warehouse/WarehouseRowActions';
import { warehousePageClass, warehouseTableDescriptionClass, warehouseTableIdentifierClass, warehouseTableQuantityClass } from '../components/warehouse/warehouseStyles';
import { stockMicroUnits, warehouseUnit } from '../components/warehouse/warehouseTableValues';
import { useWarehouseCopy, warehouseQuantity } from '../components/warehouse/warehouseGoodsCopy';
import { OrderTableRow } from '../components/orders/OrderLayout';
import { OrderSortHeader } from '../components/orders/OrderSortHeader';
import { nextOrderSort, orderValueComparator, type OrderSort } from '../utils/orderSorting';
import type { ProjectsLocationState } from '../utils/projectLinks';

interface WarehouseReorderCopy {
  title: string;
  subtitle: string;
  empty: string;
  open: string;
  summaryWarehouse: string;
  summaryMaterial: string;
  summaryTotal: string;
  productionTitle: string;
  purchasingTitle: string;
  colProduce: string;
  colSuggested: string;
}

const PAGE_SIZE = 200;
const COPY_KEY = 'orders.runtimeDomain.warehouseReorder';
const ERROR_CLASS = 'flex flex-wrap items-center justify-between gap-3 rounded-lg bg-red-100 p-3 text-sm text-red-900 dark:bg-red-950/50 dark:text-red-300';
const STOCK_SCALE = 1_000_000n;
const MAX_PROJECT_PARTS = 2_147_483_647n;
type DemandSortKey = 'sku' | 'name' | 'available' | 'minimum' | 'suggested';
type DemandSection = 'production' | 'purchasing';

type Page<T> = { items: T[]; total: number; limit: number; offset: number };

async function fetchAllPages<T>(fetchPage: (offset: number) => Promise<Page<T>>): Promise<T[]> {
  const items: T[] = [];
  let offset = 0;
  for (;;) {
    const page = await fetchPage(offset);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
    offset = page.offset + page.items.length;
  }
}

type ReorderRow = {
  id: number;
  sku: string;
  name: string;
  available: bigint;
  minimum: bigint;
  suggested: bigint;
  unit: string;
  unitLabel?: string;
  projectId?: number;
};

function formatStockMicroUnits(value: bigint, locale: string) {
  const absolute = value < 0n ? -value : value;
  return warehouseQuantity(`${value < 0n ? '-' : ''}${absolute / STOCK_SCALE}.${String(absolute % STOCK_SCALE).padStart(6, '0')}`, locale);
}

function reorderRow(resource: WarehouseArticle | SmallPart): ReorderRow {
  const minimum = stockMicroUnits(resource.minimum_stock);
  const available = stockMicroUnits(resource.balance.available);
  return {
    id: resource.id,
    sku: resource.sku,
    name: resource.name,
    available,
    minimum,
    suggested: minimum > available ? minimum - available : 0n,
    unit: resource.unit_code,
    unitLabel: 'unit' in resource ? resource.unit.label : undefined,
    projectId: 'unit' in resource ? undefined : (resource.project_id ?? undefined),
  };
}

export function WarehouseReorderPage() {
  const { t, i18n } = useTranslation();
  const goods = useWarehouseCopy();
  const { hasPermission } = useAuth();
  const canRead = hasPermission('inventory:read');
  const canUpdate = hasPermission('inventory:update');
  const canPrepareProduction = canUpdate && hasPermission('projects:read') && hasPermission('projects:create');
  const rawCopy = t(COPY_KEY, { returnObjects: true });
  const copy = (typeof rawCopy === 'object' && rawCopy !== null ? rawCopy : {}) as unknown as WarehouseReorderCopy;
  const locale = i18n.resolvedLanguage ?? i18n.language;
  const unitFor = (code: string, label?: string) => warehouseUnit(code, t('common.unitShortPiece'), label);
  const [shoppingListOpen, setShoppingListOpen] = useState(false);
  const [sorts, setSorts] = useState<Partial<Record<DemandSection, OrderSort<DemandSortKey>>>>({});
  const shoppingListContent = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const articlesQuery = useQuery({
    queryKey: ['warehouse-articles', 'production-demand', productionDemandFilter],
    queryFn: () => fetchAllPages<WarehouseArticle>((offset) => warehouseArticlesApi.list({ ...productionDemandFilter, limit: PAGE_SIZE, offset })),
    enabled: canRead,
  });
  const partsQuery = useQuery({
    queryKey: ['small-parts', 'reorder', { active: true, low_stock: true }],
    queryFn: () => fetchAllPages<SmallPart>((offset) => smallPartsApi.list({ active: true, low_stock: true, limit: PAGE_SIZE, offset })),
    enabled: canRead,
  });
  const shoppingQuery = useQuery({
    queryKey: SHOPPING_LIST_QUERY,
    queryFn: warehouseShoppingListApi.list,
    enabled: canRead,
  });
  const ordersQuery = useQuery({
    queryKey: PURCHASE_ORDERS_QUERY,
    queryFn: warehousePurchaseOrdersApi.list,
    enabled: canRead && shoppingListOpen,
  });
  const createPurchaseOrder = useMutation({
    mutationFn: warehousePurchaseOrdersApi.create,
    onSuccess: (order) => {
      queryClient.setQueryData<WarehousePurchaseOrder[]>(PURCHASE_ORDERS_QUERY, (orders = []) => [
        order, ...orders.filter(({ id }) => id !== order.id),
      ]);
      void queryClient.invalidateQueries({ queryKey: PURCHASE_ORDERS_QUERY });
    },
  });
  const addShoppingItem = useMutation({
    mutationFn: (row: ReorderRow) => warehouseShoppingListApi.add(row.id),
    onSuccess: (item) => {
      queryClient.setQueryData<WarehouseShoppingItem[]>(SHOPPING_LIST_QUERY, (items = []) => [...items.filter(({ id }) => id !== item.id), item]);
      void queryClient.invalidateQueries({ queryKey: SHOPPING_LIST_QUERY });
    },
  });
  const removeShoppingItem = useMutation({
    mutationFn: warehouseShoppingListApi.remove,
    onSuccess: (_result, id) => {
      queryClient.setQueryData<WarehouseShoppingItem[]>(SHOPPING_LIST_QUERY, (items = []) => items.filter((item) => item.id !== id));
      void queryClient.invalidateQueries({ queryKey: SHOPPING_LIST_QUERY });
      addShoppingItem.reset();
      shoppingListContent.current?.focus();
    },
  });

  const loaded = articlesQuery.isSuccess && partsQuery.isSuccess;
  const productionRows = articlesQuery.data?.filter(needsWarehouseProduction).map(reorderRow) ?? [];
  const materialRows = partsQuery.data?.map(reorderRow) ?? [];
  const sortRows = (rows: ReorderRow[], section: DemandSection) => {
    const sort = sorts[section];
    return sort ? [...rows].sort(orderValueComparator(row => row[sort.key], sort.direction, locale)) : rows;
  };
  const productionPage = useTablePagination(sortRows(productionRows, 'production'), JSON.stringify(sorts.production));
  const materialPage = useTablePagination(sortRows(materialRows, 'purchasing'), JSON.stringify(sorts.purchasing));
  if (!canRead) return <p role="alert" className="p-4 text-sm text-table-secondary md:p-8">{goods.noRead}</p>;

  const totalRows = productionRows.length + materialRows.length;
  const sections = [
    { section: 'production' as const, title: copy.productionTitle, quantityLabel: copy.colProduce, to: '/warehouse/stock', rows: productionRows, pagination: productionPage, purchasing: false },
    { section: 'purchasing' as const, title: copy.purchasingTitle, quantityLabel: copy.colSuggested, to: '/warehouse/parts', rows: materialRows, pagination: materialPage, purchasing: true },
  ];
  const loading = articlesQuery.isLoading || partsQuery.isLoading;
  const failed = articlesQuery.isError || partsQuery.isError;
  const shoppingItems = shoppingQuery.data ?? [];
  const shoppingMaterialIds = new Set(shoppingItems.map(({ resource_id }) => resource_id));
  const purchaseOrders = ordersQuery.data ?? [];
  const ordersByItemId = new Map(purchaseOrders.map((order) => [order.shopping_item_id, order]));
  const saving = addShoppingItem.isPending || removeShoppingItem.isPending || createPurchaseOrder.isPending;
  const retry = () => {
    void articlesQuery.refetch();
    void partsQuery.refetch();
  };

  function openProductionDraft(row: ReorderRow) {
    const pieces = row.suggested / STOCK_SCALE;
    const isPieceUnit = row.unit === 'C62' || row.unit === 'H87';
    const hasPieceTarget = isPieceUnit && row.suggested % STOCK_SCALE === 0n && pieces <= MAX_PROJECT_PARTS;
    const state: ProjectsLocationState = {
      productionDraft: {
        name: [...t(`${COPY_KEY}.productionProjectName`, { name: row.name })].slice(0, 255).join(''),
        description: t(`${COPY_KEY}.productionProjectDescription`, {
          sku: row.sku,
          quantity: `${formatStockMicroUnits(row.suggested, locale)} ${unitFor(row.unit, row.unitLabel)}`,
        }),
        productionArticleId: isPieceUnit ? row.id : undefined,
        target_parts_count: hasPieceTarget ? Number(pieces) : undefined,
        parent_id: row.projectId,
      },
    };
    navigate('/projects', { state });
  }

  return (
    <div className={warehousePageClass}>
      <WarehouseHeader icon={ShoppingCart} title={copy.title} description={copy.subtitle}>
        <Button type="button" variant="secondary" aria-haspopup="dialog" onClick={() => setShoppingListOpen(true)}>
          <ListChecks aria-hidden className="h-4 w-4" />
          {t(`${COPY_KEY}.shoppingList`)}{shoppingItems.length > 0 && ` (${shoppingItems.length})`}
        </Button>
        <Link
          to="/warehouse/suppliers"
          className="inline-flex min-h-[44px] items-center gap-2 rounded-lg bg-bambu-dark-tertiary px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-secondary-action-hover md:min-h-0"
        >
          <Truck aria-hidden className="h-4 w-4" />{t('suppliers.navTitle')}
        </Link>
      </WarehouseHeader>

      {addShoppingItem.isSuccess && (
        <p role="status" className="rounded-lg bg-bambu-green/10 p-3 text-sm text-accent-foreground">
          {t(`${COPY_KEY}.addedToShoppingList`, { name: addShoppingItem.variables.name })}
        </p>
      )}
      {addShoppingItem.isError && <p role="alert" className={ERROR_CLASS}>{t(`${COPY_KEY}.shoppingListSaveError`)}</p>}

      {loaded && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <CardContent className="space-y-1">
              <p className="text-sm text-table-secondary">{copy.summaryWarehouse}</p>
              <p className="text-2xl font-semibold text-white">{productionRows.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-1">
              <p className="text-sm text-table-secondary">{copy.summaryMaterial}</p>
              <p className="text-2xl font-semibold text-white">{materialRows.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="space-y-1">
              <p className="text-sm text-table-secondary">{copy.summaryTotal}</p>
              <p className="text-2xl font-semibold text-white">{totalRows}</p>
            </CardContent>
          </Card>
        </div>
      )}

      {loading && <p role="status" className="py-10 text-center text-sm text-table-secondary">{goods.loading}</p>}
      {failed && (
        <div role="alert" className={ERROR_CLASS}>
          {goods.error}
          <Button type="button" size="sm" variant="secondary" onClick={retry}>{goods.retry}</Button>
        </div>
      )}
      {loaded && totalRows === 0 && (
        <Card>
          <CardContent>
            <p className="py-4 text-center text-sm text-table-secondary">{copy.empty}</p>
          </CardContent>
        </Card>
      )}
      {loaded && sections.filter(({ rows }) => rows.length > 0).map(({ section, title, quantityLabel, to, pagination, purchasing }) => {
        const sort = sorts[section];
        const columns = [
          { key: 'sku', label: goods.sku },
          { key: 'name', label: goods.name },
          { key: 'available', label: goods.available, align: 'center' },
          { key: 'minimum', label: goods.minimum, align: 'center' },
          { key: 'suggested', label: quantityLabel, align: 'center' },
        ] as const;
        return (
          <section key={to} className="min-w-0 space-y-3">
            <h2 className="text-base font-semibold text-white">{title}</h2>
            <WarehouseTable>
              <WarehouseTableScroll label={title}>
                <table aria-label={title} className="w-full min-w-[800px] text-sm">
                  <thead className={tableHeaderClass}>
                    <tr className={tableHeaderRowClass}>
                      {columns.map(column => (
                        <OrderSortHeader key={column.key} label={column.label}
                          normalCase align={'align' in column ? column.align : 'left'}
                          direction={sort?.key === column.key ? sort.direction : undefined}
                          onSort={() => setSorts(previous => ({
                            ...previous, [section]: nextOrderSort(previous[section] ?? null, column.key),
                          }))} />
                      ))}
                      <WarehouseActionHeader />
                    </tr>
                  </thead>
                  <tbody>
                    {pagination.rows.map((row) => {
                      const target = `${to}?focus=${row.id}`;
                      const unit = unitFor(row.unit, row.unitLabel);
                      const saved = purchasing && shoppingMaterialIds.has(row.id);
                      const adding = purchasing && addShoppingItem.isPending && addShoppingItem.variables.id === row.id;
                      const quantity = (value: bigint) => `${formatStockMicroUnits(value, locale)} ${unit}`;
                      const actions: WarehouseAction[] = [
                        { label: copy.open, icon: ArrowRight, onSelect: () => navigate(target) },
                      ];
                      if (!purchasing && canPrepareProduction && row.suggested > 0n) {
                        actions.push({
                          label: t(`${COPY_KEY}.reproduce`),
                          icon: Factory,
                          onSelect: () => openProductionDraft(row),
                        });
                      }
                      if (saved) {
                        actions.push({
                          label: t(`${COPY_KEY}.onShoppingList`, { name: row.name }),
                          icon: Check,
                          onSelect: () => setShoppingListOpen(true),
                        });
                      } else if (purchasing && canUpdate && row.suggested > 0n) {
                        actions.push({
                          label: t(`${COPY_KEY}.addToShoppingList`, { name: row.name }),
                          icon: ShoppingCart,
                          disabled: saving,
                          onSelect: () => addShoppingItem.mutate(row),
                        });
                      }

                      return (
                        <OrderTableRow key={row.id} onOpen={() => navigate(target)} busy={adding} className="text-table-secondary">
                          <td className={tableBodyCellClass}><span className={`${warehouseTableIdentifierClass} text-accent-foreground wrap-anywhere`}>{row.sku}</span></td>
                          <th scope="row" className="min-w-52 wrap-anywhere px-4 py-3 text-left align-middle">
                            <Link to={target} className={`${warehouseTableDescriptionClass} rounded hover:underline focus-visible:outline-2 focus-visible:outline-accent-foreground`}>{row.name}</Link>
                          </th>
                          <td className={`${warehouseTableQuantityClass} font-medium text-amber-800 dark:text-amber-300`}>{quantity(row.available)}</td>
                          <td className={warehouseTableQuantityClass}>{quantity(row.minimum)}</td>
                          <td className={`${warehouseTableQuantityClass} font-medium text-white`}>{quantity(row.suggested)}</td>
                          <WarehouseRowActions subject={row.sku} actions={actions} />
                        </OrderTableRow>
                      );
                    })}
                  </tbody>
                </table>
              </WarehouseTableScroll>
              <TablePagination {...pagination.footer} label={title} />
            </WarehouseTable>
          </section>
        );
      })}

      <Modal
        open={shoppingListOpen}
        onClose={() => setShoppingListOpen(false)}
        title={t(`${COPY_KEY}.shoppingList`)}
        closeLabel={goods.close}
        initialFocusRef={shoppingListContent}
      >
        <div ref={shoppingListContent} tabIndex={-1} className="space-y-3 focus:outline-none">
          {shoppingQuery.isLoading && <p role="status" className="text-sm text-table-secondary">{goods.loading}</p>}
          {shoppingQuery.isError && (
            <div role="alert" className={ERROR_CLASS}>
              {t(`${COPY_KEY}.shoppingListLoadError`)}
              <Button type="button" size="sm" variant="secondary" onClick={() => void shoppingQuery.refetch()}>{goods.retry}</Button>
            </div>
          )}
          {createPurchaseOrder.isError && <p role="alert" className={ERROR_CLASS}>{goods.error}</p>}
          {removeShoppingItem.isError && <p role="alert" className={ERROR_CLASS}>{t(`${COPY_KEY}.shoppingListSaveError`)}</p>}
          {shoppingQuery.isSuccess && shoppingItems.length === 0 && (
            <p className="text-sm text-table-secondary">{t(`${COPY_KEY}.shoppingListEmpty`)}</p>
          )}
          {shoppingItems.length > 0 && (
            <ul className="divide-y divide-bambu-dark-tertiary">
              {shoppingItems.map((item) => {
                const order = ordersByItemId.get(item.id);
                const removing = removeShoppingItem.isPending && removeShoppingItem.variables === item.id;
                const label = t(`${COPY_KEY}.removeFromShoppingList`, { name: item.name });
                return (
                  <li key={item.id} className="flex flex-wrap items-center gap-3 py-3 first:pt-0 last:pb-0">
                    <div className="min-w-[9rem] flex-1 space-y-0.5 wrap-anywhere">
                      <p className="text-sm font-medium text-white">{item.name}</p>
                      <p className="font-mono text-xs text-table-secondary">{item.sku}</p>
                      <p className="text-sm tabular-nums text-table-secondary">{warehouseQuantity(item.quantity, locale)} {unitFor(item.unit_code, item.unit_label)}</p>
                    </div>
                    {order && (
                      <Link className="shrink-0 text-accent-foreground hover:underline" to={`/warehouse/purchase-orders#purchase-order-${order.id}`}>
                        {order.number}
                      </Link>
                    )}
                    {canUpdate && ordersQuery.isSuccess && !order && (
                      <Button type="button" size="sm" variant="secondary" disabled={saving}
                        onClick={() => createPurchaseOrder.mutate(item.id)}>
                        {t(`${COPY_KEY}.preparePurchaseOrder`)}
                      </Button>
                    )}
                    {canUpdate && (
                      <IconButton
                        label={label}
                        title={label}
                        icon={removing ? LoaderCircle : Trash2}
                        className={removing ? '[&_svg]:animate-spin' : ''}
                        aria-busy={removing || undefined}
                        disabled={saving}
                        onClick={() => removeShoppingItem.mutate(item.id)}
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          )}
          {ordersQuery.isError && (
            <div role="alert" className={ERROR_CLASS}>
              {goods.error}
              <Button type="button" size="sm" variant="secondary" onClick={() => void ordersQuery.refetch()}>{goods.retry}</Button>
            </div>
          )}
          <Link to="/warehouse/purchase-orders" className="inline-flex items-center gap-2 text-sm font-medium text-accent-foreground hover:underline">
            {t(`${COPY_KEY}.purchaseOrders`)} <ArrowRight aria-hidden="true" className="h-4 w-4" />
          </Link>
        </div>
      </Modal>
    </div>
  );
}
