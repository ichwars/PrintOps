import { ApiError, getAuthToken, request } from './client';

const API_BASE = '/api/v1';

export type LayoutTemplateKey = 'classic' | 'modern' | 'compact';
export type LayoutPageFormat = 'A4' | 'Letter';
export type LayoutLanguage = 'de' | 'en';
export type LayoutStatus = 'draft' | 'scheduled' | 'active' | 'superseded' | 'withdrawn';
export type LayoutValidationStatus = 'valid' | 'invalid' | 'unvalidated';
export type LayoutSourceLevel = 'system' | 'profile' | 'document_type' | 'language';
export type LayoutAssetType = 'logo' | 'letterhead_first' | 'letterhead_following' | 'font';
export type LayoutAssetRole =
  | 'logo'
  | 'letterhead_first'
  | 'letterhead_following'
  | 'font_regular'
  | 'font_bold'
  | 'font_italic'
  | 'font_bold_italic';

export interface PageRules {
  template_key: LayoutTemplateKey;
  page_format: LayoutPageFormat;
  orientation: 'portrait';
  margin_top_mm: number;
  margin_right_mm: number;
  margin_bottom_mm: number;
  margin_left_mm: number;
  first_page_content_top_mm: number;
  following_page_content_top_mm: number;
  use_first_page_letterhead: boolean;
  use_following_page_letterhead: boolean;
  reuse_first_letterhead: boolean;
}

export interface TypographyRules {
  font_family: string;
  base_size_pt: number;
  table_size_pt: number;
  metadata_size_pt: number;
  heading_scale: number;
  line_height: number;
  paragraph_spacing_mm: number;
  accent_color: string;
  text_color: string;
  muted_color: string;
}

export interface HeaderRules {
  show_logo: boolean;
  logo_width_mm: number;
  logo_alignment: 'left' | 'center' | 'right';
  show_company_details: boolean;
  show_sender_line: boolean;
  recipient_window: 'left' | 'right';
  recipient_top_mm: number;
}

export interface TitleRules {
  show_title: boolean;
  show_document_number: boolean;
  show_issue_date: boolean;
  show_service_date: boolean;
  show_due_date: boolean;
  show_customer_number: boolean;
  metadata_alignment: 'left' | 'right';
  title_spacing_mm: number;
}

export interface PositionRules {
  table_style: 'compact' | 'standard' | 'spacious';
  show_position_number: boolean;
  show_description: boolean;
  show_quantity: boolean;
  show_unit: boolean;
  show_unit_price: boolean;
  show_net_amount: boolean;
  show_tax_rate: boolean;
  show_total: boolean;
  show_secondary_description: boolean;
  repeat_header: boolean;
}

export interface TotalsRules {
  show_subtotal: boolean;
  show_discount: boolean;
  show_tax_breakdown: boolean;
  show_gross_total: boolean;
  show_prepayments: boolean;
  show_payment_terms: boolean;
  show_bank_details: boolean;
  totals_alignment: 'left' | 'right';
}

export interface TechnicalRules {
  enabled: boolean;
  show_printer: boolean;
  show_plate: boolean;
  show_material: boolean;
  show_print_time: boolean;
  show_weight: boolean;
  show_file_name: boolean;
  placement: 'position' | 'notes';
}

export interface NotesRules {
  show_intro_text: boolean;
  show_outro_text: boolean;
  show_payment_note: boolean;
  show_legal_note: boolean;
  intro_placement: 'before_title' | 'before_positions';
  outro_placement: 'after_positions' | 'after_totals';
  keep_with_next: boolean;
}

export interface FooterRules {
  enabled: boolean;
  column_layout: 'one' | 'two' | 'three';
  show_company_data: boolean;
  show_tax_data: boolean;
  show_bank_data: boolean;
  show_alternative_payment: boolean;
  show_additional_notes: boolean;
  show_page_numbers: boolean;
  page_number_format: string;
}

export interface EffectiveDocumentLayout {
  schema_version: number;
  template_version: string;
  renderer_version: string;
  validator_version: string;
  page: PageRules;
  typography: TypographyRules;
  header: HeaderRules;
  title: TitleRules;
  positions: PositionRules;
  totals: TotalsRules;
  technical: TechnicalRules;
  notes: NotesRules;
  footer: FooterRules;
}

