// Archive types
export interface ArchiveDuplicate {
  id: number;
  print_name: string | null;
  created_at: string;
  match_type: 'exact' | 'similar';  // 'exact' = hash match, 'similar' = name match
}

export interface Archive {
  id: number;
  printer_id: number | null;
  project_id: number | null;
  project_name: string | null;
  filename: string;
  file_path: string;
  file_size: number;
  content_hash: string | null;
  thumbnail_path: string | null;
  timelapse_path: string | null;
  source_3mf_path: string | null;
  f3d_path: string | null;
  duplicates: ArchiveDuplicate[] | null;
  duplicate_count: number;
  duplicate_sequence: number;  // 0 = original, 1+ = nth duplicate
  original_archive_id: number | null;  // ID of the first/original archive
  object_count: number | null;
  print_name: string | null;
  print_time_seconds: number | null;
  actual_time_seconds: number | null;  // Computed from started_at/completed_at
  time_accuracy: number | null;  // Percentage: 100 = perfect, >100 = faster than estimated
  filament_used_grams: number | null;
  filament_type: string | null;
  filament_color: string | null;
  layer_height: number | null;
  total_layers: number | null;
  nozzle_diameter: number | null;
  bed_temperature: number | null;
  bed_type: string | null;  // Build plate type from 3MF (e.g. "Cool Plate", "Textured PEI Plate")
  nozzle_temperature: number | null;
  sliced_for_model: string | null;  // Printer model this file was sliced for
  status: string;
  started_at: string | null;
  completed_at: string | null;
  extra_data: Record<string, unknown> | null;
  makerworld_url: string | null;
  designer: string | null;
  external_url: string | null;
  is_favorite: boolean;
  tags: string | null;
  notes: string | null;
  cost: number | null;
  photos: string[] | null;
  failure_reason: string | null;
  quantity: number;
  energy_kwh: number | null;
  energy_cost: number | null;
  created_at: string;
  // User tracking (Issue #206)
  created_by_id: number | null;
  created_by_username: string | null;
  // Per-archive run aggregates from PrintLogEntry (#1378)
  run_count: number;
  last_run_at: string | null;
  total_filament_actual_grams: number | null;
  successful_run_count: number;
  failed_run_count: number;
}

export interface ArchiveSlim {
  printer_id: number | null;
  print_name: string | null;
  print_time_seconds: number | null;
  actual_time_seconds: number | null;
  filament_used_grams: number | null;
  filament_type: string | null;
  filament_color: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  cost: number | null;
  energy_kwh: number | null;
  energy_cost: number | null;
  quantity: number;
  created_at: string;
}

export interface PrintLogEntry {
  id: number;
  archive_id: number | null;
  print_name: string | null;
  printer_name: string | null;
  printer_id: number | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  filament_type: string | null;
  filament_color: string | null;
  filament_used_grams: number | null;
  cost: number | null;
  energy_kwh: number | null;
  energy_cost: number | null;
  failure_reason: string | null;
  thumbnail_path: string | null;
  created_by_id: number | null;
  created_by_username: string | null;
  created_at: string;
}

export interface PrintLogResponse {
  items: PrintLogEntry[];
  total: number;
}

export interface ArchiveStats {
  total_prints: number;
  successful_prints: number;
  failed_prints: number;
  cancelled_prints: number;
  total_print_time_hours: number;
  total_filament_grams: number;
  total_cost: number;
  prints_by_filament_type: Record<string, number>;
  prints_by_printer: Record<string, number>;
  average_time_accuracy: number | null;
  time_accuracy_by_printer: Record<string, number> | null;
  total_energy_kwh: number;
  total_energy_cost: number;
  energy_source?: 'smart_plug_live' | 'smart_plug_snapshots' | 'print_logs' | string | null;
  // True when a date-filtered total-consumption query is running on incomplete
  // snapshot history (e.g. right after upgrade, before hourly snapshots have
  // a baseline). UI should explain why the number may undercount.
  energy_data_warming_up?: boolean;
}

export interface ArchiveEnergyHistoryPoint {
  bucket_start: string;
  energy_kwh: number;
  energy_cost: number;
  source: string;
  sample_count: number;
}

export interface TagInfo {
  name: string;
  count: number;
}

