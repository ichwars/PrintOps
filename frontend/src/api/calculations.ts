import { request } from './client';

export type CalculationStatus = 'draft' | 'approved' | 'superseded' | 'archived';
export type PriceMethod = 'markup' | 'target_margin';

export interface CalculationLine {
  kind: 'printed_part' | 'service' | 'material' | 'packaging' | 'shipping' | 'discount' | 'text';
  description: string;
  quantity: string;
  unit_code: string;
  unit_price: string | null;
  sort_order: number;
}

export interface CalculationOperation {
  [key: string]: unknown;
  kind: 'cad' | 'slicing' | 'setup' | 'printing' | 'drying' | 'post_processing' | 'qa' | 'packing';
  title: string;
  source_file: string | null;
  source_plate: number | null;
  good_parts: number;
  parts_per_run: number;
  scrap_runs: number;
  material_grams_per_run: string;
  print_hours_per_run: string;
  provenance: Record<string, unknown>;
  sort_order: number;
  labor: Array<{ kind: string; hours: string; hourly_rate: string; allocation_basis: 'request' | 'run' | 'unit'; sort_order: number }>;
}

export interface CalculationVariant {
  name: string;
  is_preferred: boolean;
  sort_order: number;
  price_method: PriceMethod;
  price_rate: string;
  lines: CalculationLine[];
  operations: CalculationOperation[];
}

export interface CalculationDetail {
  id: number;
  business_profile_id: number;
  customer_id: number | null;
  title: string;
  status: CalculationStatus;
  currency: string;
  notes: string | null;
  version: number;
  created_at: string;
  updated_at: string;
  variants: CalculationVariant[];
  current_revision: number | null;
  production_cost: string | null;
  selling_price: string | null;
}

export interface CalculationPage {
  items: CalculationDetail[];
  total: number;
  limit: number;
  offset: number;
}

export type CalculationCreate = Omit<CalculationDetail, 'id' | 'status' | 'version' | 'created_at' | 'updated_at' | 'current_revision' | 'production_cost' | 'selling_price'>;
export type CalculationUpdate = CalculationCreate & { expected_version: number };

export interface CalculationRevision {
  id: number; calculation_id: number; revision_number: number; snapshot: Record<string, unknown>;
  production_cost: string; selling_price: string; currency: string; approved_by_id: number | null; approved_at: string;
}

export const calculationsApi = {
  list: (params: { status?: CalculationStatus; limit?: number; offset?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.status) query.set('status', params.status);
    query.set('limit', String(params.limit ?? 50));
    query.set('offset', String(params.offset ?? 0));
    return request<CalculationPage>(`/calculations/?${query}`);
  },
  get: (id: number) => request<CalculationDetail>(`/calculations/${id}`),
  create: (input: CalculationCreate) => request<CalculationDetail>('/calculations/', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: CalculationUpdate) => request<CalculationDetail>(`/calculations/${id}`, { method: 'PUT', body: JSON.stringify(input) }),
  approve: (id: number, expectedVersion: number) => request<CalculationRevision>(`/calculations/${id}/approve`, { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion, warning_reasons: {} }) }),
  createTemplate: (id: number, name: string) => request(`/calculations/${id}/templates`, { method: 'POST', body: JSON.stringify({ name }) }),
};