export interface LayoutValueSource {
  level: LayoutSourceLevel;
  configuration_id: number | null;
  version: number | null;
}

export type LayoutRuleSources<T> = { [K in keyof T]: LayoutValueSource };
export interface SourcedLayoutRule<T> {
  value: T;
  sources: LayoutRuleSources<T>;
}

export interface SourcedDocumentLayout {
  effective: EffectiveDocumentLayout;
  page: SourcedLayoutRule<PageRules>;
  typography: SourcedLayoutRule<TypographyRules>;
  header: SourcedLayoutRule<HeaderRules>;
  title: SourcedLayoutRule<TitleRules>;
  positions: SourcedLayoutRule<PositionRules>;
  totals: SourcedLayoutRule<TotalsRules>;
  technical: SourcedLayoutRule<TechnicalRules>;
  notes: SourcedLayoutRule<NotesRules>;
  footer: SourcedLayoutRule<FooterRules>;
}

export type LayoutRulePatch<T> = { [K in keyof T]?: T[K] | null };

export interface LayoutScope {
  business_profile_id: number;
  document_type: string | null;
  language: LayoutLanguage | null;
}

export interface LayoutSummary {
  id: number;
  scope: LayoutScope;
  version: number;
  status: LayoutStatus;
  lock_version: number;
  effective_from: string | null;
  created_at: string;
  updated_at: string;
}

export interface LayoutAsset {
  id: number;
  business_profile_id: number;
  asset_type: LayoutAssetType;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  preflight_status: 'pending' | 'valid' | 'invalid';
  preflight_report: Record<string, unknown>;
  created_at: string;
}

export interface LayoutDetail {
  summary: LayoutSummary;
  effective: EffectiveDocumentLayout;
  sourced: SourcedDocumentLayout;
  validation_status: LayoutValidationStatus;
  validation_report: Record<string, unknown>;
  assets: LayoutAsset[];
}

export interface LayoutCatalog {
  templates: Array<{ key: LayoutTemplateKey; version: string; description: string }>;
  page_formats_mm: Record<LayoutPageFormat, readonly [number, number]>;
  languages: LayoutLanguage[];
  document_types: string[];
}

export interface LayoutSample {
  id: string;
  label: string;
  document_type: string;
  language: string;
  [key: string]: unknown;
}

export interface LayoutEffectiveResponse {
  effective: EffectiveDocumentLayout;
  sourced: SourcedDocumentLayout;
  effective_sha256: string;
  configuration_ids: number[];
}

export interface LayoutPatch {
  expected_lock_version: number;
  edit_session_id: string;
  page?: LayoutRulePatch<PageRules> | null;
  typography?: LayoutRulePatch<TypographyRules> | null;
  header?: LayoutRulePatch<HeaderRules> | null;
  title?: LayoutRulePatch<TitleRules> | null;
  positions?: LayoutRulePatch<PositionRules> | null;
  totals?: LayoutRulePatch<TotalsRules> | null;
  technical?: LayoutRulePatch<TechnicalRules> | null;
  notes?: LayoutRulePatch<NotesRules> | null;
  footer?: LayoutRulePatch<FooterRules> | null;
}

export interface LayoutFinding {
  code: string;
  severity: 'info' | 'warning' | 'blocker';
  field_path: string | null;
  message_key: string;
  message: string;
  correction_hint: string | null;
  external_rule_id: string | null;
}

export interface LayoutReadinessReport {
  ready: boolean;
  findings: LayoutFinding[];
  renderer_version: string;
  validator_version: string;
}

export interface LayoutAuditReceipt {
  id: number;
  layout_id: number;
  event_type: string;
  edit_session_id: string | null;
  reason: string | null;
  changed_field_paths: string[];
  actor_id: number | null;
  first_seen_at: string;
  last_seen_at: string;
}

export interface PreviewRequest {
  layout_id: number;
  layout_lock_version: number;
  source_kind: 'sample' | 'document';
  source_id: string;
}

export interface PreviewJob {
  public_id: string;
  status: 'queued' | 'running' | 'ready' | 'failed' | 'expired';
  layout_id: number;
  lock_version: number;
  expires_at: string;
  result_sha256: string | null;
}

export interface PreviewPollResult {
  job: PreviewJob | null;
  etag: string | null;
  notModified: boolean;
}

