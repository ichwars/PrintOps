import type {
  APIKey,
  APIKeyCreate,
  APIKeyCreateResponse,
  APIKeyUpdate,
  Archive,
  BOMItem,
  BOMItemCreate,
  BOMItemUpdate,
  BusinessProfile,
  BusinessProfileCreate,
  BusinessProfileOption,
  BusinessProfileUpdate,
  CustomerCreate,
  CustomerDetail,
  CustomerListParams,
  CustomerListResponse,
  CustomerUpdate,
  DisplayCurrencyResponse,
  NumberSequence,
  NumberSequenceCreate,
  NumberSequenceUpdate,
  Project,
  ProjectAttachment,
  ProjectCreate,
  ProjectExport,
  ProjectImport,
  ProjectListItem,
  ProjectUpdate,
  TimelineEvent,
  WarehouseNumberSequence,
  WarehouseNumberSequenceCreate,
  WarehouseNumberSequenceUpdate,
} from './types';
import {
  API_BASE,
  ApiError,
  authToken,
  parseContentDispositionFilename,
  request,
  withStreamToken,
} from './core';

export const businessProjectsMethods = {
  // Order management master data
  getBusinessProfiles: (includeInactive = false) =>
    request<BusinessProfile[]>(
      `/business-profiles/${includeInactive ? '?includeInactive=true' : ''}`,
    ),

  getBusinessProfileOptions: () => request<BusinessProfileOption[]>('/business-profiles/options'),

  getDisplayCurrency: () => request<DisplayCurrencyResponse>('/business-profiles/display-currency'),

  getNumberSequences: (profileId: number) =>
    request<NumberSequence[]>(`/business-profiles/${profileId}/number-sequences`),

  createNumberSequence: (profileId: number, data: NumberSequenceCreate) =>
    request<NumberSequence>(`/business-profiles/${profileId}/number-sequences`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateNumberSequence: (profileId: number, sequenceId: number, data: NumberSequenceUpdate) =>
    request<NumberSequence>(`/business-profiles/${profileId}/number-sequences/${sequenceId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  getWarehouseNumberSequences: () =>
    request<WarehouseNumberSequence[]>('/inventory/number-sequences'),

  createWarehouseNumberSequence: (data: WarehouseNumberSequenceCreate) =>
    request<WarehouseNumberSequence>('/inventory/number-sequences', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateWarehouseNumberSequence: (sequenceId: number, data: WarehouseNumberSequenceUpdate) =>
    request<WarehouseNumberSequence>(`/inventory/number-sequences/${sequenceId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  createBusinessProfile: (data: BusinessProfileCreate) =>
    request<BusinessProfile>('/business-profiles/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateBusinessProfile: (id: number, data: BusinessProfileUpdate) =>
    request<BusinessProfile>(`/business-profiles/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  setDefaultBusinessProfile: (id: number) =>
    request<BusinessProfile>(`/business-profiles/${id}/default`, { method: 'POST' }),

  deleteBusinessProfile: (id: number) =>
    request<void>(`/business-profiles/${id}`, { method: 'DELETE' }),

  uploadBusinessProfileLogo: async (id: number, version: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) headers.Authorization = `Bearer ${authToken}`;
    const response = await fetch(`${API_BASE}/business-profiles/${id}/logo?version=${version}`, {
      method: 'PUT', body: formData, headers, credentials: 'include',
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      const detail = error.detail;
      throw new ApiError(
        typeof detail === 'object' && detail && typeof detail.message === 'string' ? detail.message : `HTTP ${response.status}`,
        response.status,
        typeof detail === 'object' && detail && typeof detail.code === 'string' ? detail.code : null,
      );
    }
    return response.json() as Promise<BusinessProfile>;
  },

  deleteBusinessProfileLogo: (id: number, version: number) =>
    request<void>(`/business-profiles/${id}/logo?version=${version}`, { method: 'DELETE' }),

  getBusinessProfileLogoUrl: (id: number, logoVersion: number) =>
    withStreamToken(`${API_BASE}/business-profiles/${id}/logo?v=${logoVersion}`),

  getBusinessProfileLogoBlob: async (id: number, logoVersion: number): Promise<Blob> => {
    const headers: Record<string, string> = {};
    if (authToken) headers.Authorization = `Bearer ${authToken}`;
    const response = await fetch(`${API_BASE}/business-profiles/${id}/logo?v=${logoVersion}`, {
      headers,
      credentials: 'include',
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      const detail = error.detail;
      throw new ApiError(
        typeof detail === 'object' && detail && typeof detail.message === 'string' ? detail.message : `HTTP ${response.status}`,
        response.status,
        typeof detail === 'object' && detail && typeof detail.code === 'string' ? detail.code : null,
      );
    }
    return response.blob();
  },

  getCustomers: (params: CustomerListParams) => {
    const search = new URLSearchParams();
    search.set('business_profile_id', String(params.businessProfileId));
    if (params.search?.trim()) search.set('search', params.search.trim());
    if (params.status) search.set('status', params.status);
    if (params.kind) search.set('kind', params.kind);
    if (params.limit !== undefined) search.set('limit', String(params.limit));
    if (params.offset !== undefined) search.set('offset', String(params.offset));
    return request<CustomerListResponse>(`/customers/?${search.toString()}`);
  },

  getCustomer: (id: number) => request<CustomerDetail>(`/customers/${id}`),

  createCustomer: (data: CustomerCreate) =>
    request<CustomerDetail>('/customers/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateCustomer: (id: number, data: CustomerUpdate) =>
    request<CustomerDetail>(`/customers/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteCustomer: (id: number) => request<void>(`/customers/${id}`, { method: 'DELETE' }),

  // Projects
  getProjects: (status?: string) => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    return request<ProjectListItem[]>(`/projects/?${params}`);
  },

  getProject: (id: number) => request<Project>(`/projects/${id}`),

  createProject: (data: ProjectCreate) =>
    request<Project>('/projects/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateProject: (id: number, data: ProjectUpdate) =>
    request<Project>(`/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteProject: (id: number) =>
    request<{ message: string }>(`/projects/${id}`, { method: 'DELETE' }),

  getProjectArchives: (id: number, limit = 100, offset = 0) =>
    request<Archive[]>(`/projects/${id}/archives?limit=${limit}&offset=${offset}`),

  addArchivesToProject: (projectId: number, archiveIds: number[]) =>
    request<{ message: string }>(`/projects/${projectId}/add-archives`, {
      method: 'POST',
      body: JSON.stringify({ archive_ids: archiveIds }),
    }),

  removeArchivesFromProject: (projectId: number, archiveIds: number[]) =>
    request<{ message: string }>(`/projects/${projectId}/remove-archives`, {
      method: 'POST',
      body: JSON.stringify({ archive_ids: archiveIds }),
    }),

  addQueueItemsToProject: (projectId: number, queueItemIds: number[]) =>
    request<{ message: string }>(`/projects/${projectId}/add-queue`, {
      method: 'POST',
      body: JSON.stringify({ queue_item_ids: queueItemIds }),
    }),

  // Project Attachments
  uploadProjectAttachment: async (projectId: number, file: File): Promise<{
    status: string;
    filename: string;
    original_name: string;
    attachments: ProjectAttachment[];
  }> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/projects/${projectId}/attachments`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
  },

  getProjectAttachmentUrl: (projectId: number, filename: string) =>
    `${API_BASE}/projects/${projectId}/attachments/${encodeURIComponent(filename)}`,

  deleteProjectAttachment: (projectId: number, filename: string) =>
    request<{ status: string; message: string; attachments: ProjectAttachment[] | null }>(
      `/projects/${projectId}/attachments/${encodeURIComponent(filename)}`,
      { method: 'DELETE' }
    ),

  // #1155: Cover image
  // Browsers can't attach `Authorization: Bearer ...` to `<img src>`, so we
  // append the stream-token query string the same way archive thumbnails do.
  getProjectCoverImageUrl: (projectId: number) =>
    withStreamToken(`${API_BASE}/projects/${projectId}/cover-image`),

  uploadProjectCoverImage: async (
    projectId: number,
    file: File
  ): Promise<{ status: string; filename: string; size: number }> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/projects/${projectId}/cover-image`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
  },

  deleteProjectCoverImage: (projectId: number) =>
    request<{ status: string }>(`/projects/${projectId}/cover-image`, { method: 'DELETE' }),

  // BOM (Bill of Materials)
  getProjectBOM: (projectId: number) =>
    request<BOMItem[]>(`/projects/${projectId}/bom`),

  createBOMItem: (projectId: number, data: BOMItemCreate) =>
    request<BOMItem>(`/projects/${projectId}/bom`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateBOMItem: (projectId: number, itemId: number, data: BOMItemUpdate) =>
    request<BOMItem>(`/projects/${projectId}/bom/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteBOMItem: (projectId: number, itemId: number) =>
    request<{ status: string; message: string }>(`/projects/${projectId}/bom/${itemId}`, {
      method: 'DELETE',
    }),

  // Templates
  getTemplates: () => request<ProjectListItem[]>('/projects/templates/'),

  createTemplateFromProject: (projectId: number) =>
    request<Project>(`/projects/${projectId}/create-template`, { method: 'POST' }),

  createProjectFromTemplate: (templateId: number, name?: string) =>
    request<Project>(`/projects/from-template/${templateId}${name ? `?name=${encodeURIComponent(name)}` : ''}`, {
      method: 'POST',
    }),

  // Timeline
  getProjectTimeline: (projectId: number, limit = 50) =>
    request<TimelineEvent[]>(`/projects/${projectId}/timeline?limit=${limit}`),

  // Project Export/Import
  exportProjectJson: (projectId: number) =>
    request<ProjectExport>(`/projects/${projectId}/export?format=json`),

  importProject: (data: ProjectImport) =>
    request<Project>('/projects/import', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  importProjectFile: async (file: File): Promise<Project> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/projects/import/file`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
  },

  exportProjectZip: async (projectId: number): Promise<{ blob: Blob; filename: string }> => {
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/projects/${projectId}/export`, {
      headers,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    const contentDisposition = response.headers.get('Content-Disposition');
    const filename = parseContentDispositionFilename(contentDisposition) || `project_${projectId}.zip`;
    const blob = await response.blob();
    return { blob, filename };
  },

  // API Keys
  getAPIKeys: () => request<APIKey[]>('/api-keys/'),

  createAPIKey: (data: APIKeyCreate) =>
    request<APIKeyCreateResponse>('/api-keys/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateAPIKey: (id: number, data: APIKeyUpdate) =>
    request<APIKey>(`/api-keys/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteAPIKey: (id: number) =>
    request<{ message: string }>(`/api-keys/${id}`, { method: 'DELETE' })
};
