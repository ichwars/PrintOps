// Smart Plug types
export interface SmartPlug {
  id: number;
  name: string;
  plug_type: 'tasmota' | 'homeassistant' | 'mqtt' | 'rest';
  ip_address: string | null;  // Required for Tasmota
  ha_entity_id: string | null;  // Required for Home Assistant (e.g., "switch.printer_plug", "script.turn_on_printer")
  // Home Assistant energy sensor entities (optional)
  ha_power_entity: string | null;
  ha_energy_today_entity: string | null;
  ha_energy_total_entity: string | null;
  // MQTT fields (required when plug_type="mqtt")
  // Legacy field - kept for backward compatibility
  mqtt_topic: string | null;  // Deprecated, use mqtt_power_topic
  mqtt_multiplier: number;  // Deprecated, use mqtt_power_multiplier
  // Power monitoring
  mqtt_power_topic: string | null;  // Topic for power data
  mqtt_power_path: string | null;  // e.g., "power_l1" or "data.power"
  mqtt_power_multiplier: number;  // Unit conversion for power
  // Energy monitoring
  mqtt_energy_topic: string | null;  // Topic for energy data
  mqtt_energy_path: string | null;  // e.g., "energy_l1"
  mqtt_energy_multiplier: number;  // Unit conversion for energy
  // State monitoring
  mqtt_state_topic: string | null;  // Topic for state data
  mqtt_state_path: string | null;  // e.g., "state_l1" for ON/OFF
  mqtt_state_on_value: string | null;  // What value means "ON" (e.g., "ON", "true", "1")
  // REST/Webhook fields (required when plug_type="rest")
  rest_on_url: string | null;
  rest_on_body: string | null;
  rest_off_url: string | null;
  rest_off_body: string | null;
  rest_method: string | null;
  rest_headers: string | null;
  rest_status_url: string | null;
  rest_status_path: string | null;
  rest_status_on_value: string | null;
  rest_power_url: string | null;
  rest_power_path: string | null;
  rest_power_multiplier: number;
  rest_energy_url: string | null;
  rest_energy_path: string | null;
  rest_energy_multiplier: number;
  rest_energy_total_path: string | null;
  rest_energy_total_multiplier: number;
  printer_id: number | null;
  equipment_id: number | null;
  controls_printer_power: boolean;
  enabled: boolean;
  auto_on: boolean;
  auto_off: boolean;
  auto_off_persistent: boolean;
  off_delay_mode: 'time' | 'temperature';
  off_delay_minutes: number;
  off_temp_threshold: number;
  // #1349: auto-off after AMS drying completes.
  auto_off_after_drying: boolean;
  off_delay_after_drying_minutes: number;
  username: string | null;
  password: string | null;
  // Power alerts
  power_alert_enabled: boolean;
  power_alert_high: number | null;
  power_alert_low: number | null;
  power_alert_last_triggered: string | null;
  // Schedule
  schedule_enabled: boolean;
  schedule_on_time: string | null;
  schedule_off_time: string | null;
  // Visibility options
  show_in_switchbar: boolean;
  show_on_printer_card: boolean;  // For scripts: show on printer card
  // Status
  last_state: string | null;
  last_checked: string | null;
  auto_off_executed: boolean;  // True when auto-off was triggered after print
  created_at: string;
  updated_at: string;
}

