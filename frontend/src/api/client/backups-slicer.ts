import type {
  CloudAccountCounts,
  GitHubBackupConfig,
  GitHubBackupConfigCreate,
  GitHubBackupLog,
  GitHubBackupStatus,
  GitHubBackupTriggerResponse,
  GitHubTestConnectionResponse,
  GitProviderType,
  ImportResponse,
  LocalBackupFile,
  LocalBackupStatus,
  LocalPreset,
  LocalPresetDetail,
  LocalPresetsResponse,
  ObicoStatus,
  ObicoTestConnection,
  PipelineEligibilityReport,
  PipelineRun,
  PipelineRunListResponse,
  SliceJobEnqueueResponse,
  SliceJobState,
  SliceRequest,
  SlicerPipeline,
  SlicerPipelineCreateRequest,
  SlicerPipelineUpdateRequest,
  SlicerPipelinesListResponse,
  UnifiedPresetsResponse,
} from './types';
import { API_BASE, authToken, request } from './core';

export const backupsSlicerMethods = {
  // GitHub Backup
  getGitHubBackupConfig: () =>
    request<GitHubBackupConfig | null>('/github-backup/config'),

  getGitHubBackupCloudAccounts: () =>
    request<CloudAccountCounts>('/github-backup/cloud-accounts'),

  saveGitHubBackupConfig: (config: GitHubBackupConfigCreate) =>
    request<GitHubBackupConfig>('/github-backup/config', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  updateGitHubBackupConfig: (config: Partial<GitHubBackupConfigCreate>) =>
    request<GitHubBackupConfig>('/github-backup/config', {
      method: 'PATCH',
      body: JSON.stringify(config),
    }),

  deleteGitHubBackupConfig: () =>
    request<{ message: string }>('/github-backup/config', { method: 'DELETE' }),

  testGitHubConnection: (repoUrl: string, token: string, provider: GitProviderType = 'github') =>
    request<GitHubTestConnectionResponse>('/github-backup/test', {
      method: 'POST',
      body: JSON.stringify({ repo_url: repoUrl, token, provider }),
    }),

  testGitHubStoredConnection: () =>
    request<GitHubTestConnectionResponse>('/github-backup/test-stored', { method: 'POST' }),

  triggerGitHubBackup: () =>
    request<GitHubBackupTriggerResponse>('/github-backup/run', { method: 'POST' }),

  getGitHubBackupStatus: () =>
    request<GitHubBackupStatus>('/github-backup/status'),

  getGitHubBackupLogs: (limit: number = 50) =>
    request<GitHubBackupLog[]>(`/github-backup/logs?limit=${limit}`),

  clearGitHubBackupLogs: (keepLast: number = 10) =>
    request<{ deleted: number; message: string }>(`/github-backup/logs?keep_last=${keepLast}`, { method: 'DELETE' }),

  // Scheduled local backups
  getLocalBackupStatus: () =>
    request<LocalBackupStatus>('/local-backup/status'),

  triggerLocalBackup: () =>
    request<{ success: boolean; message: string; filename?: string }>('/local-backup/run', { method: 'POST' }),

  getLocalBackups: () =>
    request<LocalBackupFile[]>('/local-backup/backups'),

  downloadLocalBackup: async (filename: string): Promise<{ blob: Blob; filename: string }> => {
    const response = await fetch(`${API_BASE}/local-backup/backups/${encodeURIComponent(filename)}/download`, {
      headers: authToken ? { 'Authorization': `Bearer ${authToken}` } : {},
    });
    if (!response.ok) throw new Error('Download failed');
    const blob = await response.blob();
    return { blob, filename };
  },

  restoreLocalBackup: (filename: string) =>
    request<{ success: boolean; message: string }>(`/local-backup/backups/${encodeURIComponent(filename)}/restore`, { method: 'POST' }),

  deleteLocalBackup: (filename: string) =>
    request<{ success: boolean; message: string }>(`/local-backup/backups/${encodeURIComponent(filename)}`, { method: 'DELETE' }),

  // Obico AI failure detection
  getObicoStatus: () =>
    request<ObicoStatus>('/obico/status'),

  testObicoConnection: (url: string, token?: string | null) =>
    request<ObicoTestConnection>('/obico/test-connection', {
      method: 'POST',
      body: JSON.stringify({ url, token }),
    }),

  // Slicer API — slice in the background. Both endpoints return 202 + a
  // job_id; poll /slice-jobs/{id} until status is `completed` or `failed`.
  sliceLibraryFile: (fileId: number, body: SliceRequest) =>
    request<SliceJobEnqueueResponse>(`/library/files/${fileId}/slice`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  sliceArchive: (archiveId: number, body: SliceRequest) =>
    request<SliceJobEnqueueResponse>(`/archives/${archiveId}/slice`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getSliceJob: (jobId: number) =>
    request<SliceJobState>(`/slice-jobs/${jobId}`),

  // Unified slicer-preset listing — cloud + local + standard, deduped by name.
  // Used by the SliceModal; see UnifiedPresetsResponse for the shape and
  // backend/app/api/routes/slicer_presets.py for the priority rules.
  // `refresh` bypasses the in-process cloud and bundled-preset caches on the
  // backend; the SliceModal's Refresh button passes true so a preset deleted
  // in Bambu Studio or Bambu Handy shows up without the 5-min TTL wait.
  getSlicerPresets: (options?: { refresh?: boolean }) =>
    request<UnifiedPresetsResponse>(
      options?.refresh ? '/slicer/presets?refresh=true' : '/slicer/presets',
    ),

  // Slicer Pipelines (#1425) — preset bundles the SliceModal can apply in
  // one click. CRUD is gated on PIPELINES_READ / PIPELINES_WRITE.
  listSlicerPipelines: () =>
    request<SlicerPipelinesListResponse>('/slicer-pipelines/'),

  getSlicerPipeline: (id: number) =>
    request<SlicerPipeline>(`/slicer-pipelines/${id}`),

  createSlicerPipeline: (data: SlicerPipelineCreateRequest) =>
    request<SlicerPipeline>('/slicer-pipelines/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateSlicerPipeline: (id: number, data: SlicerPipelineUpdateRequest) =>
    request<SlicerPipeline>(`/slicer-pipelines/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteSlicerPipeline: (id: number) =>
    request<void>(`/slicer-pipelines/${id}`, { method: 'DELETE' }),

  checkPipelineEligibility: (
    pipelineId: number,
    source: { kind: 'libraryFile'; id: number } | { kind: 'archive'; id: number },
  ) =>
    request<PipelineEligibilityReport>(`/slicer-pipelines/${pipelineId}/check-eligibility`, {
      method: 'POST',
      body: JSON.stringify(
        source.kind === 'libraryFile'
          ? { source_library_file_id: source.id }
          : { source_archive_id: source.id },
      ),
    }),

  runPipeline: (
    pipelineId: number,
    source: { kind: 'libraryFile'; id: number } | { kind: 'archive'; id: number },
    force = false,
    copies = 1,
  ) =>
    request<PipelineRun>(`/slicer-pipelines/${pipelineId}/run`, {
      method: 'POST',
      body: JSON.stringify({
        ...(source.kind === 'libraryFile'
          ? { source_library_file_id: source.id }
          : { source_archive_id: source.id }),
        force,
        copies,
      }),
    }),

  listPipelineRuns: (pipelineId: number, limit = 5) =>
    request<PipelineRunListResponse>(
      `/slicer-pipelines/${pipelineId}/runs?limit=${limit}`,
    ),

  // Dashboard list across all pipelines (#1425 PR C).
  listAllPipelineRuns: (params: {
    limit?: number;
    offset?: number;
    pipelineId?: number;
    status?: string;
    targetPrinterId?: number;
    targetModelClass?: string;
  } = {}) => {
    const search = new URLSearchParams();
    if (params.limit) search.set('limit', String(params.limit));
    if (params.offset) search.set('offset', String(params.offset));
    if (params.pipelineId) search.set('pipeline_id', String(params.pipelineId));
    if (params.status) search.set('status', params.status);
    if (params.targetPrinterId) search.set('target_printer_id', String(params.targetPrinterId));
    if (params.targetModelClass) search.set('target_model_class', params.targetModelClass);
    const q = search.toString();
    return request<PipelineRunListResponse>(
      `/pipeline-runs${q ? '?' + q : ''}`,
    );
  },

  // Clear terminal pipeline runs (#1425 PR C polish). Deletes all runs in
  // a terminal state (completed/failed/cancelled/partial_failure); in-flight
  // runs are preserved.
  clearTerminalPipelineRuns: () =>
    request<{ deleted: number }>('/pipeline-runs/clear', { method: 'POST' }),

  getPipelineRun: (runId: number) =>
    request<PipelineRun>(`/pipeline-runs/${runId}`),

  cancelPipelineRun: (runId: number) =>
    request<PipelineRun>(`/pipeline-runs/${runId}/cancel`, { method: 'POST' }),

  retryFailedPipelineRun: (runId: number) =>
    request<PipelineRun>(`/pipeline-runs/${runId}/retry-failed`, { method: 'POST' }),

  // Canonical Bambu printer-model registry — "Bambu Lab <model>" → short code.
  // Single source of truth shared with backend (PRINTER_MODEL_MAP); the
  // SliceModal uses this to classify cloud / standard presets by their
  // `@BBL <code>` suffix against the selected printer-preset name (#1325).
  getSlicerPrinterModels: () =>
    request<Record<string, string>>('/slicer/printer-models'),

  // Local Presets (OrcaSlicer imports)
  getLocalPresets: () =>
    request<LocalPresetsResponse>('/local-presets/'),

  getLocalPresetDetail: (id: number) =>
    request<LocalPresetDetail>(`/local-presets/${id}`),

  importLocalPresets: (formData: FormData) =>
    fetch(`${API_BASE}/local-presets/import`, {
      method: 'POST',
      headers: authToken ? { 'Authorization': `Bearer ${authToken}` } : {},
      body: formData,
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return res.json() as Promise<ImportResponse>;
    }),

  createLocalPreset: (data: { name: string; preset_type: string; setting: Record<string, unknown> }) =>
    request<LocalPreset>('/local-presets/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateLocalPreset: (id: number, data: { name?: string; setting?: Record<string, unknown> }) =>
    request<LocalPreset>(`/local-presets/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteLocalPreset: (id: number) =>
    request<{ success: boolean }>(`/local-presets/${id}`, { method: 'DELETE' }),

  refreshBaseProfileCache: () =>
    request<{ refreshed: number; failed: number; total: number }>('/local-presets/base-cache/refresh', { method: 'POST' })
};
