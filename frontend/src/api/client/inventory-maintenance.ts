import type {
  CalibrationResult,
  CamWallPrinter,
  CameraDiagnoseResult,
  ColorCatalogEntry,
  ColorLookupResult,
  CsvImportPreview,
  CsvImportResult,
  ExternalLink,
  ExternalLinkCreate,
  ExternalLinkUpdate,
  FilamentSkuSettings,
  InventorySpool,
  LongLivedCameraToken,
  LongLivedTokenScope,
  MaintenanceHistory,
  MaintenanceStatus,
  MaintenanceSummary,
  MaintenanceType,
  MaintenanceTypeCreate,
  OverlayStatus,
  PlateDetectionResult,
  PlateDetectionStatus,
  PlateReference,
  PrinterDiagnosticResult,
  PrinterMaintenanceOverview,
  ShoppingListItem,
  ShoppingListItemCreate,
  SlicerSetting,
  SpoolAssignment,
  SpoolCatalogEntry,
  SpoolKProfile,
  SpoolKProfileInput,
  SpoolLabelTemplate,
  SpoolUsageRecord,
  SpoolmanBulkCreateResult,
  StorageLocation,
  UpdateCheckResult,
  UpdateStatus,
  VersionInfo,
} from './types';
import {
  API_BASE,
  authToken,
  parseContentDispositionFilename,
  request,
  uploadSpoolsCsv,
  withStreamToken,
} from './core';

