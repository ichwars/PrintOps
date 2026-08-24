import type {
  Equipment,
  EquipmentInput,
  HMSActionBody,
  MQTTLogsResponse,
  Printer,
  PrinterCreate,
  PrinterStatus,
} from './types';
import {
  API_BASE,
  authToken,
  parseContentDispositionFilename,
  request,
  withStreamToken,
} from './core';

export const printersFilesMethods = {
  // Printers
  getPrinters: () => request<Printer[]>('/printers/'),

  getPrinter: (id: number) => request<Printer>(`/printers/${id}`),

  createPrinter: (data: PrinterCreate) =>
    request<Printer>('/printers/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updatePrinter: (id: number, data: Partial<PrinterCreate>) =>
    request<Printer>(`/printers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deletePrinter: (id: number, deleteArchives: boolean = true) =>
    request<{ status: string; archives_deleted: boolean }>(
      `/printers/${id}?delete_archives=${deleteArchives}`,
      { method: 'DELETE' }
    ),

  getEquipment: (activeOnly = false) => request<Equipment[]>(`/equipment/?active_only=${activeOnly}`),

  createEquipment: (data: EquipmentInput) => request<Equipment>('/equipment/', { method: 'POST', body: JSON.stringify(data) }),

  updateEquipment: (id: number, data: Partial<EquipmentInput>) => request<Equipment>(`/equipment/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  deleteEquipment: (id: number) => request<void>(`/equipment/${id}`, { method: 'DELETE' }),

  getDeveloperModeWarnings: () =>
    request<{ printer_id: number; name: string }[]>('/printers/developer-mode-warnings'),

  getAvailableFilaments: (model: string, location?: string) => {
    const params = new URLSearchParams({ model });
    if (location) params.set('location', location);
    return request<Array<{ type: string; color: string; tray_info_idx: string; tray_sub_brands: string; extruder_id: number | null }>>(`/printers/available-filaments?${params}`);
  },

  getPrinterStatus: (id: number) =>
    request<PrinterStatus>(`/printers/${id}/status`),

  refreshPrinterStatus: (id: number) =>
    request<{ status: string }>(`/printers/${id}/refresh-status`, {
      method: 'POST',
    }),

  connectPrinter: (id: number) =>
    request<{ connected: boolean }>(`/printers/${id}/connect`, {
      method: 'POST',
    }),

  disconnectPrinter: (id: number) =>
    request<{ connected: boolean }>(`/printers/${id}/disconnect`, {
      method: 'POST',
    }),

  testExternalCamera: (printerId: number, url: string, cameraType: string) =>
    request<{ success: boolean; error?: string; resolution?: string }>(
      `/printers/${printerId}/camera/external/test?url=${encodeURIComponent(url)}&camera_type=${encodeURIComponent(cameraType)}`,
      { method: 'POST' }
    ),

  // Print Control
  stopPrint: (printerId: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/print/stop`, {
      method: 'POST',
    }),

  pausePrint: (printerId: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/print/pause`, {
      method: 'POST',
    }),

  resumePrint: (printerId: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/print/resume`, {
      method: 'POST',
    }),

  clearPlate: (printerId: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/clear-plate`, {
      method: 'POST',
    }),

  // Get current print user (for reprint tracking - Issue #206)
  getCurrentPrintUser: (printerId: number) =>
    request<{ user_id?: number; username?: string }>(`/printers/${printerId}/current-print-user`),

  // Print Speed Control
  setPrintSpeed: (printerId: number, mode: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/print-speed?mode=${mode}`, {
      method: 'POST',
    }),

  setNozzleTemperature: (printerId: number, target: number, nozzle: number = 0) =>
    request<{ success: boolean; message: string }>(
      `/printers/${printerId}/temperature/nozzle?target=${target}&nozzle=${nozzle}`,
      { method: 'POST' }
    ),

  setBedTemperature: (printerId: number, target: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/temperature/bed?target=${target}`, {
      method: 'POST',
    }),

  setChamberTemperature: (printerId: number, target: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/temperature/chamber?target=${target}`, {
      method: 'POST',
    }),

  setFanSpeed: (printerId: number, fan: 'part' | 'aux' | 'chamber', speed: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/fan-speed?fan=${fan}&speed=${speed}`, {
      method: 'POST',
    }),

  selectExtruder: (printerId: number, extruder: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/select-extruder?extruder=${extruder}`, {
      method: 'POST',
    }),

  setAirductMode: (printerId: number, mode: 'cooling' | 'heating') =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/airduct-mode?mode=${mode}`, {
      method: 'POST',
    }),

  // Bed (Z-axis) jog
  bedJog: (printerId: number, distance: number, force: boolean = false) =>
    request<{ success: boolean; message: string }>(
      `/printers/${printerId}/bed-jog?distance=${distance}&force=${force}`,
      { method: 'POST' }
    ),

  xyJog: (printerId: number, x: number, y: number) =>
    request<{ success: boolean; message: string }>(
      `/printers/${printerId}/xy-jog?x=${x}&y=${y}`,
      { method: 'POST' }
    ),

  extruderJog: (printerId: number, distance: number) =>
    request<{ success: boolean; message: string }>(
      `/printers/${printerId}/extruder-jog?distance=${distance}`,
      { method: 'POST' }
    ),

  homeAxes: (printerId: number, axes: 'z' | 'xy' | 'all' = 'z') =>
    request<{ success: boolean; message: string }>(
      `/printers/${printerId}/home-axes?axes=${axes}`,
      { method: 'POST' }
    ),

  // Chamber Light Control
  setChamberLight: (printerId: number, on: boolean) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/chamber-light?on=${on}`, {
      method: 'POST',
    }),

  // AMS Drying Control
  startDrying: (printerId: number, amsId: number, temp: number, duration: number, filament: string = '', rotateTray: boolean = false) =>
    request<{ status: string; ams_id: number; temp: number; duration: number }>(
      `/printers/${printerId}/drying/start?ams_id=${amsId}&temp=${temp}&duration=${duration}&filament=${encodeURIComponent(filament)}&rotate_tray=${rotateTray}`,
      { method: 'POST' }
    ),

  stopDrying: (printerId: number, amsId: number) =>
    request<{ status: string; ams_id: number }>(
      `/printers/${printerId}/drying/stop?ams_id=${amsId}`,
      { method: 'POST' }
    ),

  // AMS Filament Backup (auto-switch to a backup spool when one runs out)
  setAmsFilamentBackup: (printerId: number, enabled: boolean) =>
    request<{ success: boolean; ams_filament_backup: boolean }>(
      `/printers/${printerId}/ams-backup?enabled=${enabled}`,
      { method: 'POST' }
    ),

  // Per-globalTrayId remaining grams for this printer's inventory-bound slots
  // (#1766). Drives the client-side "Prefer Lowest Remaining Filament" sort
  // when computing the AMS mapping; mirrors backend `_build_inventory_remain_overrides`
  // so internal and Spoolman modes both work uniformly.
  getInventoryRemain: (printerId: number) =>
    request<{ inventory_remain_g: Record<string, number> }>(
      `/printers/${printerId}/inventory-remain`,
    ),

  // Skip Objects
  getPrintableObjects: (printerId: number) =>
    request<{
      objects: Array<{ id: number; name: string; x: number | null; y: number | null; skipped: boolean }>;
      total: number;
      skipped_count: number;
      is_printing: boolean;
      bbox_all: [number, number, number, number] | null;
    }>(`/printers/${printerId}/print/objects`),

  skipObjects: (printerId: number, objectIds: number[]) =>
    request<{ success: boolean; message: string; skipped_objects: number[] }>(
      `/printers/${printerId}/print/skip-objects`,
      {
        method: 'POST',
        body: JSON.stringify(objectIds),
      }
    ),

  // HMS Errors
  clearHMSErrors: (printerId: number) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/hms/clear`, { method: 'POST' }),

  executeHMSAction: (printerId: number, data: HMSActionBody) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/hms/execute-action`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // AMS Control
  refreshAmsSlot: (printerId: number, amsId: number, slotId: number) =>
    request<{ success: boolean; message: string }>(
      `/printers/${printerId}/ams/${amsId}/slot/${slotId}/refresh`,
      { method: 'POST' }
    ),

  // Load filament from a tray. trayId: 0-15 for AMS (amsId*4+slotId), 254 for external spool.
  loadAmsTray: (printerId: number, trayId: number) =>
    request<{ success: boolean; message: string }>(
      `/printers/${printerId}/ams/load?tray_id=${trayId}`,
      { method: 'POST' }
    ),

  // Unload the currently loaded filament.
  unloadAms: (printerId: number) =>
    request<{ success: boolean; message: string }>(
      `/printers/${printerId}/ams/unload`,
      { method: 'POST' }
    ),

  // MQTT Debug Logging
  enableMQTTLogging: (printerId: number) =>
    request<{ logging_enabled: boolean }>(`/printers/${printerId}/logging/enable`, {
      method: 'POST',
    }),

  disableMQTTLogging: (printerId: number) =>
    request<{ logging_enabled: boolean }>(`/printers/${printerId}/logging/disable`, {
      method: 'POST',
    }),

  getMQTTLogs: (printerId: number) =>
    request<MQTTLogsResponse>(`/printers/${printerId}/logging`),

  clearMQTTLogs: (printerId: number) =>
    request<{ status: string }>(`/printers/${printerId}/logging`, {
      method: 'DELETE',
    }),

  // Printer File Manager
  getPrinterFiles: (printerId: number, path = '/') =>
    request<{
      path: string;
      files: Array<{
        name: string;
        is_directory: boolean;
        size: number;
        path: string;
        mtime?: string;
      }>;
    }>(`/printers/${printerId}/files?path=${encodeURIComponent(path)}`),

  getPrinterFileDownloadUrl: (printerId: number, path: string) =>
    `${API_BASE}/printers/${printerId}/files/download?path=${encodeURIComponent(path)}`,

  getPrinterFileGcodeUrl: (printerId: number, path: string) =>
    `${API_BASE}/printers/${printerId}/files/gcode?path=${encodeURIComponent(path)}`,

  getPrinterFilePlates: (printerId: number, path: string) =>
    request<{
      printer_id: number;
      path: string;
      filename: string;
      plates: Array<{
        index: number;
        name: string | null;
        objects: string[];
        has_thumbnail: boolean;
        thumbnail_url: string | null;
        print_time_seconds: number | null;
        filament_used_grams: number | null;
        filaments: Array<{
          slot_id: number;
          type: string;
          color: string;
          used_grams: number;
          used_meters: number;
        }>;
      }>;
      is_multi_plate: boolean;
    }>(`/printers/${printerId}/files/plates?path=${encodeURIComponent(path)}`),

  getPrinterFilePlateThumbnail: (printerId: number, plateIndex: number, path: string) =>
    withStreamToken(`${API_BASE}/printers/${printerId}/files/plate-thumbnail/${plateIndex}?path=${encodeURIComponent(path)}`),

  // Downloads a single printer file (e.g. a multi-hundred-MB printer log).
  // Returns a download_id up front (before the fetch resolves) so the
  // caller can subscribe to WS 'file_download_progress' events — keyed by
  // that id — before the first one could possibly arrive. The backend
  // relays live byte progress over the same WebSocket connection used for
  // print-queue upload progress.
  downloadPrinterFile: (printerId: number, path: string): { downloadId: string; promise: Promise<void> } => {
    const downloadId = crypto.randomUUID();
    const promise = (async () => {
      const headers: Record<string, string> = {};
      if (authToken) {
        headers['Authorization'] = `Bearer ${authToken}`;
      }
      const response = await fetch(
        `${API_BASE}/printers/${printerId}/files/download?path=${encodeURIComponent(path)}&download_id=${downloadId}`,
        { headers }
      );
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }
      const disposition = response.headers.get('Content-Disposition');
      const filename = parseContentDispositionFilename(disposition) || path.split('/').pop() || 'download';
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    })();
    return { downloadId, promise };
  },

  downloadPrinterFilesAsZip: async (printerId: number, paths: string[]): Promise<Blob> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/printers/${printerId}/files/download-zip`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ paths }),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.blob();
  },

  deletePrinterFile: (printerId: number, path: string) =>
    request<{ status: string; path: string }>(`/printers/${printerId}/files?path=${encodeURIComponent(path)}`, {
      method: 'DELETE',
    }),

  getPrinterStorage: (printerId: number) =>
    request<{ used_bytes: number | null; free_bytes: number | null }>(`/printers/${printerId}/storage`)
};