export interface PreviewReport {
  status: PreviewJob['status'];
  findings: Record<string, unknown>;
}

export interface RuntimeComponentStatus {
  ready?: boolean;
  available?: boolean;
  version?: string | null;
  [key: string]: unknown;
}

export interface DocumentRuntimeReadiness {
  ready: boolean;
  renderer: RuntimeComponentStatus;
  pango: RuntimeComponentStatus;
  icc_profile_sha256: string | null;
  icc_profile_valid: boolean;
  validator: RuntimeComponentStatus;
  findings: string[];
}

export interface ExternalRenderRequest {
  document_snapshot_id: number;
  published_layout_id?: number | null;
  zugferd_artifact_id?: number | null;
  xrechnung_artifact_id?: number | null;
  idempotency_id: string;
}

export interface ExternalRenderResponse {
  artifact_id: number;
  sha256: string;
  validation_status: LayoutValidationStatus;
  content_type: string;
  correlation_id: string;
}

export type LayoutAccessState =
  | { mode: 'manage'; canRead: true; canManage: true; reason: null }
  | { mode: 'read-only'; canRead: true; canManage: false; reason: 'missing_manage_permission' }
  | { mode: 'unavailable'; canRead: false; canManage: false; reason: 'missing_read_permission' };

export function resolveLayoutAccess(
  permissions: readonly string[],
  authEnabled: boolean,
): LayoutAccessState {
  if (!authEnabled) {
    return { mode: 'manage', canRead: true, canManage: true, reason: null };
  }
  const canRead = permissions.includes('document_layouts:read');
  const canManage = permissions.includes('document_layouts:manage');
  if (canManage) {
    return { mode: 'manage', canRead: true, canManage: true, reason: null };
  }
  if (canRead) {
    return { mode: 'read-only', canRead: true, canManage: false, reason: 'missing_manage_permission' };
  }
  return { mode: 'unavailable', canRead: false, canManage: false, reason: 'missing_read_permission' };
}

export class LayoutVersionConflictError extends ApiError {
  constructor(error: ApiError) {
    super(error.message, error.status, error.code, error.detail, error.validationErrors);
    this.name = 'LayoutVersionConflictError';
  }
}

async function parseRawError(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => ({}));
  const detail = payload && typeof payload === 'object' ? (payload as { detail?: unknown }).detail : undefined;
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

async function authorizedFetch(endpoint: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  const token = getAuthToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
    cache: 'no-store',
    credentials: 'include',
  });
  if (!response.ok && response.status !== 304) throw await parseRawError(response);
  return response;
}

function queryString(values: Record<string, string | number | null | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== null && value !== undefined && value !== '') params.set(key, String(value));
  }
  const encoded = params.toString();
  return encoded ? `?${encoded}` : '';
}

export interface UploadLayoutAssetInput {
  businessProfileId: number;
  assetType: LayoutAssetType;
  declaredSha256: string;
  file: File;
  fontEmbeddingRightsConfirmed?: boolean;
  signal?: AbortSignal;
}

