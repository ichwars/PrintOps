import { API_BASE, ApiError, getAuthToken, parseContentDispositionFilename, request } from './core';

export interface LexwarePaymentItem {
  item_type: string;
  category: string;
  amount: string;
  currency: string;
  posting_date: string | null;
}

export interface LexwareDocumentFinance {
  currency: string;
  total_amount: string | null;
  open_amount: string | null;
  payment_state: 'known' | 'unknown' | 'not_applicable';
  payment_status: string | null;
  direction: 'receivable' | 'payable' | 'none';
  credit: boolean;
  overdue: boolean | null;
  included_in_totals: boolean;
  exclusion_reason: string | null;
  payment_items: LexwarePaymentItem[];
}

export interface LexwareOriginalFile {
  file_id: string;
  cached: boolean;
  filename?: string | null;
  media_type?: string | null;
  size_bytes?: number | null;
  sha256?: string | null;
  cached_at?: string | null;
}

export interface LexwareDocument {
  id: number;
  connection_id: number;
  business_profile_id: number;
  company_name: string;
  source: 'lexware';
  external_id: string;
  voucher_type: string;
  voucher_status: string;
  voucher_number: string | null;
  voucher_date: string | null;
  contact_name: string | null;
  supported: boolean;
  archived: boolean;
  in_latest_sync: boolean;
  connection_enabled: boolean;
  sync_status: string;
  last_success_at: string | null;
  updated_at: string;
  version: number;
  local_document_id: number | null;
  due_date?: string | null;
  finance?: LexwareDocumentFinance;
  files?: LexwareOriginalFile[];
}

export interface LexwareFinance {
  source: 'lexware';
  as_of: string;
  totals: Array<{
    currency: string;
    receivables: string;
    payables: string;
    overdue_receivables: string;
    overdue_payables: string;
    document_count: number;
  }>;
  included_count: number;
  linked_count: number;
  unknown_count: number;
  excluded_count: number;
  unsupported_count: number;
  stale_connection_count: number;
}

export interface LexwareDocumentFilters {
  connection_id?: number;
  business_profile_id?: number;
  search?: string;
  voucher_type?: string;
  offset?: number;
  limit?: number;
}

function query(filters: LexwareDocumentFilters): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value));
  }
  return params.size ? `?${params}` : '';
}

export const lexwareDocumentsApi = {
  list: (filters: LexwareDocumentFilters = {}) =>
    request<{ items: LexwareDocument[]; total: number }>(`/lexware/documents${query(filters)}`),
  detail: (id: number) => request<LexwareDocument>(`/lexware/documents/${id}`),
  finance: (filters: Pick<LexwareDocumentFilters, 'connection_id' | 'business_profile_id'> = {}) =>
    request<LexwareFinance>(`/lexware/finance${query(filters)}`),
  link: (id: number, localDocumentId: number | null, expectedVersion: number) =>
    request<LexwareDocument>(`/lexware/documents/${id}/link`, {
      method: 'PUT', body: JSON.stringify({ local_document_id: localDocumentId, expected_version: expectedVersion }),
    }),
  download: async (documentId: number, fileId: string) => {
    const token = getAuthToken();
    const response = await fetch(`${API_BASE}/lexware/documents/${documentId}/files/${encodeURIComponent(fileId)}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new ApiError(typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`, response.status);
    }
    return {
      blob: await response.blob(),
      filename: parseContentDispositionFilename(response.headers.get('Content-Disposition')) || `lexware-${fileId}`,
    };
  },
};
