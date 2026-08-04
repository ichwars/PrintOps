// Spoolman types
export interface SpoolmanStatus {
  enabled: boolean;
  connected: boolean;
  url: string | null;
}

export interface SkippedSpool {
  location: string;
  reason: string;
  filament_type: string | null;
  color: string | null;
}

export interface SpoolmanSyncResult {
  success: boolean;
  synced_count: number;
  skipped_count: number;
  skipped: SkippedSpool[];
  errors: string[];
}

export interface UnlinkedSpool {
  id: number;
  filament_name: string | null;
  filament_vendor: string | null;
  filament_material: string | null;
  filament_color_hex: string | null;
  remaining_weight: number | null;
  location: string | null;
}

export interface LinkedSpoolInfo {
  id: number;
  remaining_weight: number | null;
  filament_weight: number | null;
}

export interface LinkedSpoolsMap {
  linked: Record<string, LinkedSpoolInfo>; // tag (uppercase) -> spool info
}

export interface SpoolmanVendor {
  id: number;
  name: string;
}

export interface SpoolmanFilamentEntry {
  id: number;
  name: string;
  material: string | null;
  color_hex: string | null;
  color_name: string | null;
  weight: number | null;
  spool_weight: number | null;
  vendor: SpoolmanVendor | null;
}

// Inventory types
// Label printing (#809). Mirror of backend.app.services.label_renderer.TemplateName.
export type SpoolLabelTemplate =
  | 'ams_holder_74x33'
  | 'ams_holder_75x55'
  | 'box_40x30'
  | 'box_62x29'
  | 'avery_5160'
  | 'avery_l7160';

export interface InventorySpool {
  id: number;
  material: string;
  subtype: string | null;
  color_name: string | null;
  // True when color_name was synthesised from subtype because Spoolman has no
  // stored value (Spoolman-backed inventory only). The edit form uses this to
  // leave the input blank, so the user doesn't round-trip the synth value
  // back to Spoolman as if it were a real user-set color_name (#1319).
  color_name_is_synthesized?: boolean;
  rgba: string | null;
  // Multi-colour gradient stops (#1154): comma-separated 6/8-char hex.
  extra_colors: string | null;
  // Visual effect overlay: sparkle | wood | marble | glow | matte.
  effect_type: string | null;
  brand: string | null;
  label_weight: number;
  core_weight: number;
  core_weight_catalog_id: number | null;
  weight_used: number;
  // Anchor for the resettable "Total Consumed" display (#1390). The
  // counter shown on the Inventory page is `weight_used - weight_used_baseline`;
  // remaining is still `label_weight - weight_used`, so "Reset usage to 0"
  // zeroes the counter without disturbing remaining. Optional for back-compat
  // with rows from a pre-migration DB snapshot — default to 0.
  weight_used_baseline?: number;
  slicer_filament: string | null;
  slicer_filament_name: string | null;
  nozzle_temp_min: number | null;
  nozzle_temp_max: number | null;
  note: string | null;
  added_full: boolean | null;
  last_used: string | null;
  encode_time: string | null;
  tag_uid: string | null;
  tray_uuid: string | null;
  data_origin: string | null;
  tag_type: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  cost_per_kg: number | null;
  last_scale_weight: number | null;
  last_weighed_at: string | null;
  // User-defined category + per-spool low-stock threshold override (#729).
  category: string | null;
  low_stock_threshold_pct: number | null;
  k_profiles?: SpoolKProfile[];
  storage_location?: string | null;
  location_id?: number | null;
}

export interface SpoolmanBulkCreateResult {
  created: InventorySpool[];
  requested_count: number;
  failed_count: number;
}

// ── CSV import/export (#1576) ──────────────────────────────────────────────
/** One row's outcome from the import preview / real import. */
export interface CsvImportRow {
  row_number: number;
  status: 'valid' | 'error' | 'skipped';
  reason: string | null;
  material: string | null;
  brand: string | null;
  color_name: string | null;
  rgba: string | null;
  /** rgba/extra_colors/effect_type were filled from the Color Catalog. */
  resolved_color: boolean;
  /** The catalog match came from a different material's variant (no exact
   *  material match). Shown as a warning in the preview. */
  cross_material_color: boolean;
  /** An active spool with the same material+brand+color already exists.
   *  Informational only — the import still creates the row. */
  duplicate_of_existing: boolean;
}

/** Dry-run preview: per-row classification, no rows written. */
export interface CsvImportPreview {
  columns: string[];
  total: number;
  valid_count: number;
  error_count: number;
  skipped_count: number;
  rows: CsvImportRow[];
  warnings: string[];
}

/** Summary returned after a real (non-dry-run) import. */
export interface CsvImportResult {
  created: number;
  skipped: number;
  errors: number;
  error_rows: CsvImportRow[];
}

export interface SpoolUsageRecord {
  id: number;
  spool_id: number;
  printer_id: number | null;
  print_name: string | null;
  weight_used: number;
  percent_used: number;
  status: string;
  cost: number | null;
  created_at: string;
}

