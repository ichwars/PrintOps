import { request } from './core';

export type WarehouseArticleKind = 'finished' | 'trade' | 'service';
export type WarehouseStockSource = 'own' | 'material' | 'none';
export interface WarehouseBalance {
  physical: string;
  reserved: string;
  available: string;
  is_low_stock: boolean;
}
export interface WarehouseArticleInput {
  sku: string;
  name: string;
  kind: WarehouseArticleKind;
  unit_code: string;
  description?: string | null;
  sale_price?: string;
  tax_rate?: string;
  unit_cost?: string;
  minimum_stock?: string;
  stock_source?: WarehouseStockSource;
  small_part_id?: number | null;
  project_id?: number | null;
  calculation_revision_id?: number | null;
  is_active?: boolean;
}
export type WarehouseArticleCreateInput = WarehouseArticleInput;
export type WarehouseArticleUpdate = Partial<WarehouseArticleInput> & { version: number };
export interface WarehouseArticle extends Required<WarehouseArticleInput> {
  id: number;
  version: number;
  has_history: boolean;
  created_at: string;
  updated_at: string;
  balance: WarehouseBalance;
  locations: Array<WarehouseBalance & { location_id: number | null; location_name: string }>;
}
export interface WarehouseArticlePage {
  items: WarehouseArticle[];
  total: number;
  limit: number;
  offset: number;
}
export interface WarehouseArticleListParams {
  q?: string;
  active?: boolean;
  kind?: WarehouseArticleKind;
  stock_source?: WarehouseStockSource;
  low_stock?: boolean;
  limit?: number;
  offset?: number;
}
export type WarehouseMovementKind = 'opening' | 'receipt' | 'issue' | 'transfer' | 'correction' | 'reservation' | 'release' | 'reserved_issue' | 'counter';
export interface WarehouseMovementInput {
  entry_kind: WarehouseMovementKind;
  location_id?: number;
  target_location_id?: number;
  quantity?: string;
  reason: string;
  order_id?: number;
  reservation_id?: number;
  reverses_id?: number;
  idempotency_key: string;
}
export interface WarehouseMovement extends Omit<WarehouseMovementInput, 'location_id' | 'quantity' | 'order_id' | 'reservation_id' | 'reverses_id' | 'target_location_id'> {
  id: number;
  article_id: number;
  quantity: string;
  location_id: number;
  target_location_id: number | null;
  order_id: number | null;
  reservation_id: number | null;
  reverses_id: number | null;
  unit_code: string;
  physical_delta: string;
  reserved_delta: string;
  actor_id: number | null;
  created_at: string;
}
export interface WarehouseReservation {
  id: number;
  location_id: number;
  order_id: number | null;
  remaining: string;
}

function query(params: object) {
  const result = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) result.set(key, String(value));
  }
  return result.toString();
}

export const warehouseArticlesApi = {
  list: (params: WarehouseArticleListParams = {}) => request<WarehouseArticlePage>(`/warehouse-articles?${query(params)}`),
  get: (id: number) => request<WarehouseArticle>(`/warehouse-articles/${id}`),
  create: (input: WarehouseArticleInput) => request<WarehouseArticle>('/warehouse-articles', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: WarehouseArticleUpdate) => request<WarehouseArticle>(`/warehouse-articles/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  archive: (id: number, version: number) => request<WarehouseArticle>(`/warehouse-articles/${id}?version=${version}`, { method: 'DELETE' }),
  ledger: (id: number, offset = 0, limit = 50) => request<WarehouseMovement[]>(`/warehouse-articles/${id}/ledger?${query({ offset, limit })}`),
  reservations: (id: number) => request<WarehouseReservation[]>(`/warehouse-articles/${id}/reservations`),
  addLedger: (id: number, input: WarehouseMovementInput) => request<WarehouseMovement>(`/warehouse-articles/${id}/ledger`, { method: 'POST', body: JSON.stringify(input) }),
};
