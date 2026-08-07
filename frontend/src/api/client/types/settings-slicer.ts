// Settings types
export interface AppSettings {
  auto_archive: boolean;
  save_thumbnails: boolean;
  capture_finish_photo: boolean;
  default_filament_cost: number;
  currency: string;
  energy_cost_per_kwh: number;
  energy_tracking_mode: 'print' | 'total';
  calculation_defaults: string;
  small_parts_default_minimum_stock: string;
  small_parts_low_stock_warning: boolean;
  check_updates: boolean;
  check_printer_firmware: boolean;
  show_developer_lan_warning: boolean;
  show_sponsor_prompts: boolean;
  include_beta_updates: boolean;
  // #1589: false hides the local username/password form on the login page;
  // PRINTOPS_LOCAL_LOGIN=true on the server flips the reported value back to
  // true so the env-var recovery path is visible to the SPA.
  local_login_enabled: boolean;
  language: string;
  notification_language: string;
  // AMS threshold settings
  ams_humidity_good: number;  // <= this is green
  ams_humidity_fair: number;  // <= this is orange, > is red
  ams_temp_good: number;      // <= this is green/blue
  ams_temp_fair: number;      // <= this is orange, > is red
  ams_history_retention_days: number;  // days to keep AMS sensor history
  // Queue auto-drying settings
  queue_drying_enabled: boolean;  // Auto-dry AMS between queued prints
  queue_drying_block: boolean;  // Block queue until drying completes
  ambient_drying_enabled: boolean;  // Auto-dry idle printers based on humidity regardless of queue
  print_drying_enabled: boolean;  // Continue drying while a print is running on capable hardware
  drying_presets: string;  // JSON blob of drying presets per filament type
  ams_humidity_thresholds: string;  // JSON blob of per-filament humidity thresholds (#1605)
  gcode_snippets: string;  // JSON: per-model G-code injection snippets
  // Scheduled local backup
  local_backup_enabled: boolean;
  local_backup_schedule: string;
  local_backup_time: string;
  local_backup_retention: number;
  local_backup_path: string;
  // Print modal settings
  per_printer_mapping_expanded: boolean;  // Whether custom mapping is expanded by default in print modal
  // Date/time format settings
  date_format: 'system' | 'us' | 'eu' | 'iso';
  time_format: 'system' | '12h' | '24h';
  // Filament tracking
  disable_filament_warnings: boolean;  // Disable filament warnings (print insufficiency and assignment mismatch)
  prefer_lowest_filament: boolean;  // When multiple spools match, prefer lowest remaining filament
  spoolman_enabled: boolean;  // True when the user has switched filament tracking to Spoolman; backend includes this in the /settings/ response even though earlier consumers read it from the dedicated /settings/spoolman endpoint as a string
  auto_add_unknown_rfid: boolean;  // When false, the backend skips auto-creating inventory spools for unknown RFID tags and instead broadcasts an unknown_tag event for the confirmation modal
  spoolman_url: string;
  // Default printer
  default_printer_id: number | null;
  pipeline_max_copies: number;
  // Dark mode theme settings
  dark_style: 'classic' | 'glow' | 'vibrant';
  dark_background: 'neutral' | 'warm' | 'cool' | 'oled' | 'slate' | 'forest';
  dark_accent: 'green' | 'teal' | 'blue' | 'orange' | 'purple' | 'red';
  // Light mode theme settings
  light_style: 'classic' | 'glow' | 'vibrant';
  light_background: 'neutral' | 'warm' | 'cool';
  light_accent: 'green' | 'teal' | 'blue' | 'orange' | 'purple' | 'red';
  // FTP retry settings
  ftp_retry_enabled: boolean;
  ftp_retry_count: number;
  ftp_retry_delay: number;
  ftp_timeout: number;
  // MQTT relay settings
  mqtt_enabled: boolean;
  mqtt_broker: string;
  mqtt_port: number;
  mqtt_username: string;
  mqtt_password: string;
  mqtt_topic_prefix: string;
  mqtt_use_tls: boolean;
  // External URL for notifications
  external_url: string;
  // Home Assistant integration
  ha_enabled: boolean;
  ha_url: string;
  ha_token: string;
  ha_url_from_env: boolean;
  ha_token_from_env: boolean;
  ha_env_managed: boolean;
  // File Manager / Library settings
  library_archive_mode: 'always' | 'never' | 'ask';
  library_disk_warning_gb: number;
  // Camera view settings
  camera_view_mode: 'window' | 'embedded';
  // Preferred slicer (server-side API / sidecar)
  preferred_slicer: 'bambu_studio' | 'orcaslicer';
  // Desktop "Open in Slicer" override (#1329). Null inherits from
  // preferred_slicer so existing installs behave identically.
  open_in_slicer: 'bambu_studio' | 'orcaslicer' | null;
  // Use the slicer-API sidecar for slicing (in-app modal) vs desktop URI scheme
  use_slicer_api: boolean;
  // Per-install sidecar URLs. Empty string falls back to the env defaults.
  orcaslicer_api_url: string;
  bambu_studio_api_url: string;
  // Prometheus metrics
  prometheus_enabled: boolean;
  prometheus_token: string;
  // Bed cooled threshold
  bed_cooled_threshold: number;
  // Inventory low stock threshold
  low_stock_threshold: number;
  // Session policy (#1706) — admin-set ceiling, hours, [1, 720]
  session_max_hours: number;
  // User email notifications toggle
  user_notifications_enabled: boolean;
  // Default print options
  default_bed_levelling: boolean;
  default_flow_cali: boolean;
  default_vibration_cali: boolean;
  default_layer_inspect: boolean;
  default_timelapse: boolean;
  default_nozzle_offset_cali: boolean;
  // Staggered batch start defaults
  stagger_group_size: number;
  stagger_interval_minutes: number;
  // Plate-clear confirmation
  require_plate_clear: boolean;
  // Shortest job first scheduling
  queue_shortest_first: boolean;
  // Queue upload concurrency
  queue_max_concurrent_uploads: number;
  // Preheat / heat-soak before queued prints (#1468). Master toggle is the
  // default for new queue items; per-item PrintQueueItem.preheat_override can
  // flip the decision per print. Chamber target derives from the loaded AMS
  // filament types via preheat_filament_targets (JSON map of type → °C, max
  // across loaded slots); the per-item override field bypasses derivation.
  preheat_enabled: boolean;
  preheat_filament_targets: string;
  preheat_max_wait_seconds: number;
  preheat_soak_seconds: number;
  // User-configurable presets for the printer-card popovers (JSON arrays of 3 ints).
  // Empty string = use built-in defaults.
  nozzle_temp_presets: string;
  bed_temp_presets: string;
  chamber_temp_presets: string;
  fan_speed_presets: string;
  // Default sidebar order (admin-set for all users)
  default_sidebar_order: string;
  // LDAP authentication
  ldap_enabled: boolean;
  ldap_server_url: string;
  ldap_bind_dn: string;
  ldap_bind_password: string;
  ldap_search_base: string;
  ldap_user_filter: string;
  ldap_security: string;
  ldap_group_mapping: string;
  ldap_auto_provision: boolean;
  ldap_default_group: string;
  obico_enabled: boolean;
  obico_ml_url: string;
  obico_ml_token: string;
  obico_sensitivity: 'low' | 'medium' | 'high';
  obico_action: 'notify' | 'pause' | 'pause_and_off';
  obico_poll_interval: number;
  obico_enabled_printers: string;
  // Inventory forecasting global lead time
  forecast_global_lead_time_days: number;
}

