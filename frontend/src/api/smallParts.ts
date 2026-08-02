import { getAuthToken, request } from './client';
import type { ProcurementOffer } from './procurement';

const API_BASE = '/api/v1';

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

export interface SmallPartCsvImportRow {
  row_number: number;
  status: 'valid' | 'error';
  action: 'create' | 'update' | null;
  sku: string;
  name: string;
  unit_code: string;
  opening_quantity: string;
  reason: string | null;
  warnings: string[];
}

export interface SmallPartCsvImportPreview {
  rows: SmallPartCsvImportRow[];
  valid_count: number;
  error_count: number;
  skipped_count: number;
  warnings: string[];
}

export interface SmallPartCsvImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  error_rows: Array<{ row_number: number; reason: string; sku?: string; name?: string }>;
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

function parseContentDispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const rfc5987Match = header.match(/filename\*=(?:UTF-8|utf-8)''(.+?)(?:;|$)/);
  if (rfc5987Match) {
    try {
      return decodeURIComponent(rfc5987Match[1]);
    } catch {
      // Fall through to the plain filename form.
    }
  }
  const standardMatch = header.match(/filename="?([^";\n]+)"?/);
  return standardMatch?.[1] || null;
}

async function uploadSmallPartsCsv<T>(file: File, dryRun: boolean): Promise<T> {
  const form = new FormData();
  form.append('file', file);
  const headers: Record<string, string> = {};
  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}/small-parts/import${dryRun ? '?dry_run=true' : ''}`, {
    method: 'POST',
    headers,
    body: form,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = error?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message;
    throw new Error(message || `HTTP ${response.status}`);
  }
  return response.json();
}

async function downloadSmallPartsCsv(): Promise<void> {
  const headers: Record<string, string> = {};
  const token = getAuthToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}/small-parts/export`, { headers });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const detail = error?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message;
    throw new Error(message || `HTTP ${response.status}`);
  }
  const filename = parseContentDispositionFilename(response.headers.get('Content-Disposition')) || 'printops-material.csv';
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export const smallPartsApi = {
  search: (q: string) =>
    request<SmallPartOption[]>(`/small-parts/search?${queryString({ q, limit: 30 })}`),
  list: (params: SmallPartListParams = {}) =>
    request<SmallPartPage>(`/small-parts?${queryString(params)}`),
  listAll: async (params: Omit<SmallPartListParams, 'limit' | 'offset'> = {}) => {
    const limit = 200;
    const items: SmallPart[] = [];
    let offset = 0;
    while (true) {
      const page = await smallPartsApi.list({ ...params, limit, offset });
      items.push(...page.items);
      if (page.items.length === 0 || items.length >= page.total) {
        return items;
      }
      offset = page.offset + page.items.length;
    }
  },
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
  importCsvPreview: (file: File) => uploadSmallPartsCsv<SmallPartCsvImportPreview>(file, true),
  importCsv: (file: File) => uploadSmallPartsCsv<SmallPartCsvImportResult>(file, false),
  exportCsv: downloadSmallPartsCsv,
  printLabels: async (data: { small_part_ids: number[]; template: string; monochrome?: boolean }): Promise<Blob> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    const token = getAuthToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(`${API_BASE}/small-parts/labels`, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      const detail = error?.detail;
      const message = typeof detail === 'string' ? detail : detail?.message;
      throw new Error(message || `HTTP ${response.status}`);
    }
    return response.blob();
  },
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
