import { request } from './client';

export interface SupplierInput {
  name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  address_line1: string | null;
  address_line2: string | null;
  postal_code: string | null;
  city: string | null;
  country_code: string | null;
  customer_number: string | null;
  payment_terms: string | null;
  default_lead_time_days: number;
  internal_notes: string | null;
  is_active: boolean;
}

export interface Supplier extends SupplierInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface SupplierPage {
  items: Supplier[];
  total: number;
  limit: number;
  offset: number;
}

export interface SupplierListParams {
  q?: string;
  active?: boolean;
  limit?: number;
  offset?: number;
}

export type ProcurementResource =
  | { kind: 'material'; small_part_id: number }
  | {
      kind: 'filament';
      material: string;
      subtype: string | null;
      brand: string | null;
      color_name: string | null;
    };

export interface ProcurementOfferDraft {
  id?: number;
  supplier_id: number | null;
  supplier_sku: string;
  purchase_url: string;
  package_quantity: string;
  package_unit_code: string;
  minimum_order_quantity: string;
  lead_time_days: number | null;
  net_price: string;
  gross_price: string;
  is_preferred: boolean;
  is_active: boolean;
}

export interface ProcurementOffer extends ProcurementOfferDraft {
  id: number;
  supplier_id: number;
  small_part_id: number | null;
  filament_sku_settings_id: number | null;
  resource_key: string;
  created_at: string;
  updated_at: string;
  supplier: Supplier;
}

export interface WarehouseShoppingItem {
  id: number;
  resource_kind: 'material';
  resource_id: number;
  sku: string;
  name: string;
  quantity: string;
  unit_code: string;
  unit_label: string;
}

export interface WarehousePurchaseOrder {
  id: number;
  number: string;
  shopping_item_id: number | null;
  received_quantity: string;
  open_quantity: string;
  can_receive: boolean;
  supplier_name: string | null;
  sku: string;
  name: string;
  quantity: string;
  unit_code: string;
  unit_label: string;
}

function queryString<T extends object>(params: T): string {
  const result = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) result.set(key, String(value));
  });
  return result.toString();
}

function resourceQuery(resource: ProcurementResource): string {
  if (resource.kind === 'material') {
    return queryString({ kind: resource.kind, small_part_id: resource.small_part_id });
  }
  return queryString({
    kind: resource.kind,
    material: resource.material,
    subtype: resource.subtype ?? undefined,
    brand: resource.brand ?? undefined,
    color_name: resource.color_name ?? undefined,
  });
}

function writableOffer(offer: ProcurementOfferDraft): ProcurementOfferDraft {
  return {
    ...(offer.id === undefined ? {} : { id: offer.id }),
    supplier_id: offer.supplier_id,
    supplier_sku: offer.supplier_sku,
    purchase_url: offer.purchase_url,
    package_quantity: offer.package_quantity,
    package_unit_code: offer.package_unit_code,
    minimum_order_quantity: offer.minimum_order_quantity,
    lead_time_days: offer.lead_time_days,
    net_price: offer.net_price,
    gross_price: offer.gross_price,
    is_preferred: offer.is_preferred,
    is_active: offer.is_active,
  };
}

export const suppliersApi = {
  list: (params: SupplierListParams = {}) =>
    request<SupplierPage>(`/suppliers?${queryString(params)}`),
  create: (input: SupplierInput) =>
    request<Supplier>('/suppliers', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: Partial<SupplierInput>) =>
    request<Supplier>(`/suppliers/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  remove: (id: number) => request<void>(`/suppliers/${id}`, { method: 'DELETE' }),
};

export const procurementOffersApi = {
  list: (resource: ProcurementResource) =>
    request<ProcurementOffer[]>(`/procurement-offers?${resourceQuery(resource)}`),
  replace: (resource: ProcurementResource, offers: ProcurementOfferDraft[]) =>
    request<ProcurementOffer[]>('/procurement-offers/resource', {
      method: 'PUT',
      body: JSON.stringify({
        resource,
        offers: offers.filter((offer) => offer.is_active).map(writableOffer),
      }),
    }),
};

export interface WarehousePurchaseOrderReceipt {
  receipt_id: number;
  receipt_number: string;
  order: WarehousePurchaseOrder;
}

export interface WarehousePurchaseOrderReceiptHistoryRow {
  id: number;
  receipt_number: string | null;
  quantity: string;
  created_at: string;
}

export const PURCHASE_ORDERS_QUERY = ['warehouse-purchase-orders'] as const;
export const SHOPPING_LIST_QUERY = ['warehouse-shopping-list'] as const;

export const warehousePurchaseOrdersApi = {
  list: () => request<WarehousePurchaseOrder[]>('/warehouse-purchase-orders'),
  receipts: (id: number) => request<WarehousePurchaseOrderReceiptHistoryRow[]>(
    `/warehouse-purchase-orders/${id}/receipts`,
  ),
  receive: (id: number, quantity: string, idempotencyKey: string) => request<WarehousePurchaseOrderReceipt>(
    `/warehouse-purchase-orders/${id}/receipts`,
    { method: 'POST', body: JSON.stringify({ quantity, idempotency_key: idempotencyKey }) },
  ),
  create: (itemId: number) => request<WarehousePurchaseOrder>(
    `/warehouse-shopping-list/${itemId}/purchase-order`, { method: 'POST' },
  ),
};

export const warehouseShoppingListApi = {
  list: () => request<WarehouseShoppingItem[]>('/warehouse-shopping-list'),
  add: (id: number) =>
    request<WarehouseShoppingItem>(`/warehouse-shopping-list/material/${id}`, { method: 'PUT' }),
  remove: (id: number) => request<void>(`/warehouse-shopping-list/${id}`, { method: 'DELETE' }),
};