export interface SmartPlugCreate {
  name: string;
  plug_type?: 'tasmota' | 'homeassistant' | 'mqtt' | 'rest';
  ip_address?: string | null;  // Required for Tasmota
  ha_entity_id?: string | null;  // Required for Home Assistant
  // Home Assistant energy sensor entities (optional)
  ha_power_entity?: string | null;
  ha_energy_today_entity?: string | null;
  ha_energy_total_entity?: string | null;
  // MQTT fields (required when plug_type="mqtt")
  // Legacy fields - kept for backward compatibility
  mqtt_topic?: string | null;
  mqtt_multiplier?: number;
  // Power monitoring
  mqtt_power_topic?: string | null;
  mqtt_power_path?: string | null;
  mqtt_power_multiplier?: number;
  // Energy monitoring
  mqtt_energy_topic?: string | null;
  mqtt_energy_path?: string | null;
  mqtt_energy_multiplier?: number;
  // State monitoring
  mqtt_state_topic?: string | null;
  mqtt_state_path?: string | null;
  mqtt_state_on_value?: string | null;
  // REST fields
  rest_on_url?: string | null;
  rest_on_body?: string | null;
  rest_off_url?: string | null;
  rest_off_body?: string | null;
  rest_method?: string | null;
  rest_headers?: string | null;
  rest_status_url?: string | null;
  rest_status_path?: string | null;
  rest_status_on_value?: string | null;
  rest_power_url?: string | null;
  rest_power_path?: string | null;
  rest_power_multiplier?: number;
  rest_energy_url?: string | null;
  rest_energy_path?: string | null;
  rest_energy_multiplier?: number;
  rest_energy_total_path?: string | null;
  rest_energy_total_multiplier?: number;
  printer_id?: number | null;
  equipment_id?: number | null;
  controls_printer_power?: boolean;
  enabled?: boolean;
  auto_on?: boolean;
  auto_off?: boolean;
  auto_off_persistent?: boolean;
  off_delay_mode?: 'time' | 'temperature';
  off_delay_minutes?: number;
  off_temp_threshold?: number;
  // #1349
  auto_off_after_drying?: boolean;
  off_delay_after_drying_minutes?: number;
  username?: string | null;
  password?: string | null;
  // Power alerts
  power_alert_enabled?: boolean;
  power_alert_high?: number | null;
  power_alert_low?: number | null;
  // Schedule
  schedule_enabled?: boolean;
  schedule_on_time?: string | null;
  schedule_off_time?: string | null;
  // Visibility options
  show_in_switchbar?: boolean;
  show_on_printer_card?: boolean;
}

export interface SmartPlugUpdate {
  name?: string;
  plug_type?: 'tasmota' | 'homeassistant' | 'mqtt' | 'rest';
  ip_address?: string | null;
  ha_entity_id?: string | null;
  // Home Assistant energy sensor entities (optional)
  ha_power_entity?: string | null;
  ha_energy_today_entity?: string | null;
  ha_energy_total_entity?: string | null;
  // MQTT fields (legacy)
  mqtt_topic?: string | null;
  mqtt_multiplier?: number;
  // MQTT power fields
  mqtt_power_topic?: string | null;
  mqtt_power_path?: string | null;
  mqtt_power_multiplier?: number;
  // MQTT energy fields
  mqtt_energy_topic?: string | null;
  mqtt_energy_path?: string | null;
  mqtt_energy_multiplier?: number;
  // MQTT state fields
  mqtt_state_topic?: string | null;
  mqtt_state_path?: string | null;
  mqtt_state_on_value?: string | null;
  // REST fields
  rest_on_url?: string | null;
  rest_on_body?: string | null;
  rest_off_url?: string | null;
  rest_off_body?: string | null;
  rest_method?: string | null;
  rest_headers?: string | null;
  rest_status_url?: string | null;
  rest_status_path?: string | null;
  rest_status_on_value?: string | null;
  rest_power_url?: string | null;
  rest_power_path?: string | null;
  rest_power_multiplier?: number;
  rest_energy_url?: string | null;
  rest_energy_path?: string | null;
  rest_energy_multiplier?: number;
  rest_energy_total_path?: string | null;
  rest_energy_total_multiplier?: number;
  printer_id?: number | null;
  equipment_id?: number | null;
  controls_printer_power?: boolean;
  enabled?: boolean;
  auto_on?: boolean;
  auto_off?: boolean;
  auto_off_persistent?: boolean;
  off_delay_mode?: 'time' | 'temperature';
  off_delay_minutes?: number;
  off_temp_threshold?: number;
  // #1349
  auto_off_after_drying?: boolean;
  off_delay_after_drying_minutes?: number;
  username?: string | null;
  password?: string | null;
  // Power alerts
  power_alert_enabled?: boolean;
  power_alert_high?: number | null;
  power_alert_low?: number | null;
  // Schedule
  schedule_enabled?: boolean;
  schedule_on_time?: string | null;
  schedule_off_time?: string | null;
  // Visibility options
  show_in_switchbar?: boolean;
  show_on_printer_card?: boolean;
}

