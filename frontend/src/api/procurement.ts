import { request } from './client';

export interface SupplierInput {
  name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  website: string | null;
  address_line1: string | null;
  address_line2: string | null;
  postal_code: string | null;
  city: string | null;
  country_code: string | null;
  customer_number: string | null;
  payment_terms: string | null;
  default_lead_time_days: number;
  internal_notes: string | null;
  is_active: boolean;
}

export interface Supplier extends SupplierInput {
  id: number;
  created_at: string;
  updated_at: string;
}

export interface SupplierPage {
  items: Supplier[];
  total: number;
  limit: number;
  offset: number;
}

function queryString(params: Record<string, string | number | boolean | undefined>): string {
  const result = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined) result.set(key, String(value));
  });
  return result.toString();
}

export const suppliersApi = {
  list: (params: { q?: string; active?: boolean } = {}) =>
    request<SupplierPage>(`/suppliers?${queryString(params)}`),
  create: (input: SupplierInput) =>
    request<Supplier>('/suppliers', { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: Partial<SupplierInput>) =>
    request<Supplier>(`/suppliers/${id}`, { method: 'PATCH', body: JSON.stringify(input) }),
  remove: (id: number) => request<void>(`/suppliers/${id}`, { method: 'DELETE' }),
};