export interface SpoolKProfile {
  id: number;
  spool_id: number;
  printer_id: number;
  extruder: number;
  nozzle_diameter: string;
  nozzle_type: string | null;
  k_value: number;
  name: string | null;
  cali_idx: number | null;
  setting_id: string | null;
  created_at: string;
}

export interface SpoolKProfileInput {
  printer_id: number;
  extruder?: number;
  nozzle_diameter?: string;
  nozzle_type?: string | null;
  k_value: number;
  name?: string | null;
  cali_idx?: number | null;
  setting_id?: string | null;
}

export interface SpoolAssignment {
  id: number;
  spool_id: number;
  printer_id: number;
  printer_name: string | null;
  ams_id: number;
  tray_id: number;
  fingerprint_color: string | null;
  fingerprint_type: string | null;
  spool?: InventorySpool | null;
  configured: boolean;
  pending_config?: boolean;  // Slot was empty at assign time; will configure on insert
  created_at: string;
  ams_label?: string | null;  // User-defined friendly name for the AMS unit
}

export interface FilamentSkuSettings {
  id: number;
  material: string;
  subtype: string | null;
  brand: string | null;
  color_name: string | null;
  default_supplier_id: number | null;
  lead_time_days: number;
  safety_margin_value: number;
  safety_margin_unit: 'days' | 'g';
  alerts_snoozed: boolean;
}

export interface ShoppingListItem {
  id: number;
  material: string;
  subtype: string | null;
  brand: string | null;
  color_name: string | null;
  quantity_spools: number;
  note: string | null;
  status: 'pending' | 'purchased' | 'received';
  purchased_at: string | null;
  added_at: string;
}

export interface ShoppingListItemCreate {
  material: string;
  subtype: string | null;
  brand: string | null;
  color_name: string | null;
  quantity_spools: number;
  note?: string | null;
}

// Update types
export interface VersionInfo {
  version: string;
  repo: string;
}

export interface UpdateCheckResult {
  update_available: boolean;
  current_version: string;
  latest_version: string | null;
  release_name?: string;
  release_notes?: string;
  release_url?: string;
  published_at?: string;
  error?: string;
  message?: string;
  is_docker?: boolean;
  is_ha_addon?: boolean;
  is_windows_installer?: boolean;
  update_method?: 'docker' | 'git' | 'ha_addon' | 'windows_installer';
  installer_download_url?: string | null;
}

export interface UpdateStatus {
  status: 'idle' | 'checking' | 'downloading' | 'installing' | 'complete' | 'error';
  progress: number;
  message: string;
  error: string | null;
}

// Maintenance types
export interface MaintenanceType {
  id: number;
  name: string;
  description: string | null;
  default_interval_hours: number;
  interval_type: 'hours' | 'days';  // "hours" = print hours, "days" = calendar days
  icon: string | null;
  wiki_url: string | null;  // Documentation link
  is_system: boolean;
  created_at: string;
}

export interface MaintenanceTypeCreate {
  name: string;
  description?: string | null;
  default_interval_hours?: number;
  interval_type?: 'hours' | 'days';
  icon?: string | null;
  wiki_url?: string | null;
}

export interface MaintenanceStatus {
  id: number;
  printer_id: number;
  printer_name: string;
  printer_model: string | null;
  maintenance_type_id: number;
  maintenance_type_name: string;
  maintenance_type_icon: string | null;
  maintenance_type_wiki_url: string | null;  // Custom wiki URL from type
  enabled: boolean;
  interval_hours: number;  // For hours type: print hours; for days type: number of days
  interval_type: 'hours' | 'days';
  current_hours: number;
  hours_since_maintenance: number;
  hours_until_due: number;
  days_since_maintenance: number | null;  // For days type
  days_until_due: number | null;  // For days type
  is_due: boolean;
  is_warning: boolean;
  last_performed_at: string | null;
}

export interface PrinterMaintenanceOverview {
  printer_id: number;
  printer_name: string;
  printer_model: string | null;
  total_print_hours: number;
  maintenance_items: MaintenanceStatus[];
  due_count: number;
  warning_count: number;
}

export interface MaintenanceHistory {
  id: number;
  printer_maintenance_id: number;
  performed_at: string;
  hours_at_maintenance: number;
  notes: string | null;
}

export interface MaintenanceSummary {
  total_due: number;
  total_warning: number;
  printers_with_issues: Array<{
    printer_id: number;
    printer_name: string;
    due_count: number;
    warning_count: number;
  }>;
}

// External Links (sidebar)
export interface ExternalLink {
  id: number;
  name: string;
  url: string;
  icon: string;
  open_in_new_tab: boolean;
  custom_icon: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface ExternalLinkCreate {
  name: string;
  url: string;
  icon: string;
  open_in_new_tab?: boolean;
}

export interface ExternalLinkUpdate {
  name?: string;
  url?: string;
  icon?: string;
  open_in_new_tab?: boolean;
}
