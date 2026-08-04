// Notification Provider types
export type ProviderType = 'callmebot' | 'ntfy' | 'pushover' | 'telegram' | 'bark' | 'email' | 'discord' | 'webhook' | 'homeassistant';

export interface NotificationProvider {
  id: number;
  name: string;
  provider_type: ProviderType;
  enabled: boolean;
  config: Record<string, unknown>;
  // Print lifecycle events
  on_print_start: boolean;
  on_print_complete: boolean;
  on_print_failed: boolean;
  on_print_stopped: boolean;
  on_print_progress: boolean;
  on_print_missing_spool_assignment: boolean;
  // Printer status events
  on_printer_offline: boolean;
  on_printer_error: boolean;
  on_ai_failure_detection: boolean;
  on_filament_low: boolean;
  on_maintenance_due: boolean;
  // AMS environmental alarms (regular AMS)
  on_ams_humidity_high: boolean;
  on_ams_temperature_high: boolean;
  // AMS-HT environmental alarms
  on_ams_ht_humidity_high: boolean;
  on_ams_ht_temperature_high: boolean;
  // Build plate detection
  on_plate_not_empty: boolean;
  // Bed cooled
  on_bed_cooled: boolean;
  // First layer complete
  on_first_layer_complete: boolean;
  // Inventory stock alerts
  on_stock_reorder_alert: boolean;
  on_stock_break_alert: boolean;
  // Print queue events
  on_queue_job_added: boolean;
  on_queue_job_assigned: boolean;
  on_queue_job_started: boolean;
  on_queue_job_waiting: boolean;
  on_queue_job_skipped: boolean;
  on_queue_job_failed: boolean;
  on_queue_completed: boolean;
  // Quiet hours
  quiet_hours_enabled: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  // Daily digest
  daily_digest_enabled: boolean;
  daily_digest_time: string | null;
  // Printer filter
  printer_id: number | null;
  // Status tracking
  last_success: string | null;
  last_error: string | null;
  last_error_at: string | null;
  // Timestamps
  created_at: string;
  updated_at: string;
}

export interface NotificationProviderCreate {
  name: string;
  provider_type: ProviderType;
  enabled?: boolean;
  config: Record<string, unknown>;
  // Print lifecycle events
  on_print_start?: boolean;
  on_print_complete?: boolean;
  on_print_failed?: boolean;
  on_print_stopped?: boolean;
  on_print_progress?: boolean;
  on_print_missing_spool_assignment?: boolean;
  // Printer status events
  on_printer_offline?: boolean;
  on_printer_error?: boolean;
  on_ai_failure_detection?: boolean;
  on_filament_low?: boolean;
  on_maintenance_due?: boolean;
  // AMS environmental alarms (regular AMS)
  on_ams_humidity_high?: boolean;
  on_ams_temperature_high?: boolean;
  // AMS-HT environmental alarms
  on_ams_ht_humidity_high?: boolean;
  on_ams_ht_temperature_high?: boolean;
  // Build plate detection
  on_plate_not_empty?: boolean;
  // Bed cooled
  on_bed_cooled?: boolean;
  // First layer complete
  on_first_layer_complete?: boolean;
  // Inventory stock alerts
  on_stock_reorder_alert?: boolean;
  on_stock_break_alert?: boolean;
  // Print queue events
  on_queue_job_added?: boolean;
  on_queue_job_assigned?: boolean;
  on_queue_job_started?: boolean;
  on_queue_job_waiting?: boolean;
  on_queue_job_skipped?: boolean;
  on_queue_job_failed?: boolean;
  on_queue_completed?: boolean;
  // Quiet hours
  quiet_hours_enabled?: boolean;
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
  // Daily digest
  daily_digest_enabled?: boolean;
  daily_digest_time?: string | null;
  // Printer filter
  printer_id?: number | null;
}

export interface NotificationProviderUpdate {
  name?: string;
  provider_type?: ProviderType;
  enabled?: boolean;
  config?: Record<string, unknown>;
  // Print lifecycle events
  on_print_start?: boolean;
  on_print_complete?: boolean;
  on_print_failed?: boolean;
  on_print_stopped?: boolean;
  on_print_progress?: boolean;
  on_print_missing_spool_assignment?: boolean;
  // Printer status events
  on_printer_offline?: boolean;
  on_printer_error?: boolean;
  on_ai_failure_detection?: boolean;
  on_filament_low?: boolean;
  on_maintenance_due?: boolean;
  // AMS environmental alarms (regular AMS)
  on_ams_humidity_high?: boolean;
  on_ams_temperature_high?: boolean;
  // AMS-HT environmental alarms
  on_ams_ht_humidity_high?: boolean;
  on_ams_ht_temperature_high?: boolean;
  // Build plate detection
  on_plate_not_empty?: boolean;
  // Bed cooled
  on_bed_cooled?: boolean;
  // First layer complete
  on_first_layer_complete?: boolean;
  // Inventory stock alerts
  on_stock_reorder_alert?: boolean;
  on_stock_break_alert?: boolean;
  // Print queue events
  on_queue_job_added?: boolean;
  on_queue_job_assigned?: boolean;
  on_queue_job_started?: boolean;
  on_queue_job_waiting?: boolean;
  on_queue_job_skipped?: boolean;
  on_queue_job_failed?: boolean;
  on_queue_completed?: boolean;
  // Quiet hours
  quiet_hours_enabled?: boolean;
  quiet_hours_start?: string | null;
  quiet_hours_end?: string | null;
  // Daily digest
  daily_digest_enabled?: boolean;
  daily_digest_time?: string | null;
  // Printer filter
  printer_id?: number | null;
}