// Home Assistant entity for smart plug selection
export interface HAEntity {
  entity_id: string;
  friendly_name: string;
  state: string | null;
  domain: string;  // "switch", "light", "input_boolean", "script"
}

// Home Assistant sensor entity for energy monitoring
export interface HASensorEntity {
  entity_id: string;
  friendly_name: string;
  state: string | null;
  unit_of_measurement: string | null;  // "W", "kW", "kWh", "Wh"
}

export interface HATestConnectionResult {
  success: boolean;
  message: string | null;
  error: string | null;
}

export interface SmartPlugEnergy {
  power: number | null;  // Current watts
  voltage: number | null;  // Volts
  current: number | null;  // Amps
  today: number | null;  // kWh used today
  yesterday: number | null;  // kWh used yesterday
  total: number | null;  // Total kWh
  factor: number | null;  // Power factor (0-1)
  apparent_power: number | null;  // VA
  reactive_power: number | null;  // VAr
}

export interface SmartPlugStatus {
  state: string | null;
  reachable: boolean;
  device_name: string | null;
  energy: SmartPlugEnergy | null;
}

export interface SmartPlugTestResult {
  success: boolean;
  state: string | null;
  device_name: string | null;
}

// Tasmota Discovery types
export interface TasmotaScanStatus {
  running: boolean;
  scanned: number;
  total: number;
}

export interface DiscoveredTasmotaDevice {
  ip_address: string;
  name: string;
  module: number | null;
  state: string | null;
  discovered_at: string | null;
}

// Print Queue types
export interface PrintQueueItem {
  id: number;
  printer_id: number | null;  // null = unassigned
  target_model: string | null;  // Target printer model for model-based assignment
  target_location: string | null;  // Target location filter for model-based assignment
  required_filament_types: string[] | null;  // Required filament types for model-based assignment
  waiting_reason: string | null;  // Why a model-based job hasn't started yet
  // Either archive_id OR library_file_id must be set (archive created at print start)
  archive_id: number | null;
  library_file_id: number | null;
  position: number;
  scheduled_time: string | null;
  require_previous_success: boolean;
  auto_off_after: boolean;
  manual_start: boolean;  // Requires manual trigger to start (staged)
  // Set by the dispatch scheduler when the assigned spool can't satisfy
  // any required slot's grams (#1496). Surfaced on the queue row as a
  // "filament short" badge; cleared on a successful ▶ click (live recheck).
  filament_short: boolean;
  // Persistent "Print Anyway" acknowledgement — once true the scheduler
  // skips the deficit check for this item (#1698-followup). Set by the
  // start route when skip_filament_check=true, or at queue creation if
  // PrintModal's deficit warning was acknowledged.
  skip_filament_check: boolean;
  ams_mapping: number[] | null;  // AMS slot mapping for multi-color prints
  filament_overrides: Array<{ slot_id: number; type: string; color: string; color_name?: string; tray_info_idx?: string; force_color_match?: boolean }> | null;  // Filament overrides for model-based assignment
  plate_id: number | null;  // Plate ID for multi-plate 3MF files
  // Print options
  bed_levelling: boolean;
  flow_cali: boolean;
  vibration_cali: boolean;
  layer_inspect: boolean;
  timelapse: boolean;
  use_ams: boolean;
  nozzle_offset_cali: boolean;
  preheat_override: 'inherit' | 'on' | 'off';
  preheat_chamber_target_override: number | null;
  status: 'pending' | 'printing' | 'completed' | 'failed' | 'skipped' | 'cancelled';
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  created_at: string;
  archive_name?: string | null;
  archive_thumbnail?: string | null;
  // True when the linked archive has been soft-deleted; archive_name /
  // archive_thumbnail / downstream metadata are left null in that case so
  // the UI doesn't 404-storm the now-missing endpoints (#1348 follow-up).
  archive_deleted?: boolean;
  library_file_name?: string | null;
  library_file_thumbnail?: string | null;
  printer_name?: string | null;
  print_time_seconds?: number | null;  // Estimated print time from archive or library file
  filament_used_grams?: number | null;  // Estimated print weight from archive or library file
  filament_type?: string | null;  // e.g. "PLA", "PETG"
  filament_color?: string | null;  // Hex RGBA from the slicer
  bed_type?: string | null;  // Build plate type for this print (per-plate accurate, #1281)
  // User tracking (Issue #206)
  created_by_id?: number | null;
  created_by_username?: string | null;
  // Batch grouping
  batch_id?: number | null;
  batch_name?: string | null;
  // Shortest-job-first scheduling
  been_jumped?: boolean;
  // Auto-print G-code injection
  gcode_injection?: boolean;
  cleanup_library_after_dispatch?: boolean;
}

