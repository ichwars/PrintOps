import type { SliceJobProgress, SystemHealthResult } from './types';
import type {
  AMSHistoryResponse,
  AddToQueueResponse,
  BatchThumbnailResponse,
  ExternalFolderCreate,
  LibraryFile,
  LibraryFileListItem,
  LibraryFileUpdate,
  LibraryFileUploadResponse,
  LibraryFolder,
  LibraryFolderCreate,
  LibraryFolderTree,
  LibraryFolderUpdate,
  LibraryPurgePreview,
  LibraryStats,
  LibraryTag,
  LibraryTagBulkAssignResult,
  LibraryTrashListResponse,
  LibraryTrashSettings,
  PrinterSensorHistoryResponse,
  StorageUsageResponse,
  SystemInfo,
  ZipExtractResponse,
} from './specialized';
import type { LibraryFilePlatesResponse } from '../../types/plates';
import {
  API_BASE,
  authToken,
  buildSlicerUrlFilename,
  parseContentDispositionFilename,
  request,
  withStreamToken,
} from './core';

export const historyLibraryMethods = {
  // AMS History
  getAMSHistory: (printerId: number, amsId: number, hours = 24) =>
    request<AMSHistoryResponse>(`/ams-history/${printerId}/${amsId}?hours=${hours}`),

  // Printer heater (nozzle / bed / chamber) sensor history
  getPrinterSensorHistory: (printerId: number, hours = 24, kinds?: string[]) => {
    const params = new URLSearchParams({ hours: String(hours) });
    if (kinds && kinds.length > 0) params.set('kinds', kinds.join(','));
    return request<PrinterSensorHistoryResponse>(`/printer-sensor-history/${printerId}?${params.toString()}`);
  },

  // System Info
  getSystemInfo: () => request<SystemInfo>('/system/info'),

  getSystemHealth: () => request<SystemHealthResult>('/system/health'),

  getStorageUsage: (options?: { refresh?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.refresh) {
      params.set('refresh', 'true');
    }
    const query = params.toString();
    return request<StorageUsageResponse>(`/system/storage-usage${query ? `?${query}` : ''}`);
  },

  // Library (File Manager)
  getLibraryFolders: () => request<LibraryFolderTree[]>('/library/folders'),

  createLibraryFolder: (data: LibraryFolderCreate) =>
    request<LibraryFolder>('/library/folders', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateLibraryFolder: (id: number, data: LibraryFolderUpdate) =>
    request<LibraryFolder>(`/library/folders/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteLibraryFolder: (id: number) =>
    request<{ status: string; message: string }>(`/library/folders/${id}`, { method: 'DELETE' }),

  createExternalFolder: (data: ExternalFolderCreate) =>
    request<LibraryFolder>('/library/folders/external', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  scanExternalFolder: (folderId: number) =>
    request<{ status: string; added: number; removed: number }>(`/library/folders/${folderId}/scan`, {
      method: 'POST',
    }),

  getLibraryFoldersByProject: (projectId: number) =>
    request<LibraryFolder[]>(`/library/folders/by-project/${projectId}`),

  getLibraryFoldersByArchive: (archiveId: number) =>
    request<LibraryFolder[]>(`/library/folders/by-archive/${archiveId}`),

  getLibraryFiles: (
    folderId?: number | null,
    includeRoot = true,
    projectId?: number,
    scope?: 'internal' | 'external',
    recursive = false,
    tagIds: number[] = [],
  ) => {
    const params = new URLSearchParams();
    if (folderId !== undefined && folderId !== null) {
      params.set('folder_id', String(folderId));
    }
    if (projectId !== undefined) {
      params.set('project_id', String(projectId));
    }
    params.set('include_root', String(includeRoot));
    if (scope === 'internal') params.set('internal_only', 'true');
    else if (scope === 'external') params.set('external_only', 'true');
    // recursive=true expands the folder_id filter to include every descendant
    // folder (#1268). Only meaningful when folder_id is set; ignored server-side
    // otherwise. Off by default so non-search callers keep folder-scoped behavior.
    if (recursive) params.set('recursive', 'true');
    // Tag filter (#1268). Repeated ?tag_ids=N&tag_ids=M form for AND semantics
    // — backend joins the association table and HAVING COUNT(DISTINCT) matches
    // the array length. Tag filter intentionally bypasses folder scoping
    // server-side (cross-cutting design decision).
    for (const tagId of tagIds) {
      params.append('tag_ids', String(tagId));
    }
    return request<LibraryFileListItem[]>(`/library/files?${params}`);
  },

  getLibraryFolderReadme: (folderId: number) =>
    request<{ filename: string; content: string; truncated: boolean }>(
      `/library/folders/${folderId}/readme`,
    ),

  // ============ Library tag catalog (#1268) ============
  getLibraryTags: () =>
    request<LibraryTag[]>('/library/tags'),

  createLibraryTag: (name: string) =>
    request<LibraryTag>('/library/tags', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),

  updateLibraryTag: (id: number, name: string) =>
    request<LibraryTag>(`/library/tags/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ name }),
    }),

  deleteLibraryTag: (id: number) =>
    request<void>(`/library/tags/${id}`, { method: 'DELETE' }),

  bulkAssignLibraryTags: (
    fileIds: number[],
    tagIds: number[],
    action: 'add' | 'remove' | 'replace',
  ) =>
    request<LibraryTagBulkAssignResult>('/library/tags/bulk-assign', {
      method: 'POST',
      body: JSON.stringify({ file_ids: fileIds, tag_ids: tagIds, action }),
    }),

  getLibraryFile: (id: number) => request<LibraryFile>(`/library/files/${id}`),

  uploadLibraryFile: async (
    file: File,
    folderId?: number | null,
    generateStlThumbnails: boolean = true
  ): Promise<LibraryFileUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    if (folderId) params.set('folder_id', String(folderId));
    params.set('generate_stl_thumbnails', String(generateStlThumbnails));
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/library/files?${params}`, {
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

  extractZipFile: async (
    file: File,
    folderId?: number | null,
    preserveStructure: boolean = true,
    createFolderFromZip: boolean = false,
    generateStlThumbnails: boolean = true
  ): Promise<ZipExtractResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const params = new URLSearchParams();
    if (folderId) params.set('folder_id', String(folderId));
    params.set('preserve_structure', String(preserveStructure));
    params.set('create_folder_from_zip', String(createFolderFromZip));
    params.set('generate_stl_thumbnails', String(generateStlThumbnails));
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/library/files/extract-zip?${params}`, {
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

  updateLibraryFile: (id: number, data: LibraryFileUpdate) =>
    request<LibraryFile>(`/library/files/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteLibraryFile: (id: number) =>
    request<{ status: string; message: string; trashed: boolean }>(`/library/files/${id}`, { method: 'DELETE' }),

  // ========== Library Trash (#1008) ==========
  previewLibraryPurge: (olderThanDays: number, includeNeverPrinted: boolean = true) =>
    request<LibraryPurgePreview>(
      `/library/purge/preview?older_than_days=${olderThanDays}&include_never_printed=${includeNeverPrinted}`,
    ),

  executeLibraryPurge: (olderThanDays: number, includeNeverPrinted: boolean = true) =>
    request<{ moved_to_trash: number }>('/library/purge', {
      method: 'POST',
      body: JSON.stringify({ older_than_days: olderThanDays, include_never_printed: includeNeverPrinted }),
    }),

  listLibraryTrash: (limit: number = 100, offset: number = 0) =>
    request<LibraryTrashListResponse>(`/library/trash?limit=${limit}&offset=${offset}`),

  restoreLibraryTrash: (fileId: number) =>
    request<{ status: string; id: number }>(`/library/trash/${fileId}/restore`, { method: 'POST' }),

  hardDeleteLibraryTrash: (fileId: number) =>
    request<{ status: string }>(`/library/trash/${fileId}`, { method: 'DELETE' }),

  emptyLibraryTrash: () => request<{ deleted: number }>('/library/trash', { method: 'DELETE' }),

  getLibraryTrashSettings: () =>
    request<LibraryTrashSettings>('/library/trash/settings'),

  updateLibraryTrashSettings: (body: LibraryTrashSettings) =>
    request<LibraryTrashSettings>('/library/trash/settings', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  getLibraryFileDownloadUrl: (id: number) => `${API_BASE}/library/files/${id}/download`,

  createLibrarySlicerToken: (fileId: number) =>
    request<{ token: string }>(`/library/files/${fileId}/slicer-token`, { method: 'POST' }),

  getLibrarySlicerDownloadUrl: (fileId: number, token: string, filename: string) =>
    `${API_BASE}/library/files/${fileId}/dl/${token}/${encodeURIComponent(buildSlicerUrlFilename(filename))}`,

  downloadLibraryFile: async (id: number, filename?: string): Promise<void> => {
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/library/files/${id}/download`, { headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    const disposition = response.headers.get('Content-Disposition');
    const downloadFilename = parseContentDispositionFilename(disposition) || filename || `file_${id}`;
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

  getLibraryFileThumbnailUrl: (id: number) => withStreamToken(`${API_BASE}/library/files/${id}/thumbnail`),

  getLibraryFilePlateThumbnail: (id: number, plateIndex: number) =>
    withStreamToken(`${API_BASE}/library/files/${id}/plate-thumbnail/${plateIndex}`),

  getLibraryFileGcodeUrl: (id: number) => `${API_BASE}/library/files/${id}/gcode`,

  moveLibraryFiles: (fileIds: number[], folderId: number | null) =>
    request<{ status: string; moved: number }>('/library/files/move', {
      method: 'POST',
      body: JSON.stringify({ file_ids: fileIds, folder_id: folderId }),
    }),

  bulkDeleteLibrary: (fileIds: number[], folderIds: number[]) =>
    request<{ deleted_files: number; deleted_folders: number }>('/library/bulk-delete', {
      method: 'POST',
      body: JSON.stringify({ file_ids: fileIds, folder_ids: folderIds }),
    }),

  getLibraryStats: () => request<LibraryStats>('/library/stats'),

  batchGenerateStlThumbnails: (options: {
    file_ids?: number[];
    folder_id?: number;
    all_missing?: boolean;
  }) =>
    request<BatchThumbnailResponse>('/library/generate-stl-thumbnails', {
      method: 'POST',
      body: JSON.stringify(options),
    }),

  addLibraryFilesToQueue: (fileIds: number[]) =>
    request<AddToQueueResponse>('/library/files/add-to-queue', {
      method: 'POST',
      body: JSON.stringify({ file_ids: fileIds }),
    }),

  getLibraryFilePlates: (fileId: number) =>
    request<LibraryFilePlatesResponse>(`/library/files/${fileId}/plates`),

  getLibraryFileFilamentRequirements: (
    fileId: number,
    plateId?: number,
    requestId?: string,
  ) => {
    const qs = new URLSearchParams();
    if (plateId !== undefined) qs.set('plate_id', String(plateId));
    if (requestId) qs.set('request_id', requestId);
    return request<{
      file_id: number;
      filename: string;
      filaments: Array<{
        slot_id: number;
        type: string;
        color: string;
        used_grams: number;
        used_meters: number;
        used_in_plate?: boolean;
      }>;
    }>(`/library/files/${fileId}/filament-requirements${qs.toString() ? `?${qs}` : ''}`);
  },

  /** Poll the sidecar's per-request progress snapshot via the PrintOps
   * proxy. Used by the SliceModal's filament-discovery path so the inline
   * spinner + persistent toast can show "Generating G-code (45%)" while
   * the preview slice runs. Returns null on 404 (sidecar doesn't yet
   * have an entry — early race window — or it expired) so the poller
   * can keep trying. */
  getPreviewSliceProgress: async (requestId: string): Promise<SliceJobProgress | null> => {
    try {
      return await request<SliceJobProgress>(`/slicer/preview-progress/${encodeURIComponent(requestId)}`);
    } catch {
      return null;
    }
  }
};
