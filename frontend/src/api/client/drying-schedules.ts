import { request } from './core';

export interface DryingScheduleWrite {
  ams_id: number;
  local_time: string;
  timezone: string;
  filament: string;
  temperature: number;
  duration_hours: number;
  rotate_tray: boolean;
  enabled: boolean;
}

export interface DryingSchedule extends DryingScheduleWrite {
  id: number;
  printer_id: number;
}

export interface DryingRun {
  id: number;
  schedule_id: number;
  ams_id: number;
  occurrence_day: string;
  status: string;
  reason: string | null;
  active_printer_id: number | null;
}

export interface DryingCapability {
  ams_id: number;
  module_type: string | null;
  max_temperature: number | null;
  reason: string | null;
}

export interface DryingSchedules {
  schedules: DryingSchedule[];
  runs: DryingRun[];
  capabilities: DryingCapability[];
}

const path = (printerId: number) => `/printers/${printerId}/drying/schedules`;
export const dryingSchedulesApi = {
  list: (printerId: number) => request<DryingSchedules>(path(printerId)),
  save: (printerId: number, data: DryingScheduleWrite, id?: number) => request<DryingSchedule>(
    `${path(printerId)}${id === undefined ? '' : `/${id}`}`,
    { method: id === undefined ? 'POST' : 'PUT', body: JSON.stringify(data) },
  ),
  remove: (printerId: number, id: number) => request<void>(`${path(printerId)}/${id}`, { method: 'DELETE' }),
  resolve: (printerId: number, id: number) => request<DryingRun>(`${path(printerId)}/runs/${id}/resolve`, { method: 'POST' }),
};
