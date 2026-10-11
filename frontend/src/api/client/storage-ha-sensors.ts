import { request } from './core';

export interface StorageHASensorCreate {
  location_id: number;
  name: string;
  entity_id: string;
  device_class: 'temperature' | 'humidity';
  unit: '°C' | '°F' | 'K' | '%';
  alert_above: number | null;
  alert_below: number | null;
  notify_on_alert: boolean;
}

export interface StorageHASensor extends StorageHASensorCreate { id: number }
export interface StorageHASensorReading {
  id: number;
  location_id: number;
  name: string;
  entity_id: string;
  device_class: string;
  unit: string;
  value: number | null;
  alerting: boolean;
  status: 'fresh' | 'stale' | 'unavailable' | 'pending';
  last_checked: string | null;
  last_read_at: string | null;
}

export const storageHASensorsMethods = {
  getStorageHASensors: (locationId: number) => request<StorageHASensor[]>(`/storage-ha-sensors/?location_id=${locationId}`),
  getStorageHASensorReadings: () => request<StorageHASensorReading[]>('/storage-ha-sensors/readings'),
  getStorageHAEntities: () => request<import('./types').HADisplayEntity[]>('/storage-ha-sensors/entities'),
  createStorageHASensor: (data: StorageHASensorCreate) => request<StorageHASensor>('/storage-ha-sensors/', { method: 'POST', body: JSON.stringify(data) }),
  updateStorageHASensor: (id: number, data: Omit<StorageHASensorCreate, 'location_id'>) => request<StorageHASensor>(`/storage-ha-sensors/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteStorageHASensor: (id: number) => request<void>(`/storage-ha-sensors/${id}`, { method: 'DELETE' }),
};
