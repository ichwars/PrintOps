import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { SmallPartsPage } from '../../pages/SmallPartsPage';
import { server } from '../mocks/server';

const part = {
  id: 7,
  sku: 'M3-INSERT',
  name: 'M3 Gewindeeinsatz',
  description: null,
  search_terms: null,
  category_id: null,
  unit_code: 'C62',
  location_id: null,
  minimum_stock: '20.000000',
  unit_cost: '0.080000',
  supplier_reference: null,
  default_consumption_reason: 'Produktion',
  internal_notes: null,
  is_active: true,
  preferred_offer: {
    id: 8,
    supplier_id: 3,
    small_part_id: 7,
    filament_sku_settings_id: null,
    resource_key: 'material:7',
    supplier_sku: 'M3-100',
    purchase_url: null,
    package_quantity: '100',
    package_unit_code: 'C62',
    minimum_order_quantity: '1',
    lead_time_days: 5,
    net_price: '7.5',
    gross_price: '8.93',
    is_preferred: true,
    is_active: true,
    created_at: '2026-07-18T10:00:00Z',
    updated_at: '2026-07-18T10:00:00Z',
    supplier: {
      id: 3,
      name: 'Schrauben GmbH',
      default_lead_time_days: 5,
      is_active: true,
    },
  },
  category: null,
  unit: { code: 'C62', label: 'Stück', decimal_places: 0, is_active: true },
  balance: { physical: '50.000000', reserved: '8.000000', available: '42.000000', is_low_stock: false },
  created_at: '2026-07-18T10:00:00Z',
  updated_at: '2026-07-18T10:00:00Z',
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <SmallPartsPage />
    </QueryClientProvider>,
  );
}

describe('SmallPartsPage', () => {
  it('uses Material wording and the shared field styling without a duplicate filter border', async () => {
    server.use(
      http.get('/api/v1/small-parts', () => HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 })),
    );
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Material' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Material hinzufügen' })).toBeInTheDocument();
    const search = screen.getByRole('searchbox', { name: 'Material durchsuchen' });
    expect(search).toHaveClass('pl-9', 'bg-bambu-dark', 'border-bambu-dark-tertiary', 'text-white');
    expect(search).not.toHaveClass('bg-gray-800', 'border-gray-600');

    const lowStockFilter = screen.getByRole('checkbox', { name: 'Nur niedriger Bestand' }).closest('label');
    expect(lowStockFilter).not.toHaveClass('border', 'border-gray-700');
    expect(await screen.findByText('Noch kein passendes Material vorhanden.')).toBeInTheDocument();
  });

  it('shows balances, procurement summary, and searches the material catalog', async () => {
    const seenQueries: string[] = [];
    server.use(
      http.get('/api/v1/small-parts', ({ request }) => {
        seenQueries.push(new URL(request.url).searchParams.get('q') ?? '');
        return HttpResponse.json({ items: [part], total: 1, limit: 50, offset: 0 });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText('M3 Gewindeeinsatz')).toBeInTheDocument();
    expect(screen.getByText('42 Stück verfügbar')).toBeInTheDocument();
    expect(screen.getByText('Schrauben GmbH')).toBeInTheDocument();
    expect(screen.getByText('7,50 € netto')).toBeInTheDocument();
    expect(screen.getByText('5 Tage Lieferzeit')).toBeInTheDocument();
    await user.type(screen.getByRole('searchbox', { name: 'Material durchsuchen' }), 'M3');

    await waitFor(() => expect(seenQueries).toContain('M3'));
  });

  it('prefills a stock receipt with the material default consumption reason', async () => {
    const posted = vi.fn();
    server.use(
      http.get('/api/v1/small-parts', () => HttpResponse.json({ items: [part], total: 1, limit: 50, offset: 0 })),
      http.get('/api/v1/small-parts/7/ledger', () => HttpResponse.json([])),
      http.post('/api/v1/small-parts/7/ledger', async ({ request }) => {
        posted(await request.json());
        return HttpResponse.json({
          id: 1,
          small_part_id: 7,
          entry_kind: 'receipt',
          physical_delta: '10.000000',
          reserved_delta: '0.000000',
          reason: 'Produktion',
          reference_type: null,
          reference_id: null,
          actor_id: null,
          idempotency_key: 'receipt-test-0001',
          created_at: '2026-07-18T12:00:00Z',
        }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: 'Bestand buchen' }));
    expect(screen.getByLabelText('Grund')).toHaveValue('Produktion');
    await user.type(screen.getByLabelText('Menge'), '10');
    await user.click(screen.getByRole('button', { name: 'Buchung speichern' }));

    await waitFor(() => expect(posted).toHaveBeenCalledWith(expect.objectContaining({ quantity: '10', reason: 'Produktion' })));
  });
});
