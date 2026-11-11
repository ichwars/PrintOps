import { request } from './core';
import type { SpoolFilamentPreset, SpoolKProfileInput } from './types';

export interface FilamentProfileWrite {
  material: string;
  brand: string;
  subtype: string;
  color_name: string;
  slicer_filament: string | null;
  slicer_filament_name: string | null;
  presets: SpoolFilamentPreset[];
  k_profiles: SpoolKProfileInput[];
}

export interface FilamentProfileDefault extends FilamentProfileWrite {
  id: number;
  can_edit: boolean;
}

const path = '/inventory/profile-defaults';
export const filamentProfileDefaultsApi = {
  list: () => request<FilamentProfileDefault[]>(`${path}/`),
  save: (body: FilamentProfileWrite) => request<FilamentProfileDefault>(`${path}/`, {
    method: 'PUT', body: JSON.stringify(body),
  }),
  remove: (id: number) => request<{ status: string }>(`${path}/${id}`, { method: 'DELETE' }),
  apply: (id: number, spoolman: boolean) => request<{ applied: number; failed: number }>(
    `${path}/${id}/apply?spoolman=${spoolman}`, { method: 'POST' },
  ),
};
