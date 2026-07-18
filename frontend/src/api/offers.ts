import { request } from './client';

export type OfferStatus = 'draft' | 'sent' | 'accepted' | 'rejected';

export interface ReservationAllocation {
  id: number;
  inventory_backend: string;
  spool_id: number | null;
  external_spool_id: string | null;
  small_part_id: number | null;
  allocated_quantity: string;
  consumed_quantity: string;
}

export interface StockReservation {
  id: number;
  source_key: string;
  resource_kind: 'filament' | 'small_part';
  material_code: string | null;
  requested_quantity: string;
  unit_code: string;
  status: string;
  released_at: string | null;
  allocations: ReservationAllocation[];
}

export interface Offer {
  id: number;
  business_profile_id: number;
  customer_id: number | null;
  calculation_revision_id: number;
  order_id: number | null;
  number: string;
  status: OfferStatus;
  preferred_variant_sort_order: number;
  snapshot: Record<string, unknown>;
  sent_at: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface CustomerOrder {
  id: number;
  business_profile_id: number;
  customer_id: number | null;
  offer_id: number;
  project_id: number;
  number: string;
  status: 'active' | 'cancelled' | 'completed';
  accepted_snapshot: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  reservations: StockReservation[];
}

export interface AcceptanceResult { offer: Offer; order: CustomerOrder; project_id: number }

export const offersApi = {
  list: (status?: OfferStatus) => request<Offer[]>(`/offers${status ? `?status=${status}` : ''}`),
  get: (id: number) => request<Offer>(`/offers/${id}`),
  create: (calculationRevisionId: number) => request<Offer>('/offers', { method: 'POST', body: JSON.stringify({ calculation_revision_id: calculationRevisionId }) }),
  send: (id: number, expectedVersion: number) => request<Offer>(`/offers/${id}/send`, { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }) }),
  reject: (id: number, expectedVersion: number) => request<Offer>(`/offers/${id}/reject`, { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion }) }),
  accept: (id: number, expectedVersion: number, idempotencyKey: string) => request<AcceptanceResult>(`/offers/${id}/accept`, { method: 'POST', body: JSON.stringify({ expected_version: expectedVersion, idempotency_key: idempotencyKey }) }),
};

export const ordersApi = {
  list: () => request<CustomerOrder[]>('/orders'),
  get: (id: number) => request<CustomerOrder>(`/orders/${id}`),
  cancel: (id: number, idempotencyKey: string) => request<CustomerOrder>(`/orders/${id}/cancel`, { method: 'POST', body: JSON.stringify({ idempotency_key: idempotencyKey }) }),
  issueSmallPart: (id: number, allocationId: number, quantity: string, idempotencyKey: string) => request<CustomerOrder>(`/orders/${id}/small-parts/${allocationId}/issue`, { method: 'POST', body: JSON.stringify({ quantity, idempotency_key: idempotencyKey }) }),
  reconcileFilament: (id: number, allocationId: number, quantity: string, idempotencyKey: string) => request<CustomerOrder>(`/orders/${id}/filament/${allocationId}/reconcile`, { method: 'POST', body: JSON.stringify({ quantity, idempotency_key: idempotencyKey }) }),
};
