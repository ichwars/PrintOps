import { request } from './core';

export interface ConnectedApp {
  id: number;
  name: string;
  client_id: string;
  redirect_uri: string;
  enabled: boolean;
  created_at: string;
  last_used_at: string | null;
}
export interface ConnectedAppSecret extends ConnectedApp { client_secret: string }
export interface ConnectAuthorizeInfo {
  app_name: string;
  username: string;
  redirect_uri: string;
  already_granted: boolean;
}
export interface ConnectAuthorizeRequest {
  client_id: string;
  redirect_uri: string;
  code_challenge: string;
  code_challenge_method: 'S256';
}
export const connectedAppsApi = {
  list: () => request<ConnectedApp[]>('/connect/apps'),
  create: (data: { name: string; redirect_uri: string }) => request<ConnectedAppSecret>('/connect/apps', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: number, data: Partial<Pick<ConnectedApp, 'name' | 'redirect_uri' | 'enabled'>>) => request<ConnectedApp>(`/connect/apps/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  rotate: (id: number) => request<ConnectedAppSecret>(`/connect/apps/${id}/rotate-secret`, { method: 'POST' }),
  remove: (id: number) => request<{ message: string }>(`/connect/apps/${id}`, { method: 'DELETE' }),
  info: (client_id: string, redirect_uri: string) => request<ConnectAuthorizeInfo>(`/connect/authorize/info?${new URLSearchParams({ client_id, redirect_uri })}`),
  authorize: (data: ConnectAuthorizeRequest) => request<{ code: string; redirect_uri: string }>('/connect/authorize', { method: 'POST', body: JSON.stringify(data) }),
};
