import { request } from './client/core';

export interface TelegramQualityConfig {
  enabled: boolean;
  actors: { actor_id: number; user_id: number }[];
  status: 'disabled' | 'idle' | 'polling' | 'webhook_conflict' | 'transport_error';
}

export const getTelegramQuality = (id: number) => request<TelegramQualityConfig>(`/notifications/${id}/telegram-quality`);
export const saveTelegramQuality = (id: number, data: Pick<TelegramQualityConfig, 'enabled' | 'actors'>) =>
  request<TelegramQualityConfig>(`/notifications/${id}/telegram-quality`, { method: 'PUT', body: JSON.stringify(data) });
