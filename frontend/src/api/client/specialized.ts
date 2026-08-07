import { API_BASE, authToken, parseContentDispositionFilename, request } from './core';

// AMS History types
export interface AMSHistoryPoint {
  recorded_at: string;
  humidity: number | null;
  humidity_raw: number | null;
  temperature: number | null;
}

export interface AMSHistoryResponse {
  printer_id: number;
  ams_id: number;
  data: AMSHistoryPoint[];
  min_humidity: number | null;
  max_humidity: number | null;
  avg_humidity: number | null;
  min_temperature: number | null;
  max_temperature: number | null;
  avg_temperature: number | null;
}

export type HeaterSensorKind = 'nozzle' | 'nozzle_2' | 'bed' | 'chamber';

export interface HeaterHistoryPoint {
  recorded_at: string;
  value: number | null;
  target: number | null;
}

export interface HeaterSeries {
  sensor_kind: HeaterSensorKind;
  data: HeaterHistoryPoint[];
  min_value: number | null;
  max_value: number | null;
  avg_value: number | null;
}

export interface PrinterSensorHistoryResponse {
  printer_id: number;
  series: HeaterSeries[];
}

// System Info types
export interface SystemInfo {
  app: {
    version: string;
    base_dir: string;
    archive_dir: string;
  };
  database: {
    engine: string;
    version: string;
    archives: number;
    archives_completed: number;
    archives_failed: number;
    archives_printing: number;
    printers: number;
    filaments: number;
    projects: number;
    smart_plugs: number;
    total_print_time_seconds: number;
    total_print_time_formatted: string;
    total_filament_grams: number;
    total_filament_kg: number;
  };
  printers: {
    total: number;
    connected: number;
    connected_list: Array<{
      id: number;
      name: string;
      state: string;
      model: string;
    }>;
  };
  storage: {
    archive_size_bytes: number;
    archive_size_formatted: string;
    database_size_bytes: number;
    database_size_formatted: string;
    disk_total_bytes: number;
    disk_total_formatted: string;
    disk_used_bytes: number;
    disk_used_formatted: string;
    disk_free_bytes: number;
    disk_free_formatted: string;
    disk_percent_used: number;
  };
  system: {
    platform: string;
    platform_release: string;
    platform_version: string;
    architecture: string;
    hostname: string;
    python_version: string;
    uptime_seconds: number;
    uptime_formatted: string;
    boot_time: string;
  };
  memory: {
    total_bytes: number;
    total_formatted: string;
    available_bytes: number;
    available_formatted: string;
    used_bytes: number;
    used_formatted: string;
    percent_used: number;
  };
  cpu: {
    count: number;
    count_logical: number;
    percent: number;
  };
}

export interface StorageUsageCategory {
  key: string;
  label: string;
  bytes: number;
  formatted: string;
  percent_of_total: number;
}

export interface StorageUsageOtherItem {
  bucket: string;
  label: string;
  kind: 'system' | 'data';
  deletable: boolean;
  bytes: number;
  formatted: string;
  percent_of_total: number;
}

export interface StorageUsageResponse {
  roots: string[];
  total_bytes: number;
  total_formatted: string;
  categories: StorageUsageCategory[];
  other_breakdown: StorageUsageOtherItem[];
  scan_errors: number;
  generated_at: string;
  cache: {
    hit: boolean;
    age_seconds: number;
    max_age_seconds: number;
  };
}

// Library (File Manager) types
export interface LibraryFolderTree {
  id: number;
  name: string;
  parent_id: number | null;
  project_id: number | null;
  archive_id: number | null;
  project_name: string | null;
  archive_name: string | null;
  is_external: boolean;
  external_path: string | null;
  external_readonly: boolean;
  file_count: number;
  // max(folder.updated_at, max(immediate-child file.updated_at)). Used by
  // the File Manager folder tree's "sort by recent activity" mode (#1770).
  latest_activity_at: string | null;
  children: LibraryFolderTree[];
}