// GitHub Backup types
export type ScheduleType = 'hourly' | 'daily' | 'weekly';

export type GitProviderType = 'github' | 'gitea' | 'forgejo' | 'gitlab';

export interface GitHubBackupConfig {
  id: number;
  repository_url: string;
  has_token: boolean;
  branch: string;
  provider: GitProviderType;
  allow_insecure_http: boolean;
  schedule_enabled: boolean;
  schedule_type: ScheduleType;
  backup_kprofiles: boolean;
  backup_cloud_profiles: boolean;
  backup_settings: boolean;
  backup_spools: boolean;
  backup_archives: boolean;
  enabled: boolean;
  last_backup_at: string | null;
  last_backup_status: string | null;
  last_backup_message: string | null;
  last_backup_commit_sha: string | null;
  next_scheduled_run: string | null;
  created_at: string;
  updated_at: string;
}

export interface GitHubBackupConfigCreate {
  repository_url: string;
  access_token: string;
  branch?: string;
  provider?: GitProviderType;
  allow_insecure_http?: boolean;
  schedule_enabled?: boolean;
  schedule_type?: ScheduleType;
  backup_kprofiles?: boolean;
  backup_cloud_profiles?: boolean;
  backup_settings?: boolean;
  backup_spools?: boolean;
  backup_archives?: boolean;
  enabled?: boolean;
}

export interface GitHubBackupLog {
  id: number;
  config_id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  trigger: string;
  commit_sha: string | null;
  files_changed: number;
  error_message: string | null;
}

export interface GitHubBackupStatus {
  configured: boolean;
  enabled: boolean;
  is_running: boolean;
  progress: string | null;
  last_backup_at: string | null;
  last_backup_status: string | null;
  next_scheduled_run: string | null;
}

export interface CloudAccountCounts {
  bambu: number;
  orca: number;
}

export interface LocalBackupStatus {
  enabled: boolean;
  schedule: string;
  time: string;
  retention: number;
  path: string;
  default_path: string;
  is_running: boolean;
  last_backup_at: string | null;
  last_status: string | null;
  last_message: string | null;
  next_run: string | null;
  timezone: string;
}

export interface LocalBackupFile {
  filename: string;
  size: number;
  created_at: string;
}

export interface ObicoDetectionEvent {
  printer_id: number;
  task_name: string;
  timestamp: string;
  current_p: number;
  score: number;
  class: 'safe' | 'warning' | 'failure';
  detections: number;
}

export interface ObicoStatus {
  is_running: boolean;
  last_error: string | null;
  per_printer: Record<string, { class: string; frame_count: number; score: number }>;
  thresholds: { low: number; high: number };
  history: ObicoDetectionEvent[];
  enabled: boolean;
  ml_url: string;
  sensitivity: 'low' | 'medium' | 'high';
  action: 'notify' | 'pause' | 'pause_and_off';
  poll_interval: number;
  external_url_configured: boolean;
}

export interface ObicoTestConnection {
  ok: boolean;
  status_code: number | null;
  body: string | null;
  error: string | null;
  auth_ok?: boolean | null;
}

export interface GitHubTestConnectionResponse {
  success: boolean;
  message: string;
  repo_name: string | null;
  permissions: Record<string, boolean> | null;
  // true = confirmed private, false = confirmed public/internal,
  // null = could not determine. Backend rejects save unless true.
  is_private: boolean | null;
}

export interface GitHubBackupTriggerResponse {
  success: boolean;
  message: string;
  log_id: number | null;
  commit_sha: string | null;
  files_changed: number;
}

export interface NotificationTestRequest {
  provider_type: ProviderType;
  config: Record<string, unknown>;
}

export interface NotificationTestResponse {
  success: boolean;
  message: string;
}

// Provider-specific config types for reference
export interface CallMeBotConfig {
  phone: string;
  apikey: string;
}

export interface NtfyConfig {
  server?: string;
  topic: string;
  auth_token?: string | null;
}

export interface PushoverConfig {
  user_key: string;
  app_token: string;
  priority?: number;
  retry?: number;
  expire?: number;
}

export interface TelegramConfig {
  bot_token: string;
  chat_id: string;
  message_thread_id?: number | string | null;
}

export interface BarkConfig {
  device_key: string;
  server?: string;
  group?: string;
  sound?: string;
  level?: 'passive' | 'active' | 'timeSensitive' | 'critical' | string;
}

export interface EmailConfig {
  smtp_server: string;
  smtp_port?: number;
  username: string;
  password: string;
  from_email: string;
  to_email: string;
  use_tls?: boolean;
}

// Notification Template types
export interface NotificationTemplate {
  id: number;
  event_type: string;
  name: string;
  title_template: string;
  body_template: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationTemplateUpdate {
  title_template?: string;
  body_template?: string;
}

export interface EventVariablesResponse {
  event_type: string;
  event_name: string;
  variables: string[];
}

export interface TemplatePreviewRequest {
  event_type: string;
  title_template: string;
  body_template: string;
}

export interface TemplatePreviewResponse {
  title: string;
  body: string;
}

// Notification Log types
export interface NotificationLogEntry {
  id: number;
  provider_id: number;
  provider_name: string | null;
  provider_type: string | null;
  event_type: string;
  title: string;
  message: string;
  success: boolean;
  error_message: string | null;
  printer_id: number | null;
  printer_name: string | null;
  created_at: string;
}

export interface NotificationLogStats {
  total: number;
  success_count: number;
  failure_count: number;
  by_event_type: Record<string, number>;
  by_provider: Record<string, number>;
}