export type AppSettingsUpdate = Partial<AppSettings>;

// MQTT relay status
export interface MQTTStatus {
  enabled: boolean;
  connected: boolean;
  broker: string;
  port: number;
  topic_prefix: string;
}

// Cloud types
export interface CloudAuthStatus {
  is_authenticated: boolean;
  email: string | null;
  region?: 'global' | 'china' | null;
  sign_in_expired?: boolean;
}

export interface CloudLoginResponse {
  success: boolean;
  needs_verification: boolean;
  message: string;
  verification_type?: 'email' | 'totp' | null;
  tfa_key?: string | null;
}

// Orca Cloud types — RFC 8628 device pairing against Orca's external-app API.
// See backend/app/services/orca_cloud.py for the flow and token lifecycle.
export interface OrcaDeviceStartResponse {
  attempt_id: string;
  user_code: string;
  verification_uri: string;
  verification_uri_complete: string;
  interval: number;
  expires_in: number;
}

export type OrcaDevicePollStatus =
  | 'authorization_pending'
  | 'slow_down'
  | 'access_denied'
  | 'expired_token'
  | 'complete';

export interface OrcaDevicePollResponse {
  status: OrcaDevicePollStatus;
  connected: boolean;
  email: string | null;
  user_id: string | null;
}

export interface OrcaAuthStatusResponse {
  connected: boolean;
  email: string | null;
  user_id: string | null;
}