export interface PrintBatch {
  id: number;
  name: string;
  archive_id: number | null;
  library_file_id: number | null;
  quantity: number;
  status: string;
  created_at: string;
  created_by_id: number | null;
  created_by_username: string | null;
  pending_count: number;
  printing_count: number;
  completed_count: number;
  failed_count: number;
  cancelled_count: number;
}

export interface PrintQueueItemCreate {
  printer_id?: number | null;  // null = unassigned
  target_model?: string | null;  // Target printer model (mutually exclusive with printer_id)
  target_location?: string | null;  // Target location filter (only used with target_model)
  filament_overrides?: Array<{ slot_id: number; type: string; color: string; color_name?: string; force_color_match?: boolean }> | null;
  archive_id?: number | null;
  library_file_id?: number | null;
  scheduled_time?: string | null;
  require_previous_success?: boolean;
  auto_off_after?: boolean;
  manual_start?: boolean;  // Requires manual trigger to start (staged)
  insert_at_top?: boolean;  // Insert ahead of other pending items in the same queue scope
  insert_position?: number | null;  // 1-indexed insertion position for priority queueing
  // PrintModal "Print Anyway" on the deficit warning — persisted so the
  // scheduler doesn't immediately re-flag this item (#1698-followup).
  skip_filament_check?: boolean;
  ams_mapping?: number[] | null;  // AMS slot mapping for multi-color prints
  plate_id?: number | null;  // Plate ID for multi-plate 3MF files
  // Print options
  bed_levelling?: boolean;
  flow_cali?: boolean;
  vibration_cali?: boolean;
  layer_inspect?: boolean;
  timelapse?: boolean;
  use_ams?: boolean;
  nozzle_offset_cali?: boolean;
  preheat_override?: 'inherit' | 'on' | 'off';
  preheat_chamber_target_override?: number | null;
  // Auto-print G-code injection
  gcode_injection?: boolean;
  // Batch: create multiple copies (creates a batch if > 1)
  quantity?: number;
  // Existing batch to add this item into (multi-plate auto-batch flow).
  batch_id?: number | null;
  // Project to associate the resulting archive with
  project_id?: number;
  // Delete transient uploaded library file after scheduler creates the archive
  cleanup_library_after_dispatch?: boolean;
}

export interface PrintBatchCreate {
  name: string;
  archive_id?: number | null;
  library_file_id?: number | null;
  /** When set, the listed pending items are assigned to the new batch
   *  (manual "Group as batch"). When omitted/empty, an empty batch is
   *  returned so the client can pass batch_id on subsequent addToQueue calls. */
  item_ids?: number[];
}