export interface LibraryFolder {
  id: number;
  name: string;
  parent_id: number | null;
  project_id: number | null;
  archive_id: number | null;
  project_name: string | null;
  archive_name: string | null;
  is_external: boolean;
  external_path: string | null;
  external_readonly: boolean;
  external_show_hidden: boolean;
  file_count: number;
  latest_activity_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LibraryFolderCreate {
  name: string;
  parent_id?: number | null;
  project_id?: number | null;
  archive_id?: number | null;
}

export interface ExternalFolderCreate {
  name: string;
  external_path: string;
  readonly?: boolean;
  show_hidden?: boolean;
  parent_id?: number | null;
}

export interface LibraryFolderUpdate {
  name?: string;
  parent_id?: number | null;
  project_id?: number | null;  // 0 to unlink
  archive_id?: number | null;  // 0 to unlink
}

export interface LibraryFileDuplicate {
  id: number;
  filename: string;
  folder_id: number | null;
  folder_name: string | null;
  created_at: string;
}

export interface LibraryFile {
  id: number;
  folder_id: number | null;
  folder_name: string | null;
  project_id: number | null;
  project_name: string | null;
  is_external: boolean;
  filename: string;
  file_path: string;
  file_type: string;
  file_size: number;
  file_hash: string | null;
  thumbnail_path: string | null;
  metadata: Record<string, unknown> | null;
  print_count: number;
  last_printed_at: string | null;
  notes: string | null;
  duplicates: LibraryFileDuplicate[] | null;
  duplicate_count: number;
  // User tracking (Issue #206)
  created_by_id: number | null;
  created_by_username: string | null;
  created_at: string;
  updated_at: string;
  // Metadata fields
  print_name: string | null;
  print_time_seconds: number | null;
  filament_used_grams: number | null;
  sliced_for_model: string | null;
}

export interface LibraryTagSummary {
  id: number;
  name: string;
}

export interface LibraryFileListItem {
  id: number;
  folder_id: number | null;
  is_external: boolean;
  filename: string;
  file_type: string;
  file_size: number;
  thumbnail_path: string | null;
  print_count: number;
  duplicate_count: number;
  // User tracking (Issue #206)
  created_by_id: number | null;
  created_by_username: string | null;
  created_at: string;
  // Real on-disk modification time (#2680). Null for managed uploads; the date
  // sort and "Modified" column use `fs_modified_at ?? created_at`.
  fs_modified_at: string | null;
  print_name: string | null;
  print_time_seconds: number | null;
  filament_used_grams: number | null;
  sliced_for_model: string | null;
  // Tags assigned to this file (#1268). The backend always emits an empty
  // array when a file has no tags, but the field is typed optional so any
  // legacy code path (or mock) that constructs a LibraryFileListItem without
  // it doesn't crash the renderer. Read sites use `file.tags ?? []`.
  tags?: LibraryTagSummary[];
}

// Library tag catalog (#1268)
export interface LibraryTag {
  id: number;
  name: string;
  file_count: number;
  created_at: string;
  updated_at: string;
}

export interface LibraryTagBulkAssignResult {
  files_updated: number;
  associations_added: number;
  associations_removed: number;
}

export interface LibraryFileUpdate {
  filename?: string;
  folder_id?: number | null;
  project_id?: number | null;
  notes?: string | null;
}

// Library trash (#1008)
export interface LibraryTrashItem {
  id: number;
  filename: string;
  file_size: number;
  thumbnail_path: string | null;
  folder_id: number | null;
  folder_name: string | null;
  created_by_id: number | null;
  created_by_username: string | null;
  deleted_at: string;
  auto_purge_at: string;
}

export interface LibraryTrashListResponse {
  items: LibraryTrashItem[];
  total: number;
  retention_days: number;
}

export interface LibraryPurgePreview {
  count: number;
  total_bytes: number;
  sample_filenames: string[];
  older_than_days: number;
  include_never_printed: boolean;
}

export interface LibraryTrashSettings {
  retention_days: number;
  auto_purge_enabled: boolean;
  auto_purge_days: number;
  auto_purge_include_never_printed: boolean;
}

export interface ArchivePurgePreview {
  count: number;
  total_bytes: number;
  sample_filenames: string[];
  older_than_days: number;
}

export interface ArchivePurgeSettings {
  enabled: boolean;
  days: number;
  // #1390: when true, bulk-deletes the linked PrintLogEntry rows so the
  // contribution drops from Quick Stats too. Default false — soft-delete,
  // Quick Stats preserved.
  purge_stats: boolean;
}

export interface LibraryFileUploadResponse {
  id: number;
  filename: string;
  file_type: string;
  file_size: number;
  thumbnail_path: string | null;
  duplicate_of: number | null;
  metadata: Record<string, unknown> | null;
}

export interface LibraryStats {
  total_files: number;
  total_folders: number;
  total_size_bytes: number;
  files_by_type: Record<string, number>;
  total_prints: number;
  disk_free_bytes: number;
  disk_total_bytes: number;
  disk_used_bytes: number;
}

export interface ZipExtractResult {
  filename: string;
  file_id: number;
  folder_id: number | null;
}

export interface ZipExtractError {
  filename: string;
  error: string;
}

export interface ZipExtractResponse {
  extracted: number;
  folders_created: number;
  files: ZipExtractResult[];
  errors: ZipExtractError[];
}

// STL Thumbnail Generation types
export interface BatchThumbnailResult {
  file_id: number;
  filename: string;
  success: boolean;
  error?: string | null;
}

export interface BatchThumbnailResponse {
  processed: number;
  succeeded: number;
  failed: number;
  results: BatchThumbnailResult[];
}

// Library Queue types
export interface AddToQueueResult {
  file_id: number;
  filename: string;
  queue_item_id: number;
  archive_id: number;
}

export interface AddToQueueError {
  file_id: number;
  filename: string;
  error: string;
}

export interface AddToQueueResponse {
  added: AddToQueueResult[];
  errors: AddToQueueError[];
}

// Discovery types
export interface DiscoveredPrinter {
  serial: string;
  name: string;
  ip_address: string;
  model: string | null;
  discovered_at: string | null;
}

export interface DiscoveryStatus {
  running: boolean;
}

export interface DiscoveryInfo {
  is_docker: boolean;
  ssdp_running: boolean;
  scan_running: boolean;
  subnets: string[];
}

export interface SubnetScanStatus {
  running: boolean;
  scanned: number;
  total: number;
}

// Discovery API
export const discoveryApi = {
  getInfo: () => request<DiscoveryInfo>('/discovery/info'),

  getStatus: () => request<DiscoveryStatus>('/discovery/status'),

  startDiscovery: (duration: number = 10) =>
    request<DiscoveryStatus>(`/discovery/start?duration=${duration}`, { method: 'POST' }),

  stopDiscovery: () =>
    request<DiscoveryStatus>('/discovery/stop', { method: 'POST' }),

  getDiscoveredPrinters: () =>
    request<DiscoveredPrinter[]>('/discovery/printers'),

  // Subnet scanning (for Docker environments)
  startSubnetScan: (subnet: string, timeout: number = 1.0) =>
    request<SubnetScanStatus>('/discovery/scan', {
      method: 'POST',
      body: JSON.stringify({ subnet, timeout }),
    }),

  getScanStatus: () => request<SubnetScanStatus>('/discovery/scan/status'),

  stopSubnetScan: () =>
    request<SubnetScanStatus>('/discovery/scan/stop', { method: 'POST' }),
};

// Virtual Printer types
// Canonical wire values: `archive`, `review`, `queue`, `proxy`. The legacy
// `immediate` (→ archive) and `print_queue` (→ queue) names are still
// accepted by the backend so older API clients keep working, but new code
// should send the canonical names.
export type VirtualPrinterMode = 'archive' | 'review' | 'queue' | 'proxy' | 'immediate' | 'print_queue';

export interface VirtualPrinterProxyStatus {
  running: boolean;
  target_host: string;
  ftp_port: number;
  mqtt_port: number;
  ftp_connections: number;
  mqtt_connections: number;
}

export interface VirtualPrinterStatus {
  enabled: boolean;
  running: boolean;
  mode: VirtualPrinterMode;
  name: string;
  serial: string;
  model: string;
  model_name: string;
  pending_files: number;
  target_printer_ip?: string;  // For proxy mode
  proxy?: VirtualPrinterProxyStatus;  // For proxy mode
}

export interface VirtualPrinterSettings {
  enabled: boolean;
  access_code_set: boolean;
  mode: VirtualPrinterMode;
  model: string;
  target_printer_id: number | null;  // For proxy mode
  remote_interface_ip: string | null;  // For SSDP proxy across networks
  tailscale_disabled: boolean;
  archive_name_source: 'metadata' | 'filename';  // Source for archive's display name
  status: VirtualPrinterStatus;
}

export interface NetworkInterface {
  name: string;
  ip: string;
  netmask: string;
  subnet: string;
  is_alias?: boolean;
  label?: string;
}

export interface VirtualPrinterModels {
  models: Record<string, string>;  // SSDP code -> display name
  default: string;
}

export interface PendingUpload {
  id: number;
  filename: string;
  // Resolved name the review card should show — mirrors what archive_print
  // will eventually write to PrintArchive.print_name (#1152 follow-up). Falls
  // back to the stripped filename stem when the 3MF has no embedded title or
  // the operator has chosen the "filename" archive-name source.
  display_name: string;
  file_size: number;
  source_ip: string | null;
  status: string;
  tags: string | null;
  notes: string | null;
  project_id: number | null;
  uploaded_at: string;
}

// Virtual Printer API
export const virtualPrinterApi = {
  getSettings: () => request<VirtualPrinterSettings>('/settings/virtual-printer'),

  getModels: () => request<VirtualPrinterModels>('/settings/virtual-printer/models'),

  updateSettings: (data: {
    enabled?: boolean;
    access_code?: string;
    mode?: 'archive' | 'review' | 'queue' | 'proxy';
    model?: string;
    target_printer_id?: number;
    remote_interface_ip?: string;
    tailscale_disabled?: boolean;
    archive_name_source?: 'metadata' | 'filename';
  }) => {
    const params = new URLSearchParams();
    if (data.enabled !== undefined) params.set('enabled', String(data.enabled));
    if (data.access_code !== undefined) params.set('access_code', data.access_code);
    if (data.mode !== undefined) params.set('mode', data.mode);
    if (data.model !== undefined) params.set('model', data.model);
    if (data.target_printer_id !== undefined) params.set('target_printer_id', String(data.target_printer_id));
    if (data.remote_interface_ip !== undefined) params.set('remote_interface_ip', data.remote_interface_ip);
    if (data.tailscale_disabled !== undefined) params.set('tailscale_disabled', String(data.tailscale_disabled));
    if (data.archive_name_source !== undefined) params.set('archive_name_source', data.archive_name_source);

    return request<VirtualPrinterSettings>(`/settings/virtual-printer?${params.toString()}`, {
      method: 'PUT',
    });
  },
};

// Multi Virtual Printer API
export interface VirtualPrinterConfig {
  id: number;
  name: string;
  enabled: boolean;
  mode: VirtualPrinterMode;
  model: string | null;
  model_name: string | null;
  access_code_set: boolean;
  serial: string;
  target_printer_id: number | null;
  auto_dispatch: boolean;
  queue_force_color_match: boolean;
  gcode_injection: boolean;
  tailscale_disabled: boolean;
  bind_ip: string | null;
  remote_interface_ip: string | null;
  position: number;
  status: { running: boolean; pending_files: number; proxy?: VirtualPrinterProxyStatus };
}

export interface VirtualPrinterListResponse {
  printers: VirtualPrinterConfig[];
  models: Record<string, string>;
}

export const multiVirtualPrinterApi = {
  list: () => request<VirtualPrinterListResponse>('/virtual-printers'),

  get: (id: number) => request<VirtualPrinterConfig>(`/virtual-printers/${id}`),

  create: (data: {
    name?: string;
    enabled?: boolean;
    mode?: string;
    model?: string;
    access_code?: string;
    target_printer_id?: number;
    auto_dispatch?: boolean;
    queue_force_color_match?: boolean;
    gcode_injection?: boolean;
    bind_ip?: string;
    remote_interface_ip?: string;
  }) =>
    request<VirtualPrinterConfig>('/virtual-printers', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: number, data: {
    name?: string;
    enabled?: boolean;
    mode?: string;
    model?: string;
    access_code?: string;
    target_printer_id?: number;
    auto_dispatch?: boolean;
    queue_force_color_match?: boolean;
    gcode_injection?: boolean;
    tailscale_disabled?: boolean;
    bind_ip?: string;
    remote_interface_ip?: string;
  }) =>
    request<VirtualPrinterConfig>(`/virtual-printers/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  remove: (id: number) =>
    request<{ detail: string; id: number }>(`/virtual-printers/${id}`, {
      method: 'DELETE',
    }),

  getTailscaleStatus: () =>
    request<TailscaleStatusResponse>('/virtual-printers/tailscale-status'),

  getCaCertificate: () =>
    request<VPCaCertificate>('/virtual-printers/ca-certificate'),

  diagnose: (id: number) =>
    request<VPDiagnosticResult>(`/virtual-printers/${id}/diagnostic`),
};

/** The shared CA certificate every virtual printer presents — imported once
 *  into the slicer's trust store. Only the public certificate is returned. */
export interface VPCaCertificate {
  pem: string;
  fingerprint_sha256: string;
  not_valid_after: string;
}

export type VPDiagnosticStatus = 'pass' | 'fail' | 'warn' | 'skip';

export interface VPDiagnosticCheck {
  id:
    | 'enabled'
    | 'running'
    | 'bind_interface'
    | 'access_code'
    | 'target_printer'
    | 'port_ftps'
    | 'port_mqtt'
    | 'port_bind'
    | 'certificate';
  status: VPDiagnosticStatus;
  params: Record<string, string | number>;
}

export interface VPDiagnosticResult {
  vp_id: number;
  vp_name: string;
  mode: string;
  overall: 'ok' | 'warnings' | 'problems';
  checks: VPDiagnosticCheck[];
}

export interface TailscaleStatusResponse {
  available: boolean;
  fqdn: string;
  hostname: string;
  tailnet_name: string;
  tailscale_ips: string[];
  error: string | null;
}

// Pending Uploads API
export const pendingUploadsApi = {
  list: () => request<PendingUpload[]>('/pending-uploads/'),

  getCount: () => request<{ count: number }>('/pending-uploads/count'),

  get: (id: number) => request<PendingUpload>(`/pending-uploads/${id}`),

  archive: (id: number, data?: { tags?: string; notes?: string; project_id?: number }) =>
    request<{ id: number; print_name: string; filename: string }>(`/pending-uploads/${id}/archive`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),

  discard: (id: number) =>
    request<{ success: boolean }>(`/pending-uploads/${id}`, { method: 'DELETE' }),

  archiveAll: () =>
    request<{ archived: number; failed: number }>('/pending-uploads/archive-all', { method: 'POST' }),

  discardAll: () =>
    request<{ discarded: number }>('/pending-uploads/discard-all', { method: 'DELETE' }),
};

// Firmware API Types
export interface AvailableFirmwareVersion {
  version: string;
  file_available: boolean;
  download_url: string | null;
  release_notes: string | null;
  release_time: string | null;
}

export interface FirmwareUpdateInfo {
  printer_id: number;
  printer_name: string;
  model: string | null;
  current_version: string | null;
  latest_version: string | null;
  update_available: boolean;
  download_url: string | null;
  release_notes: string | null;
  available_versions: AvailableFirmwareVersion[];
}

export interface FirmwareUploadPrepare {
  can_proceed: boolean;
  sd_card_present: boolean;
  sd_card_free_space: number;
  firmware_size: number;
  space_sufficient: boolean;
  update_available: boolean;
  current_version: string | null;
  latest_version: string | null;
  target_version: string | null;
  firmware_filename: string | null;
  errors: string[];
}

export interface FirmwareUploadStatus {
  status: 'idle' | 'preparing' | 'downloading' | 'uploading' | 'complete' | 'error';
  progress: number;
  message: string;
  error: string | null;
  firmware_filename: string | null;
  firmware_version: string | null;
}

// Firmware API
export const firmwareApi = {
  checkUpdates: () =>
    request<{ updates: FirmwareUpdateInfo[]; updates_available: number }>('/firmware/updates'),

  checkPrinterUpdate: (printerId: number) =>
    request<FirmwareUpdateInfo>(`/firmware/updates/${printerId}`),

  prepareUpload: (printerId: number, version?: string) =>
    request<FirmwareUploadPrepare>(
      `/firmware/updates/${printerId}/prepare${version ? `?version=${encodeURIComponent(version)}` : ''}`,
    ),

  startUpload: (printerId: number, version?: string) =>
    request<{ started: boolean; message: string }>(
      `/firmware/updates/${printerId}/upload${version ? `?version=${encodeURIComponent(version)}` : ''}`,
      { method: 'POST' },
    ),

  getUploadStatus: (printerId: number) =>
    request<FirmwareUploadStatus>(`/firmware/updates/${printerId}/upload/status`),
};

// Support types
export interface DebugLoggingState {
  enabled: boolean;
  enabled_at: string | null;
  duration_seconds: number | null;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  logger_name: string;
  message: string;
}

export interface LogsResponse {
  entries: LogEntry[];
  total_in_file: number;
  filtered_count: number;
}

// Support API
export const supportApi = {
  getDebugLoggingState: () =>
    request<DebugLoggingState>('/support/debug-logging'),

  setDebugLogging: (enabled: boolean) =>
    request<DebugLoggingState>('/support/debug-logging', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),

  downloadSupportBundle: async () => {
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/support/bundle`, { headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    // Get filename from Content-Disposition header or use default
    const disposition = response.headers.get('Content-Disposition');
    const filename = parseContentDispositionFilename(disposition) || 'printops-support.zip';

    // Download the blob
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

  getLogs: (params?: { limit?: number; level?: string; search?: string }) => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', params.limit.toString());
    if (params?.level) searchParams.set('level', params.level);
    if (params?.search) searchParams.set('search', params.search);
    const query = searchParams.toString();
    return request<LogsResponse>(`/support/logs${query ? `?${query}` : ''}`);
  },

  clearLogs: () =>
    request<{ message: string }>('/support/logs', { method: 'DELETE' }),
};

// SpoolBuddy types
export interface SpoolBuddyDevice {
  id: number;
  device_id: string;
  hostname: string;
  ip_address: string;
  backend_url?: string | null;
  firmware_version: string | null;
  has_nfc: boolean;
  has_scale: boolean;
  tare_offset: number;
  calibration_factor: number;
  nfc_reader_type: string | null;
  nfc_connection: string | null;
  display_brightness: number;
  display_blank_timeout: number;
  has_backlight: boolean;
  last_calibrated_at: string | null;
  last_seen: string | null;
  pending_command: string | null;
  nfc_ok: boolean;
  scale_ok: boolean;
  uptime_s: number;
  update_status: string | null;
  update_message: string | null;
  system_stats: {
    os?: { os?: string; kernel?: string; arch?: string; python?: string };
    cpu_temp_c?: number;
    cpu_count?: number;
    load_avg?: number[];
    memory?: { total_mb?: number; available_mb?: number; used_mb?: number; percent?: number };
    disk?: { total_gb?: number; used_gb?: number; free_gb?: number; percent?: number };
    system_uptime_s?: number;
  } | null;
  online: boolean;
}

export interface DaemonUpdateCheck {
  current_version: string;
  latest_version: string | null;
  update_available: boolean;
}

// SpoolBuddy API
export const spoolbuddyApi = {
  getDevices: () =>
    request<SpoolBuddyDevice[]>('/spoolbuddy/devices'),

  deleteDevice: (deviceId: string) =>
    request<{ status: string; device_id: string }>(`/spoolbuddy/devices/${deviceId}`, {
      method: 'DELETE',
    }),

  tare: (deviceId: string) =>
    request<{ status: string }>(`/spoolbuddy/devices/${deviceId}/calibration/tare`, {
      method: 'POST',
      body: '{}',
    }),

  getCalibration: (deviceId: string) =>
    request<{ tare_offset: number; calibration_factor: number }>(`/spoolbuddy/devices/${deviceId}/calibration`),

  setCalibrationFactor: (deviceId: string, knownWeightGrams: number, rawAdc: number, tareRawAdc?: number) =>
    request<{ tare_offset: number; calibration_factor: number }>(`/spoolbuddy/devices/${deviceId}/calibration/set-factor`, {
      method: 'POST',
      body: JSON.stringify({ known_weight_grams: knownWeightGrams, raw_adc: rawAdc, tare_raw_adc: tareRawAdc }),
    }),

  updateSpoolWeight: (spoolId: number, weightGrams: number) =>
    request<{ status: string; weight_used: number }>('/spoolbuddy/scale/update-spool-weight', {
      method: 'POST',
      body: JSON.stringify({ spool_id: spoolId, weight_grams: weightGrams }),
    }),

  updateDisplay: (deviceId: string, brightness: number, blankTimeout: number) =>
    request<{ status: string }>(`/spoolbuddy/devices/${deviceId}/display`, {
      method: 'PUT',
      body: JSON.stringify({ brightness, blank_timeout: blankTimeout }),
    }),

  updateSystemConfig: (deviceId: string, backendUrl: string, apiKey?: string) =>
    request<{ status: string; message: string }>(`/spoolbuddy/devices/${deviceId}/system/config`, {
      method: 'POST',
      body: JSON.stringify({ backend_url: backendUrl, ...(apiKey ? { api_key: apiKey } : {}) }),
    }),

  checkDaemonUpdate: (deviceId: string) =>
    request<DaemonUpdateCheck>(`/spoolbuddy/devices/${deviceId}/update-check`),

  triggerUpdate: (deviceId: string) =>
    request<{ status: string; message: string }>(`/spoolbuddy/devices/${deviceId}/update`, {
      method: 'POST',
      body: '{}',
    }),

  getSSHPublicKey: () =>
    request<{ public_key: string }>('/spoolbuddy/ssh/public-key'),

  writeTag: (deviceId: string, spoolId: number) =>
    request<{ status: string; warnings?: string[] }>('/spoolbuddy/nfc/write-tag', {
      method: 'POST',
      body: JSON.stringify({ device_id: deviceId, spool_id: spoolId }),
    }),

  cancelWrite: (deviceId: string) =>
    request<{ status: string }>(`/spoolbuddy/devices/${deviceId}/cancel-write`, {
      method: 'POST',
      body: '{}',
    }),

  systemCommand: (deviceId: string, command: 'reboot' | 'shutdown' | 'restart_daemon' | 'restart_browser') =>
    request<{ status: string; command: string }>(`/spoolbuddy/devices/${deviceId}/system/command`, {
      method: 'POST',
      body: JSON.stringify({ command }),
    }),

  queueDiagnostics: (deviceId: string, type: 'nfc' | 'scale' | 'read_tag') =>
    request<{ status: string; diagnostic: string; message: string }>(
      `/spoolbuddy/diagnostics/${deviceId}/run?diagnostic=${type}`,
      { method: 'POST', body: '{}' }
    ),

  getDiagnosticResult: (deviceId: string, type: 'nfc' | 'scale' | 'read_tag') =>
    request<{ diagnostic: string; success: boolean; output: string; exit_code: number }>(
      `/spoolbuddy/diagnostics/${deviceId}/result?diagnostic=${type}`,
      { method: 'GET' }
    ),
};

export interface BugReportRequest {
  description: string;
  email?: string;
  screenshot_base64?: string;
  include_support_info?: boolean;
  debug_logs?: string;
}

export interface BugReportResponse {
  success: boolean;
  message: string;
  issue_url?: string;
  issue_number?: number;
}

export interface BugReportStatusResponse {
  repository: string;
  relay_configured: boolean;
  issue_url: string;
}

export const bugReportApi = {
  getStatus: () => request<BugReportStatusResponse>('/bug-report/status'),
  submit: (data: BugReportRequest) =>
    request<BugReportResponse>('/bug-report/submit', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  startLogging: () =>
    request<{ started: boolean; was_debug: boolean }>('/bug-report/start-logging', {
      method: 'POST',
    }),
  stopLogging: (wasDebug: boolean) =>
    request<{ logs: string }>(`/bug-report/stop-logging?was_debug=${wasDebug}`, {
      method: 'POST',
    }),
};

export interface SponsorPromptCheckResponse {
  show: boolean;
  milestone?: string;
  family?: 'prints' | 'cost' | 'archives' | 'anniversary' | 'version-update';
  threshold?: number;
  payload?: Record<string, unknown>;
}

export const sponsorPromptApi = {
  check: () => request<SponsorPromptCheckResponse>('/sponsor-prompt/check'),
  dismiss: (milestone: string) =>
    request<void>('/sponsor-prompt/dismiss', {
      method: 'POST',
      body: JSON.stringify({ milestone }),
    }),
};