// Orca profiles are shaped to match Bambu Cloud's SlicerSetting on the wire
// so the frontend can use the same visual components for both surfaces (cards,
// grouped sections, filter bar). Backend handles the source-specific
// transformation in routes/orca_cloud.py::_orca_to_setting.
export interface OrcaProfileMeta {
  setting_id: string;
  name: string;
  type: string;
  version: string | null;
  user_id: string | null;
  updated_time: string | null;
  is_custom: boolean;
}

export interface OrcaProfileListResponse {
  filament: OrcaProfileMeta[];
  printer: OrcaProfileMeta[];
  process: OrcaProfileMeta[];
}

export interface OrcaProfileDetail {
  setting_id: string;
  name: string;
  type: string;
  version: string | null;
  base_id: string | null;
  update_time: string | null;
  setting: Record<string, unknown>;
}

// MakerWorld integration. Full metadata/instance shapes come back as
// Record<string, unknown> — MakerWorld's API adds fields over time, so we
// pass them through verbatim rather than maintaining a brittle mirror.
export interface MakerworldStatus {
  has_cloud_token: boolean;
  can_download: boolean;
}

export interface MakerworldResolvedModel {
  model_id: number;
  profile_id: number | null;
  design: Record<string, unknown>;
  instances: Array<Record<string, unknown>>;
  already_imported_library_ids: number[];
}

export interface MakerworldImportResponse {
  library_file_id: number;
  filename: string;
  folder_id: number | null;
  profile_id: number | null;
  was_existing: boolean;
}

export interface MakerworldRecentImport {
  library_file_id: number;
  filename: string;
  folder_id: number | null;
  thumbnail_path: string | null;
  source_url: string | null;
  created_at: string;
}

export interface SlicerSetting {
  setting_id: string;
  name: string;
  type: string;
  version: string | null;
  user_id: string | null;
  updated_time: string | null;
  is_custom: boolean;
}

export interface SpoolCatalogEntry {
  id: number;
  name: string;
  weight: number;
  is_default: boolean;
}

export interface StorageLocation {
  id: number;
  name: string;
  identifier: string | null;
  spool_count: number;
  created_at: string;
  updated_at: string;
}

export interface ColorCatalogEntry {
  id: number;
  manufacturer: string;
  color_name: string;
  hex_color: string;
  material: string | null;
  is_default: boolean;
  // #1154: optional multi-colour gradient stops + visual effect.
  extra_colors?: string | null;
  effect_type?: string | null;
}

export interface ColorLookupResult {
  found: boolean;
  hex_color: string | null;
  material: string | null;
}

