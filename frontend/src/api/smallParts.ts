import { request } from './client';
import type { ProcurementOffer } from './procurement';

export interface SmallPartBalance {
  physical: string;
  reserved: string;
  available: string;
  is_low_stock: boolean;
}

export interface SmallPartCategory {
  id: number;
  name: string;
  is_active: boolean;
}

export interface SmallPartUnit {
  code: string;
  label: string;
  decimal_places: number;
  is_active: boolean;
}

export interface SmallPartOption {
  id: number;
  sku: string;
  name: string;
  unit_code: string;
  unit_cost: string;
  available: string;
}

export interface SmallPart extends SmallPartOption {
  description: string | null;
  search_terms: string | null;
  category_id: number | null;
  location_id: number | null;
  minimum_stock: string;
  supplier_reference: string | null;
  default_consumption_reason: string;
  internal_notes: string | null;
  is_active: boolean;
  preferred_offer: ProcurementOffer | null;
  category: SmallPartCategory | null;
  unit: SmallPartUnit;
  balance: SmallPartBalance;
  created_at: string;
  updated_at: string;
}

export interface SmallPartInput {
  sku: string;
  name: string;
  description?: string | null;
  search_terms?: string | null;
  category_id?: number | null;
  unit_code: string;
  location_id?: number | null;
  minimum_stock: string;
  unit_cost: string;
  supplier_reference?: string | null;
  default_consumption_reason: string;
  internal_notes?: string | null;
  is_active: boolean;
}

export interface SmallPartCreateInput extends SmallPartInput {
  opening_quantity: string;
}

export type SmallPartUpdate = Partial<SmallPartInput>;

export interface SmallPartLedgerInput {
  entry_kind: 'receipt' | 'correction';
  quantity: string;
  reason: string;
  idempotency_key: string;
}

export interface SmallPartLedgerEntry {
  id: number;
  small_part_id: number;
  entry_kind: string;
  physical_delta: string;
  reserved_delta: string;
  reason: string;
  reference_type: string | null;
  reference_id: number | null;
  actor_id: number | null;
  idempotency_key: string;
  created_at: string;
}

export interface SmallPartListParams {
  q?: string;
  active?: boolean;
  low_stock?: boolean;
  limit?: number;
  offset?: number;
}

export interface SmallPartPage {
  items: SmallPart[];
  total: number;
  limit: number;
  offset: number;
}

function queryString<T extends object>(params: T): string {
  const result = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) result.set(key, String(value));
  });
  return result.toString();
}

export const smallPartsApi = {
  search: (q: string) =>
    request<SmallPartOption[]>(`/small-parts/search?${queryString({ q, limit: 30 })}`),
  list: (params: SmallPartListParams = {}) =>
    request<SmallPartPage>(`/small-parts?${queryString(params)}`),
  get: (id: number) => request<SmallPart>(`/small-parts/${id}`),
  create: (input: SmallPartCreateInput) =>
    request<SmallPart>('/small-parts', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: SmallPartUpdate) =>
    request<SmallPart>(`/small-parts/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  ledger: (id: number) => request<SmallPartLedgerEntry[]>(`/small-parts/${id}/ledger`),
  addLedger: (id: number, input: SmallPartLedgerInput) =>
    request<SmallPartLedgerEntry>(`/small-parts/${id}/ledger`, {
      method: 'POST',
      body: JSON.stringify(input),
    }),
  categories: {
    list: () => request<SmallPartCategory[]>('/small-parts/settings/categories'),
    create: (input: { name: string; is_active?: boolean }) =>
      request<SmallPartCategory>('/small-parts/settings/categories', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    update: (id: number, input: Partial<Pick<SmallPartCategory, 'name' | 'is_active'>>) =>
      request<SmallPartCategory>(`/small-parts/settings/categories/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }),
    remove: (id: number) =>
      request<void>(`/small-parts/settings/categories/${id}`, { method: 'DELETE' }),
  },
  units: {
    list: () => request<SmallPartUnit[]>('/small-parts/settings/units'),
    create: (input: Omit<SmallPartUnit, 'is_active'> & { is_active?: boolean }) =>
      request<SmallPartUnit>('/small-parts/settings/units', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    update: (code: string, input: Partial<Omit<SmallPartUnit, 'code'>>) =>
      request<SmallPartUnit>(`/small-parts/settings/units/${encodeURIComponent(code)}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }),
    remove: (code: string) =>
      request<void>(`/small-parts/settings/units/${encodeURIComponent(code)}`, { method: 'DELETE' }),
  },
};