export interface FailureAnalysis {
  period_days: number;
  total_prints: number;
  failed_prints: number;
  failure_rate: number;
  failures_by_reason: Record<string, number>;
  failures_by_filament: Record<string, number>;
  failures_by_printer: Record<string, number>;
  failures_by_hour: Record<number, number>;
  recent_failures: Array<{
    id: number;
    print_name: string;
    failure_reason: string | null;
    filament_type: string | null;
    printer_id: number | null;
    created_at: string | null;
  }>;
  trend: Array<{
    week_start: string;
    total_prints: number;
    failed_prints: number;
    failure_rate: number;
  }>;
}

export interface BulkUploadResult {
  uploaded: number;
  failed: number;
  results: Array<{ filename: string; id: number; status: string }>;
  errors: Array<{ filename: string; error: string }>;
}

// Archive Comparison types
export interface ComparisonArchiveInfo {
  id: number;
  print_name: string;
  status: string;
  created_at: string | null;
  printer_id: number | null;
  project_name: string | null;
}

export interface ComparisonField {
  field: string;
  label: string;
  unit: string | null;
  values: (string | number | null)[];
  raw_values: (string | number | null)[];
  has_difference: boolean;
}

export interface SuccessCorrelationInsight {
  field: string;
  label: string;
  insight: string;
  success_avg?: number;
  failed_avg?: number;
  success_values?: string[];
  failed_values?: string[];
}

export interface SuccessCorrelation {
  has_both_outcomes: boolean;
  message?: string;
  successful_count?: number;
  failed_count?: number;
  insights?: SuccessCorrelationInsight[];
}

export interface ArchiveComparison {
  archives: ComparisonArchiveInfo[];
  comparison: ComparisonField[];
  differences: ComparisonField[];
  success_correlation: SuccessCorrelation;
}

export interface SimilarArchive {
  archive: {
    id: number;
    print_name: string;
    status: string;
    created_at: string | null;
  };
  match_reason: string;
  match_score: number;
}

// Project types
export interface ProjectStats {
  total_archives: number;
  total_items: number;  // Sum of quantities (total items printed)
  completed_prints: number;  // Sum of quantities for completed prints (parts)
  failed_prints: number;
  queued_prints: number;
  in_progress_prints: number;
  total_print_time_hours: number;
  total_filament_grams: number;
  progress_percent: number | null;  // Plates progress (total_archives / target_count)
  parts_progress_percent: number | null;  // Parts progress (completed_prints / target_parts_count)
  estimated_cost: number;
  total_energy_kwh: number;
  total_energy_cost: number;
  remaining_prints: number | null;  // Remaining plates
  remaining_parts: number | null;  // Remaining parts
  bom_total_items: number;
  bom_completed_items: number;
  bom_cost: number;
}

export interface ProjectChildPreview {
  id: number;
  name: string;
  color: string | null;
  status: string;
  progress_percent: number | null;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  color: string | null;
  status: string;  // active, completed, archived
  target_count: number | null;  // Target number of plates/print jobs
  target_parts_count: number | null;  // Target number of parts/objects
  notes: string | null;
  attachments: ProjectAttachment[] | null;
  tags: string | null;
  due_date: string | null;
  priority: string;  // low, normal, high, urgent
  budget: number | null;
  is_template: boolean;
  template_source_id: number | null;
  parent_id: number | null;
  parent_name: string | null;
  children: ProjectChildPreview[];
  created_at: string;
  updated_at: string;
  stats?: ProjectStats;
  url: string | null;  // External link rendered next to project name on the card (#1155)
  cover_image_filename: string | null;  // Filename within project attachments dir (#1155)
}

export interface ProjectAttachment {
  filename: string;
  original_name: string;
  size: number;
  uploaded_at: string;
}

export interface ArchivePreview {
  id: number;
  print_name: string | null;
  thumbnail_path: string | null;
  status: string;
  filament_type: string | null;
  filament_color: string | null;
}

export interface ProjectListItem {
  id: number;
  name: string;
  description: string | null;
  color: string | null;
  status: string;
  target_count: number | null;  // Target number of plates/print jobs
  target_parts_count: number | null;  // Target number of parts/objects
  budget: number | null;
  created_at: string;
  archive_count: number;  // Number of print jobs (plates)
  total_items: number;  // Sum of quantities (total items printed, including failed)
  completed_count: number;  // Sum of quantities for completed prints only (parts)
  failed_count: number;  // Sum of quantities for failed prints
  queue_count: number;
  progress_percent: number | null;  // Plates progress
  archives: ArchivePreview[];
  url: string | null;  // #1155
  cover_image_filename: string | null;  // #1155
}

export interface ProjectCreate {
  name: string;
  description?: string;
  color?: string;
  target_count?: number;
  target_parts_count?: number;
  notes?: string;
  tags?: string;
  due_date?: string;
  priority?: string;
  budget?: number | null;
  parent_id?: number;
  url?: string | null;  // #1155
}

