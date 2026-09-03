import { request } from './core';
import type { WarehouseArticleCreateInput } from './warehouse-articles';

export type LexwareResourceKind = 'contacts' | 'articles';

export interface LexwareConnection {
  id: number;
  business_profile_id: number;
  organization_id: string;
  company_name: string;
  enabled: boolean;
  connected: boolean;
  version: number;
  sync_status: string;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_error: string | null;
}

export interface LexwareOrganization {
  organization_id: string;
  company_name: string;
}

export interface LexwareResource {
  id: number;
  external_id: string;
  name: string;
  number: string | null;
  archived: boolean;
  version_hash: string;
  customer_id: number | null;
  article_id: number | null;
  payload: Record<string, unknown>;
  updated_at: string;
}

export interface LexwarePreviewRequest {
  resource_id: number;
  customer_id?: number | null;
  article_id?: number | null;
}

export interface LexwarePreview {
  resource_id: number;
  version_hash: string;
  local_version: number | null;
  customer_id: number | null;
  article_id: number | null;
  source: Record<string, unknown>;
  current: Record<string, unknown>;
  changes: Array<{ field: string; current: unknown; incoming: unknown }>;
  affected_profiles: Array<{ id: number; name: string }>;
  warnings: string[];
}

export type LexwareArticleOptions = Pick<WarehouseArticleCreateInput, 'sku' | 'kind' | 'unit_code' | 'small_part_id' | 'project_id' | 'calculation_revision_id'>
  & Required<Pick<WarehouseArticleCreateInput, 'stock_source'>>;

export interface LexwareImportRequest extends LexwarePreviewRequest {
  version_hash: string;
  local_version: number | null;
  fields: string[];
  article_options?: LexwareArticleOptions;
  confirmed_unit_code?: string | null;
}

export interface LexwareImportResult {
  customer_id?: number | null;
  article_id?: number | null;
  unchanged: boolean;
}

const base = '/lexware/connections';

/** Requests go to PrintOps only. Upstream access and token storage belong to the backend. */
export const lexwareApi = {
  connections: () => request<LexwareConnection[]>(base),
  test: (apiKey: string) => request<LexwareOrganization>(`${base}/test`, {
    method: 'POST', body: JSON.stringify({ api_key: apiKey }),
  }),
  create: (data: { business_profile_id: number; api_key: string; organization_id: string }) =>
    request<LexwareConnection>(base, { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: { enabled?: boolean; api_key?: string }) =>
    request<LexwareConnection>(`${base}/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  disconnect: (id: number) => request<void>(`${base}/${id}`, { method: 'DELETE' }),
  sync: (id: number) => request<{ status: 'queued' }>(`${base}/${id}/sync`, { method: 'POST' }),
  resources: (id: number, kind: LexwareResourceKind) =>
    request<LexwareResource[]>(`${base}/${id}/resources?kind=${kind}`),
  preview: (id: number, data: LexwarePreviewRequest) =>
    request<LexwarePreview>(`${base}/${id}/preview`, { method: 'POST', body: JSON.stringify(data) }),
  import: (id: number, data: LexwareImportRequest) =>
    request<LexwareImportResult>(`${base}/${id}/import`, { method: 'POST', body: JSON.stringify(data) }),
};