export interface SlicerSettingsResponse {
  filament: SlicerSetting[];
  printer: SlicerSetting[];
  process: SlicerSetting[];
}

export interface SlicerSettingDetail {
  message?: string | null;
  code?: string | null;
  error?: string | null;
  public: boolean;
  version?: string | null;
  type: string;
  name: string;
  update_time?: string | null;
  nickname?: string | null;
  base_id?: string | null;
  setting: Record<string, unknown>;
  filament_id?: string | null;
  setting_id?: string | null;
}

export interface SlicerSettingCreate {
  type: string;  // 'filament', 'print', or 'printer'
  name: string;
  base_id: string;
  setting: Record<string, unknown>;
}

export interface SlicerSettingUpdate {
  name?: string;
  setting?: Record<string, unknown>;
}

export interface SlicerSettingDeleteResponse {
  success: boolean;
  message: string;
}

// Built-in filament fallback (static table from backend)
export interface BuiltinFilament {
  filament_id: string;
  name: string;
}

// Slice request/response — POST /library/files/{id}/slice and /archives/{id}/slice
//
// Two preset shapes are accepted per slot:
//   - Legacy bare integer ids (`*_preset_id`) — pre-cloud-tier clients.
//   - Source-aware refs (`*_preset: PresetRef`) — new SliceModal that picks
//     across cloud / local / standard tiers. Source-aware refs win when both
//     are present in the same payload.
export type PresetSource = 'orca_cloud' | 'cloud' | 'local' | 'standard';

export interface PresetRef {
  source: PresetSource;
  id: string;
}

export interface SliceRequest {
  printer_preset_id?: number;
  process_preset_id?: number;
  filament_preset_id?: number;
  printer_preset?: PresetRef;
  process_preset?: PresetRef;
  filament_preset?: PresetRef;
  // Multi-color: one PresetRef per plate slot, in plate order. Always
  // preferred over the singular `filament_preset` when both are sent; the
  // backend validator promotes a singular into a one-element list when this
  // is omitted, so legacy single-color clients keep working unchanged.
  filament_presets?: PresetRef[];
  plate?: number;
  export_3mf?: boolean;
  // Build-plate override (#1337). When omitted, the slicer uses the process
  // preset's curr_bed_type as-is. Canonical values match BambuStudio /
  // OrcaSlicer's enum: "Cool Plate", "Engineering Plate", "High Temp Plate",
  // "Textured PEI Plate", "Smooth PEI Plate", "Cool Plate (SuperTack)",
  // "Supertack Plate".
  bed_type?: string | null;
  // 3MF only: honour the file's embedded project settings instead of the
  // selected profile triplet.
  use_embedded_settings?: boolean;
}

// GET /api/v1/slicer/presets — unified listing across cloud / local / standard.
export type SlicerCloudStatus = 'ok' | 'not_authenticated' | 'expired' | 'unreachable';

export interface UnifiedPreset {
  id: string;
  name: string;
  source: PresetSource;
  // Populated for the filament slot only — used by the SliceModal multi-color
  // pre-pick to score presets against each plate slot's required (type,
  // colour). Optional because the bundled / standard tier rarely carries a
  // colour (colour is a runtime spool attribute on Bambu) and older API
  // responses pre-date these fields entirely.
  filament_type?: string | null;
  filament_colour?: string | null;
  // Printer-preset names a process / filament preset declares itself
  // compatible with. Populated for the local tier (the slicer's own
  // `compatible_printers`); null for cloud / standard. The SliceModal filters
  // the process / filament dropdowns by the selected printer using this when
  // present (#1325).
  compatible_printers?: string[] | null;
}

export interface UnifiedPresetsBySlot {
  printer: UnifiedPreset[];
  process: UnifiedPreset[];
  filament: UnifiedPreset[];
}

