

export interface SpoolmanSlotAssignmentRow {
  printer_id: number;
  ams_id: number;
  tray_id: number;
  spoolman_spool_id: number;
}

export interface PrinterMaintenanceInfo {
  due_count: number;
  warning_count: number;
  total_print_hours: number;
}

export type SortOption = 'name' | 'status' | 'model' | 'location' | 'eta';

export type ViewMode = 'expanded' | 'compact';
