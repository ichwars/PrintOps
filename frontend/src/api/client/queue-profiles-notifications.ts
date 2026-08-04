import type {
  EventVariablesResponse,
  Filament,
  InventorySpool,
  KProfileCreate,
  KProfileDelete,
  KProfileNotesResponse,
  KProfilesResponse,
  LinkedSpoolsMap,
  NotificationLogEntry,
  NotificationLogStats,
  NotificationProvider,
  NotificationProviderCreate,
  NotificationProviderUpdate,
  NotificationTemplate,
  NotificationTemplateUpdate,
  NotificationTestRequest,
  NotificationTestResponse,
  PrintBatch,
  PrintBatchCreate,
  PrintQueueBulkUpdate,
  PrintQueueBulkUpdateResponse,
  PrintQueueItem,
  PrintQueueItemCreate,
  PrintQueueItemUpdate,
  SlotPresetMapping,
  SpoolmanFilamentEntry,
  SpoolmanStatus,
  SpoolmanSyncResult,
  TemplatePreviewRequest,
  TemplatePreviewResponse,
  UnlinkedSpool,
} from './types';
import { request } from './core';

export const queueProfilesNotificationsMethods = {
  // Print Queue
  getQueue: (printerId?: number, status?: string, targetModel?: string) => {
    const params = new URLSearchParams();
    if (printerId) params.set('printer_id', String(printerId));
    if (status) params.set('status', status);
    if (targetModel) params.set('target_model', targetModel);
    return request<PrintQueueItem[]>(`/queue/?${params}`);
  },

  getQueueItem: (id: number) => request<PrintQueueItem>(`/queue/${id}`),

  addToQueue: (data: PrintQueueItemCreate) =>
    request<PrintQueueItem>('/queue/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateQueueItem: (id: number, data: PrintQueueItemUpdate) =>
    request<PrintQueueItem>(`/queue/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  removeFromQueue: (id: number) =>
    request<{ message: string }>(`/queue/${id}`, { method: 'DELETE' }),

  reorderQueue: (items: { id: number; position: number }[]) =>
    request<{ message: string }>('/queue/reorder', {
      method: 'POST',
      body: JSON.stringify({ items }),
    }),

  cancelQueueItem: (id: number) =>
    request<{ message: string }>(`/queue/${id}/cancel`, { method: 'POST' }),

  stopQueueItem: (id: number) =>
    request<{ message: string }>(`/queue/${id}/stop`, { method: 'POST' }),

  /**
   * Start a staged queue item. The backend re-checks live filament deficit
   * for the assigned spool and, when short, returns 409 with a structured
   * payload so the caller can confirm and retry. Pass `skipFilamentCheck`
   * after the user confirms "Print Anyway" (#1496).
   */
  startQueueItem: (id: number, opts?: { skipFilamentCheck?: boolean }) => {
    const qs = opts?.skipFilamentCheck ? '?skip_filament_check=true' : '';
    return request<PrintQueueItem>(`/queue/${id}/start${qs}`, { method: 'POST' });
  },

  /**
   * Clear the `require_previous_success` gate for a printer after the user
   * resolves the failure. Acknowledges any failed/aborted predecessors and
   * restores skipped items whose error_message matches the gate string
   * back to pending. Returns counts so the UI can render a precise toast.
   */
  resumeQueueAfterFailure: (printerId: number) =>
    request<{ acknowledged: number; restored: number }>(
      `/queue/printer/${printerId}/resume`,
      { method: 'POST' },
    ),

  bulkUpdateQueue: (data: PrintQueueBulkUpdate) =>
    request<PrintQueueBulkUpdateResponse>('/queue/bulk', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // Batches
  getBatches: (status?: string) => {
    const params = status ? `?status=${status}` : '';
    return request<PrintBatch[]>(`/queue/batches${params}`);
  },

  getBatch: (id: number) => request<PrintBatch>(`/queue/batches/${id}`),

  cancelBatch: (id: number) =>
    request<{ message: string }>(`/queue/batches/${id}`, { method: 'DELETE' }),

  createBatch: (data: PrintBatchCreate) =>
    request<PrintBatch>('/queue/batches', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  ungroupBatch: (id: number) =>
    request<{ ungrouped_count: number; message: string }>(
      `/queue/batches/${id}/ungroup`,
      { method: 'POST' },
    ),

  // K-Profiles
  getKProfiles: (printerId: number, nozzleDiameter = '0.4') =>
    request<KProfilesResponse>(`/printers/${printerId}/kprofiles/?nozzle_diameter=${nozzleDiameter}`),

  setKProfile: (printerId: number, profile: KProfileCreate) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/kprofiles/`, {
      method: 'POST',
      body: JSON.stringify(profile),
    }),

  deleteKProfile: (printerId: number, profile: KProfileDelete) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/kprofiles/`, {
      method: 'DELETE',
      body: JSON.stringify(profile),
    }),

  setKProfilesBatch: (printerId: number, profiles: KProfileCreate[]) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/kprofiles/batch`, {
      method: 'POST',
      body: JSON.stringify(profiles),
    }),

  // K-Profile Notes (stored locally, not on printer)
  getKProfileNotes: (printerId: number) =>
    request<KProfileNotesResponse>(`/printers/${printerId}/kprofiles/notes`),

  setKProfileNote: (printerId: number, settingId: string, note: string) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/kprofiles/notes`, {
      method: 'PUT',
      body: JSON.stringify({ setting_id: settingId, note }),
    }),

  deleteKProfileNote: (printerId: number, settingId: string) =>
    request<{ success: boolean; message: string }>(`/printers/${printerId}/kprofiles/notes/${encodeURIComponent(settingId)}`, {
      method: 'DELETE',
    }),

  // Slot Preset Mappings
  getSlotPresets: (printerId: number) =>
    request<Record<number, SlotPresetMapping>>(`/printers/${printerId}/slot-presets`),

  getSlotPreset: (printerId: number, amsId: number, trayId: number) =>
    request<SlotPresetMapping | null>(`/printers/${printerId}/slot-presets/${amsId}/${trayId}`),

  saveSlotPreset: (printerId: number, amsId: number, trayId: number, presetId: string, presetName: string, presetSource = 'cloud') =>
    request<SlotPresetMapping>(`/printers/${printerId}/slot-presets/${amsId}/${trayId}?preset_id=${encodeURIComponent(presetId)}&preset_name=${encodeURIComponent(presetName)}&preset_source=${encodeURIComponent(presetSource)}`, {
      method: 'PUT',
    }),

  deleteSlotPreset: (printerId: number, amsId: number, trayId: number) =>
    request<{ success: boolean }>(`/printers/${printerId}/slot-presets/${amsId}/${trayId}`, {
      method: 'DELETE',
    }),

  // AMS Labels (user-defined friendly names)
  getAmsLabels: (printerId: number) =>
    request<Record<number, string>>(`/printers/${printerId}/ams-labels`),

  saveAmsLabel: (printerId: number, amsId: number, label: string, amsSerial = '') =>
    request<{ ams_id: number; label: string }>(
      `/printers/${printerId}/ams-labels/${amsId}`,
      {
        method: 'PUT',
        body: JSON.stringify({ label, ams_serial: amsSerial }),
      }
    ),

  deleteAmsLabel: (printerId: number, amsId: number, amsSerial = '') =>
    request<{ success: boolean }>(`/printers/${printerId}/ams-labels/${amsId}?ams_serial=${encodeURIComponent(amsSerial)}`, {
      method: 'DELETE',
    }),

  configureAmsSlot: (
    printerId: number,
    amsId: number,
    trayId: number,
    config: {
      tray_info_idx: string;
      tray_type: string;
      tray_sub_brands: string;
      tray_color: string;
      nozzle_temp_min: number;
      nozzle_temp_max: number;
      cali_idx: number;
      nozzle_diameter: string;
      setting_id?: string;
      kprofile_filament_id?: string;
      kprofile_setting_id?: string;
      k_value?: number;
    }
  ) => {
    const params = new URLSearchParams({
      tray_info_idx: config.tray_info_idx,
      tray_type: config.tray_type,
      tray_sub_brands: config.tray_sub_brands,
      tray_color: config.tray_color,
      nozzle_temp_min: config.nozzle_temp_min.toString(),
      nozzle_temp_max: config.nozzle_temp_max.toString(),
      cali_idx: config.cali_idx.toString(),
      nozzle_diameter: config.nozzle_diameter,
    });
    if (config.setting_id) {
      params.set('setting_id', config.setting_id);
    }
    if (config.kprofile_filament_id) {
      params.set('kprofile_filament_id', config.kprofile_filament_id);
    }
    if (config.kprofile_setting_id) {
      params.set('kprofile_setting_id', config.kprofile_setting_id);
    }
    if (config.k_value !== undefined && config.k_value > 0) {
      params.set('k_value', config.k_value.toString());
    }
    return request<{ success: boolean; message: string }>(
      `/printers/${printerId}/slots/${amsId}/${trayId}/configure?${params}`,
      { method: 'POST' }
    );
  },

  resetAmsSlot: (printerId: number, amsId: number, trayId: number) =>
    request<{ success: boolean; message: string }>(
      `/printers/${printerId}/ams/${amsId}/tray/${trayId}/reset`,
      { method: 'POST' }
    ),

  // Filament Catalog (material types with cost/temp data)
  listFilaments: () => request<Filament[]>('/filament-catalog/'),

  getFilament: (id: number) => request<Filament>(`/filament-catalog/${id}`),

  getFilamentsByType: (type: string) => request<Filament[]>(`/filament-catalog/by-type/${type}`),

  // Notification Providers
  getNotificationProviders: () => request<NotificationProvider[]>('/notifications/'),

  getNotificationProvider: (id: number) => request<NotificationProvider>(`/notifications/${id}`),

  createNotificationProvider: (data: NotificationProviderCreate) =>
    request<NotificationProvider>('/notifications/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateNotificationProvider: (id: number, data: NotificationProviderUpdate) =>
    request<NotificationProvider>(`/notifications/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteNotificationProvider: (id: number) =>
    request<{ message: string }>(`/notifications/${id}`, { method: 'DELETE' }),

  testNotificationProvider: (id: number) =>
    request<NotificationTestResponse>(`/notifications/${id}/test`, { method: 'POST' }),

  testNotificationConfig: (data: NotificationTestRequest) =>
    request<NotificationTestResponse>('/notifications/test-config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  testAllNotificationProviders: () =>
    request<{
      tested: number;
      success: number;
      failed: number;
      results: Array<{
        provider_id: number;
        provider_name: string;
        provider_type: string;
        success: boolean;
        message: string;
      }>;
    }>('/notifications/test-all', { method: 'POST' }),

  // Notification Templates
  getNotificationTemplates: () => request<NotificationTemplate[]>('/notification-templates'),

  getNotificationTemplate: (id: number) => request<NotificationTemplate>(`/notification-templates/${id}`),

  updateNotificationTemplate: (id: number, data: NotificationTemplateUpdate) =>
    request<NotificationTemplate>(`/notification-templates/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  resetNotificationTemplate: (id: number) =>
    request<NotificationTemplate>(`/notification-templates/${id}/reset`, {
      method: 'POST',
    }),

  getTemplateVariables: () => request<EventVariablesResponse[]>('/notification-templates/variables'),

  previewTemplate: (data: TemplatePreviewRequest) =>
    request<TemplatePreviewResponse>('/notification-templates/preview', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // Notification Logs
  getNotificationLogs: (params?: {
    limit?: number;
    offset?: number;
    provider_id?: number;
    event_type?: string;
    success?: boolean;
    days?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    if (params?.provider_id) searchParams.set('provider_id', String(params.provider_id));
    if (params?.event_type) searchParams.set('event_type', params.event_type);
    if (params?.success !== undefined) searchParams.set('success', String(params.success));
    if (params?.days) searchParams.set('days', String(params.days));
    return request<NotificationLogEntry[]>(`/notifications/logs?${searchParams}`);
  },

  getNotificationLogStats: (days = 7) =>
    request<NotificationLogStats>(`/notifications/logs/stats?days=${days}`),

  clearNotificationLogs: (olderThanDays = 30) =>
    request<{ deleted: number; message: string }>(
      `/notifications/logs?older_than_days=${olderThanDays}`,
      { method: 'DELETE' }
    ),

  // Spoolman Integration
  getSpoolmanStatus: () => request<SpoolmanStatus>('/spoolman/status'),

  connectSpoolman: () =>
    request<{ success: boolean; message: string }>('/spoolman/connect', {
      method: 'POST',
    }),

  disconnectSpoolman: () =>
    request<{ success: boolean; message: string }>('/spoolman/disconnect', {
      method: 'POST',
    }),

  syncPrinterAms: (printerId: number) =>
    request<SpoolmanSyncResult>(`/spoolman/sync/${printerId}`, {
      method: 'POST',
    }),

  syncAllPrintersAms: () =>
    request<SpoolmanSyncResult>('/spoolman/sync-all', {
      method: 'POST',
    }),

  getSpoolmanSpools: () =>
    request<{ spools: unknown[] }>('/spoolman/spools'),

  /** @deprecated Use getSpoolmanInventoryFilaments() — this endpoint has no SSRF guard */
  getSpoolmanFilaments: () =>
    request<{ filaments: unknown[] }>('/spoolman/filaments'),

  getSpoolmanInventoryFilaments: () =>
    request<SpoolmanFilamentEntry[]>('/spoolman/inventory/filaments'),

  patchSpoolmanFilament: (
    filamentId: number,
    data: { name?: string; spool_weight?: number | null; keep_existing_spools?: boolean },
  ) =>
    request<SpoolmanFilamentEntry>(`/spoolman/inventory/filaments/${filamentId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  getUnlinkedSpools: () =>
    request<UnlinkedSpool[]>('/spoolman/spools/unlinked'),

  getLinkedSpools: () =>
    request<LinkedSpoolsMap>('/spoolman/spools/linked'),

  linkSpool: (
    spoolId: number,
    context: {
      spoolTag: string;
      printerId: number;
      amsId: number;
      trayId: number;
    }
  ) =>
    request<{ success: boolean; message: string }>(`/spoolman/spools/${spoolId}/link`, {
      method: 'POST',
      body: JSON.stringify({
        spool_tag: context.spoolTag,
        printer_id: context.printerId,
        ams_id: context.amsId,
        tray_id: context.trayId,
      }),
    }),

  unlinkSpool: (spoolId: number) =>
    request<{ success: boolean; message: string }>(`/spoolman/spools/${spoolId}/unlink`, {
      method: 'POST',
    }),

  createSpoolmanSpoolFromSlot: (data: { printer_id: number; ams_id: number; tray_id: number }) =>
    request<{ success: boolean; spool_id: number | null }>(`/spoolman/spools/from-slot`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  createSpoolFromSlot: (data: { printer_id: number; ams_id: number; tray_id: number }) =>
    request<InventorySpool>(`/inventory/spools/from-slot`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getSpoolmanSettings: () =>
    request<{ spoolman_enabled: string; spoolman_url: string; spoolman_sync_mode: string; spoolman_disable_weight_sync: string; spoolman_report_partial_usage: string; auto_add_unknown_rfid: string; }>('/settings/spoolman'),

  updateSpoolmanSettings: (data: { spoolman_enabled?: string; spoolman_url?: string; spoolman_sync_mode?: string; spoolman_disable_weight_sync?: string; spoolman_report_partial_usage?: string; auto_add_unknown_rfid?: string; }) =>
    request<{ spoolman_enabled: string; spoolman_url: string; spoolman_sync_mode: string; spoolman_disable_weight_sync: string; spoolman_report_partial_usage: string; auto_add_unknown_rfid: string; }>('/settings/spoolman', {
      method: 'PUT',
      body: JSON.stringify(data),
    })
};