export interface UnifiedPresetsResponse {
  // Priority order: local > orca_cloud > cloud > standard. No cross-tier
  // dedup — every tier surfaces its full list so the user can pick from
  // any source. The order drives auto-pick + visual group rendering only.
  orca_cloud: UnifiedPresetsBySlot;
  cloud: UnifiedPresetsBySlot;
  local: UnifiedPresetsBySlot;
  standard: UnifiedPresetsBySlot;
  cloud_status: SlicerCloudStatus;
  orca_cloud_status: SlicerCloudStatus;
}

// Slicer Pipelines (#1425) — named bundles of preset slots the SliceModal
// can apply in one click. PR A surfaces only the bundle; target_* and
// fanout_strategy round-trip from the backend but the UI doesn't yet expose
// them (they come alive in PR B / PR C).
export interface SlicerPipeline {
  id: number;
  name: string;
  description: string | null;
  printer_preset: PresetRef;
  process_preset: PresetRef;
  filament_presets: PresetRef[];
  bed_type: string | null;
  target_kind: 'specific_printer' | 'printer_class';
  target_printer_id: number | null;
  target_model_class: string | null;
  fanout_strategy: 'max_parallel' | 'fill_one_first' | 'round_robin';
  created_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface SlicerPipelineCreateRequest {
  name: string;
  description?: string | null;
  printer_preset: PresetRef;
  process_preset: PresetRef;
  filament_presets: PresetRef[];
  bed_type?: string | null;
}

export type SlicerPipelineUpdateRequest = Partial<SlicerPipelineCreateRequest> & {
  target_kind?: 'specific_printer' | 'printer_class';
  // ``target_printer_id: 0`` means "clear the target" — the backend maps that
  // to null. Use null in TypeScript for the same intent.
  target_printer_id?: number | null;
  target_model_class?: string | null;
  fanout_strategy?: 'max_parallel' | 'fill_one_first' | 'round_robin';
};

export interface SlicerPipelinesListResponse {
  pipelines: SlicerPipeline[];
}

// Slicer Pipeline runs (#1425 PR B + PR C)
export type PipelineEligibilityKind =
  | 'printer_not_set'
  | 'printer_not_found'
  | 'printer_disabled'
  | 'printer_offline'
  | 'filament_type_mismatch'
  | 'filament_color_mismatch'
  | 'ams_slot_missing'
  | 'filament_unverified'
  | 'no_class_matches'
  | 'class_not_set';

export interface PipelineEligibilityIssue {
  kind: PipelineEligibilityKind;
  slot_index: number | null;
  expected: string | null;
  actual: string | null;
}

export interface PipelinePerPrinterReport {
  printer_id: number;
  printer_name: string;
  ok: boolean;
  issues: PipelineEligibilityIssue[];
}

export interface PipelineEligibilityReport {
  ok: boolean;
  target_kind: 'specific_printer' | 'printer_class';
  target_printer_id: number | null;
  target_printer_name: string | null;
  target_model_class: string | null;
  issues: PipelineEligibilityIssue[];
  printer_reports: PipelinePerPrinterReport[];
}

export interface PipelineJob {
  id: number;
  pipeline_run_id: number;
  copy_index: number;
  assigned_printer_id: number | null;
  assigned_printer_name: string | null;
  queue_entry_id: number | null;
  status:
    | 'pending'
    | 'awaiting_printer'
    | 'queued'
    | 'printing'
    | 'completed'
    | 'failed'
    | 'cancelled';
  error_message: string | null;
  dispatched_at: string | null;
  completed_at: string | null;
}

export interface PipelineRun {
  id: number;
  pipeline_id: number | null;
  pipeline_name: string | null;
  source_library_file_id: number | null;
  source_archive_id: number | null;
  source_filename: string | null;
  parent_run_id: number | null;
  copies: number;
  copies_completed: number;
  copies_failed: number;
  copies_cancelled: number;
  copies_in_progress: number;
  status:
    | 'queued'
    | 'slicing'
    | 'dispatching'
    | 'in_progress'
    | 'completed'
    | 'failed'
    | 'partial_failure'
    | 'cancelled';
  slice_job_id: number | null;
  sliced_library_file_id: number | null;
  eligibility_overridden: boolean;
  error_message: string | null;
  created_by: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  jobs: PipelineJob[];
  target_kind: 'specific_printer' | 'printer_class' | null;
  target_printer_id: number | null;
  target_model_class: string | null;
  fanout_strategy: 'max_parallel' | 'fill_one_first' | 'round_robin' | null;
}

export interface PipelineRunListResponse {
  runs: PipelineRun[];
  total: number;
}

export interface SliceResponse {
  library_file_id: number;
  name: string;
  print_time_seconds: number;
  filament_used_g: number;
  filament_used_mm: number;
  used_embedded_settings: boolean;
}

export interface SliceArchiveResponse {
  archive_id: number;
  name: string;
  print_time_seconds: number;
  filament_used_g: number;
  filament_used_mm: number;
  used_embedded_settings: boolean;
}

// Background slice-job lifecycle. POST /slice returns 202 + this shape;
// the frontend polls /slice-jobs/{id} until status is terminal.
export type SliceJobStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface SliceJobEnqueueResponse {
  job_id: number;
  status: SliceJobStatus;
  status_url: string;
}

export interface SliceJobProgress {
  /** Stage label emitted by the slicer ("Generating G-code", "Slicing finished"). */
  stage: string;
  total_percent: number;
  plate_percent: number;
  /** 1-indexed plate position; 0 means "all plates" / final completion. */
  plate_index: number;
  plate_count: number;
  updated_at: number;
  /** When the backend is in the cross-class slice-all loop (#1493), each
   *  per-plate sub-slice's progress is augmented with the loop position
   *  so the toast can show "Plate 2 of 5 — Generating G-code 47%". The
   *  fields are absent on a single-plate slice. */
  multi_plate_index?: number;
  multi_plate_count?: number;
}

export interface SliceJobState {
  job_id: number;
  status: SliceJobStatus;
  kind: 'library_file' | 'archive';
  source_id: number;
  source_name: string;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  /** Live progress fed by the sidecar's --pipe channel; null until the
   * slicer emits its first frame (early "Initializing" phase) or when
   * the sidecar doesn't support progress. */
  progress: SliceJobProgress | null;
  result?: SliceResponse | SliceArchiveResponse;
  error_status?: number;
  error_detail?: string;
}

// Local preset types (OrcaSlicer imports)
export interface LocalPreset {
  id: number;
  name: string;
  preset_type: string;
  source: string;
  filament_type: string | null;
  filament_vendor: string | null;
  nozzle_temp_min: number | null;
  nozzle_temp_max: number | null;
  pressure_advance: string | null;
  default_filament_colour: string | null;
  filament_cost: string | null;
  filament_density: string | null;
  compatible_printers: string | null;
  inherits: string | null;
  version: string | null;
  created_at: string;
  updated_at: string;
}

export interface LocalPresetDetail extends LocalPreset {
  setting: Record<string, unknown>;
}

export interface LocalPresetsResponse {
  filament: LocalPreset[];
  printer: LocalPreset[];
  process: LocalPreset[];
}

export interface ImportResponse {
  success: boolean;
  imported: number;
  skipped: number;
  errors: string[];
}

export interface FieldOption {
  value: string;
  label: string;
}

export interface FieldDefinition {
  key: string;
  label: string;
  type: 'text' | 'number' | 'boolean' | 'select';
  category: string;
  description?: string;
  options?: FieldOption[];
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
}

export interface FieldDefinitionsResponse {
  version: string;
  description: string;
  fields: FieldDefinition[];
}

export interface CloudDevice {
  dev_id: string;
  name: string;
  dev_model_name: string | null;
  dev_product_name: string | null;
  online: boolean;
}