export interface PrintQueueItemUpdate {
  printer_id?: number | null;  // null = unassign
  target_model?: string | null;  // Target printer model (mutually exclusive with printer_id)
  target_location?: string | null;  // Target location filter (only used with target_model)
  filament_overrides?: Array<{ slot_id: number; type: string; color: string; color_name?: string; force_color_match?: boolean }> | null;
  position?: number;
  scheduled_time?: string | null;
  require_previous_success?: boolean;
  auto_off_after?: boolean;
  manual_start?: boolean;
  ams_mapping?: number[];
  plate_id?: number | null;  // Plate ID for multi-plate 3MF files
  // Print options
  bed_levelling?: boolean;
  flow_cali?: boolean;
  vibration_cali?: boolean;
  layer_inspect?: boolean;
  timelapse?: boolean;
  use_ams?: boolean;
  nozzle_offset_cali?: boolean;
  preheat_override?: 'inherit' | 'on' | 'off';
  preheat_chamber_target_override?: number | null;
  // Auto-print G-code injection
  gcode_injection?: boolean;
}

export interface PrintQueueBulkUpdate {
  item_ids: number[];
  printer_id?: number | null;
  scheduled_time?: string | null;
  require_previous_success?: boolean;
  auto_off_after?: boolean;
  manual_start?: boolean;
  // Print options
  bed_levelling?: boolean;
  flow_cali?: boolean;
  vibration_cali?: boolean;
  layer_inspect?: boolean;
  timelapse?: boolean;
  use_ams?: boolean;
  nozzle_offset_cali?: boolean;
  preheat_override?: 'inherit' | 'on' | 'off';
  preheat_chamber_target_override?: number | null;
  // Auto-print G-code injection
  gcode_injection?: boolean;
}

export interface PrintQueueBulkUpdateResponse {
  updated_count: number;
  skipped_count: number;
  message: string;
}

// MQTT Logging types
export interface MQTTLogEntry {
  timestamp: string;
  topic: string;
  direction: 'in' | 'out';
  payload: Record<string, unknown>;
}

export interface MQTTLogsResponse {
  logging_enabled: boolean;
  logs: MQTTLogEntry[];
}

// K-Profile types
export interface KProfile {
  slot_id: number;
  extruder_id: number;
  nozzle_id: string;
  nozzle_diameter: string;
  filament_id: string;
  name: string;
  k_value: string;
  n_coef: string;
  ams_id: number;
  tray_id: number;
  setting_id: string | null;
}

export interface KProfileCreate {
  slot_id?: number;  // Storage slot, 0 for new profiles
  extruder_id?: number;
  nozzle_id: string;
  nozzle_diameter: string;
  filament_id: string;
  name: string;
  k_value: string;
  n_coef?: string;
  ams_id?: number;
  tray_id?: number;
  setting_id?: string | null;
}

export interface KProfileDelete {
  slot_id: number;  // cali_idx - calibration index to delete
  extruder_id: number;
  nozzle_id: string;  // e.g., "HH00-0.4"
  nozzle_diameter: string;  // e.g., "0.4"
  filament_id: string;  // Bambu filament identifier
  setting_id?: string | null;  // Setting ID (for X1C series)
}

export interface KProfilesResponse {
  profiles: KProfile[];
  nozzle_diameter: string;
}

export interface KProfileNote {
  setting_id: string;
  note: string;
}

export interface KProfileNotesResponse {
  notes: Record<string, string>;  // setting_id -> note
}

// Slot Preset Mapping
export interface SlotPresetMapping {
  ams_id: number;
  tray_id: number;
  preset_id: string;
  preset_name: string;
}

// Filament types
export interface Filament {
  id: number;
  name: string;
  type: string;  // PLA, PETG, ABS, etc.
  brand: string | null;
  color: string | null;
  color_hex: string | null;
  cost_per_kg: number;
  spool_weight_g: number;
  currency: string;
  density: number | null;
  print_temp_min: number | null;
  print_temp_max: number | null;
  bed_temp_min: number | null;
  bed_temp_max: number | null;
  created_at: string;
  updated_at: string;
}
