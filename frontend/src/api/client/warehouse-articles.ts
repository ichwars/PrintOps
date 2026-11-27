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
  stock_checked_at?: string | null;
  last_used_at?: string | null;
  consumed?: string;
  locations: Array<WarehouseBalance & { location_id: number | null; location_name: string }>;
}
export interface WarehouseArticlePage {
  items: WarehouseArticle[];
  total: number;
  limit: number;
  offset: number;
}
export interface WarehouseForecastRow {
  id: number;
  sku: string;
  name: string;
  unit_code: string;
  available: string;
  minimum_stock: string;
  daily_usage: string | null;
  projected_available: string | null;
  days_until_minimum: number | null;
}
export interface WarehouseForecastPage {
  items: WarehouseForecastRow[];
  window_days: number;
  total: number;
  limit: number;
  offset: number;
}
export type WarehouseArticleSortColumn = 'id' | 'sku' | 'name' | 'kind' | 'physical' | 'reserved' | 'available'
  | 'minimum_stock' | 'created_at' | 'last_used_at' | 'consumed' | 'remaining' | 'stock_checked_at';

export interface WarehouseArticleListParams {
  article_id?: number;
  sort_by?: WarehouseArticleSortColumn | 'stock_source' | 'is_active' | 'unit_cost' | 'sale_price' | 'updated_at';
  sort_dir?: 'asc' | 'desc';
  q?: string;
  active?: boolean;
  kind?: WarehouseArticleKind;
  stock_source?: WarehouseStockSource;
  usage?: 'used' | 'new';
  location_id?: number;
  unit_code?: string;
  low_stock?: boolean;
  limit?: number;
  offset?: number;
}
export const productionDemandFilter = {
  active: true, kind: 'finished', stock_source: 'own', low_stock: true,
} as const satisfies WarehouseArticleListParams;

export function needsWarehouseProduction(article: WarehouseArticle): boolean {
  return article.is_active && article.kind === productionDemandFilter.kind &&
    article.stock_source === productionDemandFilter.stock_source && article.balance.is_low_stock;
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

export function canArchiveWarehouseArticle(article: WarehouseArticle) {
  return Number(article.balance.physical) === 0 && Number(article.balance.reserved) === 0;
}

export const warehouseArticlesApi = {
  confirmStockCheck: (ids: number[]) => request<{ stock_checked_at: string }>('/warehouse-articles/stock-check', { method: 'POST', body: JSON.stringify({ ids }) }),
  list: (params: WarehouseArticleListParams = {}) => request<WarehouseArticlePage>(`/warehouse-articles?${query(params)}`),
  forecast: (offset: number, limit: number) => request<WarehouseForecastPage>(`/warehouse-articles/forecast?${query({ offset, limit })}`),
  get: (id: number) => request<WarehouseArticle>(`/warehouse-articles/${id}`),
  create: (input: WarehouseArticleInput) => request<WarehouseArticle>('/warehouse-articles', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: WarehouseArticleUpdate) => request<WarehouseArticle>(`/warehouse-articles/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  archive: (id: number, version: number) => request<WarehouseArticle>(`/warehouse-articles/${id}?version=${version}`, { method: 'DELETE' }),
  setActive: (article: WarehouseArticle, active: boolean) => active
    ? warehouseArticlesApi.update(article.id, { version: article.version, is_active: true })
    : warehouseArticlesApi.archive(article.id, article.version),
  ledger: (id: number, offset = 0, limit = 50) => request<WarehouseMovement[]>(`/warehouse-articles/${id}/ledger?${query({ offset, limit })}`),
  reservations: (id: number) => request<WarehouseReservation[]>(`/warehouse-articles/${id}/reservations`),
  addLedger: (id: number, input: WarehouseMovementInput) => request<WarehouseMovement>(`/warehouse-articles/${id}/ledger`, { method: 'POST', body: JSON.stringify(input) }),
};