export const documentLayoutsApi = {
  getCatalog: () => request<LayoutCatalog>('/document-layouts/catalog'),
  getSamples: () => request<LayoutSample[]>('/document-layouts/samples'),
  listLayouts: (businessProfileId: number) =>
    request<LayoutSummary[]>(`/document-layouts${queryString({ business_profile_id: businessProfileId })}`),
  getEffectiveLayout: (scope: {
    businessProfileId: number;
    documentType?: string | null;
    language?: LayoutLanguage | null;
    draftLayoutId?: number | null;
  }) =>
    request<LayoutEffectiveResponse>(`/document-layouts/effective${queryString({
      business_profile_id: scope.businessProfileId,
      document_type: scope.documentType,
      language: scope.language,
      draft_layout_id: scope.draftLayoutId,
    })}`),
  createLayout: (command: { scope: LayoutScope; template_key: LayoutTemplateKey; reason: string }) =>
    request<LayoutSummary>('/document-layouts', { method: 'POST', body: JSON.stringify(command) }),
  cloneLayout: (command: { source_layout_id: number; reason: string }) =>
    request<LayoutSummary>('/document-layouts/clone', { method: 'POST', body: JSON.stringify(command) }),
  getLayout: (layoutId: number) => request<LayoutDetail>(`/document-layouts/${layoutId}`),
  patchLayout: async (layoutId: number, patch: LayoutPatch, signal?: AbortSignal) => {
    try {
      return await request<LayoutSummary>(`/document-layouts/${layoutId}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
        signal,
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        throw new LayoutVersionConflictError(error);
      }
      throw error;
    }
  },
  getReadiness: (layoutId: number, signal?: AbortSignal) =>
    request<LayoutReadinessReport>(`/document-layouts/${layoutId}/readiness`, { signal }),
  publishLayout: (
    layoutId: number,
    command: { expected_lock_version: number; reason: string; effective_from: string | null },
  ) =>
    request<LayoutSummary>(`/document-layouts/${layoutId}/publish`, {
      method: 'POST',
      body: JSON.stringify(command),
    }),
  withdrawLayout: (layoutId: number, command: { reason: string }) =>
    request<LayoutSummary>(`/document-layouts/${layoutId}/withdraw`, {
      method: 'POST',
      body: JSON.stringify(command),
    }),
  getAudit: (layoutId: number) =>
    request<LayoutAuditReceipt[]>(`/document-layouts/${layoutId}/audit`),
  uploadAsset: async (input: UploadLayoutAssetInput) => {
    const form = new FormData();
    form.append('business_profile_id', String(input.businessProfileId));
    form.append('asset_type', input.assetType);
    form.append('declared_sha256', input.declaredSha256);
    form.append('font_embedding_rights_confirmed', String(input.fontEmbeddingRightsConfirmed ?? false));
    form.append('file', input.file);
    const response = await authorizedFetch('/document-layouts/assets', {
      method: 'POST',
      body: form,
      signal: input.signal,
    });
    return response.json() as Promise<LayoutAsset>;
  },
  attachAsset: (layoutId: number, assetId: number, role: LayoutAssetRole) =>
    request<{ layout_id: number; asset_id: number; role: LayoutAssetRole }>(
      `/document-layouts/${layoutId}/assets`,
      { method: 'POST', body: JSON.stringify({ asset_id: assetId, role }) },
    ),
  deleteAsset: (assetId: number) =>
    request<void>(`/document-layouts/assets/${assetId}`, { method: 'DELETE' }),
  createPreview: (command: PreviewRequest, signal?: AbortSignal) =>
    request<PreviewJob>('/document-layouts/preview', {
      method: 'POST',
      body: JSON.stringify(command),
      signal,
    }),
  pollPreviewJob: async (
    publicId: string,
    options: { signal?: AbortSignal; etag?: string | null } = {},
  ): Promise<PreviewPollResult> => {
    const headers: Record<string, string> = {};
    if (options.etag) headers['If-None-Match'] = options.etag;
    const response = await authorizedFetch(
      `/document-layouts/preview/${encodeURIComponent(publicId)}`,
      { headers, signal: options.signal },
    );
    if (response.status === 304) {
      return { job: null, etag: options.etag ?? null, notModified: true };
    }
    return {
      job: await response.json() as PreviewJob,
      etag: response.headers.get('ETag'),
      notModified: false,
    };
  },
  getPreviewReport: (publicId: string, signal?: AbortSignal) =>
    request<PreviewReport>(
      `/document-layouts/preview/${encodeURIComponent(publicId)}/report`,
      { signal },
    ),
  downloadPreviewPdf: async (publicId: string, signal?: AbortSignal) => {
    const response = await authorizedFetch(
      `/document-layouts/preview/${encodeURIComponent(publicId)}/pdf`,
      { signal },
    );
    return { blob: await response.blob(), etag: response.headers.get('ETag') };
  },
  getRuntimeReadiness: (signal?: AbortSignal) =>
    request<DocumentRuntimeReadiness>('/document-render/readiness', { signal }),
  exportExternal: (command: ExternalRenderRequest, signal?: AbortSignal) =>
    request<ExternalRenderResponse>('/document-render', {
      method: 'POST',
      body: JSON.stringify(command),
      signal,
    }),
  downloadExternalArtifact: async (artifactId: number, signal?: AbortSignal) => {
    const response = await authorizedFetch(`/document-render/artifacts/${artifactId}`, { signal });
    return { blob: await response.blob(), etag: response.headers.get('ETag') };
  },
};
