// Camera diagnostic result (#1395 follow-up). Returned by
// POST /printers/{id}/camera/diagnose; the frontend modal renders one
// row per stage and looks up the summary code in i18n for the user-
// facing remediation hint.
export interface CameraDiagnoseStage {
  name: 'tcp_reachable' | 'first_frame' | 'live_stream_active';
  status: 'ok' | 'failed' | 'skipped';
  duration_ms: number;
  code: string | null;
}

export interface CameraDiagnoseResult {
  printer_id: number;
  protocol: 'rtsp' | 'chamber_image';
  port: number;
  // 'default' = historical X1/H2 tuning. Anything else = this model has
  // an override entry in backend/app/services/camera_profiles.py.
  profile: string;
  overall_status: 'ok' | 'failed';
  stages: CameraDiagnoseStage[];
  // i18n key under `camera.diagnose.summary.*`.
  summary_code: string;
}

// Technical live-stream details, returned by GET /printers/{id}/camera/stream-info.
// Separate from CameraDiagnoseResult (a one-shot connectivity test) — this
// describes the pipeline currently serving (or that would serve) the feed:
// which technology, codec, resolution, measured rate. All "live" fields are
// null when no stream is currently active.
export interface CameraStreamInfo {
  printer_id: number;
  source: 'built_in_rtsp' | 'built_in_chamber_image' | 'external';
  pipeline: string; // e.g. 'go2rtc', 'chamber_binary', 'external_mjpeg', 'external_rtsp', 'external_snapshot', 'external_usb'
  go2rtc_stream: string | null;
  port: number | null;
  camera_profile: string | null;
  tls_proxy: boolean;
  codec: string | null;
  codec_profile: string | null;
  codec_level: string | null;
  resolution: { width: number; height: number } | null;
  fps_target: number | null;
  fps_measured: number | null;
  bitrate_kbps: number | null;
  stream_uptime_seconds: number | null;
  active: boolean;
}

// Connection diagnostic (GET /printers/{id}/diagnostic and
// POST /printers/diagnostic). Each check's `id` + `status` resolve a
// localized title/fix under `diagnostic.check.*`; `params` interpolate it.
export type DiagnosticStatus = 'pass' | 'fail' | 'warn' | 'skip';

export interface DiagnosticCheck {
  id:
    | 'port_mqtt'
    | 'port_ftps'
    | 'port_rtsps'
    | 'network_mode'
    | 'subnet'
    | 'mqtt_auth'
    | 'developer_mode';
  status: DiagnosticStatus;
  params: Record<string, string | number>;
}

export interface PrinterDiagnosticResult {
  printer_id: number | null;
  ip_address: string;
  overall: 'ok' | 'warnings' | 'problems';
  checks: DiagnosticCheck[];
}

// --- Log-health scan: self-service triage on the System page + bug reporter.
// The backend matches recent logs against a curated known-issue catalog;
// human-readable cause/fix text is rendered from i18n keys keyed by signature_id.
export type LogFindingSeverity = 'error' | 'warning';

export type LogFindingCategory = 'layer8' | 'environment' | 'bug';

export interface LogFinding {
  signature_id: string;
  severity: LogFindingSeverity;
  category: LogFindingCategory;
  wiki_anchor: string;
  count: number;
  first_seen: string;
  last_seen: string;
  sample: string;
}

export interface SystemHealthResult {
  findings: LogFinding[];
  scanned_entries: number;
  log_available: boolean;
  summary: {
    total: number;
    layer8: number;
    environment: number;
    bug: number;
  };
}

// Long-lived camera-stream tokens (#1108). The `token` field is populated
// only on the create response — listing endpoints set it to null because
// the plaintext value is shown to the user exactly once.
export interface LongLivedCameraToken {
  id: number;
  user_id: number;
  name: string;
  scope: LongLivedTokenScope;
  lookup_prefix: string;
  created_at: string;
  expires_at: string;
  last_used_at: string | null;
  token: string | null;
}

export type LongLivedTokenScope = 'camera_stream' | 'camwall' | 'overlay';

export interface CamWallPrinter {
  id: number;
  name: string;
  camera_rotation: number;
  connected: boolean;
  state: string | null;
  progress: number | null;
  remaining_time: number | null;
  layer_num: number | null;
  total_layers: number | null;
  hms_errors: HMSError[];
}

export interface OverlayStatus {
  id: number;
  name: string;
  camera_rotation: number;
  connected: boolean;
  state: string | null;
  current_print: string | null;
  gcode_file: string | null;
  progress: number | null;
  remaining_time: number | null;
  layer_num: number | null;
  total_layers: number | null;
  stg_cur_name: string | null;
  time_format: 'system' | '12h' | '24h';
}