export const inventoryMaintenanceMethods = {
  // Inventory
  getSpools: (includeArchived = false) =>
    request<InventorySpool[]>(`/inventory/spools?include_archived=${includeArchived}`),

  getSpool: (id: number) => request<InventorySpool>(`/inventory/spools/${id}`),

  createSpool: (data: Omit<InventorySpool, 'id' | 'archived_at' | 'created_at' | 'updated_at' | 'k_profiles'>) =>
    request<InventorySpool>('/inventory/spools', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  bulkCreateSpools: (data: Omit<InventorySpool, 'id' | 'archived_at' | 'created_at' | 'updated_at' | 'k_profiles'>, quantity: number) =>
    request<InventorySpool[]>('/inventory/spools/bulk', {
      method: 'POST',
      body: JSON.stringify({ spool: data, quantity }),
    }),

  // ── CSV import/export (#1576) ────────────────────────────────────────────
  // dry_run=true → preview (no write); omitted → real import. Both share one
  // multipart upload helper; see `uploadSpoolsCsv` below.
  importSpoolsCsvPreview: (file: File): Promise<CsvImportPreview> => uploadSpoolsCsv<CsvImportPreview>(file, true),

  importSpoolsCsv: (file: File): Promise<CsvImportResult> => uploadSpoolsCsv<CsvImportResult>(file, false),

  exportSpoolsCsv: async (): Promise<void> => {
    const headers: Record<string, string> = {};
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
    const response = await fetch(`${API_BASE}/inventory/spools/export`, { headers });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    const disposition = response.headers.get('Content-Disposition');
    const filename = parseContentDispositionFilename(disposition) || 'printops_inventory.csv';
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  },

  updateSpool: (id: number, data: Partial<Omit<InventorySpool, 'id' | 'archived_at' | 'created_at' | 'updated_at' | 'k_profiles'>>) =>
    request<InventorySpool>(`/inventory/spools/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteSpool: (id: number) =>
    request<{ status: string }>(`/inventory/spools/${id}`, { method: 'DELETE' }),

  archiveSpool: (id: number) =>
    request<InventorySpool>(`/inventory/spools/${id}/archive`, { method: 'POST' }),

  restoreSpool: (id: number) =>
    request<InventorySpool>(`/inventory/spools/${id}/restore`, { method: 'POST' }),

  resetSpoolConsumedCounter: (id: number) =>
    request<InventorySpool>(`/inventory/spools/${id}/reset-consumed-counter`, { method: 'POST' }),

  refillSpool: (id: number, data: { added_weight: number; note?: string | null }) =>
    request<InventorySpool>(`/inventory/spools/${id}/refill`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  bulkResetSpoolConsumedCounter: (spoolIds: number[]) =>
    request<{ reset: number }>(`/inventory/spools/reset-consumed-counter-bulk`, {
      method: 'POST',
      body: JSON.stringify({ spool_ids: spoolIds }),
    }),

  bulkUpdateSpools: (ids: number[], update: Partial<Omit<InventorySpool, 'id' | 'archived_at' | 'created_at' | 'updated_at' | 'k_profiles'>>) =>
    request<{ updated: number; not_found: number[] }>(`/inventory/spools/bulk-update`, {
      method: 'POST',
      body: JSON.stringify({ ids, update }),
    }),

  bulkDeleteSpools: (ids: number[]) =>
    request<{ deleted: number; not_found: number[] }>(`/inventory/spools/bulk-delete`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  bulkArchiveSpools: (ids: number[]) =>
    request<{ archived: number; already_archived: number[]; not_found: number[] }>(`/inventory/spools/bulk-archive`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  bulkRestoreSpools: (ids: number[]) =>
    request<{ restored: number; already_active: number[]; not_found: number[] }>(`/inventory/spools/bulk-restore`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  mergeSpools: (targetId: number, sourceIds: number[]) =>
    request<{
      target_id: number;
      merged: number;
      source_ids: number[];
      archived: number[];
      reassigned: Record<string, number>;
    }>('/inventory/spools/merge', {
      method: 'POST',
      body: JSON.stringify({ target_id: targetId, source_ids: sourceIds }),
    }),

  getSpoolKProfiles: (spoolId: number) =>
    request<SpoolKProfile[]>(`/inventory/spools/${spoolId}/k-profiles`),

  saveSpoolKProfiles: (spoolId: number, profiles: SpoolKProfileInput[]) =>
    request<SpoolKProfile[]>(`/inventory/spools/${spoolId}/k-profiles`, {
      method: 'PUT',
      body: JSON.stringify(profiles),
    }),

  getAssignments: (printerId?: number) =>
    request<SpoolAssignment[]>(`/inventory/assignments${printerId ? `?printer_id=${printerId}` : ''}`),

  assignSpool: (data: { spool_id: number; printer_id: number; ams_id: number; tray_id: number }) =>
    request<SpoolAssignment>('/inventory/assignments', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  unassignSpool: (printerId: number, amsId: number, trayId: number) =>
    request<{ status: string }>(`/inventory/assignments/${printerId}/${amsId}/${trayId}`, { method: 'DELETE' }),

  // ── Spool label printing (#809) ──────────────────────────────────────────
  // Both endpoints return application/pdf. Frontend opens the resulting Blob
  // in a new tab so the user can print or save from the browser's PDF viewer.
  printSpoolLabels: async (data: { spool_ids: number[]; template: SpoolLabelTemplate; monochrome?: boolean }): Promise<Blob> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
    const response = await fetch(`${API_BASE}/inventory/labels`, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.blob();
  },

  printSpoolmanSpoolLabels: async (data: { spool_ids: number[]; template: SpoolLabelTemplate; monochrome?: boolean }): Promise<Blob> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
    const response = await fetch(`${API_BASE}/spoolman/labels`, {
      method: 'POST',
      headers,
      body: JSON.stringify(data),
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.blob();
  },

  getSpoolCatalog: () =>
    request<SpoolCatalogEntry[]>('/inventory/catalog'),

  addCatalogEntry: (data: { name: string; weight: number }) =>
    request<SpoolCatalogEntry>('/inventory/catalog', { method: 'POST', body: JSON.stringify(data) }),

  updateCatalogEntry: (id: number, data: { name: string; weight: number }) =>
    request<SpoolCatalogEntry>(`/inventory/catalog/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  deleteCatalogEntry: (id: number) =>
    request<{ status: string }>(`/inventory/catalog/${id}`, { method: 'DELETE' }),

  bulkDeleteCatalogEntries: (ids: number[]) =>
    request<{ deleted: number }>('/inventory/catalog/bulk-delete', { method: 'POST', body: JSON.stringify({ ids }) }),

  resetSpoolCatalog: () =>
    request<{ status: string }>('/inventory/catalog/reset', { method: 'POST' }),

  getLocations: () =>
    request<StorageLocation[]>('/inventory/locations'),

  createLocation: (data: { name: string; identifier?: string | null }) =>
    request<StorageLocation>('/inventory/locations', { method: 'POST', body: JSON.stringify(data) }),

  updateLocation: (id: number, data: { name?: string; identifier?: string | null }) =>
    request<StorageLocation>(`/inventory/locations/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  deleteLocation: (id: number) =>
    request<{ status: string }>(`/inventory/locations/${id}`, { method: 'DELETE' }),

  getColorCatalog: () =>
    request<ColorCatalogEntry[]>('/inventory/colors'),

  getColorNameMap: () =>
    request<{ colors: Record<string, string> }>('/inventory/colors/map'),

  addColorEntry: (data: {
    manufacturer: string;
    color_name: string;
    hex_color: string;
    material: string | null;
    extra_colors?: string | null;
    effect_type?: string | null;
  }) =>
    request<ColorCatalogEntry>('/inventory/colors', { method: 'POST', body: JSON.stringify(data) }),

  updateColorEntry: (
    id: number,
    data: {
      manufacturer: string;
      color_name: string;
      hex_color: string;
      material: string | null;
      extra_colors?: string | null;
      effect_type?: string | null;
    },
  ) => request<ColorCatalogEntry>(`/inventory/colors/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  deleteColorEntry: (id: number) =>
    request<{ status: string }>(`/inventory/colors/${id}`, { method: 'DELETE' }),

  bulkDeleteColorEntries: (ids: number[]) =>
    request<{ deleted: number }>('/inventory/colors/bulk-delete', { method: 'POST', body: JSON.stringify({ ids }) }),

  resetColorCatalog: () =>
    request<{ status: string }>('/inventory/colors/reset', { method: 'POST' }),

  lookupColor: (manufacturer: string, colorName: string, material?: string) =>
    request<ColorLookupResult>(`/inventory/colors/lookup?manufacturer=${encodeURIComponent(manufacturer)}&color_name=${encodeURIComponent(colorName)}${material ? `&material=${encodeURIComponent(material)}` : ''}`),

  searchColors: (manufacturer?: string, material?: string) =>
    request<ColorCatalogEntry[]>(`/inventory/colors/search?${manufacturer ? `manufacturer=${encodeURIComponent(manufacturer)}` : ''}${manufacturer && material ? '&' : ''}${material ? `material=${encodeURIComponent(material)}` : ''}`),

  linkTagToSpool: (spoolId: number, data: { tag_uid?: string; tray_uuid?: string; tag_type?: string; data_origin?: string }) =>
    request<InventorySpool>(`/inventory/spools/${spoolId}/link-tag`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  getSpoolUsageHistory: (spoolId: number, limit = 50) =>
    request<SpoolUsageRecord[]>(`/inventory/spools/${spoolId}/usage?limit=${limit}`),

  getAllUsageHistory: (limit = 100, printerId?: number) =>
    request<SpoolUsageRecord[]>(`/inventory/usage?limit=${limit}${printerId ? `&printer_id=${printerId}` : ''}`),

  clearSpoolUsageHistory: (spoolId: number) =>
    request<{ status: string }>(`/inventory/spools/${spoolId}/usage`, { method: 'DELETE' }),

  syncWeightsFromAms: () =>
    request<{ synced: number; skipped: number }>('/inventory/sync-ams-weights', { method: 'POST' }),

  getSkuSettings: () =>
    request<FilamentSkuSettings[]>('/inventory/sku-settings'),

  upsertSkuSettings: (data: Omit<FilamentSkuSettings, 'id'>) =>
    request<FilamentSkuSettings>('/inventory/sku-settings', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  getShoppingList: () =>
    request<ShoppingListItem[]>('/inventory/shopping-list'),

  addToShoppingList: (data: ShoppingListItemCreate) =>
    request<ShoppingListItem>('/inventory/shopping-list', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  removeFromShoppingList: (id: number) =>
    request<{ status: string }>(`/inventory/shopping-list/${id}`, { method: 'DELETE' }),

  clearShoppingList: () =>
    request<{ deleted: number }>('/inventory/shopping-list', { method: 'DELETE' }),

  updateShoppingListStatus: (id: number, status: 'pending' | 'purchased' | 'received') =>
    request<ShoppingListItem>(`/inventory/shopping-list/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),

  getFilamentPresets: () =>
    request<SlicerSetting[]>('/cloud/filaments'),

  // Spoolman Inventory proxy (unified UI when Spoolman is enabled)
  getSpoolmanInventorySpools: (includeArchived = false) =>
    request<InventorySpool[]>(`/spoolman/inventory/spools?include_archived=${includeArchived}`),

  getSpoolmanInventorySpool: (id: number) =>
    request<InventorySpool>(`/spoolman/inventory/spools/${id}`),

  createSpoolmanInventorySpool: (data: Omit<InventorySpool, 'id' | 'archived_at' | 'created_at' | 'updated_at' | 'k_profiles'>) =>
    request<InventorySpool>('/spoolman/inventory/spools', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  bulkCreateSpoolmanInventorySpools: (
    data: Omit<InventorySpool, 'id' | 'archived_at' | 'created_at' | 'updated_at' | 'k_profiles'>,
    quantity: number,
  ) =>
    request<SpoolmanBulkCreateResult | InventorySpool[]>('/spoolman/inventory/spools/bulk', {
      method: 'POST',
      body: JSON.stringify({ spool: data, quantity }),
    }),

  updateSpoolmanInventorySpool: (
    id: number,
    data: Partial<Omit<InventorySpool, 'id' | 'archived_at' | 'created_at' | 'updated_at' | 'k_profiles'>>,
  ) =>
    request<InventorySpool>(`/spoolman/inventory/spools/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteSpoolmanInventorySpool: (id: number) =>
    request<{ status: string }>(`/spoolman/inventory/spools/${id}`, { method: 'DELETE' }),

  archiveSpoolmanInventorySpool: (id: number) =>
    request<InventorySpool>(`/spoolman/inventory/spools/${id}/archive`, { method: 'POST' }),

  restoreSpoolmanInventorySpool: (id: number) =>
    request<InventorySpool>(`/spoolman/inventory/spools/${id}/restore`, { method: 'POST' }),

  resetSpoolmanInventorySpoolConsumedCounter: (id: number) =>
    request<InventorySpool>(`/spoolman/inventory/spools/${id}/reset-consumed-counter`, { method: 'POST' }),

  refillSpoolmanInventorySpool: (id: number, data: { added_weight: number; note?: string | null }) =>
    request<InventorySpool>(`/spoolman/inventory/spools/${id}/refill`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  bulkResetSpoolmanInventorySpoolConsumedCounter: (spoolIds: number[]) =>
    request<{ reset: number }>(`/spoolman/inventory/spools/reset-consumed-counter-bulk`, {
      method: 'POST',
      body: JSON.stringify({ spool_ids: spoolIds }),
    }),

  bulkUpdateSpoolmanInventorySpools: (ids: number[], update: Partial<Omit<InventorySpool, 'id' | 'archived_at' | 'created_at' | 'updated_at' | 'k_profiles'>>) =>
    request<{ updated: number; errors: Array<{ id: number; status: number; detail: string }> }>(`/spoolman/inventory/spools/bulk-update`, {
      method: 'POST',
      body: JSON.stringify({ ids, update }),
    }),

  bulkDeleteSpoolmanInventorySpools: (ids: number[]) =>
    request<{ deleted: number; errors: Array<{ id: number; status: number; detail: string }> }>(`/spoolman/inventory/spools/bulk-delete`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  bulkArchiveSpoolmanInventorySpools: (ids: number[]) =>
    request<{ archived: number; errors: Array<{ id: number; status: number; detail: string }> }>(`/spoolman/inventory/spools/bulk-archive`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  bulkRestoreSpoolmanInventorySpools: (ids: number[]) =>
    request<{ restored: number; errors: Array<{ id: number; status: number; detail: string }> }>(`/spoolman/inventory/spools/bulk-restore`, {
      method: 'POST',
      body: JSON.stringify({ ids }),
    }),

  linkTagToSpoolmanSpool: (spoolId: number, data: { tag_uid?: string; tray_uuid?: string }) =>
    request<InventorySpool>(`/spoolman/inventory/spools/${spoolId}/tag`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  syncSpoolmanSpoolWeight: (spoolId: number, weightGrams: number) =>
    request<{ status: string; weight_used: number }>(`/spoolman/inventory/spools/${spoolId}/weight`, {
      method: 'PATCH',
      body: JSON.stringify({ weight_grams: weightGrams }),
    }),

  assignSpoolmanSlot: (data: { spoolman_spool_id: number; printer_id: number; ams_id: number; tray_id: number }) =>
    request<InventorySpool>('/spoolman/inventory/slot-assignments', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  unassignSpoolmanSlot: (spoolmanSpoolId: number) =>
    request<InventorySpool>(`/spoolman/inventory/slot-assignments/${spoolmanSpoolId}`, { method: 'DELETE' }),

  getSpoolmanSlotAssignment: (printerId: number, amsId: number, trayId: number) =>
    request<InventorySpool | null>(
      `/spoolman/inventory/slot-assignments?printer_id=${printerId}&ams_id=${amsId}&tray_id=${trayId}`,
    ),

  getSpoolmanSlotAssignments: (printerId?: number) =>
    request<Array<{
      printer_id: number;
      printer_name: string | null;
      ams_id: number;
      tray_id: number;
      spoolman_spool_id: number;
      ams_label: string | null;
    }>>(
      printerId !== undefined
        ? `/spoolman/inventory/slot-assignments/all?printer_id=${printerId}`
        : '/spoolman/inventory/slot-assignments/all',
    ),

  syncSpoolmanAmsWeights: () =>
    request<{ synced: number; skipped: number }>('/spoolman/inventory/sync-ams-weights', { method: 'POST' }),

  getSpoolmanKProfiles: (spoolId: number) =>
    request<SpoolKProfile[]>(`/spoolman/inventory/spools/${spoolId}/k-profiles`),

  saveSpoolmanKProfiles: (spoolId: number, profiles: SpoolKProfileInput[]) =>
    request<SpoolKProfile[]>(`/spoolman/inventory/spools/${spoolId}/k-profiles`, {
      method: 'PUT',
      body: JSON.stringify(profiles),
    }),

  // Updates
  getVersion: () => request<VersionInfo>('/updates/version'),

  checkForUpdates: () => request<UpdateCheckResult>('/updates/check'),

  applyUpdate: () =>
    request<{ success: boolean; message: string; status?: UpdateStatus; is_docker?: boolean; is_ha_addon?: boolean; is_windows_installer?: boolean }>('/updates/apply', {
      method: 'POST',
    }),

  getUpdateStatus: () => request<UpdateStatus>('/updates/status'),

  // Maintenance
  getMaintenanceTypes: () => request<MaintenanceType[]>('/maintenance/types'),

  createMaintenanceType: (data: MaintenanceTypeCreate) =>
    request<MaintenanceType>('/maintenance/types', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateMaintenanceType: (id: number, data: Partial<MaintenanceTypeCreate>) =>
    request<MaintenanceType>(`/maintenance/types/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteMaintenanceType: (id: number) =>
    request<{ status: string }>(`/maintenance/types/${id}`, { method: 'DELETE' }),

  restoreDefaultMaintenanceTypes: () =>
    request<{ restored: number }>(`/maintenance/types/restore-defaults`, { method: 'POST' }),

  getMaintenanceOverview: () => request<PrinterMaintenanceOverview[]>('/maintenance/overview'),

  getPrinterMaintenance: (printerId: number) =>
    request<PrinterMaintenanceOverview>(`/maintenance/printers/${printerId}`),

  updateMaintenanceItem: (itemId: number, data: { custom_interval_hours?: number | null; custom_interval_type?: 'hours' | 'days' | null; enabled?: boolean }) =>
    request<MaintenanceStatus>(`/maintenance/items/${itemId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  performMaintenance: (itemId: number, notes?: string) =>
    request<MaintenanceStatus>(`/maintenance/items/${itemId}/perform`, {
      method: 'POST',
      body: JSON.stringify({ notes }),
    }),

  getMaintenanceHistory: (itemId: number) =>
    request<MaintenanceHistory[]>(`/maintenance/items/${itemId}/history`),

  getMaintenanceSummary: () => request<MaintenanceSummary>('/maintenance/summary'),

  setPrinterHours: (printerId: number, totalHours: number) =>
    request<{ printer_id: number; total_hours: number; archive_hours: number; offset_hours: number }>(
      `/maintenance/printers/${printerId}/hours?total_hours=${totalHours}`,
      { method: 'PATCH' }
    ),

  assignMaintenanceType: (printerId: number, typeId: number) =>
    request<MaintenanceStatus>(`/maintenance/printers/${printerId}/assign/${typeId}`, {
      method: 'POST',
    }),

  removeMaintenanceItem: (itemId: number) =>
    request<{ status: string }>(`/maintenance/items/${itemId}`, {
      method: 'DELETE',
    }),

  // Camera
  getCameraStreamToken: () =>
    request<{ token: string }>('/printers/camera/stream-token', { method: 'POST' }),

  // WebSocket auth (GHSA-r2qv follow-up) — mint a short-lived token for
  // the /ws connection. Browsers can't attach Authorization headers to a
  // WebSocket handshake, so the token rides in the ?token= query param.
  getWebSocketToken: () =>
    request<{ token: string }>('/auth/ws-token', { method: 'POST' }),

  // Long-lived camera-stream tokens (#1108)
  createLongLivedCameraToken: (payload: { name: string; expires_in_days: number; scope?: LongLivedTokenScope }) =>
    request<LongLivedCameraToken>('/auth/tokens', {
      method: 'POST',
      body: JSON.stringify({ scope: 'camera_stream', ...payload }),
    }),

  listMyLongLivedCameraTokens: () =>
    request<LongLivedCameraToken[]>('/auth/tokens'),

  listAllLongLivedCameraTokens: () =>
    request<LongLivedCameraToken[]>('/auth/tokens/all'),

  listLongLivedCameraTokensForUser: (userId: number) =>
    request<LongLivedCameraToken[]>(`/auth/tokens?user_id=${userId}`),

  revokeLongLivedCameraToken: (tokenId: number) =>
    request<void>(`/auth/tokens/${tokenId}`, { method: 'DELETE' }),

  getCamWallPrinters: (token?: string) =>
    request<CamWallPrinter[]>(
      token ? `/camwall/printers?token=${encodeURIComponent(token)}` : '/camwall/printers',
    ),

  getOverlayStatus: (printerId: number, token?: string) =>
    request<OverlayStatus>(
      token
        ? `/printers/${printerId}/overlay-status?token=${encodeURIComponent(token)}`
        : `/printers/${printerId}/overlay-status`,
    ),

  getCameraStreamUrl: (printerId: number, fps = 10) =>
    withStreamToken(`${API_BASE}/printers/${printerId}/camera/stream?fps=${fps}`),

  getCameraSnapshotUrl: (printerId: number) =>
    withStreamToken(`${API_BASE}/printers/${printerId}/camera/snapshot`),

  testCameraConnection: (printerId: number) =>
    request<{ success: boolean; message?: string; error?: string }>(`/printers/${printerId}/camera/test`),

  getCameraStatus: (printerId: number) =>
    request<{ active: boolean; stalled: boolean }>(`/printers/${printerId}/camera/status`),

  diagnoseCamera: (printerId: number) =>
    request<CameraDiagnoseResult>(`/printers/${printerId}/camera/diagnose`, { method: 'POST' }),

  diagnosePrinter: (printerId: number) =>
    request<PrinterDiagnosticResult>(`/printers/${printerId}/diagnostic`),

  diagnoseConnection: (body: {
    ip_address: string;
    serial_number?: string;
    access_code?: string;
  }) =>
    request<PrinterDiagnosticResult>('/printers/diagnostic', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  // Plate Detection - Multi-reference calibration (stores up to 5 references per printer)
  checkPlateEmpty: (printerId: number, options?: { useExternal?: boolean; includeDebugImage?: boolean }) => {
    const params = new URLSearchParams();
    // Only forward use_external when the caller explicitly sets it. Omitted →
    // backend derives the default from the printer's external_camera_enabled
    // setting so calibration and runtime checks use the same camera (#1359).
    if (options?.useExternal !== undefined) {
      params.set('use_external', String(options.useExternal));
    }
    params.set('include_debug_image', String(options?.includeDebugImage ?? false));
    return request<PlateDetectionResult>(
      `/printers/${printerId}/camera/check-plate?${params.toString()}`
    );
  },

  getPlateDetectionStatus: (printerId: number) => {
    return request<PlateDetectionStatus & { chamber_light?: boolean }>(
      `/printers/${printerId}/camera/plate-detection/status`
    );
  },

  calibratePlateDetection: (printerId: number, options?: { label?: string; useExternal?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.label) params.set('label', options.label);
    if (options?.useExternal !== undefined) {
      params.set('use_external', String(options.useExternal));
    }
    return request<CalibrationResult & { index: number }>(
      `/printers/${printerId}/camera/plate-detection/calibrate?${params.toString()}`,
      { method: 'POST' }
    );
  },

  deletePlateCalibration: (printerId: number) => {
    return request<CalibrationResult>(
      `/printers/${printerId}/camera/plate-detection/calibrate`,
      { method: 'DELETE' }
    );
  },

  getPlateReferences: (printerId: number) => {
    return request<{
      references: PlateReference[];
      max_references: number;
    }>(`/printers/${printerId}/camera/plate-detection/references`);
  },

  getPlateReferenceThumbnailUrl: (printerId: number, index: number) =>
    withStreamToken(`${API_BASE}/printers/${printerId}/camera/plate-detection/references/${index}/thumbnail`),

  updatePlateReferenceLabel: (printerId: number, index: number, label: string) => {
    const params = new URLSearchParams();
    params.set('label', label);
    return request<{ success: boolean; index: number; label: string }>(
      `/printers/${printerId}/camera/plate-detection/references/${index}?${params.toString()}`,
      { method: 'PUT' }
    );
  },

  deletePlateReference: (printerId: number, index: number) => {
    return request<{ success: boolean; message: string }>(
      `/printers/${printerId}/camera/plate-detection/references/${index}`,
      { method: 'DELETE' }
    );
  },

  // External Links
  getExternalLinks: () => request<ExternalLink[]>('/external-links/'),

  getExternalLink: (id: number) => request<ExternalLink>(`/external-links/${id}`),

  createExternalLink: (data: ExternalLinkCreate) =>
    request<ExternalLink>('/external-links/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateExternalLink: (id: number, data: ExternalLinkUpdate) =>
    request<ExternalLink>(`/external-links/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteExternalLink: (id: number) =>
    request<{ message: string }>(`/external-links/${id}`, { method: 'DELETE' }),

  reorderExternalLinks: (ids: number[]) =>
    request<ExternalLink[]>('/external-links/reorder', {
      method: 'PUT',
      body: JSON.stringify({ ids }),
    }),

  uploadExternalLinkIcon: async (id: number, file: File): Promise<ExternalLink> => {
    const formData = new FormData();
    formData.append('file', file);
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(`${API_BASE}/external-links/${id}/icon`, {
      method: 'POST',
      headers,
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
  },

  deleteExternalLinkIcon: (id: number) =>
    request<ExternalLink>(`/external-links/${id}/icon`, { method: 'DELETE' }),

  getExternalLinkIconUrl: (id: number) => withStreamToken(`${API_BASE}/external-links/${id}/icon`)
};
