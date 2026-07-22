import { ApiError, getAuthToken, request } from './client';

export type DocumentType =
  | 'quotation'
  | 'order_confirmation'
  | 'delivery_note'
  | 'advance_invoice'
  | 'progress_invoice'
  | 'final_invoice'
  | 'invoice'
  | 'cancellation_invoice'
  | 'invoice_correction'
  | 'commercial_credit_note'
  | 'payment_reminder'
  | 'dunning_notice'
  | 'self_billing';

export type ConfigurationStatus = 'draft' | 'scheduled' | 'active' | 'superseded';
export type ReadinessStatus = 'ready' | 'warnings' | 'blocked';

export interface DocumentCatalogItem {
  key: DocumentType;
  einvoice: boolean;
  issuer_role: 'seller' | 'buyer';
  has_payment_terms: boolean;
  has_tax: boolean;
  allowed_successors: DocumentType[];
}

export interface DocumentCatalogResponse {
  document_types: DocumentCatalogItem[];
  tax_rule_version: string;
  einvoice_rule_versions: Record<string, string>;
}

export interface PlaceholderCatalogResponse {
  placeholders: string[];
  text_block_purposes: string[];
}

export interface DocumentConfigurationSummary {
  id: number;
  business_profile_id: number;
  document_type: DocumentType;
  language: string;
  version: number;
  status: ConfigurationStatus;
  effective_from: string | null;
  lock_version: number;
  change_reason: string | null;
  created_by_id: number | null;
  published_by_id: number | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  publication_validation_status: string | null;
  rule_versions: Record<string, string>;
}

export interface DocumentAuditEvent {
  id: number;
  action: string;
  object_type: string;
  object_id: number;
  actor_id: number | null;
  reason: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  correlation_id: string;
  created_at: string;
}

export interface PaymentPolicyDraft {
  payment_term_days: number;
  currency: string;
  due_date_basis: string;
  payment_methods: string[];
  discount_days: number;
  discount_percent: string;
  installments: Array<{ percent: string; due_days: number }>;
  prepayment_percent: string;
  installment_enabled: boolean;
  bank_account_id: number | null;
  bank_assignments: Array<{ bank_account_id: number; is_default: boolean }>;
  use_term_in_invoice_text: boolean;
}

export interface BasicPolicyDraft {
  subject: string;
  validity_days: number | null;
  date_rule: string;
  rounding_mode: string;
  reference_requirements: Record<string, boolean>;
  allowed_successors: DocumentType[];
}

export interface ContentPolicyDraft {
  include_calculation_data: boolean;
  visible_content: Record<string, boolean>;
}

export interface TaxPolicyDraft {
  allowed_cases: string[];
  decision_rules: Record<string, unknown>;
  allow_override: boolean;
}

export interface EInvoicePolicyDraft {
  requirement: string;
  en16931_version: string;
  cius_name: string;
  cius_version: string;
  syntax: string;
  zugferd_profile: string;
  process_identifier: string | null;
  seller_identifier: string | null;
  seller_identifier_scheme: string | null;
  default_payment_method: string | null;
  bank_account_id: number | null;
  recipient_requirements: Record<string, unknown>;
}

export interface DunningPolicyDraft {
  enabled: boolean;
  annual_interest_rate: string;
  flat_fee: string;
  stages: Array<{
    level: number;
    wait_days: number;
    fee: string;
    charge_interest: boolean;
    new_due_days: number;
    body: string;
    escalation_hint: string | null;
  }>;
}

export interface DocumentConfigurationDraft {
  document_type: DocumentType;
  language: string;
  basic: BasicPolicyDraft;
  payment: PaymentPolicyDraft;
  dunning: DunningPolicyDraft;
  content: ContentPolicyDraft;
  tax: TaxPolicyDraft;
  einvoice: EInvoicePolicyDraft;
  text_blocks: Array<{
    purpose: string;
    body: string;
    condition: Record<string, unknown> | null;
    position: number;
  }>;
}

export interface PolicyFinding {
  severity: 'warning' | 'blocker';
  code: string;
  field_path: string;
  message_key: string;
  rule_id: string | null;
}

export interface ReadinessFinding extends PolicyFinding {
  correction: string;
}

export interface DocumentConfigurationDetail extends DocumentConfigurationSummary {
  policy: DocumentConfigurationDraft | null;
  validation_findings: PolicyFinding[];
}

export interface ReadinessReport {
  context: 'configuration' | 'document';
  status: ReadinessStatus;
  findings: ReadinessFinding[];
}

export interface SourcedValue<T> {
  value: T;
  source: 'system' | 'business_profile' | 'customer' | 'configuration' | 'document';
  overridable: boolean;
}

export interface EffectiveDocumentPolicy {
  configuration_id: number;
  configuration_version: number;
  basic: Record<string, SourcedValue<unknown>>;
  payment: Record<string, SourcedValue<unknown>>;
  content: Record<string, SourcedValue<unknown>>;
  tax: Record<string, SourcedValue<unknown>>;
  einvoice: Record<string, SourcedValue<unknown>>;
  text_blocks: Array<{
    purpose: string;
    body: SourcedValue<string>;
    condition: Record<string, unknown> | null;
    position: number;
  }>;
}

export interface EffectivePolicyContext {
  business_profile_id: number;
  customer_id?: number | null;
  document_type: DocumentType;
  language: string;
  document_overrides?: Record<string, unknown>;
}