// Printer types
export interface Printer {
  id: number;
  name: string;
  serial_number: string;
  ip_address: string;
  // Optional because the backend only returns access_code when the caller has
  // PRINTERS_UPDATE — Admin / Operator JWTs or auth-disabled mode. Viewers and
  // API keys receive a Printer without this field.
  access_code?: string;
  model: string | null;
  location: string | null;  // Group/location name
  nozzle_count: number;  // 1 or 2, auto-detected from MQTT
  supports_nozzle_flow_type: boolean;
  is_active: boolean;
  auto_archive: boolean;
  external_camera_url: string | null;
  external_camera_type: string | null;  // "mjpeg", "rtsp", "snapshot"
  external_camera_enabled: boolean;
  external_camera_snapshot_url: string | null;  // optional single-frame override (#1177)
  camera_rotation: number;  // 0, 90, 180, 270 degrees
  plate_detection_enabled: boolean;  // Check plate before print
  plate_detection_roi?: PlateDetectionROI;  // ROI for plate detection
  created_at: string;
  updated_at: string;
  acquisition_date: string | null;
  acquisition_value: string | null;
  service_years: string | null;
  annual_hours: string | null;
  maintenance_rate: string | null;
  nominal_power_watts: string | null;
  residual_value: string | null;
  hourly_rate: string | null;
}

export interface HMSError {
  code: string;
  attr: number;  // Attribute value for constructing wiki URL
  module: number;
  severity: number;  // 1=fatal, 2=serious, 3=common, 4=info
  actions?: string[];  // List of user-facing action keys (e.g. "CHECK_FILAMENT")
  job_id?: string;  // Optional job ID for actions that require it (e.g. "CHECK_ASSISTANT")
  // Canonical hex identifier the firmware matches against — 8 chars for
  // print_error-sourced faults, 16 chars for hms[]-array-sourced faults. Send
  // this back as HmsActionBody.print_error so we don't truncate the 64-bit
  // identifier into the silent-rejection short code (#1830).
  full_code?: string;
}

export interface HMSActionBody {
  print_error: string;  // HMS error code (e.g. "05000070")
  action: string;  // "HMS action to execute (e.g. 'resume_after_error')"
  job_id: string | null;  // Optional job ID for context (if applicable)
}

export interface AMSTray {
  id: number;
  tray_color: string | null;
  tray_type: string | null;
  tray_sub_brands: string | null;  // Full name like "PLA Basic", "PETG HF"
  tray_id_name: string | null;  // Bambu filament ID like "A00-Y2" (can decode to color)
  tray_info_idx: string | null;  // Filament preset ID like "GFA00" - maps to cloud setting_id
  remain: number;
  k: number | null;  // Pressure advance value (from tray or K-profile lookup)
  cali_idx: number | null;  // Calibration index for K-profile lookup
  tag_uid: string | null;  // RFID tag UID (any tag)
  tray_uuid: string | null;  // Bambu Lab spool UUID (32-char hex, only valid for Bambu Lab spools)
  nozzle_temp_min: number | null;  // Min nozzle temperature
  nozzle_temp_max: number | null;  // Max nozzle temperature
  drying_temp: number | null;      // RFID-recommended drying temp
  drying_time: number | null;      // RFID-recommended drying time (hours)
  state: number | null;            // AMS tray state: 9=empty, 10=spool present not loaded, 11=loaded
  exists?: boolean | null;         // Physical spool presence from tray_exist_bits, if available
}

export interface AMSUnit {
  id: number;
  humidity: number | null;
  temp: number | null;
  is_ams_ht: boolean;  // True for AMS-HT (single spool), False for regular AMS (4 spools)
  tray: AMSTray[];
  serial_number: string;  // AMS unit serial number (from MQTT sn field)
  sw_ver: string;         // AMS firmware version (from get_version info.module ams/* entry)
  dry_time: number;       // Minutes remaining (0 = not drying, >0 = drying active)
  dry_status: number;     // 0=Off, 1=Checking, 2=Drying, 3=Cooling, 4=Stopping, 5=Error
  dry_sub_status: number; // 0=Off, 1=Heating, 2=Dehumidify
  dry_sf_reason: number[]; // Cannot-dry reasons (1=InsufficientPower, 8=NeedPluginPower)
  dry_target_temp: number | null; // Active-cycle target °C (Bambu does not echo)
  dry_filament: string | null;    // Active-cycle filament name we sent
  module_type: string;    // "ams", "n3f", "n3s"
}

export interface NozzleInfo {
  nozzle_type: string;  // "stainless_steel" or "hardened_steel"
  nozzle_diameter: string;  // e.g., "0.4"
}

