import { batched, batchedRecord, readBulkRecord } from '../batch';
import { getAuthSessionId } from './core';
import type {
  AppSettings,
  AppSettingsUpdate,
  AppUiFlags,
  BuiltinFilament,
  CloudAuthStatus,
  CloudDevice,
  CloudLoginResponse,
  DiscoveredTasmotaDevice,
  FieldDefinitionsResponse,
  HAEntity,
  HADisplayEntity,
  HASensorEntity,
  HATestConnectionResult,
  MQTTStatus,
  MakerworldImportResponse,
  MakerworldRecentImport,
  MakerworldResolvedModel,
  MakerworldStatus,
  OrcaAuthStatusResponse,
  OrcaDevicePollResponse,
  OrcaDeviceStartResponse,
  OrcaProfileDetail,
  OrcaProfileListResponse,
  SlicerSettingCreate,
  SlicerSettingDeleteResponse,
  SlicerSettingDetail,
  SlicerSettingUpdate,
  SlicerSettingsResponse,
  SmartPlug,
  PrinterHASensor,
  PrinterHASensorCreate,
  PrinterHASensorReading,
  PrinterHAInterlockOverrideStatus,
  PrinterHASensorUpdate,
  SmartPlugCreate,
  SmartPlugStatus,
  SmartPlugTestResult,
  SmartPlugUpdate,
  TasmotaScanStatus,
} from './types';
import type { NetworkInterface } from './specialized';
import { API_BASE, authToken, request } from './core';

type CardPlugs = { plug: SmartPlug | null; scripts: SmartPlug[] };
const pendingCardPlugs = new Map<string, Promise<Map<number, CardPlugs>>>();

function readCardPlugs(ids: number[]) {
  const sorted = [...ids].sort((a, b) => a - b);
  const key = `${getAuthSessionId()}:${sorted.join(',')}`;
  const existing = pendingCardPlugs.get(key);
  if (existing) return existing;
  const loading = readBulkRecord<CardPlugs>('/bulk/card-plugs', sorted).finally(() => pendingCardPlugs.delete(key));
  pendingCardPlugs.set(key, loading);
  return loading;
}

const smartPlugBatch = batched(
  (id) => request<SmartPlug | null>(`/smart-plugs/by-printer/${id}`),
  async (ids) => new Map([...(await readCardPlugs(ids))].map(([id, card]) => [id, card.plug])),
);

const scriptPlugsBatch = batched(
  (id) => request<SmartPlug[]>(`/smart-plugs/by-printer/${id}/scripts`),
  async (ids) => new Map([...(await readCardPlugs(ids))].map(([id, card]) => [id, card.scripts])),
);

const sensorReadingsBatch = batchedRecord(
  (id) => request<PrinterHASensorReading[]>(`/ha-sensors/by-printer/${id}/readings`),
  '/bulk/ha-sensor-readings',
);

