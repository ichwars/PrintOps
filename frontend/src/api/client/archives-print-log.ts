import type {
  Archive,
  ArchiveComparison,
  ArchiveDuplicate,
  ArchiveEnergyHistoryPoint,
  ArchiveSlim,
  ArchiveStats,
  BulkUploadResult,
  FailureAnalysis,
  PrintLogEntry,
  PrintLogResponse,
  SimilarArchive,
  TagInfo,
} from './types';
import type { ArchivePurgePreview, ArchivePurgeSettings } from './specialized';
import type { ArchivePlatesResponse } from '../../types/plates';
import {
  API_BASE,
  authToken,
  parseContentDispositionFilename,
  request,
  withStreamToken,
} from './core';

export const archivesPrintLogMethods = {
  // Archives
  getArchives: (printerId?: number, projectId?: number, limit = 10000, offset = 0, dateFrom?: string, dateTo?: string) => {
    const params = new URLSearchParams();
    if (printerId) params.set('printer_id', String(printerId));
    if (projectId) params.set('project_id', String(projectId));
    params.set('limit', String(limit));
    params.set('offset', String(offset));
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    return request<Archive[]>(`/archives/?${params}`);
  },

  getArchivesSlim: (dateFrom?: string, dateTo?: string, createdById?: number) => {
    const params = new URLSearchParams();
    if (dateFrom) params.set('date_from', dateFrom);
    if (dateTo) params.set('date_to', dateTo);
    if (createdById !== undefined) params.set('created_by_id', String(createdById));
    const qs = params.toString();
    return request<ArchiveSlim[]>(`/archives/slim${qs ? `?${qs}` : ''}`);
  },

  getArchive: (id: number) => request<Archive>(`/archives/${id}`),

  getArchiveRuns: (id: number) => request<PrintLogResponse>(`/archives/${id}/runs`),

  /**
   * Pre-flight for the delete-confirm modal (#1734). Returns the number of
   * related queue items that will be removed along with the archive AND how
   * many are currently printing (server 409s on delete if > 0).
   */
  getArchiveDeleteImpact: (id: number) =>
    request<{ related_queue_items: number; currently_printing: number }>(
      `/archives/${id}/delete-impact`
    ),

  searchArchives: (query: string, options?: {
    printerId?: number;
    projectId?: number;
    status?: string;
    limit?: number;
    offset?: number;
  }) => {
    const params = new URLSearchParams();
    params.set('q', query);
    if (options?.printerId) params.set('printer_id', String(options.printerId));
    if (options?.projectId) params.set('project_id', String(options.projectId));
    if (options?.status) params.set('status', options.status);
    if (options?.limit) params.set('limit', String(options.limit));
    if (options?.offset) params.set('offset', String(options.offset));
    return request<Archive[]>(`/archives/search?${params}`);
  },

  rebuildSearchIndex: () => request<{ message: string }>('/archives/search/rebuild-index', { method: 'POST' }),

  getNo3MFWarning: () => request<{ has_fallback: boolean }>('/archives/no-3mf-warning'),

  updateArchive: (id: number, data: {
    printer_id?: number | null;
    project_id?: number | null;
    print_name?: string;
    is_favorite?: boolean;
    tags?: string;
    notes?: string;
    cost?: number;
    failure_reason?: string | null;
    status?: string;
    quantity?: number;
    external_url?: string | null;
  }) =>
    request<Archive>(`/archives/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  toggleFavorite: (id: number) =>
    request<Archive>(`/archives/${id}/favorite`, { method: 'POST' }),

  // Soft-deletes by default (#1343): files removed from disk, row hidden
  // from listings, but its filament / time / cost / energy contribution
  // stays in Quick Stats. Pass purgeStats=true to hard-delete and drop the
  // row from statistics too.
  deleteArchive: (id: number, purgeStats: boolean = false) =>
    request<void>(`/archives/${id}${purgeStats ? '?purge_stats=true' : ''}`, { method: 'DELETE' }),

  // ========== Archive auto-purge (#1008 follow-up) ==========
  previewArchivePurge: (olderThanDays: number, purgeStats: boolean = false) =>
    request<ArchivePurgePreview>(
      `/archives/purge/preview?older_than_days=${olderThanDays}&purge_stats=${purgeStats}`,
    ),

  // #1390: purgeStats=false (default) soft-deletes each old archive — Quick Stats
  // preserved, files removed from disk, row hidden via deleted_at. true matches
  // the single-archive delete's `?purge_stats=true` semantics (hard-deletes the
  // linked PrintLogEntry rows so the contribution drops from /stats too).
  executeArchivePurge: (olderThanDays: number, purgeStats: boolean = false) =>
    request<{ deleted: number; purge_stats: boolean }>('/archives/purge', {
      method: 'POST',
      body: JSON.stringify({ older_than_days: olderThanDays, purge_stats: purgeStats }),
    }),

  getArchivePurgeSettings: () =>
    request<ArchivePurgeSettings>('/archives/purge/settings'),

  updateArchivePurgeSettings: (body: ArchivePurgeSettings) =>
    request<ArchivePurgeSettings>('/archives/purge/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  getArchiveStats: (options?: { dateFrom?: string; dateTo?: string; createdById?: number }) => {
    const params = new URLSearchParams();
    if (options?.dateFrom) params.set('date_from', options.dateFrom);
    if (options?.dateTo) params.set('date_to', options.dateTo);
    if (options?.createdById !== undefined) params.set('created_by_id', String(options.createdById));
    const qs = params.toString();
    return request<ArchiveStats>(`/archives/stats${qs ? `?${qs}` : ''}`);
  },

  getArchiveEnergyHistory: (options?: { dateFrom?: string; dateTo?: string; bucket?: 'hour' | 'day' }) => {
    const params = new URLSearchParams();
    if (options?.dateFrom) params.set('date_from', options.dateFrom);
    if (options?.dateTo) params.set('date_to', options.dateTo);
    if (options?.bucket) params.set('bucket', options.bucket);
    const qs = params.toString();
    return request<ArchiveEnergyHistoryPoint[]>(`/archives/energy-history${qs ? `?${qs}` : ''}`);
  },

  // Tag management
  getTags: () => request<TagInfo[]>('/archives/tags'),

  renameTag: (oldName: string, newName: string) =>
    request<{ affected: number }>(`/archives/tags/${encodeURIComponent(oldName)}`, {
      method: 'PUT',
      body: JSON.stringify({ new_name: newName }),
    }),

  deleteTag: (name: string) =>
    request<{ affected: number }>(`/archives/tags/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    }),

  recalculateCosts: () =>
    request<{ message: string; updated: number }>('/archives/recalculate-costs', { method: 'POST' }),

  getFailureAnalysis: (options?: { days?: number; dateFrom?: string; dateTo?: string; printerId?: number; projectId?: number; createdById?: number }) => {
    const params = new URLSearchParams();
    if (options?.days) params.set('days', String(options.days));
    if (options?.dateFrom) params.set('date_from', options.dateFrom);
    if (options?.dateTo) params.set('date_to', options.dateTo);
    if (options?.printerId) params.set('printer_id', String(options.printerId));
    if (options?.projectId) params.set('project_id', String(options.projectId));
    if (options?.createdById !== undefined) params.set('created_by_id', String(options.createdById));
    const qs = params.toString();
    return request<FailureAnalysis>(`/archives/analysis/failures${qs ? `?${qs}` : ''}`);
  },

  compareArchives: (archiveIds: number[]) =>
    request<ArchiveComparison>(`/archives/compare?archive_ids=${archiveIds.join(',')}`),

  findSimilarArchives: (archiveId: number, limit = 10) =>
    request<SimilarArchive[]>(`/archives/${archiveId}/similar?limit=${limit}`),

  exportArchives: async (options?: {
    format?: 'csv' | 'xlsx';
    fields?: string[];
    printerId?: number;
    projectId?: number;
    status?: string;
    dateFrom?: string;
    dateTo?: string;
    search?: string;
  }): Promise<{ blob: Blob; filename: string }> => {
    const params = new URLSearchParams();
    if (options?.format) params.set('format', options.format);
    if (options?.fields) params.set('fields', options.fields.join(','));
    if (options?.printerId) params.set('printer_id', String(options.printerId));
    if (options?.projectId) params.set('project_id', String(options.projectId));
    if (options?.status) params.set('status', options.status);
    if (options?.dateFrom) params.set('date_from', options.dateFrom);
    if (options?.dateTo) params.set('date_to', options.dateTo);
    if (options?.search) params.set('search', options.search);

    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/export?${params}`, { headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const contentDisposition = response.headers.get('Content-Disposition');
    let filename = options?.format === 'xlsx' ? 'archives_export.xlsx' : 'archives_export.csv';
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="?([^"]+)"?/);
      if (match) filename = match[1];
    }

    const blob = await response.blob();
    return { blob, filename };
  },

  exportStats: async (options?: {
    format?: 'csv' | 'xlsx';
    days?: number;
    printerId?: number;
    projectId?: number;
    createdById?: number;
  }): Promise<{ blob: Blob; filename: string }> => {
    const params = new URLSearchParams();
    if (options?.format) params.set('format', options.format);
    if (options?.days) params.set('days', String(options.days));
    if (options?.printerId) params.set('printer_id', String(options.printerId));
    if (options?.projectId) params.set('project_id', String(options.projectId));
    if (options?.createdById !== undefined) params.set('created_by_id', String(options.createdById));

    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/stats/export?${params}`, { headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    const contentDisposition = response.headers.get('Content-Disposition');
    let filename = options?.format === 'xlsx' ? 'stats_export.xlsx' : 'stats_export.csv';
    if (contentDisposition) {
      const match = contentDisposition.match(/filename="?([^"]+)"?/);
      if (match) filename = match[1];
    }

    const blob = await response.blob();
    return { blob, filename };
  },

  getArchiveDuplicates: (id: number) =>
    request<{ duplicates: ArchiveDuplicate[]; count: number }>(`/archives/${id}/duplicates`),

  backfillContentHashes: () =>
    request<{ updated: number; errors: Array<{ id: number; error: string }> }>('/archives/backfill-hashes', {
      method: 'POST',
    }),

  getArchiveThumbnail: (id: number) => withStreamToken(`${API_BASE}/archives/${id}/thumbnail?v=${Date.now()}`),

  getArchivePlateThumbnail: (id: number, plateIndex: number) =>
    withStreamToken(`${API_BASE}/archives/${id}/plate-thumbnail/${plateIndex}`),

  getArchiveDownload: (id: number) => `${API_BASE}/archives/${id}/download`,

  downloadArchive: async (id: number, filename?: string): Promise<void> => {
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/${id}/download`, { headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    const disposition = response.headers.get('Content-Disposition');
    const downloadFilename = parseContentDispositionFilename(disposition) || filename || `archive_${id}.3mf`;
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = downloadFilename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },

  getArchiveGcode: (id: number) => `${API_BASE}/archives/${id}/gcode`,

  getArchivePlatePreview: (id: number) => withStreamToken(`${API_BASE}/archives/${id}/plate-preview`),

  getArchiveTimelapse: (id: number) => withStreamToken(`${API_BASE}/archives/${id}/timelapse?v=${Date.now()}`),

  scanArchiveTimelapse: (id: number) =>
    request<{
      status: string;
      message: string;
      filename?: string;
      available_files?: Array<{ name: string; path: string; size: number; mtime: string | null }>;
    }>(`/archives/${id}/timelapse/scan`, {
      method: 'POST',
    }),

  selectArchiveTimelapse: (id: number, filename: string) =>
    request<{ status: string; message: string; filename: string }>(
      `/archives/${id}/timelapse/select?filename=${encodeURIComponent(filename)}`,
      { method: 'POST' }
    ),

  deleteArchiveTimelapse: (id: number) =>
    request<{ status: string }>(`/archives/${id}/timelapse`, {
      method: 'DELETE',
    }),

  uploadArchiveTimelapse: async (archiveId: number, file: File): Promise<{ status: string; filename: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/${archiveId}/timelapse/upload`, {
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

  // Timelapse Editor
  getTimelapseInfo: (archiveId: number) =>
    request<{
      duration: number;
      width: number;
      height: number;
      fps: number;
      codec: string;
      file_size: number;
      has_audio: boolean;
    }>(`/archives/${archiveId}/timelapse/info`),

  getTimelapseThumbnails: (archiveId: number, count: number = 10) =>
    request<{
      thumbnails: string[];
      timestamps: number[];
    }>(`/archives/${archiveId}/timelapse/thumbnails?count=${count}`),

  processTimelapse: async (
    archiveId: number,
    params: {
      trimStart?: number;
      trimEnd?: number;
      speed?: number;
      saveMode: 'replace' | 'new';
      outputFilename?: string;
    },
    audioFile?: File
  ): Promise<{ status: string; output_path: string | null; message: string }> => {
    const formData = new FormData();
    formData.append('trim_start', String(params.trimStart ?? 0));
    if (params.trimEnd !== undefined) {
      formData.append('trim_end', String(params.trimEnd));
    }
    formData.append('speed', String(params.speed ?? 1));
    formData.append('save_mode', params.saveMode);
    if (params.outputFilename) {
      formData.append('output_filename', params.outputFilename);
    }
    if (audioFile) {
      formData.append('audio', audioFile);
    }
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/${archiveId}/timelapse/process`, {
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

  // Photos
  getArchivePhotoUrl: (archiveId: number, filename: string) =>
    withStreamToken(`${API_BASE}/archives/${archiveId}/photos/${encodeURIComponent(filename)}`),

  uploadArchivePhoto: async (archiveId: number, file: File): Promise<{ status: string; filename: string; photos: string[] }> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/${archiveId}/photos`, {
      headers,
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
  },

  deleteArchivePhoto: (archiveId: number, filename: string) =>
    request<{ status: string; photos: string[] | null }>(`/archives/${archiveId}/photos/${encodeURIComponent(filename)}`, {
      method: 'DELETE',
    }),

  // Source 3MF (original slicer project file)
  getSource3mfDownloadUrl: (archiveId: number) =>
    `${API_BASE}/archives/${archiveId}/source`,

  downloadSource3mf: async (archiveId: number): Promise<void> => {
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/${archiveId}/source`, { headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    const disposition = response.headers.get('Content-Disposition');
    const filename = parseContentDispositionFilename(disposition) || `source_${archiveId}.3mf`;
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },

  getSource3mfForSlicer: (archiveId: number, filename: string) => {
    // Sanitize: slicers url_decode() the entire URL, so / \ ? # in filenames break path routing
    const safe = filename.replace(/[/\\?#]/g, '_');
    return `${API_BASE}/archives/${archiveId}/source/${encodeURIComponent(safe.endsWith('.3mf') ? safe : safe + '.3mf')}`;
  },

  createSourceSlicerToken: (archiveId: number) =>
    request<{ token: string }>(`/archives/${archiveId}/source-slicer-token`, { method: 'POST' }),

  getSourceSlicerDownloadUrl: (archiveId: number, token: string, filename: string) => {
    const safe = filename.replace(/[/\\?#]/g, '_');
    return `${API_BASE}/archives/${archiveId}/source-dl/${token}/${encodeURIComponent(safe.endsWith('.3mf') ? safe : safe + '.3mf')}`;
  },

  uploadSource3mf: async (archiveId: number, file: File): Promise<{ status: string; filename: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/${archiveId}/source`, {
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

  deleteSource3mf: (archiveId: number) =>
    request<{ status: string }>(`/archives/${archiveId}/source`, {
      method: 'DELETE',
    }),

  // F3D (Fusion 360 design file)
  getF3dDownloadUrl: (archiveId: number) =>
    `${API_BASE}/archives/${archiveId}/f3d`,

  downloadF3d: async (archiveId: number): Promise<void> => {
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/${archiveId}/f3d`, { headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    const disposition = response.headers.get('Content-Disposition');
    const filename = parseContentDispositionFilename(disposition) || `archive_${archiveId}.f3d`;
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },

  uploadF3d: async (archiveId: number, file: File): Promise<{ status: string; filename: string }> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/archives/${archiveId}/f3d`, {
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

  deleteF3d: (archiveId: number) =>
    request<{ status: string }>(`/archives/${archiveId}/f3d`, {
      method: 'DELETE',
    }),

  // QR Code
  getArchiveQRCodeUrl: (archiveId: number, size = 200) =>
    withStreamToken(`${API_BASE}/archives/${archiveId}/qrcode?size=${size}`),

  getArchiveCapabilities: (id: number) =>
    request<{
      has_model: boolean;
      has_gcode: boolean;
      has_source: boolean;
      build_volume: { x: number; y: number; z: number };
      filament_colors: string[];
    }>(`/archives/${id}/capabilities`),

  // Project Page
  getArchiveProjectPage: (id: number) =>
    request<{
      title: string | null;
      description: string | null;
      designer: string | null;
      designer_user_id: string | null;
      license: string | null;
      copyright: string | null;
      creation_date: string | null;
      modification_date: string | null;
      origin: string | null;
      profile_title: string | null;
      profile_description: string | null;
      profile_cover: string | null;
      profile_user_id: string | null;
      profile_user_name: string | null;
      design_model_id: string | null;
      design_profile_id: string | null;
      design_region: string | null;
      model_pictures: Array<{ name: string; path: string; url: string }>;
      profile_pictures: Array<{ name: string; path: string; url: string }>;
      thumbnails: Array<{ name: string; path: string; url: string }>;
    }>(`/archives/${id}/project-page`),

  updateArchiveProjectPage: (id: number, data: {
    title?: string;
    description?: string;
    designer?: string;
    license?: string;
    copyright?: string;
    profile_title?: string;
    profile_description?: string;
  }) =>
    request(`/archives/${id}/project-page`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  getArchiveProjectImageUrl: (archiveId: number, imagePath: string) =>
    withStreamToken(`${API_BASE}/archives/${archiveId}/project-image/${encodeURIComponent(imagePath)}`),

  getArchiveForSlicer: (id: number, filename: string) => {
    const safe = filename.replace(/[/\\?#]/g, '_');
    return `${API_BASE}/archives/${id}/file/${encodeURIComponent(safe.endsWith('.3mf') ? safe : safe + '.3mf')}`;
  },

  createArchiveSlicerToken: (archiveId: number) =>
    request<{ token: string }>(`/archives/${archiveId}/slicer-token`, { method: 'POST' }),

  getArchiveSlicerDownloadUrl: (archiveId: number, token: string, filename: string) => {
    const safe = filename.replace(/[/\\?#]/g, '_');
    return `${API_BASE}/archives/${archiveId}/dl/${token}/${encodeURIComponent(safe.endsWith('.3mf') ? safe : safe + '.3mf')}`;
  },

  getArchivePlates: (archiveId: number) =>
    request<ArchivePlatesResponse>(`/archives/${archiveId}/plates`),

  getArchiveFilamentRequirements: (
    archiveId: number,
    plateId?: number,
    requestId?: string,
  ) => {
    const qs = new URLSearchParams();
    if (plateId !== undefined) qs.set('plate_id', String(plateId));
    if (requestId) qs.set('request_id', requestId);
    return request<{
      archive_id: number;
      filename: string;
      plate_id: number | null;
      filaments: Array<{
        slot_id: number;
        type: string;
        color: string;
        used_grams: number;
        used_meters: number;
        used_in_plate?: boolean;
      }>;
    }>(`/archives/${archiveId}/filament-requirements${qs.toString() ? `?${qs}` : ''}`);
  },

  uploadArchive: async (file: File, printerId?: number): Promise<Archive> => {
    const formData = new FormData();
    formData.append('file', file);
    const url = printerId
      ? `${API_BASE}/archives/upload?printer_id=${printerId}`
      : `${API_BASE}/archives/upload`;
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(url, {
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

  uploadArchivesBulk: async (files: File[], printerId?: number): Promise<BulkUploadResult> => {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    const url = printerId
      ? `${API_BASE}/archives/upload-bulk?printer_id=${printerId}`
      : `${API_BASE}/archives/upload-bulk`;
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(url, {
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

  // Print Log
  getPrintLog: (params?: {
    search?: string;
    printerId?: number;
    username?: string;
    status?: string;
    dateFrom?: string;
    dateTo?: string;
    limit?: number;
    offset?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.search) searchParams.set('search', params.search);
    if (params?.printerId) searchParams.set('printer_id', String(params.printerId));
    if (params?.username) searchParams.set('created_by_username', params.username);
    if (params?.status) searchParams.set('status', params.status);
    if (params?.dateFrom) searchParams.set('date_from', params.dateFrom);
    if (params?.dateTo) searchParams.set('date_to', params.dateTo);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset !== undefined) searchParams.set('offset', String(params.offset));
    return request<PrintLogResponse>(`/print-log/?${searchParams}`);
  },

  getPrintLogThumbnail: (id: number) => withStreamToken(`${API_BASE}/print-log/${id}/thumbnail`),

  clearPrintLog: () =>
    request<{ deleted: number }>('/print-log/', { method: 'DELETE' }),

  deletePrintLogEntry: (id: number) =>
    request<{ status: string; id: number }>(`/print-log/${id}`, { method: 'DELETE' }),

  // Edit failure_reason / status on a single Print Log row (#1687 part 4).
  // Distinct from updateArchive: archives describe the model, log entries
  // describe a single print event. Orphan entries (no archive_id) have no
  // archive to reach through and this is the only path to classify them.
  updatePrintLogEntry: (
    id: number,
    body: { failure_reason?: string | null; status?: string },
  ) =>
    request<PrintLogEntry>(`/print-log/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    })
};