export interface NozzleRackSlot {
  id: number;
  nozzle_type: string;
  nozzle_diameter: string;
  wear: number | null;
  stat: number | null;  // Nozzle status (e.g. mounted/docked)
  max_temp: number;
  serial_number: string;
  filament_color: string;  // RGBA hex ("00000000" = no filament)
  filament_id: string;
  filament_type: string;  // Material type (e.g. "PLA", "PETG")
}

export interface PrintOptions {
  // Core AI detectors
  spaghetti_detector: boolean;
  print_halt: boolean;
  halt_print_sensitivity: string;  // "low", "medium", "high" - spaghetti sensitivity
  first_layer_inspector: boolean;
  printing_monitor: boolean;
  buildplate_marker_detector: boolean;
  allow_skip_parts: boolean;
  // Additional AI detectors (decoded from cfg bitmask)
  nozzle_clumping_detector: boolean;
  nozzle_clumping_sensitivity: string;  // "low", "medium", "high"
  pileup_detector: boolean;
  pileup_sensitivity: string;  // "low", "medium", "high"
  airprint_detector: boolean;
  airprint_sensitivity: string;  // "low", "medium", "high"
  auto_recovery_step_loss: boolean;
  filament_tangle_detect: boolean;
}

export interface FilaSwitchState {
  installed: boolean;
  // in[track] = currently loaded slot for that track (-1 = empty)
  in_slots: number[];
  // out[track] = extruder this track terminates at (0 = right, 1 = left)
  out_extruders: number[];
  stat: number;
  info: number;
}

export interface PrinterStatus {
  id: number;
  name: string;
  connected: boolean;
  state: string | null;
  current_print: string | null;
  subtask_name: string | null;
  current_archive_id: number | null;
  current_plate_id: number | null;
  gcode_file: string | null;
  progress: number | null;
  remaining_time: number | null;
  layer_num: number | null;
  total_layers: number | null;
  temperatures: {
    bed?: number;
    bed_target?: number;
    bed_heating?: boolean;  // Actual heater state from MQTT
    nozzle?: number;
    nozzle_target?: number;
    nozzle_heating?: boolean;  // Actual heater state from MQTT
    nozzle_2?: number;  // Second nozzle for H2 series (dual nozzle)
    nozzle_2_target?: number;
    nozzle_2_heating?: boolean;  // Actual heater state from MQTT
    chamber?: number;
    chamber_target?: number;
    chamber_heating?: boolean;  // Actual heater state from MQTT
  } | null;
  cover_url: string | null;
  hms_errors: HMSError[];
  ams: AMSUnit[];
  ams_exists: boolean;
  vt_tray: AMSTray[];  // Virtual tray / external spool(s)
  store_to_sdcard: boolean;  // Store sent files on SD card
  timelapse: boolean;  // Timelapse recording active
  ipcam: boolean;  // Live view enabled
  wifi_signal: number | null;  // WiFi signal strength in dBm
  wired_network: boolean;  // Ethernet connection detected
  door_open: boolean;  // Enclosure door open (models with a door sensor: X1/X1C/X1E/X2D/P2S/H2*)
  nozzles: NozzleInfo[];  // Nozzle hardware info (index 0=left/primary, 1=right)
  nozzle_rack: NozzleRackSlot[];  // H2C 6-nozzle tool-changer rack
  print_options: PrintOptions | null;  // AI detection and print options
  // Calibration stage tracking
  stg_cur: number;  // Current stage number (-1 = not calibrating)
  stg_cur_name: string | null;  // Human-readable current stage name
  stg: number[];  // List of stage numbers in calibration sequence
  // Air conditioning mode (0=cooling, 1=heating)
  airduct_mode: number;
  // Print speed level (1=silent, 2=standard, 3=sport, 4=ludicrous)
  speed_level: number;
  // Chamber light on/off
  chamber_light: boolean;
  // Active extruder for dual nozzle (0=right, 1=left)
  active_extruder: number;
  // AMS mapping - which AMS is connected to which nozzle
  // Format: [ams_id_for_nozzle0, ams_id_for_nozzle1, ...] where -1 means no AMS
  ams_mapping: number[];
  // Per-AMS extruder mapping - extracted from each AMS unit's info field
  // Format: {ams_id: extruder_id} where extruder 0=right, 1=left
  // Note: JSON keys are always strings
  ams_extruder_map: Record<string, number>;
  // Filament Track Switch accessory — null when not installed. When present,
  // AMS slots aren't tied to a specific extruder; the FTS routes any slot to
  // either extruder, so per-extruder slot filtering must be skipped.
  fila_switch: FilaSwitchState | null;
  // Currently loaded tray (global tray ID, 255 = no filament loaded, 254 = external spool)
  tray_now: number;
  expected_tray: number | null;
  previous_tray: number | null;
  // AMS status for filament change tracking (0=idle, 1=filament_change, 2=rfid_identifying, 3=assist, 4=calibration)
  ams_status_main: number;
  // AMS sub-status for filament change step (when main=1): 4=retraction, 6=load verification, 7=purge
  ams_status_sub: number;
  // mc_print_sub_stage - filament change step indicator used by OrcaSlicer/BambuStudio
  mc_print_sub_stage: number;
  // Timestamp of last AMS data update (for RFID refresh detection)
  last_ams_update: number;
  // Number of printable objects in current print (for skip objects feature)
  printable_objects_count: number;
  // Fan speeds (0-100 percentage, null if not available for this model)
  cooling_fan_speed: number | null;  // Part cooling fan
  big_fan1_speed: number | null;     // Auxiliary fan
  big_fan2_speed: number | null;     // Chamber/exhaust fan
  heatbreak_fan_speed: number | null; // Hotend heatbreak fan
  firmware_version: string | null;   // Firmware version from MQTT
  // Developer LAN mode: true = enabled, false = disabled, null = unknown
  developer_mode: boolean | null;
  control_connection?: {
    local_status_available: boolean;
    local_control_available: boolean;
    developer_lan: boolean | null;
    cloud_configured: boolean;
    cloud_device_id: string | null;
    active_control_path: 'local' | 'cloud' | 'none';
  } | null;
  // AMS Filament Backup ("auto-switch" to a backup spool when one runs out).
  // true = ON, false = OFF, null = unknown / unsupported (A1 family).
  ams_filament_backup: boolean | null;
  // Queue: printer is awaiting user ack that the build plate was cleared after a
  // finished/failed print. Persisted across restarts (#961).
  awaiting_plate_clear: boolean;
  // AMS drying support
  supports_drying: boolean;
  drying_screen_only?: boolean;
  // Active chamber heater (responds to M141). True only for H2C/H2D/H2DPro/H2S/X2D.
  supports_chamber_heater?: boolean;
}