export interface ProjectUpdate {
  name?: string;
  description?: string;
  color?: string;
  status?: string;
  target_count?: number;
  target_parts_count?: number;
  notes?: string;
  tags?: string;
  due_date?: string;
  priority?: string;
  budget?: number | null;
  parent_id?: number;
  url?: string | null;  // #1155 — explicit null clears the URL
}

// BOM Types - Tracks sourced/purchased parts (hardware, electronics, etc.)
export interface BOMItem {
  id: number;
  project_id: number;
  name: string;
  quantity_needed: number;
  quantity_acquired: number;
  unit_price: number | null;
  sourcing_url: string | null;
  archive_id: number | null;
  archive_name: string | null;
  stl_filename: string | null;
  remarks: string | null;
  sort_order: number;
  is_complete: boolean;
  created_at: string;
  updated_at: string;
}

export interface BOMItemCreate {
  name: string;
  quantity_needed?: number;
  unit_price?: number;
  sourcing_url?: string;
  archive_id?: number;
  stl_filename?: string;
  remarks?: string;
}

export interface BOMItemUpdate {
  name?: string;
  quantity_needed?: number;
  quantity_acquired?: number;
  unit_price?: number;
  sourcing_url?: string;
  archive_id?: number;
  stl_filename?: string;
  remarks?: string;
}

// Project Export/Import Types
export interface BOMItemExport {
  name: string;
  quantity_needed: number;
  quantity_acquired: number;
  unit_price: number | null;
  sourcing_url: string | null;
  stl_filename: string | null;
  remarks: string | null;
}

export interface LinkedFolderExport {
  name: string;
}

export interface ProjectExport {
  name: string;
  description: string | null;
  color: string | null;
  status: string;
  target_count: number | null;
  target_parts_count: number | null;
  notes: string | null;
  tags: string | null;
  due_date: string | null;
  priority: string;
  budget: number | null;
  bom_items: BOMItemExport[];
  linked_folders: LinkedFolderExport[];
}

export interface ProjectImport {
  name: string;
  description?: string;
  color?: string;
  status?: string;
  target_count?: number;
  target_parts_count?: number;
  notes?: string;
  tags?: string;
  due_date?: string;
  priority?: string;
  budget?: number | null;
  bom_items?: BOMItemExport[];
  linked_folders?: LinkedFolderExport[];
}

// Timeline Types
export interface TimelineEvent {
  event_type: string;
  timestamp: string;
  title: string;
  description: string | null;
  metadata: Record<string, unknown> | null;
}

// API Key types
export interface APIKey {
  id: number;
  name: string;
  key_prefix: string;
  user_id: number | null;  // Owner; null on legacy keys created before per-user ownership (#1182)
  can_queue: boolean;
  can_control_printer: boolean;
  can_read_status: boolean;
  can_manage_library: boolean;
  can_manage_inventory: boolean;
  can_manage_maintenance: boolean;
  can_manage_archives: boolean;
  can_manage_projects: boolean;
  can_render_documents: boolean;
  can_access_cloud: boolean;
  can_update_energy_cost: boolean;
  printer_ids: number[] | null;
  enabled: boolean;
  last_used: string | null;
  created_at: string;
  expires_at: string | null;
}

export interface APIKeyCreate {
  name: string;
  can_queue?: boolean;
  can_control_printer?: boolean;
  can_read_status?: boolean;
  can_manage_library?: boolean;
  can_manage_inventory?: boolean;
  can_manage_maintenance?: boolean;
  can_manage_archives?: boolean;
  can_manage_projects?: boolean;
  can_render_documents?: boolean;
  can_access_cloud?: boolean;
  can_update_energy_cost?: boolean;
  printer_ids?: number[] | null;
  expires_at?: string | null;
}

export interface APIKeyCreateResponse extends APIKey {
  key: string;  // Full key, only shown on creation
}

export interface APIKeyUpdate {
  name?: string;
  can_queue?: boolean;
  can_control_printer?: boolean;
  can_read_status?: boolean;
  can_manage_library?: boolean;
  can_manage_inventory?: boolean;
  can_manage_maintenance?: boolean;
  can_manage_archives?: boolean;
  can_manage_projects?: boolean;
  can_render_documents?: boolean;
  can_access_cloud?: boolean;
  can_update_energy_cost?: boolean;
  printer_ids?: number[] | null;
  enabled?: boolean;
  expires_at?: string | null;
}
