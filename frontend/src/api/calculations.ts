import { getAuthToken, request } from './client';

export type CalculationStatus = 'draft' | 'approved' | 'superseded' | 'archived';
export type PriceMethod = 'markup' | 'target_margin' | 'explicit_price';

export interface CalculationPreviewInput {
  good_parts: number; parts_per_run: number; scrap_runs: number;
  material_grams_per_run: string; material_price_per_kg: string;
  print_hours_per_run: string; machine_cost_per_hour: string;
  acquisition_value?: string; residual_value?: string; service_years?: string;
  annual_hours?: string; maintenance_rate?: string;
  printer_power_kw: string; electricity_price_per_kwh: string;
  drying_hours: string; dryer_power_kw: string;
  labor: Array<{ kind: string; hours: string; hourly_rate: string; allocation_basis: 'request' | 'run' | 'unit'; sort_order: number }>;
  consumables: string; packaging: string; additional_costs: string; risk_rate: string;
  shipping: string; price_method: PriceMethod; price_rate: string; explicit_price: string;
  discount_rate: string; tax_rate: string; minimum_price: string; minimum_profit: string;
  rounding_mode: 'none' | '0.05' | '0.10' | '0.50' | '1.00' | 'x.90' | 'x.99';
}

export interface CalculationPreview {
  total_runs: number; material_cost: string; machine_cost: string; energy_cost: string;
  labor_cost: string; consumables: string; packaging: string; additional_costs: string;
  risk_cost: string; production_cost: string; shipping: string; selling_price: string;
  net_price: string; contribution: string; effective_margin: string; tax: string;
  gross_price: string; unit_price: string;
}

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
  uploadSource: async (file: File) => {
    const form = new FormData(); form.append('file', file);
    const token = getAuthToken();
    const response = await fetch('/api/v1/calculations/source-files', { method: 'POST', body: form, credentials: 'include', headers: token ? { Authorization: `Bearer ${token}` } : undefined });
    if (!response.ok) throw new Error(`Upload failed (${response.status})`);
    return response.json() as Promise<{ source_file: string; filename: string; size_bytes: number; plate_count: number; print_time_seconds: number | null; material_grams: number; filaments: Array<Record<string, unknown>> }>;
  },
  preview: (input: CalculationPreviewInput) => request<CalculationPreview>('/calculations/preview', { method: 'POST', body: JSON.stringify(input) }),
  previewBatch: (operations: CalculationPreviewInput[], commercial: CalculationPreviewInput) => request<CalculationPreview>('/calculations/preview-batch', { method: 'POST', body: JSON.stringify({ operations, commercial }) }),
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
  archive: (id: number, expectedVersion: number) => request<CalculationDetail>(`/calculations/${id}/archive?expected_version=${expectedVersion}`, { method: 'POST' }),
  revisions: (id: number) => request<CalculationRevision[]>(`/calculations/${id}/revisions`),
  createTemplate: (id: number, name: string) => request(`/calculations/${id}/templates`, { method: 'POST', body: JSON.stringify({ name }) }),
};