export interface EInvoiceArtifact {
  id: number;
  document_id: number;
  document_number: string | null;
  kind: string;
  content_type: string;
  sha256: string;
  validation_status: string;
  rule_versions: Record<string, unknown>;
  created_at: string;
}

export interface EInvoiceValidationReport {
  artifact_id: number;
  sha256: string;
  rule_versions: Record<string, unknown>;
  [key: string]: unknown;
}

export interface ConfigurationFilters {
  businessProfileId?: number;
  documentType?: DocumentType;
  language?: string;
  status?: ConfigurationStatus;
}

function queryString(filters: ConfigurationFilters): string {
  const params = new URLSearchParams();
  if (filters.businessProfileId) params.set('business_profile_id', String(filters.businessProfileId));
  if (filters.documentType) params.set('document_type', filters.documentType);
  if (filters.language) params.set('language', filters.language);
  if (filters.status) params.set('status', filters.status);
  const value = params.toString();
  return value ? `?${value}` : '';
}

async function parseDownloadError(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => ({}));
  const detail = payload?.detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const structured = detail as Record<string, unknown>;
    return new ApiError(
      typeof structured.message === 'string' ? structured.message : `HTTP ${response.status}`,
      response.status,
      typeof structured.code === 'string' ? structured.code : null,
      structured,
    );
  }
  return new ApiError(typeof detail === 'string' ? detail : `HTTP ${response.status}`, response.status);
}

export const documentManagementApi = {
  getCatalog: () => request<DocumentCatalogResponse>('/document-configurations/catalog'),
  getPlaceholders: () => request<PlaceholderCatalogResponse>('/document-configurations/placeholders'),
  listConfigurations: (filters: ConfigurationFilters = {}) =>
    request<DocumentConfigurationSummary[]>(`/document-configurations/${queryString(filters)}`),
  getConfiguration: (configurationId: number) =>
    request<DocumentConfigurationDetail>(`/document-configurations/${configurationId}`),
  createConfiguration: (command: {
    business_profile_id: number;
    document_type: DocumentType;
    language: string;
    change_reason?: string | null;
  }) => request<DocumentConfigurationDetail>('/document-configurations/', {
    method: 'POST',
    body: JSON.stringify(command),
  }),
  updateConfiguration: (configurationId: number, expectedVersion: number, patch: Record<string, unknown>) =>
    request<DocumentConfigurationDetail>(`/document-configurations/${configurationId}`, {
      method: 'PATCH',
      body: JSON.stringify({ expected_version: expectedVersion, patch }),
    }),
  cloneConfiguration: (configurationId: number) =>
    request<DocumentConfigurationDetail>(`/document-configurations/${configurationId}/clone`, { method: 'POST' }),
  getConfigurationReadiness: (configurationId: number) =>
    request<ReadinessReport>(`/document-configurations/${configurationId}/readiness`),
  publishConfiguration: (configurationId: number, expectedVersion: number, effectiveFrom: string, reason: string) =>
    request<DocumentConfigurationDetail>(`/document-configurations/${configurationId}/publish`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: expectedVersion, effective_from: effectiveFrom, reason }),
    }),
  withdrawConfiguration: (configurationId: number, expectedVersion: number, reason: string) =>
    request<DocumentConfigurationDetail>(`/document-configurations/${configurationId}/withdraw`, {
      method: 'POST',
      body: JSON.stringify({ expected_version: expectedVersion, reason }),
    }),
  getConfigurationHistory: (configurationId: number) =>
    request<DocumentConfigurationSummary[]>(`/document-configurations/${configurationId}/history`),
  getConfigurationAudit: (configurationId: number) =>
    request<DocumentAuditEvent[]>(`/document-configurations/${configurationId}/audit`),
  getSelectedConfiguration: async (filters: ConfigurationFilters) => {
    const configurations = await request<DocumentConfigurationSummary[]>(
      `/document-configurations/${queryString(filters)}`,
    );
    return configurations[0]
      ? request<DocumentConfigurationDetail>(`/document-configurations/${configurations[0].id}`)
      : null;
  },
  getEffectivePolicy: (context: EffectivePolicyContext) =>
    request<EffectiveDocumentPolicy>('/document-configurations/effective', {
      method: 'POST',
      body: JSON.stringify({ document_overrides: {}, ...context }),
    }),
  validateDocument: (documentId: number) =>
    request<ReadinessReport>(`/commercial-documents/${documentId}/validate`, { method: 'POST' }),
  getEInvoiceArtifact: (artifactId: number) => request<EInvoiceArtifact>(`/einvoices/${artifactId}`),
  getEInvoiceValidation: (artifactId: number) =>
    request<EInvoiceValidationReport>(`/einvoices/${artifactId}/validation`),
  downloadEInvoice: async (artifactId: number): Promise<{ blob: Blob; filename: string }> => {
    const headers: Record<string, string> = {};
    const token = getAuthToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(`/api/v1/einvoices/${artifactId}/download`, {
      headers,
      cache: 'no-store',
      credentials: 'include',
    });
    if (!response.ok) throw await parseDownloadError(response);
    const disposition = response.headers.get('Content-Disposition');
    const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1] ?? `einvoice-${artifactId}.xml`;
    return { blob: await response.blob(), filename };
  },
};