export interface PrinterCreate {
  name: string;
  serial_number: string;
  ip_address: string;
  access_code: string;
  model?: string;
  location?: string;
  auto_archive?: boolean;
  // Maintenance Mode flag (#1476). Backend already gates MQTT, queue dispatch,
  // scheduler, metrics and the print picker on this; toggling via PATCH
  // /printers/{id} disconnects or reconnects MQTT accordingly.
  is_active?: boolean;
  external_camera_url?: string | null;
  external_camera_type?: string | null;
  external_camera_enabled?: boolean;
  external_camera_snapshot_url?: string | null;
  camera_rotation?: number;
  plate_detection_enabled?: boolean;
  plate_detection_roi?: PlateDetectionROI;
  acquisition_date?: string | null;
  acquisition_value?: string | null;
  service_years?: string | null;
  annual_hours?: string | null;
  maintenance_rate?: string | null;
  nominal_power_watts?: string | null;
}

export interface Equipment {
  id: number;
  equipment_type: 'dryer';
  name: string;
  is_active: boolean;
  acquisition_date: string;
  acquisition_value: string;
  service_years: string;
  annual_hours: string;
  maintenance_rate: string;
  nominal_power_watts: string;
  residual_value: string;
  hourly_rate: string;
  created_at: string;
  updated_at: string;
}

export type EquipmentInput = Omit<Equipment, 'id' | 'residual_value' | 'hourly_rate' | 'created_at' | 'updated_at'>;

// Plate Detection
export interface PlateDetectionROI {
  x: number;  // X start % (0.0-1.0)
  y: number;  // Y start % (0.0-1.0)
  w: number;  // Width % (0.0-1.0)
  h: number;  // Height % (0.0-1.0)
}

export interface PlateDetectionResult {
  is_empty: boolean;
  confidence: number;
  difference_percent: number;
  message: string;
  has_debug_image: boolean;
  debug_image_url?: string;
  needs_calibration: boolean;
  light_warning?: boolean;
  reference_count?: number;
  max_references?: number;
  roi?: PlateDetectionROI;
}

export interface PlateDetectionStatus {
  available: boolean;
  calibrated: boolean;
  reference_count: number;
  max_references: number;
  message: string;
}

export interface CalibrationResult {
  success: boolean;
  message: string;
}

export interface PlateReference {
  index: number;
  label: string;
  timestamp: string;
  has_image: boolean;
  thumbnail_url: string;
}