export const settingsCloudPlugsMethods = {
  // Settings
  getSettings: () => request<AppSettings>('/settings/'),

  getDefaultSidebarOrder: () => request<{ default_sidebar_order: string }>('/settings/default-sidebar-order'),

  // Allowlisted configuration for signed-in users across normal application pages.
  getUiFlags: () => request<AppUiFlags>('/settings/ui-flags'),

  // Public appearance and printer-card preferences.
  getUiPreferences: () =>
    request<{
      require_plate_clear?: boolean;
      check_printer_firmware?: boolean;
      show_developer_lan_warning?: boolean;
      show_sponsor_prompts?: boolean;
      camera_view_mode?: 'window' | 'embedded';
      time_format?: 'system' | '12h' | '24h';
      date_format?: string;
      drying_presets?: string;
      ams_humidity_thresholds?: string;
      ams_humidity_good?: number;
      ams_humidity_fair?: number;
      ams_temp_good?: number;
      ams_temp_fair?: number;
      bed_cooled_threshold?: number;
      nozzle_temp_presets?: string;
      bed_temp_presets?: string;
      chamber_temp_presets?: string;
      fan_speed_presets?: string;
    }>('/settings/ui-preferences'),

  updateSettings: (data: AppSettingsUpdate, signal?: AbortSignal) =>
    request<AppSettings>('/settings/', {
      method: 'PUT',
      body: JSON.stringify(data),
      signal,
    }),

  getMQTTStatus: () => request<MQTTStatus>('/settings/mqtt/status'),

  resetSettings: () =>
    request<AppSettings>('/settings/reset', { method: 'POST' }),

  exportBackup: async (): Promise<{ blob: Blob; filename: string }> => {
    // New simplified backup - complete database + all files
    const url = `${API_BASE}/settings/backup`;
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(url, { headers });

    // Check for errors
    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(errorText || `Backup failed with status ${response.status}`);
    }

    // Get filename from Content-Disposition header
    const contentDisposition = response.headers.get('Content-Disposition');
    let filename = 'printops-backup.zip';
    if (contentDisposition) {
      const match = contentDisposition.match(/filename=([^;]+)/);
      if (match) filename = match[1].trim().replace(/^"(.*)"$/, '$1');
    }

    const blob = await response.blob();
    return { blob, filename };
  },

  importBackup: async (file: File) => {
    // New simplified restore - replaces database + all directories
    const formData = new FormData();
    formData.append('file', file);
    const url = `${API_BASE}/settings/restore`;
    const headers: Record<string, string> = {};
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    });
    return response.json() as Promise<{
      success: boolean;
      message: string;
    }>;
  },

  checkFfmpeg: () =>
    request<{ installed: boolean; path: string | null }>('/settings/check-ffmpeg'),

  getNetworkInterfaces: () =>
    request<{ interfaces: NetworkInterface[] }>('/settings/network-interfaces'),

  // Cloud
  getCloudStatus: () => request<CloudAuthStatus>('/cloud/status'),

  cloudLogin: (email: string, password: string, region = 'global') =>
    request<CloudLoginResponse>('/cloud/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, region }),
    }),

  cloudVerify: (email: string, code: string, tfaKey?: string, region: string = 'global') =>
    request<CloudLoginResponse>('/cloud/verify', {
      method: 'POST',
      body: JSON.stringify({ email, code, tfa_key: tfaKey, region }),
    }),

  cloudSetToken: (access_token: string, region: string = 'global') =>
    request<CloudAuthStatus>('/cloud/token', {
      method: 'POST',
      body: JSON.stringify({ access_token, region }),
    }),

  cloudLogout: () =>
    request<{ success: boolean }>('/cloud/logout', { method: 'POST' }),

  // Orca Cloud — RFC 8628 device pairing. deviceStart() returns a short
  // user_code + verification link; the user approves it in their Orca Cloud
  // settings while the frontend polls devicePoll() every `interval` seconds
  // until the status flips to 'complete' (or a terminal deny/expire).
  orcaCloudDeviceStart: () =>
    request<OrcaDeviceStartResponse>('/orca-cloud/device/start', {
      method: 'POST',
    }),

  orcaCloudDevicePoll: (attemptId: string) =>
    request<OrcaDevicePollResponse>('/orca-cloud/device/poll', {
      method: 'POST',
      body: JSON.stringify({ attempt_id: attemptId }),
    }),

  orcaCloudStatus: () =>
    request<OrcaAuthStatusResponse>('/orca-cloud/status'),

  orcaCloudLogout: () =>
    request<{ success: boolean }>('/orca-cloud/logout', { method: 'POST' }),

  orcaCloudListProfiles: () =>
    request<OrcaProfileListResponse>('/orca-cloud/profiles'),

  orcaCloudGetProfile: (id: string) =>
    request<OrcaProfileDetail>(`/orca-cloud/profiles/${id}`),

  getCloudSettings: (version = '02.04.00.70') =>
    request<SlicerSettingsResponse>(`/cloud/settings?version=${version}`),

  getBuiltinFilaments: () =>
    request<BuiltinFilament[]>('/cloud/builtin-filaments'),

  getFilamentIdMap: () =>
    request<Record<string, string>>('/cloud/filament-id-map'),

  /** Material-disambiguated hex→name lookup. Same hex can map to different
   *  catalog names depending on material (e.g. #000000 is "Charcoal" in PLA
   *  Matte but "Black" in PLA Basic). The flat ``/inventory/colors/map``
   *  collapses these to the first hit; this endpoint preserves the material
   *  context. Returns ``{color_name: null}`` when the hex isn't in the
   *  catalog at all. #1718. */
  getColorByMaterial: (hex: string, material?: string) => {
    const params = new URLSearchParams({ hex });
    if (material) params.set('material', material);
    return request<{ color_name: string | null }>(
      `/inventory/colors/by-material?${params.toString()}`,
    );
  },

  // MakerWorld URL-paste import flow.
  getMakerworldStatus: () =>
    request<MakerworldStatus>('/makerworld/status'),

  resolveMakerworldUrl: (url: string) =>
    request<MakerworldResolvedModel>('/makerworld/resolve', {
      method: 'POST',
      body: JSON.stringify({ url }),
    }),

  getMakerworldRecentImports: (limit = 10) =>
    request<MakerworldRecentImport[]>(`/makerworld/recent-imports?limit=${limit}`),

  importMakerworldInstance: (
    model_id: number,
    instance_id: number | null,
    profile_id?: number | null,
    folder_id?: number | null,
  ) =>
    request<MakerworldImportResponse>('/makerworld/import', {
      method: 'POST',
      body: JSON.stringify({
        model_id,
        instance_id: instance_id ?? null,
        profile_id: profile_id ?? null,
        folder_id: folder_id ?? null,
      }),
    }),

  getCloudSettingDetail: (settingId: string) =>
    request<SlicerSettingDetail>(`/cloud/settings/${settingId}`),

  createCloudSetting: (data: SlicerSettingCreate) =>
    request<SlicerSettingDetail>('/cloud/settings', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateCloudSetting: (settingId: string, data: SlicerSettingUpdate) =>
    request<SlicerSettingDetail>(`/cloud/settings/${settingId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  deleteCloudSetting: (settingId: string) =>
    request<SlicerSettingDeleteResponse>(`/cloud/settings/${settingId}`, {
      method: 'DELETE',
    }),

  getCloudDevices: () => request<CloudDevice[]>('/cloud/devices'),

  getCloudFields: (presetType: 'filament' | 'print' | 'process' | 'printer') =>
    request<FieldDefinitionsResponse>(`/cloud/fields/${presetType}`),

  getAllCloudFields: () =>
    request<Record<string, FieldDefinitionsResponse>>('/cloud/fields'),

  getFilamentInfo: (settingIds: string[]) =>
    request<Record<string, { name: string; k: number | null }>>('/cloud/filament-info', {
      method: 'POST',
      body: JSON.stringify(settingIds),
    }),

  // Smart Plugs
  getSmartPlugs: () => request<SmartPlug[]>('/smart-plugs/'),

  getSmartPlug: (id: number) => request<SmartPlug>(`/smart-plugs/${id}`),

  getSmartPlugByPrinter: smartPlugBatch,

  getScriptPlugsByPrinter: scriptPlugsBatch,

  createSmartPlug: (data: SmartPlugCreate) =>
    request<SmartPlug>('/smart-plugs/', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateSmartPlug: (id: number, data: SmartPlugUpdate) =>
    request<SmartPlug>(`/smart-plugs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteSmartPlug: (id: number) =>
    request<void>(`/smart-plugs/${id}`, { method: 'DELETE' }),

  controlSmartPlug: (id: number, action: 'on' | 'off' | 'toggle') =>
    request<{ success: boolean; action: string }>(`/smart-plugs/${id}/control`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    }),

  getSmartPlugStatus: (id: number) =>
    request<SmartPlugStatus>(`/smart-plugs/${id}/status`),

  testSmartPlugConnection: (ip_address: string, username?: string | null, password?: string | null, plug_id?: number) =>
    request<SmartPlugTestResult>('/smart-plugs/test-connection', {
      method: 'POST',
      body: JSON.stringify({ ip_address, username, password, plug_id }),
    }),

  // Tasmota Discovery (auto-detects network)
  startTasmotaScan: () =>
    request<TasmotaScanStatus>('/smart-plugs/discover/scan', { method: 'POST' }),

  getTasmotaScanStatus: () =>
    request<TasmotaScanStatus>('/smart-plugs/discover/status'),

  stopTasmotaScan: () =>
    request<TasmotaScanStatus>('/smart-plugs/discover/stop', { method: 'POST' }),

  getDiscoveredTasmotaDevices: () =>
    request<DiscoveredTasmotaDevice[]>('/smart-plugs/discover/devices'),

  // Home Assistant Integration
  testHAConnection: (url: string, token: string) =>
    request<HATestConnectionResult>('/smart-plugs/ha/test-connection', {
      method: 'POST',
      body: JSON.stringify({ url, token }),
    }),

  getHAEntities: (search?: string) => {
    const params = search ? `?search=${encodeURIComponent(search)}` : '';
    return request<HAEntity[]>(`/smart-plugs/ha/entities${params}`);
  },

  getHASensorEntities: () =>
    request<HASensorEntity[]>('/smart-plugs/ha/sensors'),

  getHASensors: (printerId?: number) =>
    request<PrinterHASensor[]>(`/ha-sensors/${printerId ? `?printer_id=${printerId}` : ''}`),

  getHASensorReadings: sensorReadingsBatch,

  getHAInterlockOverride: (printerId: number) =>
    request<PrinterHAInterlockOverrideStatus>(`/ha-sensors/printers/${printerId}/interlock-override`),

  setHAInterlockOverride: (printerId: number, reason: string) =>
    request<PrinterHAInterlockOverrideStatus>(`/ha-sensors/printers/${printerId}/interlock-override`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  clearHAInterlockOverride: (printerId: number) =>
    request<PrinterHAInterlockOverrideStatus>(`/ha-sensors/printers/${printerId}/interlock-override`, {
      method: 'DELETE',
    }),

  getBindableHAEntities: (search?: string) => {
    const params = search ? `?search=${encodeURIComponent(search)}` : '';
    return request<HADisplayEntity[]>(`/ha-sensors/entities${params}`);
  },

  createHASensor: (data: PrinterHASensorCreate) =>
    request<PrinterHASensor>('/ha-sensors/', { method: 'POST', body: JSON.stringify(data) }),

  updateHASensor: (id: number, data: PrinterHASensorUpdate) =>
    request<PrinterHASensor>(`/ha-sensors/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),

  deleteHASensor: (id: number) =>
    request<{ message: string }>(`/ha-sensors/${id}`, { method: 'DELETE' }),

  // REST smart plug
  testRESTConnection: (url: string, method: string = 'GET', headers?: string | null, plug_id?: number) =>
    request<{ success: boolean; error: string | null }>('/smart-plugs/rest/test-connection', {
      method: 'POST',
      body: JSON.stringify({ url, method, headers, plug_id }),
    })
};
