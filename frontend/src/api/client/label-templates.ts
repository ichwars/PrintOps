import { request } from './core';
import type { LabelSheetLayout } from './types';

interface SavedLabelTemplate {
  id: number;
  name: string;
  layout: LabelSheetLayout;
}

const path = '/label-templates';
export const labelTemplatesApi = {
  list: () => request<SavedLabelTemplate[]>(`${path}/`),
  save: (body: Omit<SavedLabelTemplate, 'id'>, id?: number) =>
    request<SavedLabelTemplate>(`${path}/${id ?? ''}`, {
      method: id === undefined ? 'POST' : 'PUT', body: JSON.stringify(body),
    }),
  remove: (id: number) => request<{ status: string }>(`${path}/${id}`, { method: 'DELETE' }),
};
